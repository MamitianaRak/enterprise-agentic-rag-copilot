"""Registry of indexed documents per domain, so they can be listed and deleted.

`access` holds the groups allowed to retrieve a document (`["all"]` for everyone). The same list
is written on every chunk in Pinecone, where retrieval filters on it."""
import json
from datetime import datetime, timezone
from app.services.db import connect

PUBLIC_ACCESS = ["all"]


def init_documents() -> None:
    con = connect()
    con.execute(
        """CREATE TABLE IF NOT EXISTS documents (
            domain TEXT NOT NULL,
            filename TEXT NOT NULL,
            chunks INTEGER NOT NULL,
            indexed_at TEXT NOT NULL,
            access TEXT NOT NULL DEFAULT '["all"]',
            PRIMARY KEY (domain, filename)
        )"""
    )
    # Databases created before document rights lack the access column.
    if "access" not in {row[1] for row in con.execute("PRAGMA table_info(documents)")}:
        con.execute("""ALTER TABLE documents ADD COLUMN access TEXT NOT NULL DEFAULT '["all"]'""")
    con.commit()
    con.close()


def _document(row) -> dict:
    return {"filename": row["filename"], "chunks": row["chunks"], "indexed_at": row["indexed_at"],
            "access": json.loads(row["access"])}


def register_document(domain: str, filename: str, chunks: int, access: list[str] | None = None) -> None:
    con = connect()
    con.execute(
        """INSERT INTO documents(domain, filename, chunks, indexed_at, access) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(domain, filename) DO UPDATE SET chunks = excluded.chunks,
             indexed_at = excluded.indexed_at, access = excluded.access""",
        (domain, filename, chunks, datetime.now(timezone.utc).isoformat(), json.dumps(access or PUBLIC_ACCESS)),
    )
    con.commit()
    con.close()


def get_document(domain: str, filename: str) -> dict | None:
    con = connect()
    row = con.execute(
        "SELECT * FROM documents WHERE domain = ? AND filename = ?", (domain, filename)
    ).fetchone()
    con.close()
    return _document(row) if row else None


def list_documents(domain: str, groups: list[str] | None = None) -> list[dict]:
    """Documents of a domain; with `groups`, only those one of the groups may retrieve."""
    con = connect()
    rows = con.execute("SELECT * FROM documents WHERE domain = ? ORDER BY filename", (domain,)).fetchall()
    con.close()
    documents = [_document(r) for r in rows]
    if groups is None:
        return documents
    return [d for d in documents if set(d["access"]) & set(groups)]


def unregister_document(domain: str, filename: str) -> None:
    con = connect()
    con.execute("DELETE FROM documents WHERE domain = ? AND filename = ?", (domain, filename))
    con.commit()
    con.close()
