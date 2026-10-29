from fastapi import APIRouter, Depends, Path, Query
from app.api.chat import THREAD_ID_PATTERN, authorized_domain, owned_thread
from app.core.auth import current_user
from app.rag.registry import clear_history, get_history
from app.services.conversations import conversation_owner, delete_conversation, list_conversations
from app.services.users import User

router = APIRouter(prefix="/api", tags=["sessions"])

ThreadId = Path(pattern=THREAD_ID_PATTERN)


@router.get("/sessions/{domain}")
def sessions(domain: str, limit: int = Query(default=50, ge=1, le=200), user: User = Depends(current_user)):
    d = authorized_domain(domain, user)
    return {"domain": d.name, "sessions": list_conversations(d.name, user.username, limit)}


@router.get("/sessions/{domain}/{thread_id}")
def session_history(domain: str, thread_id: str = ThreadId, user: User = Depends(current_user)):
    d = authorized_domain(domain, user)
    owned_thread(d, thread_id, user)
    # A thread that does not exist yet has no history (and no owner to check).
    turns = get_history(d, thread_id) if conversation_owner(d.name, thread_id) else []
    return {"domain": d.name, "thread_id": thread_id, "turns": turns}


@router.delete("/sessions/{domain}/{thread_id}")
def delete_session(domain: str, thread_id: str = ThreadId, user: User = Depends(current_user)):
    d = authorized_domain(domain, user)
    owned_thread(d, thread_id, user)
    clear_history(d, thread_id)
    delete_conversation(d.name, thread_id)
    return {"deleted": True, "domain": d.name, "thread_id": thread_id}
