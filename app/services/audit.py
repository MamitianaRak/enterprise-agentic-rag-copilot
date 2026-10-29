import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from app.core.config import get_settings


settings = get_settings()


def init_db() -> None:
    Path(settings.audit_db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(settings.audit_db_path)
    con.execute(
        """CREATE TABLE IF NOT EXISTS query_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            question TEXT NOT NULL,
            source_used TEXT NOT NULL,
            trace_json TEXT NOT NULL,
            domain TEXT NOT NULL DEFAULT 'hr'
        )"""
    )
    # Databases created before multi-domain support lack the domain column.
    columns = {row[1] for row in con.execute("PRAGMA table_info(query_audit)")}
    if "domain" not in columns:
        con.execute("ALTER TABLE query_audit ADD COLUMN domain TEXT NOT NULL DEFAULT 'hr'")
    # Databases created before authentication lack the user column.
    if "username" not in columns:
        con.execute("ALTER TABLE query_audit ADD COLUMN username TEXT NOT NULL DEFAULT ''")
    con.commit()
    con.close()


def write_audit(domain: str, question: str, source_used: str, trace: list[str], username: str = "") -> None:
    con = sqlite3.connect(settings.audit_db_path)
    con.execute(
        "INSERT INTO query_audit(created_at, domain, username, question, source_used, trace_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), domain, username, question, source_used, json.dumps(trace)),
    )
    con.commit()
    con.close()
