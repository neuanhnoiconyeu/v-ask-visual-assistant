"""Source-level safety checks for the extension until npm can run TypeScript tests."""
from __future__ import annotations

import unittest
from pathlib import Path


SOURCE = (Path(__file__).parent / "vscode-extension" / "src" / "extension.ts").read_text(encoding="utf-8")


class ExtensionSourceTests(unittest.TestCase):
    def test_webview_messages_are_checked_before_proposal_actions(self):
        self.assertIn('if (typeof data.type !== "string") return;', SOURCE)
        self.assertIn('typeof data.proposalId === "string"', SOURCE)
        self.assertIn('data.text.length > 50000', SOURCE)

    def test_preview_uses_vscode_diff_without_project_writes(self):
        self.assertIn('executeCommand("vscode.diff"', SOURCE)
        self.assertIn('openTextDocument({ content: file.originalContent })', SOURCE)
        self.assertNotIn("writeFile(", SOURCE)

    def test_apply_is_modal_and_passes_the_active_workspace(self):
        self.assertIn('showWarningMessage(`Apply V-Ask proposal', SOURCE)
        self.assertIn('{ modal: true }', SOURCE)
        self.assertIn('{ workspaceRoot: root }', SOURCE)


if __name__ == "__main__":
    unittest.main()
