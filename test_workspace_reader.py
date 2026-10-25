"""Tests for bounded, read-only project workspace indexing and search."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from workspace_reader import (
    WorkspaceError,
    _is_symlink_or_reparse_point,
    index_workspace,
    resolve_workspace,
    resolve_workspace_file,
    search_workspace,
)


class WorkspaceReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, relative_path: str, content: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_discovers_nested_source_and_project_configuration_files(self):
        self._write("src/main.py", "def run():\n    return True\n")
        self._write("src/App.java", "class App {}\n")
        self._write("web/app.ts", "export function boot() {}\n")
        self._write("native/main.cpp", "int main() { return 0; }\n")
        self._write("pyproject.toml", "[project]\nname='demo'\n")
        self._write("notes.bin", "not indexed")

        index = index_workspace(self.root)

        paths = {file.relative_path for file in index.files}
        self.assertEqual(
            paths,
            {"src/main.py", "src/App.java", "web/app.ts", "native/main.cpp", "pyproject.toml"},
        )

    def test_excludes_generated_dependency_and_sensitive_files_and_content(self):
        self._write("src/app.py", "print('safe')\n")
        self._write(".env", "API_KEY=secret-value\n")
        self._write(".env.local", "LOCAL_KEY=secret-value\n")
        self._write("credentials.json", '{"token": "hidden"}\n')
        self._write("secrets/config.yaml", "password: hidden\n")
        self._write("src/hardcoded.py", 'API_KEY = "supersecret-value-123"\n')
        self._write("src/inline_config.py", 'config = {"password": "embedded-secret-value"}\n')
        self._write("node_modules/pkg/index.js", "module.exports = 1\n")
        self._write(".venv/lib/site.py", "print('no')\n")
        self._write("build/out.c", "int generated;\n")
        self._write("__pycache__/module.py", "cached = True\n")

        index = index_workspace(self.root)

        self.assertEqual([file.relative_path for file in index.files], ["src/app.py"])
        self.assertGreaterEqual(index.skipped_files, 3)

    def test_rejects_traversal_absolute_paths_and_non_directories(self):
        outside = Path(self.temp_dir.name) / "outside.py"
        outside.write_text("secret", encoding="utf-8")
        for unsafe in ("../outside.py", str(outside), r"C:\outside.py", "src/../../outside.py"):
            with self.subTest(path=unsafe):
                with self.assertRaises(WorkspaceError):
                    resolve_workspace_file(self.root, unsafe)
        with self.assertRaises(WorkspaceError):
            resolve_workspace(outside)
        with self.assertRaises(WorkspaceError):
            resolve_workspace(Path(self.temp_dir.name) / "missing")

    def test_skips_symlink_files_and_directories_outside_workspace(self):
        outside = Path(self.temp_dir.name) / "outside"
        outside.mkdir()
        (outside / "leak.py").write_text("OUTSIDE_SECRET_SENTINEL", encoding="utf-8")
        self._write("linked-file.py", "OUTSIDE_SECRET_SENTINEL")
        self._write("linked-dir/leak.py", "OUTSIDE_SECRET_SENTINEL")
        original_is_symlink = Path.is_symlink

        def simulated_symlink(path: Path) -> bool:
            return original_is_symlink(path) or path.name in {"linked-file.py", "linked-dir"}

        with patch.object(Path, "is_symlink", simulated_symlink):
            index = index_workspace(self.root)
            self.assertNotIn("linked-file.py", {file.relative_path for file in index.files})
            self.assertNotIn("linked-dir/leak.py", {file.relative_path for file in index.files})
            with self.assertRaises(WorkspaceError):
                resolve_workspace_file(self.root, "linked-file.py")
        self.assertNotIn("OUTSIDE_SECRET_SENTINEL", search_workspace(index, "OUTSIDE_SECRET_SENTINEL"))

    def test_rejects_windows_junction_reparse_points(self):
        with (
            patch.object(Path, "is_symlink", return_value=False),
            patch.object(Path, "lstat", return_value=SimpleNamespace(st_file_attributes=0x400)),
        ):
            self.assertTrue(_is_symlink_or_reparse_point(self.root / "junction"))

    def test_applies_per_file_total_byte_and_file_count_limits(self):
        self._write("a.py", "a = 1234\n")
        self._write("b.py", "b = 5678\n")
        self._write("large.py", "c = 12345678901234567890\n")

        index = index_workspace(
            self.root, max_file_bytes=12, max_total_bytes=12, max_files=10
        )

        self.assertEqual(index.file_count, 1)
        self.assertLessEqual(index.total_bytes, 12)
        self.assertTrue(index.truncated)
        self.assertGreaterEqual(index.skipped_files, 2)
        file_limited = index_workspace(
            self.root, max_file_bytes=12, max_total_bytes=100, max_files=1
        )
        self.assertEqual(file_limited.file_count, 1)
        self.assertTrue(file_limited.truncated)

    def test_retrieval_returns_relevant_path_and_line_ranges(self):
        self._write(
            "src/totals.py",
            "import math\n\nclass Cart:\n    def calculate_total(self, items):\n"
            "        subtotal = sum(items)\n        return math.ceil(subtotal)\n",
        )
        self._write("src/other.py", "def unrelated():\n    return 'nothing'\n")
        index = index_workspace(self.root)

        result = search_workspace(index, "How does calculate_total sum items?")

        self.assertIn("File: src/totals.py (lines", result)
        self.assertIn("calculate_total", result)
        self.assertIn("sum(items)", result)
        self.assertNotIn("src/other.py", result)

    def test_retrieval_respects_context_limit_and_reports_no_matches(self):
        self._write("src/large.py", "\n".join(f"value_{i} = needle" for i in range(100)))
        index = index_workspace(self.root)

        result = search_workspace(index, "needle", max_context_chars=500)

        self.assertLessEqual(len(result), 500)
        self.assertIn("File: src/large.py", result)
        self.assertIn("No relevant code excerpts", search_workspace(index, "not_present_xyz"))


if __name__ == "__main__":
    unittest.main()
