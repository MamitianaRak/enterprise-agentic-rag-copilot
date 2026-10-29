import json
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.api.errors import to_http_error
from app.core.auth import current_user, require_domain
from app.rag.registry import DEFAULT_DOMAIN, Domain, ask, get_domain, stream
from app.services.actions import propose
from app.services.audit import write_audit
from app.services.conversations import conversation_owner, touch_conversation
from app.services.users import User

router = APIRouter(prefix="/api", tags=["chat"])

THREAD_ID_PATTERN = r"^[A-Za-z0-9_-]{3,120}$"


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=3000)
    thread_id: Optional[str] = Field(default=None, pattern=THREAD_ID_PATTERN,
                                     description="Conversation id; omit to start a new conversation")


def resolve_domain(name: str) -> Domain:
    try:
        return get_domain(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown domain: {name}")


def authorized_domain(name: str, user: User) -> Domain:
    domain = resolve_domain(name)
    require_domain(user, domain.name)
    return domain


def owned_thread(domain: Domain, thread_id: str, user: User) -> str:
    """A thread of another user answers 404, not 403, so its existence is not revealed."""
    owner = conversation_owner(domain.name, thread_id)
    if owner is not None and owner != user.username:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return thread_id


def finish_chat(domain: Domain, question: str, thread_id: str, result: dict, user: User) -> dict:
    """Record the turn and shape the response, for both the plain and the streaming endpoint."""
    write_audit(domain.name, question, result["source_used"], result.get("trace", []), user.username)
    touch_conversation(domain.name, thread_id, question, user.username)
    return {
        "domain": domain.name,
        "thread_id": thread_id,
        "memory_turns": len(result.get("memory", [])),
        "answer": result["answer"],
        "source_used": result["source_used"],
        "trace": result.get("trace", []),
        "citations": result.get("citations", []),
        # The query that produced the evidence: the web query when the answer comes from the web.
        "rewritten_query": (result.get("source_used") == "web_search" and result.get("web_query"))
        or result.get("current_query", question),
        "support_status": result.get("support_status", ""),
        "usefulness": result.get("usefulness", ""),
        "triage": result.get("triage"),  # CloudOps: severity, service, category; None for HR
        # An escalation to approve (ticket, incident, HR case), or None: see app/services/actions.py.
        "proposed_action": propose(domain.name, thread_id, user.username, question, result),
    }


def run_chat(domain: Domain, payload: ChatRequest, user: User):
    thread_id = owned_thread(domain, payload.thread_id or uuid.uuid4().hex, user)
    try:
        result = ask(domain, payload.question, thread_id, user.access_groups)
        return finish_chat(domain, payload.question, thread_id, result, user)
    except Exception as exc:
        raise to_http_error(exc, f"Answering ({domain.name})") from exc


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/{domain}/stream")
def chat_stream(domain: str, payload: ChatRequest, user: User = Depends(current_user)):
    """Server-Sent Events: `start`, one `step` per new trace line, then `result` or `error`."""
    d = authorized_domain(domain, user)
    thread_id = owned_thread(d, payload.thread_id or uuid.uuid4().hex, user)

    def events():
        yield sse("start", {"thread_id": thread_id})
        sent, final = 0, None
        try:
            for state in stream(d, payload.question, thread_id, user.access_groups):
                trace = state.get("trace", [])
                for line in trace[sent:]:
                    yield sse("step", {"line": line})
                sent, final = len(trace), state
            yield sse("result", finish_chat(d, payload.question, thread_id, final, user))
        except Exception as exc:
            err = to_http_error(exc, f"Answering ({d.name})")
            yield sse("error", {"status": err.status_code, "detail": err.detail})

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/{domain}")
def chat(domain: str, payload: ChatRequest, user: User = Depends(current_user)):
    return run_chat(authorized_domain(domain, user), payload, user)


@router.post("/chat", include_in_schema=False)
def chat_default(payload: ChatRequest, user: User = Depends(current_user)):
    """Backward-compatible alias for the default domain."""
    return run_chat(authorized_domain(DEFAULT_DOMAIN, user), payload, user)
