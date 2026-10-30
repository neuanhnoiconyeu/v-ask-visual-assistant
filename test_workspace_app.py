"""Streamlit AppTest coverage for workspace indexing and context selection."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest
from memory import new_conversation
from workspace_reader import index_workspace


class WorkspaceAppTests(unittest.TestCase):
    def test_mode_switch_renders_an_independent_developer_composer(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
        self.assertEqual(len(app.exception), 0)

        app.segmented_control[0].set_value("Debug Assistant").run()

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.text_area(key="developer_code_debug_assistant").label, "Code")
        self.assertNotIn("developer_code_code_review", app.session_state)

    def test_welcome_actions_keep_mode_switching_without_duplicate_workflow_buttons(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
        conversations = dict(app.session_state["mode_conversation_ids"])
        conversations["Debug Assistant"] = new_conversation("Debug Assistant")
        app.session_state["mode_conversation_ids"] = conversations
        app.session_state["assistant_mode"] = "Debug Assistant"
        app.session_state["active_workspace_mode"] = "Debug Assistant"
        app.run()

        self.assertEqual(app.button(key="welcome_new_conversation").label, "New conversation")
        self.assertEqual(app.button(key="welcome_explore_project").label, "Explore project")
        self.assertNotIn("quick_mode_1", [button.key for button in app.button])
        app.button(key="welcome_explore_project").click().run()

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["assistant_mode"], "General chat")

    def test_streamlit_app_renders_with_an_indexed_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            source = root / "src" / "main.py"
            source.parent.mkdir(parents=True)
            source.write_text("def run():\n    return True\n", encoding="utf-8")

            app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
            self.assertEqual(len(app.exception), 0)
            app.session_state["workspace_index"] = index_workspace(root)
            app.session_state["workspace_selection_root"] = str(root.resolve())
            app.run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.session_state["workspace_index"].file_count, 1)
            self.assertEqual(app.button(key="tool_new_conversation").label, "New conversation")
            self.assertEqual(len(app.exception), 0)


if __name__ == "__main__":
    unittest.main()
