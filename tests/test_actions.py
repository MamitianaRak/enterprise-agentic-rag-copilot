"""Escalation actions: rule-based proposals, human approval, single execution."""
import pytest
from fastapi.testclient import TestClient
from app.api import actions as actions_api
from app.api import chat
from app.core.auth import create_token
from app.main import app
from app.services.actions import escalation_policy
from app.services.db import connect
from app.services.users import DEMO_ACCOUNTS

client = TestClient(app)


def bearer(account: str) -> dict:
    return {"Authorization": f"Bearer {create_token(DEMO_ACCOUNTS[account])}"}


def result(source="private_kb", severity=None, service=""):
    triage = {"severity": severity, "service": service, "category": ""} if severity else None
    return {"answer": "Restart the client.", "source_used": source, "triage": triage}


# --- Escalation policy (rules only) ---------------------------------------------------------

@pytest.mark.parametrize("domain, question, outcome, expected", [
    ("it", "Outlook is down for the whole team", result(severity="P1"), ("it_ticket", "P1")),
    ("it", "How long must my password be?", result(severity="P4"), None),
    ("it", "My badge printer shows error 7781", result("insufficient_evidence", "P3"), ("it_ticket", "P3")),
    ("cloudops", "Checkout is down for everyone", result(severity="SEV1", service="checkout-api"), ("incident", "SEV1")),
    ("cloudops", "Latency is slightly up in one region", result(severity="SEV3"), None),
    ("hr", "My manager keeps harassing me", result(), ("hr_case", "confidential")),
    ("hr", "How many leave days do I get?", result(), None),
    ("hr", "What is the paternity leave policy?", result("insufficient_evidence"), ("hr_case", "normal")),
    ("it", "Hi there!", result("direct", "none"), None),
])
def test_escalation_policy(domain, question, outcome, expected):
    proposal = escalation_policy(domain, question, outcome)
    assert (proposal.kind, proposal.priority) == expected if expected else proposal is None


# --- Approval flow ---------------------------------------------------------------------------

@pytest.fixture
def p1_answer(monkeypatch):
    monkeypatch.setattr(chat, "ask", lambda d, q, t, g: {**result(severity="P1"), "trace": [], "citations": [], "memory": []})


def ask_p1(account="employee"):
    res = client.post("/api/chat/it", json={"question": "Outlook is down for the whole team"}, headers=bearer(account))
    assert res.status_code == 200
    return res.json()["proposed_action"]


def test_an_approved_proposal_opens_exactly_one_ticket(p1_answer):
    action = ask_p1()
    assert action["status"] == "proposed" and action["kind"] == "it_ticket" and action["priority"] == "P1"

    done = client.post(f"/api/actions/{action['id']}/approve", headers=bearer("employee"))
    assert done.status_code == 200
    assert done.json()["status"] == "executed" and done.json()["reference"].startswith("IT-")

    again = client.post(f"/api/actions/{action['id']}/approve", headers=bearer("employee"))
    assert again.status_code == 409
    tickets = connect().execute("SELECT COUNT(*) FROM tickets WHERE reference = ?", (done.json()["reference"],))
    assert tickets.fetchone()[0] == 1


def test_a_rejected_proposal_opens_nothing(p1_answer):
    action = ask_p1()
    res = client.post(f"/api/actions/{action['id']}/reject", headers=bearer("employee"))
    assert res.json()["status"] == "rejected" and res.json()["reference"] == ""
    assert client.post(f"/api/actions/{action['id']}/approve", headers=bearer("employee")).status_code == 409


def test_only_the_requester_can_decide(p1_answer):
    action = ask_p1("employee")
    assert client.post(f"/api/actions/{action['id']}/approve", headers=bearer("hr-manager")).status_code == 404
    assert client.post(f"/api/actions/{action['id']}/approve").status_code == 401
    mine = client.get("/api/actions", headers=bearer("employee")).json()["actions"]
    theirs = client.get("/api/actions", headers=bearer("hr-manager")).json()["actions"]
    assert action["id"] in [a["id"] for a in mine] and action["id"] not in [a["id"] for a in theirs]


def test_an_expired_proposal_cannot_be_approved(p1_answer):
    action = ask_p1()
    con = connect()
    con.execute("UPDATE actions SET created_at = '2020-01-01T00:00:00+00:00' WHERE id = ?", (action["id"],))
    con.commit()
    res = client.post(f"/api/actions/{action['id']}/approve", headers=bearer("employee"))
    assert res.status_code == 409 and "expired" in res.json()["detail"]


def test_a_ticketing_outage_leaves_the_proposal_retryable(p1_answer, monkeypatch):
    action = ask_p1()

    class Down:
        def create(self, kind, payload, requester):
            raise ConnectionError("ITSM unreachable")

    monkeypatch.setattr(actions_api, "ticketing", Down())
    assert client.post(f"/api/actions/{action['id']}/approve", headers=bearer("employee")).status_code == 502
    monkeypatch.undo()
    retry = client.post(f"/api/actions/{action['id']}/approve", headers=bearer("employee"))
    assert retry.status_code == 200 and retry.json()["status"] == "executed"


def test_a_plain_answer_proposes_nothing(monkeypatch):
    monkeypatch.setattr(chat, "ask", lambda d, q, t, g: {**result(severity="P4"), "trace": [], "citations": [], "memory": []})
    res = client.post("/api/chat/it", json={"question": "Password length?"}, headers=bearer("employee"))
    assert res.json()["proposed_action"] is None
