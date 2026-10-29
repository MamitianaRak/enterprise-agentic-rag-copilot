from fastapi import APIRouter, Depends, HTTPException, Path, Query
from app.api.chat import authorized_domain
from app.core.auth import current_user
from app.services.actions import ActionError, LocalTicketing, decide, list_actions
from app.services.users import User

router = APIRouter(prefix="/api/actions", tags=["actions"])

ActionId = Path(pattern=r"^[a-f0-9]{32}$")
ticketing = LocalTicketing()


def run_decision(action_id: str, user: User, approve: bool) -> dict:
    try:
        return decide(action_id, user.username, approve, ticketing)
    except ActionError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("")
def my_actions(domain: str | None = Query(default=None), user: User = Depends(current_user)):
    """The user's proposed and decided actions, newest first."""
    if domain:
        authorized_domain(domain, user)
    return {"actions": list_actions(user.username, domain)}


@router.post("/{action_id}/approve")
def approve(action_id: str = ActionId, user: User = Depends(current_user)):
    """Execute the stored proposal: the request carries no parameters that could alter it."""
    return run_decision(action_id, user, approve=True)


@router.post("/{action_id}/reject")
def reject(action_id: str = ActionId, user: User = Depends(current_user)):
    return run_decision(action_id, user, approve=False)
