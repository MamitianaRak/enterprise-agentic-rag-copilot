import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.api.errors import to_http_error
from app.core.auth import create_token
from app.main import app
from app.services import ingestion
from app.services.users import DEMO_ACCOUNTS

client = TestClient(app)
ADMIN = {"Authorization": f"Bearer {create_token(DEMO_ACCOUNTS['admin'])}"}


@pytest.fixture
def fake_pinecone(monkeypatch, tmp_path):
    """Record vector writes/deletes instead of calling Pinecone; isolate uploads."""
    store = {"vectors": {}, "deleted": []}

    def add_documents(chunks, namespace, ids=None):
        for i, c in zip(ids, chunks):
            store["vectors"][i] = c
        return ids

    def delete_vectors(ids, namespace):
        store["deleted"].extend(ids)
        for i in ids:
            store["vectors"].pop(i, None)

    monkeypatch.setattr(ingestion, "add_documents", add_documents)
    monkeypatch.setattr(ingestion, "delete_vectors", delete_vectors)
    monkeypatch.setattr(ingestion.settings, "upload_dir", str(tmp_path))
    from app.api import ingest
    monkeypatch.setattr(ingest.settings, "upload_dir", str(tmp_path))
    return store


def upload(name, text):
    return client.post("/api/ingest/hr", files={"file": (name, text.encode())}, headers=ADMIN)


def test_upload_list_and_delete_document(fake_pinecone):
    res = upload("leave.md", "Employees receive 20 annual leave days.")
    assert res.status_code == 200 and res.json()["chunks"] == 1

    docs = client.get("/api/documents/hr", headers=ADMIN).json()["documents"]
    assert [d["filename"] for d in docs if d["filename"] == "leave.md"] == ["leave.md"]
    chunk = next(iter(fake_pinecone["vectors"].values()))
    assert chunk.metadata["filename"] == "leave.md" and chunk.metadata["domain"] == "hr"

    res = client.delete("/api/documents/hr/leave.md", headers=ADMIN)
    assert res.status_code == 200
    assert fake_pinecone["vectors"] == {}
    listed = client.get("/api/documents/hr", headers=ADMIN).json()["documents"]
    assert "leave.md" not in [d["filename"] for d in listed]


def test_reupload_replaces_instead_of_duplicating(fake_pinecone):
    long_text = "\n\n".join(f"Paragraph {i}: " + "policy detail " * 60 for i in range(6))
    first = upload("handbook.txt", long_text).json()["chunks"]
    assert first > 1
    second = upload("handbook.txt", "Short new version.").json()["chunks"]
    assert second == 1
    # Same stable ids were overwritten and the leftovers of the longer version removed.
    assert len(fake_pinecone["vectors"]) == 1
    assert len(fake_pinecone["deleted"]) == first - 1
    client.delete("/api/documents/hr/handbook.txt", headers=ADMIN)


def test_document_routes_validate_input(fake_pinecone):
    assert client.delete("/api/documents/hr/leave.md").status_code == 401
    assert client.delete("/api/documents/hr/missing.md", headers=ADMIN).status_code == 404
    assert upload("empty.txt", "   ").status_code == 400
    assert upload("image.png", "x").status_code == 400


@pytest.mark.parametrize("exc, status", [
    (RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded"), 503),
    (TimeoutError("Request timed out"), 504),
    (RuntimeError("GOOGLE_API_KEY is missing"), 500),
    (ValueError("boom with internal details"), 500),
])
def test_errors_become_actionable_messages(exc, status):
    err = to_http_error(exc, "Answering")
    assert isinstance(err, HTTPException) and err.status_code == status
    assert "internal details" not in err.detail
