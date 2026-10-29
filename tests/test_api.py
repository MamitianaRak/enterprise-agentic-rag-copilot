import json
import pytest
from fastapi.testclient import TestClient
from app.api import chat
from app.core.auth import create_token
from app.main import app
from app.services.users import DEMO_ACCOUNTS


def bearer(account: str) -> dict:
    return {"Authorization": f"Bearer {create_token(DEMO_ACCOUNTS[account])}"}


# The demo admin can use every domain; access rules are tested in test_auth.py.
client = TestClient(app, headers=bearer("admin"))

FAKE_RESULT = {
    "answer": "20 days.",
    "source_used": "private_kb",
    "trace": ["Router → KB"],
    "citations": [],
    "current_query": "leave days",
    "memory": [{"question": "leave days", "answer": "20 days.", "source_used": "private_kb"}],
}


@pytest.fixture
def fake_ask(monkeypatch):
    calls = []

    def ask(domain, question, thread_id, access_groups):
        calls.append((domain.name, question, thread_id))
        return FAKE_RESULT

    monkeypatch.setattr(chat, "ask", ask)
    return calls


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_domains_expose_ui_config():
    data = client.get("/api/domains").json()
    assert data["default"] == "hr"
    hr = next(d for d in data["domains"] if d["name"] == "hr")
    assert hr["label"] == "HR Policy"
    assert hr["examples"] and hr["placeholder"] and hr["accent"].startswith("#")
    cloudops = next(d for d in data["domains"] if d["name"] == "cloudops")
    assert cloudops["label"] == "CloudOps" and cloudops["examples"]
    it = next(d for d in data["domains"] if d["name"] == "it")
    assert it["label"] == "IT Support" and it["examples"]
    assert [d["name"] for d in data["domains"]] == ["hr", "it", "cloudops"]


def test_cloudops_chat_returns_triage(monkeypatch):
    triage = {"severity": "SEV2", "service": "checkout-api", "category": "deployment"}
    monkeypatch.setattr(chat, "ask", lambda domain, question, thread_id, groups: {**FAKE_RESULT, "triage": triage})
    res = client.post("/api/chat/cloudops", json={"question": "checkout 502", "thread_id": "inc-1"})
    assert res.status_code == 200
    assert res.json()["domain"] == "cloudops" and res.json()["triage"] == triage


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_chat_stream_sends_steps_then_result(monkeypatch):
    states = [
        {"trace": []},
        {"trace": ["Memory → new conversation"]},
        {"trace": ["Memory → new conversation", "Router → KB"]},
        {**FAKE_RESULT, "trace": ["Memory → new conversation", "Router → KB", "Answer generation → PRIVATE KB"]},
    ]
    monkeypatch.setattr(chat, "stream", lambda domain, question, thread_id, groups: iter(states))
    res = client.post("/api/chat/hr/stream", json={"question": "leave days", "thread_id": "stream-1"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(res.text)
    assert events[0] == ("start", {"thread_id": "stream-1"})
    assert [e[1]["line"] for e in events if e[0] == "step"] == [
        "Memory → new conversation", "Router → KB", "Answer generation → PRIVATE KB",
    ]
    assert events[-1][0] == "result" and events[-1][1]["answer"] == "20 days."


def test_chat_stream_reports_errors_as_events(monkeypatch):
    def failing(domain, question, thread_id, groups):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")
        yield  # pragma: no cover

    monkeypatch.setattr(chat, "stream", failing)
    events = parse_sse(client.post("/api/chat/hr/stream", json={"question": "leave days"}).text)
    assert events[-1][0] == "error" and events[-1][1]["status"] == 503


def test_chat_by_domain(fake_ask):
    res = client.post("/api/chat/hr", json={"question": "leave days", "thread_id": "abc-123"})
    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == "20 days."
    assert data["domain"] == "hr"
    assert data["thread_id"] == "abc-123"
    assert data["memory_turns"] == 1
    assert fake_ask == [("hr", "leave days", "abc-123")]


def test_chat_without_thread_id_creates_one(fake_ask):
    res = client.post("/api/chat/hr", json={"question": "leave days"})
    thread_id = res.json()["thread_id"]
    assert len(thread_id) == 32
    assert fake_ask == [("hr", "leave days", thread_id)]


def test_invalid_thread_id_is_rejected(fake_ask):
    res = client.post("/api/chat/hr", json={"question": "leave days", "thread_id": "../etc"})
    assert res.status_code == 422
    assert fake_ask == []


def test_legacy_chat_route_uses_default_domain(fake_ask):
    res = client.post("/api/chat", json={"question": "leave days", "thread_id": "abc-123"})
    assert res.status_code == 200
    assert fake_ask == [("hr", "leave days", "abc-123")]


def test_conversations_are_listed_per_domain(fake_ask):
    client.post("/api/chat/hr", json={"question": "How many leave days?", "thread_id": "conv-a"})
    client.post("/api/chat/hr", json={"question": "And sick leave?", "thread_id": "conv-a"})
    client.post("/api/chat/hr", json={"question": "Remote work policy?", "thread_id": "conv-b"})

    sessions = {s["thread_id"]: s for s in client.get("/api/sessions/hr").json()["sessions"]}
    assert sessions["conv-a"]["title"] == "How many leave days?"   # title = first question
    assert sessions["conv-a"]["turns"] == 2
    assert sessions["conv-b"]["turns"] == 1

    client.delete("/api/sessions/hr/conv-a")
    remaining = [s["thread_id"] for s in client.get("/api/sessions/hr").json()["sessions"]]
    assert "conv-a" not in remaining and "conv-b" in remaining
    assert client.get("/api/sessions/finance").status_code == 404


def test_session_history_and_delete():
    assert client.get("/api/sessions/hr/unknown-thread").json()["turns"] == []
    assert client.delete("/api/sessions/hr/unknown-thread").json()["deleted"] is True
    assert client.get("/api/sessions/finance/abc").status_code == 404


def test_unknown_domain_is_404(fake_ask):
    res = client.post("/api/chat/finance", json={"question": "budget"})
    assert res.status_code == 404
    assert fake_ask == []


def test_ingest_requires_an_admin():
    res = client.post("/api/ingest/hr", files={"file": ("a.txt", b"hello")}, headers=bearer("employee"))
    assert res.status_code == 403


def test_root_points_to_docs():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["docs"] == "/docs"
