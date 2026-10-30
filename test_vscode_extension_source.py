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

    def test_chat_and_proposals_include_the_active_workspace_file(self):
        self.assertIn('selectedFiles: this.contextFiles()', SOURCE)
        self.assertIn('files.add(vscode.workspace.asRelativePath(editor.document.uri, false)', SOURCE)

    def test_backend_discovery_never_uses_the_installed_extension_directory(self):
        self.assertIn('Multiple V-Ask backends were found', SOURCE)
        self.assertIn('validatedBackendPath', SOURCE)
        self.assertIn('llm_client.py', SOURCE)
        self.assertIn('config.py', SOURCE)
        self.assertNotIn('path.resolve(__dirname, "../../vask_service.py")', SOURCE)

    def test_configuration_and_connection_commands_are_registered(self):
        self.assertIn('vask.configureBackend', SOURCE)
        self.assertIn('vask.testBackendConnection', SOURCE)
        self.assertIn('showOpenDialog', SOURCE)
        self.assertIn('Backend configured and connected.', SOURCE)

    def test_workspace_chat_uses_active_document_buffer_and_index(self):
        self.assertIn('content: editor.document.getText()', SOURCE)
        self.assertIn('editorContext: this.editorContext()', SOURCE)
        self.assertIn('await this.ensureIndex(root, false)', SOURCE)


if __name__ == "__main__":
    unittest.main()
