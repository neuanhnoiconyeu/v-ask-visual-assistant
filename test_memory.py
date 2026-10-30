"""Persistence and isolation checks for V-Ask assistant workspaces."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import memory


class ModeConversationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.db_path = self.data_dir / "history.sqlite3"
        self.data_patch = patch.object(memory, "DATA_DIR", self.data_dir)
        self.path_patch = patch.object(memory, "DB_PATH", self.db_path)
        self.data_patch.start()
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.data_patch.stop()
        self.temp_dir.cleanup()

    def test_each_mode_restores_only_its_own_messages(self):
        memory.initialize()
        modes = (
            "General chat", "Explain Code", "Debug Assistant", "Code Review", "Generate Tests",
        )
        conversation_ids = {
            mode: memory.get_or_create_mode_conversation(mode) for mode in modes
        }
        for mode, conversation_id in conversation_ids.items():
            memory.add_message(conversation_id, "user", f"{mode}-only message")

        self.assertEqual(len(set(conversation_ids.values())), len(modes))
        for mode, conversation_id in conversation_ids.items():
            messages = memory.get_messages(conversation_id)
            self.assertEqual(messages[0]["content"], f"{mode}-only message")
            self.assertEqual(memory.get_or_create_mode_conversation(mode), conversation_id)

    def test_new_conversation_does_not_replace_another_mode_workspace(self):
        memory.initialize()
        review_id = memory.get_or_create_mode_conversation("Code Review")
        memory.add_message(review_id, "assistant", "Review history")
        next_debug_id = memory.new_conversation("Debug Assistant")

        self.assertEqual(memory.get_messages(review_id)[0]["content"], "Review history")
        self.assertEqual(memory.get_messages(next_debug_id), [])

    def test_legacy_messages_are_migrated_to_general_chat(self):
        self.data_dir.mkdir(parents=True)
        legacy_id = "legacy-conversation"
        timestamp = datetime.now(timezone.utc).isoformat()
        db = sqlite3.connect(self.db_path)
        try:
            with db:
                db.execute(
                    """
                    CREATE TABLE messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
                        role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
                    )
                    """
                )
                db.execute(
                    "INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",
                    (legacy_id, "user", "Existing history", timestamp),
                )
        finally:
            db.close()

        memory.initialize()

        self.assertEqual(memory.get_or_create_mode_conversation("General chat"), legacy_id)
        self.assertEqual(memory.get_messages(legacy_id)[0]["content"], "Existing history")


if __name__ == "__main__":
    unittest.main()
