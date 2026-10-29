"""Authentication, domain access, conversation ownership and document rights."""
from datetime import datetime, timedelta, timezone
import jwt
import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from app.api import chat
from app.core import auth
from app.core.auth import create_token
from app.main import app
from app.rag.common.state import initial_state
from app.rag.common.vectorstore import access_filter
from app.rag.hr.graph import build_graph
from app.services import ingestion
from app.services.documents import register_document, unregister_document
from app.services.users import DEMO_ACCOUNTS, User, save_user

client = TestClient(app)
SALARY_BANDS = "Band C (senior): 55,000 to 72,000 EUR"
FULL = {"status": "fully_supported", "evidence": ["band"]}
USEFUL = {"status": "useful", "reason": "answers it"}


def bearer(account: str) -> dict:
    return {"Authorization": f"Bearer {create_token(DEMO_ACCOUNTS[account])}"}


@pytest.fixture
def fake_ask(monkeypatch):
    calls = []

    def ask(domain, question, thread_id, access_groups):
        calls.append({"domain": domain.name, "thread_id": thread_id, "groups": access_groups})
        return {"answer": "ok", "source_used": "private_kb", "trace": [], "citations": [], "memory": []}

    monkeypatch.setattr(chat, "ask", ask)
    return calls


# --- Authentication -------------------------------------------------------------------------

@pytest.mark.parametrize("method, path", [
    ("post", "/api/chat/hr"), ("post", "/api/chat/hr/stream"), ("get", "/api/sessions/hr"),
    ("get", "/api/sessions/hr/t-1"), ("get", "/api/documents/hr"), ("delete", "/api/documents/hr/a.md"),
])
def test_every_data_endpoint_requires_a_token(method, path):
    res = getattr(client, method)(path, **({"json": {"question": "leave days"}} if method == "post" else {}))
    assert res.status_code == 401


def test_public_endpoints_stay_open():
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/domains").status_code == 200


def test_tampered_and_expired_tokens_are_rejected():
    forged = jwt.encode({"sub": "admin"}, "another-secret", algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    expired = jwt.encode({"sub": "admin", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                         auth.settings.jwt_secret, algorithm="HS256")
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert res.status_code == 401 and "expired" in res.json()["detail"]


def test_password_login():
    save_user(User("jdoe", "Jane Doe", "employee", ("hr",), ()), "correct horse battery")
    res = client.post("/api/auth/login", json={"username": "jdoe", "password": "correct horse battery"})
    assert res.status_code == 200 and res.json()["user"]["domains"] == ["hr"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {res.json()['access_token']}"})
    assert me.json()["username"] == "jdoe"
    assert client.post("/api/auth/login", json={"username": "jdoe", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "nobody", "password": "x"}).status_code == 401


def test_demo_accounts_can_be_turned_off(monkeypatch):
    assert client.post("/api/auth/demo", json={"account": "employee"}).status_code == 200
    token = bearer("employee")
    monkeypatch.setattr(auth.settings, "demo_accounts", False)  # the one shared Settings instance
    assert client.post("/api/auth/demo", json={"account": "employee"}).status_code == 404
    assert client.get("/api/auth/demo-accounts").json() == {"accounts": []}
    assert client.get("/api/auth/me", headers=token).status_code == 401  # existing demo sessions end


# --- Domain access and conversation ownership ------------------------------------------------

def test_a_domain_outside_the_account_is_forbidden(fake_ask):
    res = client.post("/api/chat/cloudops", json={"question": "checkout 502"}, headers=bearer("employee"))
    assert res.status_code == 403
    assert client.get("/api/sessions/cloudops", headers=bearer("employee")).status_code == 403
    assert fake_ask == []


def test_the_user_groups_reach_the_graph(fake_ask):
    client.post("/api/chat/hr", json={"question": "leave days"}, headers=bearer("employee"))
    client.post("/api/chat/hr", json={"question": "leave days"}, headers=bearer("hr-manager"))
    assert [c["groups"] for c in fake_ask] == [["all"], ["all", "hr-managers"]]


def test_nobody_can_read_or_continue_someone_else_conversation(fake_ask):
    alex, sam = bearer("employee"), bearer("hr-manager")
    client.post("/api/chat/hr", json={"question": "My leave balance?", "thread_id": "alex-private"}, headers=alex)

    assert client.get("/api/sessions/hr/alex-private", headers=sam).status_code == 404
    assert client.delete("/api/sessions/hr/alex-private", headers=sam).status_code == 404
    res = client.post("/api/chat/hr", json={"question": "and?", "thread_id": "alex-private"}, headers=sam)
    assert res.status_code == 404
    assert "alex-private" not in [s["thread_id"] for s in client.get("/api/sessions/hr", headers=sam).json()["sessions"]]
    assert "alex-private" in [s["thread_id"] for s in client.get("/api/sessions/hr", headers=alex).json()["sessions"]]
    assert len(fake_ask) == 1  # Sam's attempt never reached the graph


# --- Document rights ---------------------------------------------------------------------------

def test_restricted_documents_are_invisible_to_other_groups():
    register_document("hr", "bands.md", 3, ["hr-managers"])
    try:
        employee = client.get("/api/documents/hr", headers=bearer("employee")).json()["documents"]
        manager = client.get("/api/documents/hr", headers=bearer("hr-manager")).json()["documents"]
        assert "bands.md" not in [d["filename"] for d in employee]
        assert "bands.md" in [d["filename"] for d in manager]
    finally:
        unregister_document("hr", "bands.md")


def test_the_pinecone_filter_matches_any_of_the_user_groups():
    assert access_filter(["hr-managers", "all", "all"]) == {"access": {"$in": ["all", "hr-managers"]}}


def test_upload_tags_every_chunk_with_its_groups(monkeypatch, tmp_path):
    written = []
    monkeypatch.setattr(ingestion, "add_documents", lambda chunks, ns, ids=None: written.extend(chunks))
    monkeypatch.setattr(ingestion.settings, "upload_dir", str(tmp_path))
    from app.api import ingest
    monkeypatch.setattr(ingest.settings, "upload_dir", str(tmp_path))

    res = client.post("/api/ingest/hr", files={"file": ("bands.md", SALARY_BANDS.encode())},
                      data={"access": "HR-Managers, legal"}, headers=bearer("admin"))
    assert res.status_code == 200 and res.json()["access"] == ["hr-managers", "legal"]
    assert written and all(c.metadata["access"] == ["hr-managers", "legal"] for c in written)
    bad = client.post("/api/ingest/hr", files={"file": ("x.md", b"text")}, data={"access": "no spaces!"},
                      headers=bearer("admin"))
    assert bad.status_code == 400
    unregister_document("hr", "bands.md")


@pytest.fixture
def confidential_kb(kb_docs):
    restricted = Document(page_content=SALARY_BANDS,
                          metadata={"filename": "compensation_bands_confidential.md", "access": ["hr-managers"]})
    return [*kb_docs, restricted]


def test_an_employee_never_gets_restricted_chunks_into_the_llm_prompt(patch_rag, monkeypatch, confidential_kb):
    from tests.conftest import FakeRetriever  # noqa: PLC0415
    from app.rag.common import nodes
    monkeypatch.setattr(nodes, "get_retriever", lambda ns, groups: FakeRetriever(confidential_kb, groups))

    fake = patch_rag([{"route": "kb"}, {"grade": "good"}, FULL, USEFUL], text="answer")
    employee = build_graph().invoke(initial_state("What is the senior salary band?", ["all"]))
    assert SALARY_BANDS not in "\n".join(map(str, fake.prompts))
    assert "compensation_bands_confidential.md" not in [c["title"] for c in employee["citations"]]

    fake = patch_rag([{"route": "kb"}, {"grade": "good"}, FULL, USEFUL], text="answer")
    manager = build_graph().invoke(initial_state("What is the senior salary band?", ["all", "hr-managers"]))
    assert SALARY_BANDS in "\n".join(map(str, fake.prompts))
    assert "compensation_bands_confidential.md" in [c["title"] for c in manager["citations"]]
