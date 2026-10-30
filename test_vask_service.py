"""Unit coverage for the local VS Code service contract without real AI calls."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vask_service import ApiError, VaskService


class VaskServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        (self.root / "app.py").write_text("def greet(name):\n    return f'Hi {name}'\n", encoding="utf-8")
        self.service = VaskService()

    def tearDown(self):
        self.temp.cleanup()

    def test_index_returns_only_safe_workspace_metadata(self):
        result = self.service.index({"workspaceRoot": str(self.root), "refresh": True})
        self.assertEqual(result["fileCount"], 1)
        self.assertEqual(result["files"], ["app.py"])
        self.assertNotIn("text", result)

    def test_chat_uses_mode_and_bounded_workspace_context(self):
        with patch("vask_service.answer", return_value="Hello") as mocked:
            response = self.service.chat({
                "mode": "Explain Code", "message": "Explain greet",
                "workspaceRoot": str(self.root), "selectedFiles": ["app.py"],
            })
        self.assertEqual(response["reply"], "Hello")
        self.assertTrue(response["conversationId"])
        self.assertEqual(response["context"]["includedFiles"], ["app.py"])
        self.assertEqual(mocked.call_args.kwargs["mode"], "Explain Code")

    def test_chat_includes_unsaved_active_editor_buffer_without_reading_disk(self):
        with patch("vask_service.answer", return_value="Hello") as mocked:
            response = self.service.chat({
                "mode": "Debug Assistant", "message": "Check this file",
                "editorContext": {"relativePath": "main.cpp", "languageId": "cpp", "content": "int main(){ return 42; }"},
            })
        self.assertTrue(response["context"]["activeEditor"]["included"])
        self.assertIn("Active editor buffer", mocked.call_args.kwargs["workspace_context"])
        self.assertIn("return 42", mocked.call_args.kwargs["workspace_context"])

    def test_invalid_modes_and_workspace_paths_are_rejected(self):
        with self.assertRaises(ApiError) as mode_error:
            self.service.new_conversation({"mode": "not a mode"})
        self.assertEqual(mode_error.exception.code, "invalid_mode")
        with self.assertRaises(ApiError) as root_error:
            self.service.index({"workspaceRoot": str(self.root / "missing")})
        self.assertEqual(root_error.exception.code, "invalid_workspace")

    def test_conversation_endpoint_restores_mode_history_unless_fresh(self):
        original = self.service.new_conversation({"mode": "Code Review"})["conversationId"]
        restored = self.service.new_conversation({"mode": "Code Review"})["conversationId"]
        fresh = self.service.new_conversation({"mode": "Code Review", "fresh": True})["conversationId"]
        self.assertEqual(restored, original)
        self.assertNotEqual(fresh, original)

    def test_proposal_is_reviewable_and_rejectable_without_writing_files(self):
        model_result = json.dumps({
            "schema_version": 1,
            "explanation": "Use a clearer greeting.",
            "files": [{
                "path": "app.py",
                "reason": "Update the greeting text.",
                "patch": "@@ -1,2 +1,2 @@\n def greet(name):\n-    return f'Hi {name}'\n+    return f'Hello {name}'\n",
            }],
        })
        with patch("vask_service.request_change_proposal", return_value=model_result):
            proposal = self.service.proposal({"workspaceRoot": str(self.root), "request": "Change greet to say Hello"})
        self.assertEqual(proposal["state"], "Ready for review")
        self.assertTrue(proposal["files"][0]["previewAvailable"])
        self.assertIn("Hi", proposal["files"][0]["originalContent"])
        self.assertIn("Hello", proposal["files"][0]["proposedContent"])
        rejected = self.service.proposal_action(proposal["proposalId"], "reject")
        self.assertEqual(rejected["state"], "Rejected")
        self.assertIn("Hi", (self.root / "app.py").read_text(encoding="utf-8"))

    def test_multi_file_proposal_and_apply_workspace_conflict_are_reported(self):
        (self.root / "helper.py").write_text("def helper():\n    return False\n", encoding="utf-8")
        model_result = json.dumps({"schema_version": 1, "explanation": "Update both functions.", "files": [
            {"path": "app.py", "reason": "Update greeting.", "patch": "@@ -1,2 +1,2 @@\n def greet(name):\n-    return f'Hi {name}'\n+    return f'Hello {name}'\n"},
            {"path": "helper.py", "reason": "Update helper.", "patch": "@@ -1,2 +1,2 @@\n def helper():\n-    return False\n+    return True\n"},
        ]})
        with patch("vask_service.request_change_proposal", return_value=model_result):
            proposal = self.service.proposal({"workspaceRoot": str(self.root), "request": "Update greet and helper"})
        self.assertEqual([item["path"] for item in proposal["files"]], ["app.py", "helper.py"])
        conflict = self.service.proposal_action(proposal["proposalId"], "apply", {"workspaceRoot": str(self.root.parent)})
        self.assertEqual(conflict["state"], "Conflict")
        self.assertIn("Hi", (self.root / "app.py").read_text(encoding="utf-8"))

    def test_apply_detects_a_file_changed_after_proposal_generation(self):
        model_result = json.dumps({"schema_version": 1, "explanation": "Update greeting.", "files": [
            {"path": "app.py", "reason": "Update greeting.", "patch": "@@ -1,2 +1,2 @@\n def greet(name):\n-    return f'Hi {name}'\n+    return f'Hello {name}'\n"},
        ]})
        with patch("vask_service.request_change_proposal", return_value=model_result):
            proposal = self.service.proposal({"workspaceRoot": str(self.root), "request": "Change greet"})
        (self.root / "app.py").write_text("def greet(name):\n    return 'Changed elsewhere'\n", encoding="utf-8")
        result = self.service.proposal_action(proposal["proposalId"], "apply", {"workspaceRoot": str(self.root)})
        self.assertEqual(result["state"], "Conflict")
        self.assertEqual(result["results"][0]["status"], "Conflict")
        self.assertIn("Changed elsewhere", (self.root / "app.py").read_text(encoding="utf-8"))

    def test_oversized_preview_falls_back_to_the_unified_diff(self):
        model_result = json.dumps({"schema_version": 1, "explanation": "Update greeting.", "files": [
            {"path": "app.py", "reason": "Update greeting.", "patch": "@@ -1,2 +1,2 @@\n def greet(name):\n-    return f'Hi {name}'\n+    return f'Hello {name}'\n"},
        ]})
        with patch("vask_service.request_change_proposal", return_value=model_result), patch("vask_service.MAX_PROPOSAL_PREVIEW_CHARS", 1):
            proposal = self.service.proposal({"workspaceRoot": str(self.root), "request": "Change greet"})
        file = proposal["files"][0]
        self.assertFalse(file["previewAvailable"])
        self.assertIsNone(file["originalContent"])
        self.assertTrue(file["diff"])

    def test_markdown_fenced_proposal_json_is_normalized_before_strict_validation(self):
        response = '{"schema_version":1,"explanation":"x","files":[]}'
        self.assertEqual(
            self.service._normalized_proposal_response("```json\n" + response + "\n```"),
            response,
        )
        self.assertEqual(self.service._normalized_proposal_response("plain text"), "plain text")

    def test_invalid_proposal_and_unsafe_or_provider_failed_proposals_are_rejected(self):
        with self.assertRaises(ApiError) as missing:
            self.service.proposal_action("not-found", "reject")
        self.assertEqual(missing.exception.code, "proposal_not_found")
        unsafe = json.dumps({"schema_version": 1, "explanation": "Unsafe.", "files": [
            {"path": "../outside.py", "reason": "Unsafe.", "patch": "@@ -0,0 +1 @@\n+bad\n"},
        ]})
        with patch("vask_service.request_change_proposal", return_value=unsafe), self.assertRaises(ApiError) as invalid:
            self.service.proposal({"workspaceRoot": str(self.root), "request": "Change greet"})
        self.assertEqual(invalid.exception.code, "proposal_invalid")
        with patch("vask_service.request_change_proposal", side_effect=TimeoutError("timed out")), self.assertRaises(ApiError) as provider:
            self.service.proposal({"workspaceRoot": str(self.root), "request": "Change greet"})
        self.assertEqual(provider.exception.code, "provider_request_failed")


if __name__ == "__main__":
    unittest.main()
