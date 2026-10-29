"""Index of conversations per domain and owner (title, turns, dates). The messages themselves
live in the LangGraph checkpointer; this table makes them listable and records who owns each
thread, so nobody can read or continue someone else's conversation."""
from datetime import datetime, timezone
from app.services.db import connect

TITLE_LENGTH = 80


def init_conversations() -> None:
    con = connect()
    con.execute(
        """CREATE TABLE IF NOT EXISTS conversations (
            domain TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            title TEXT NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            turns INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (domain, thread_id)
        )"""
    )
    # Databases created before authentication lack the owner column.
    if "username" not in {row[1] for row in con.execute("PRAGMA table_info(conversations)")}:
        con.execute("ALTER TABLE conversations ADD COLUMN username TEXT NOT NULL DEFAULT ''")
    con.commit()
    con.close()


def conversation_owner(domain: str, thread_id: str) -> str | None:
    """The owner of a conversation, or None when the thread does not exist yet."""
    con = connect()
    row = con.execute(
        "SELECT username FROM conversations WHERE domain = ? AND thread_id = ?", (domain, thread_id)
    ).fetchone()
    con.close()
    return row["username"] if row else None


def touch_conversation(domain: str, thread_id: str, question: str, username: str) -> None:
    """Create the conversation on its first question, then bump turns and updated_at."""
    now = datetime.now(timezone.utc).isoformat()
    title = question.strip().replace("\n", " ")[:TITLE_LENGTH]
    con = connect()
    con.execute(
        """INSERT INTO conversations(domain, thread_id, username, title, turns, created_at, updated_at)
           VALUES (?, ?, ?, ?, 1, ?, ?)
           ON CONFLICT(domain, thread_id) DO UPDATE SET turns = turns + 1, updated_at = excluded.updated_at""",
        (domain, thread_id, username, title, now, now),
    )
    con.commit()
    con.close()


def list_conversations(domain: str, username: str, limit: int = 50) -> list[dict]:
    con = connect()
    rows = con.execute(
        "SELECT thread_id, title, turns, created_at, updated_at FROM conversations "
        "WHERE domain = ? AND username = ? ORDER BY updated_at DESC LIMIT ?",
        (domain, username, limit),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def delete_conversation(domain: str, thread_id: str) -> None:
    con = connect()
    con.execute("DELETE FROM conversations WHERE domain = ? AND thread_id = ?", (domain, thread_id))
    con.commit()
    con.close()
