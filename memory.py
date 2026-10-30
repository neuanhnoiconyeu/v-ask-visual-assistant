"""Local, persistent SQLite chat history and personal notes."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from collections.abc import Iterator
from uuid import uuid4

from config import DATA_DIR, DB_PATH


DEFAULT_MODE = "General chat"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize() -> None:
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_conversations_mode_updated
            ON conversations(mode, updated_at DESC);
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
        # Existing installations stored messages without a conversation registry.
        # Keep their history available in the original general-chat workspace.
        db.execute(
            """
            INSERT OR IGNORE INTO conversations(id, mode, created_at, updated_at)
            SELECT conversation_id, ?, MIN(created_at), MAX(created_at)
            FROM messages
            GROUP BY conversation_id
            """,
            (DEFAULT_MODE,),
        )


def new_conversation(mode: str = DEFAULT_MODE) -> str:
    """Create a persistent conversation owned by one assistant workspace."""
    conversation_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as db:
        db.execute(
            "INSERT INTO conversations(id,mode,created_at,updated_at) VALUES(?,?,?,?)",
            (conversation_id, mode, created_at, created_at),
        )
    return conversation_id


def get_or_create_mode_conversation(mode: str) -> str:
    """Restore the latest conversation for a mode, or create its first one."""
    with _connect() as db:
        row = db.execute(
            "SELECT id FROM conversations WHERE mode=? ORDER BY updated_at DESC, created_at DESC LIMIT 1",
            (mode,),
        ).fetchone()
    return str(row["id"]) if row else new_conversation(mode)


def add_message(conversation_id: str, role: str, content: str) -> None:
    if role not in {"user", "assistant"}:
        raise ValueError("Invalid chat role")
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as db:
        db.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",
                   (conversation_id, role, content, now))
        db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))


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
