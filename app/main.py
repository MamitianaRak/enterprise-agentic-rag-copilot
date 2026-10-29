from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import actions, auth, chat, health, ingest, sessions
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.actions import init_actions
from app.services.audit import init_db
from app.services.conversations import init_conversations
from app.services.documents import init_documents
from app.services.users import init_users


configure_logging()
settings = get_settings()
if settings.app_env == "production" and settings.jwt_secret == "dev-only-secret-change-me":
    raise RuntimeError("Set JWT_SECRET: the default secret would let anyone forge a session token.")
init_db()
init_conversations()
init_documents()
init_users()
init_actions()


# API only: the web UI is the React app in frontend/ (Vite in dev, nginx or a static host in prod).
app = FastAPI(title=settings.app_name, version="2.0.0")

cors_origins = [o.strip().rstrip("/") for o in settings.cors_origins.split(",") if o.strip()]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Accept", "Authorization"],
    )

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(ingest.router)
app.include_router(sessions.router)
app.include_router(actions.router)


@app.get("/", include_in_schema=False)
def root():
    return {"service": settings.app_name, "docs": "/docs", "health": "/api/health"}
