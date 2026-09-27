"""Local, persistent SQLite chat history and personal notes."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from config import DATA_DIR, DB_PATH


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def initialize() -> None:
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)


def new_conversation() -> str:
    return str(uuid4())


def add_message(conversation_id: str, role: str, content: str) -> None:
    if role not in {"user", "assistant"}:
        raise ValueError("Invalid chat role")
    with _connect() as db:
        db.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",
                   (conversation_id, role, content, datetime.now(timezone.utc).isoformat()))


def get_messages(conversation_id: str, limit: int = 80) -> list[dict[str, str]]:
    with _connect() as db:
        rows = db.execute("SELECT role,content FROM (SELECT id,role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?) ORDER BY id",
                          (conversation_id, limit)).fetchall()
    return [dict(row) for row in rows]


def add_note(content: str) -> None:
    content = content.strip()
    if content:
        with _connect() as db:
            db.execute("INSERT INTO notes(content,created_at) VALUES(?,?)",
                       (content, datetime.now(timezone.utc).isoformat()))


def get_notes() -> list[dict[str, str]]:
    with _connect() as db:
        rows = db.execute("SELECT id,content,created_at FROM notes ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def delete_note(note_id: int) -> None:
    with _connect() as db:
        db.execute("DELETE FROM notes WHERE id=?", (note_id,))


def clear_conversation(conversation_id: str) -> None:
    with _connect() as db:
        db.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
