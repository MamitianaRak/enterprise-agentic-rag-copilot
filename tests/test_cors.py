from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from app.main import app


def test_no_cors_headers_by_default():
    # Same-origin setups (Vite proxy, nginx) need no CORS: the API must not advertise any.
    res = TestClient(app).get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in res.headers


def test_configured_origin_is_allowed_for_streaming_and_admin_calls():
    # Same middleware settings as app/main.py when CORS_ORIGINS is set.
    api = FastAPI()
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["https://enterprise-copilot.onrender.com"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Accept", "Authorization"],
    )

    @api.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(api)
    preflight = client.options(
        "/ping",
        headers={
            "Origin": "https://enterprise-copilot.onrender.com",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://enterprise-copilot.onrender.com"

    other = client.get("/ping", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers
