"""Tests for safe Project Explorer and bounded multi-file model context."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from llm_client import answer, request_change_proposal
from patch_applier import context_file_paths
from workspace_context import (
    assemble_selected_files,
    build_file_tree,
    build_workspace_context,
)
from workspace_reader import WorkspaceError, index_workspace, read_workspace_file


class WorkspaceContextTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def write(self, relative_path: str, content: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_tree_contains_only_indexed_supported_files(self):
        self.write("src/auth/login.py", "def login(): return True\n")
        self.write("src/auth/session.ts", "export const session = true;\n")
        self.write("node_modules/pkg/index.js", "ignored = true\n")
        self.write("image.bin", "ignored")
        tree = build_file_tree(index_workspace(self.root))

        self.assertIn("src", tree.directories)
        self.assertIn("src/auth/login.py", tree.directories["src"].directories["auth"].files)
        self.assertIn("src/auth/session.ts", tree.directories["src"].directories["auth"].files)
        self.assertNotIn("node_modules", tree.directories)
        self.assertNotIn("image.bin", tree.files)

    def test_selected_multiple_files_have_explicit_boundaries_and_retrieval(self):
        self.write("src/auth.py", "def authenticate(token):\n    return validate(token)\n")
        self.write("src/session.py", "def create_session(user):\n    return authenticate(user.token)\n")
        self.write("src/unrelated.py", "def render_home():\n    return 'home'\n")
        index = index_workspace(self.root)

        result = build_workspace_context(
            index,
            "Where is authenticate used?",
            {"src/auth.py", "src/session.py"},
        )

        self.assertIn("Selected workspace files", result.content)
        self.assertIn("File: src/auth.py", result.content)
        self.assertIn("File: src/session.py", result.content)
        self.assertNotIn("File: src/unrelated.py", result.content)
        self.assertEqual(set(result.included_files), {"src/auth.py", "src/session.py"})
        self.assertEqual(result.retrieved_files, ())
        self.assertLessEqual(result.char_count, 12_000)
        self.assertEqual(result.estimated_tokens, (result.char_count + 3) // 4)

    def test_selected_files_are_not_duplicated_in_search_results(self):
        self.write("src/auth.py", "def authenticate(token):\n    return validate(token)\n")
        self.write("src/session.py", "def create_session(token):\n    return authenticate(token)\n")
        index = index_workspace(self.root)
        result = build_workspace_context(index, "authenticate token", {"src/auth.py"})

        self.assertIn("File: src/auth.py\n```", result.content)
        self.assertNotIn("File: src/auth.py (lines", result.content)
        self.assertIn("File: src/session.py (lines", result.content)
        self.assertEqual(result.retrieved_files, ("src/session.py",))

    def test_context_budget_marks_truncated_and_omitted_files(self):
        self.write("a.py", "value = '" + "x" * 250 + "'\n")
        self.write("b.py", "value = '" + "y" * 250 + "'\n")
        index = index_workspace(self.root)

        result = assemble_selected_files(index, {"a.py", "b.py"}, max_chars=150)

        self.assertLessEqual(result.char_count, 150)
        self.assertEqual(result.included_files, ("a.py",))
        self.assertEqual(result.truncated_files, ("a.py",))
        self.assertEqual(result.omitted_files[0].path, "b.py")
        self.assertIn("limit", result.omitted_files[0].reason)

    def test_markdown_fences_inside_files_do_not_break_context_boundaries(self):
        self.write("docs.md", "Example follows:\n```\nsearchable example\n```\n")
        index = index_workspace(self.root)

        selected = assemble_selected_files(index, {"docs.md"})
        retrieved = build_workspace_context(index, "searchable")

        self.assertTrue(selected.content.startswith("File: docs.md\n````md\n"))
        self.assertTrue(selected.content.endswith("\n````"))
        self.assertIn("File: docs.md (lines", retrieved.content)
        self.assertIn("\n````md\n", retrieved.content)

    def test_stale_or_traversal_selections_are_reported_and_not_read(self):
        self.write("safe.py", "value = 1\n")
        index = index_workspace(self.root)

        result = assemble_selected_files(index, {"../outside.py", "deleted.py"})

        self.assertEqual(result.content, "")
        self.assertEqual({issue.path for issue in result.omitted_files}, {"../outside.py", "deleted.py"})
        self.assertTrue(all("not in the current index" in issue.reason for issue in result.omitted_files))

    def test_sensitive_change_after_index_is_omitted_without_echoing_secret(self):
        path = self.root / "config.py"
        path.write_text("API_KEY = os.environ['API_KEY']\n", encoding="utf-8")
        index = index_workspace(self.root)
        path.write_text('API_KEY = "very-secret-value-123456"\n', encoding="utf-8")

        result = assemble_selected_files(index, {"config.py"})

        self.assertEqual(result.content, "")
        self.assertNotIn("very-secret-value", result.content)
        self.assertIn("sensitive data", result.omitted_files[0].reason)

    def test_permission_errors_are_reported_without_breaking_other_selected_files(self):
        self.write("a.py", "value = 1\n")
        self.write("b.py", "value = 2\n")
        index = index_workspace(self.root)
        original_read = read_workspace_file

        def controlled_read(root, relative_path, **kwargs):
            if relative_path == "a.py":
                raise WorkspaceError("This file could not be read safely.")
            return original_read(root, relative_path, **kwargs)

        with patch("workspace_context.read_workspace_file", side_effect=controlled_read):
            result = assemble_selected_files(index, {"a.py", "b.py"})

        self.assertIn("File: b.py", result.content)
        self.assertEqual(result.omitted_files[0].path, "a.py")
        self.assertIn("could not be read safely", result.omitted_files[0].reason)

    def test_model_client_keeps_workspace_context_separate_from_history(self):
        workspace = "Selected workspace files:\nFile: src/a.py\n```py\nx = 1\n```"
        completion = Mock(return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Answer"))]
        ))
        client = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=completion)
        ))
        history = [{"role": "user", "content": "Explain this file"}]

        with patch("llm_client._client", return_value=client):
            response = answer(history, workspace_context=workspace)

        self.assertEqual(response, "Answer")
        messages = completion.call_args.kwargs["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn(workspace, messages[0]["content"])
        self.assertEqual(messages[1], history[0])
        self.assertNotIn("API_KEY", messages[0]["content"])

    def test_multi_file_context_is_available_to_phase_three_proposals(self):
        context = "Selected workspace files:\nFile: src/a.py\n```py\na = 1\n```\n\nFile: src/b.py\n```py\nb = a\n```"
        baseline = {"src/a.py": "a" * 64, "src/b.py": "b" * 64}
        completion = Mock(return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"schema_version":1,"explanation":"","files":[]}'))]
        ))
        client = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=completion)
        ))

        with patch("llm_client._client", return_value=client):
            response = request_change_proposal("Update both modules", context, baseline)

        self.assertIn('"schema_version"', response)
        self.assertEqual(context_file_paths(context), {"src/a.py", "src/b.py"})
        user_message = completion.call_args.kwargs["messages"][1]["content"]
        self.assertIn("File: src/a.py", user_message)
        self.assertIn("File: src/b.py", user_message)


if __name__ == "__main__":
    unittest.main()
