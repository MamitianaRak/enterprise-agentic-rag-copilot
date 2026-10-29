"""Escalation actions: the agent proposes, a human approves, the server executes.

1. After an answer, `escalation_policy` decides with plain rules, from the agent's triage and
   outcome, whether to propose an action. The LLM never triggers one by itself.
2. The proposal is stored here with all its parameters; the browser only gets its id back, so
   it cannot change what will be executed.
3. Only the user who asked can approve or reject it, once: a second decision is refused, so an
   approval clicked twice never opens two tickets.
4. Approval runs the stored action through a `Ticketing` backend. `LocalTicketing` keeps
   tickets in SQLite; a Jira or ServiceNow client would implement the same method.
"""
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from app.services.db import connect

PROPOSAL_TTL = timedelta(hours=24)
EXCERPT = 600

KINDS = {
    "it_ticket": {"label": "IT ticket", "prefix": "IT"},
    "incident": {"label": "Incident", "prefix": "INC"},
    "hr_case": {"label": "HR case", "prefix": "HR"},
}

# Sensitive HR topics always get a human, even when the handbook answers them.
SENSITIVE_HR = re.compile(
    r"harass|discriminat|bully|retaliat|assault|whistleblow|threat|unsafe|abuse", re.IGNORECASE
)
NO_ANSWER = {"web_search", "insufficient_evidence"}


class ActionError(Exception):
    """A decision that cannot be applied; `status` is the HTTP code to answer with."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


class Ticketing(Protocol):
    def create(self, kind: str, payload: dict, requester: str) -> str:
        """Open the ticket and return its reference."""


@dataclass
class Proposal:
    kind: str
    title: str
    priority: str
    reason: str


def escalation_policy(domain: str, question: str, result: dict) -> Proposal | None:
    """Whether this answer should come with an action to approve. Rules only, no LLM."""
    source = result.get("source_used", "")
    if source in ("", "direct"):
        return None
    severity = (result.get("triage") or {}).get("severity", "none")
    service = (result.get("triage") or {}).get("service", "")
    title = re.sub(r"\s+", " ", question).strip()[:120]

    if domain == "it":
        if severity in ("P1", "P2"):
            return Proposal("it_ticket", title, severity, f"Triaged {severity}: the service desk should take over.")
        if source in NO_ANSWER:
            return Proposal("it_ticket", title, severity if severity != "none" else "P3",
                            "The IT knowledge base has no answer for this.")
    if domain == "cloudops" and severity in ("SEV1", "SEV2"):
        where = f" on {service}" if service else ""
        return Proposal("incident", title, severity, f"Triaged {severity}{where}: open an incident and page on-call.")
    if domain == "hr":
        if SENSITIVE_HR.search(question):
            return Proposal("hr_case", title, "confidential", "Sensitive topic: an HR partner should follow up.")
        if source in NO_ANSWER:
            return Proposal("hr_case", title, "normal", "The HR handbook does not answer this.")
    return None


def init_actions() -> None:
    con = connect()
    con.execute(
        """CREATE TABLE IF NOT EXISTS actions (
            id TEXT PRIMARY KEY,
            domain TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            username TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            reference TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            decided_at TEXT NOT NULL DEFAULT ''
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS tickets (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT NOT NULL,
            kind TEXT NOT NULL,
            requester TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    con.commit()
    con.close()


def _public(row) -> dict:
    payload = json.loads(row["payload"])
    return {"id": row["id"], "kind": row["kind"], "label": KINDS[row["kind"]]["label"], "status": row["status"],
            "title": payload["title"], "priority": payload["priority"], "reason": payload["reason"],
            "reference": row["reference"], "created_at": row["created_at"]}


def propose(domain: str, thread_id: str, username: str, question: str, result: dict) -> dict | None:
    """Store the proposal of the escalation policy, if any, and return what the browser shows."""
    proposal = escalation_policy(domain, question, result)
    if proposal is None:
        return None
    payload = {
        "title": proposal.title, "priority": proposal.priority, "reason": proposal.reason,
        "question": question, "answer_excerpt": (result.get("answer") or "")[:EXCERPT],
        "triage": result.get("triage"), "source_used": result.get("source_used"),
    }
    action_id = uuid.uuid4().hex
    con = connect()
    con.execute(
        "INSERT INTO actions(id, domain, thread_id, username, kind, status, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?)",
        (action_id, domain, thread_id, username, proposal.kind, json.dumps(payload),
         datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    row = con.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    con.close()
    return _public(row)


def decide(action_id: str, username: str, approve: bool, ticketing: Ticketing) -> dict:
    """Approve (execute) or reject a proposal of this user. Each proposal is decided once."""
    con = connect()
    try:
        row = con.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
        if row is None or row["username"] != username:  # another user's action does not exist for you
            raise ActionError(404, "Action not found")
        if row["status"] != "proposed":
            raise ActionError(409, f"This action was already {row['status']}.")
        if datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"]) > PROPOSAL_TTL:
            raise ActionError(409, "This proposal has expired. Ask again to get a new one.")

        # Claim the proposal before executing: a concurrent second click updates no row and stops here.
        status = "approved" if approve else "rejected"
        now = datetime.now(timezone.utc).isoformat()
        claimed = con.execute(
            "UPDATE actions SET status = ?, decided_at = ? WHERE id = ? AND status = 'proposed'",
            (status, now, action_id),
        ).rowcount
        con.commit()
        if not claimed:
            raise ActionError(409, "This action was already decided.")
        if approve:
            try:
                reference = ticketing.create(row["kind"], json.loads(row["payload"]), username)
            except Exception as exc:
                # Nothing was created: put the proposal back so the user can try again.
                con.execute("UPDATE actions SET status = 'proposed', decided_at = '' WHERE id = ?", (action_id,))
                con.commit()
                raise ActionError(502, "The ticketing system did not answer. Try again in a moment.") from exc
            con.execute("UPDATE actions SET status = 'executed', reference = ? WHERE id = ?", (reference, action_id))
            con.commit()
        return _public(con.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone())
    finally:
        con.close()


def list_actions(username: str, domain: str | None = None) -> list[dict]:
    con = connect()
    query, params = "SELECT * FROM actions WHERE username = ?", [username]
    if domain:
        query, params = query + " AND domain = ?", [*params, domain]
    rows = con.execute(query + " ORDER BY created_at DESC LIMIT 50", params).fetchall()
    con.close()
    return [_public(r) for r in rows]


class LocalTicketing:
    """Tickets kept in the application database: the stand-in for Jira or ServiceNow."""

    def create(self, kind: str, payload: dict, requester: str) -> str:
        con = connect()
        cursor = con.execute(
            "INSERT INTO tickets(reference, kind, requester, payload, created_at) VALUES ('', ?, ?, ?, ?)",
            (kind, requester, json.dumps(payload), datetime.now(timezone.utc).isoformat()),
        )
        reference = f"{KINDS[kind]['prefix']}-{1000 + cursor.lastrowid}"
        con.execute("UPDATE tickets SET reference = ? WHERE seq = ?", (reference, cursor.lastrowid))
        con.commit()
        con.close()
        return reference
