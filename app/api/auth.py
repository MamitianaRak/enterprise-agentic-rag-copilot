from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.core.auth import create_token, current_user, unauthorized
from app.core.config import get_settings
from app.services.users import DEMO_ACCOUNTS, User, authenticate

router = APIRouter(prefix="/api/auth", tags=["auth"])

settings = get_settings()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class DemoLoginRequest(BaseModel):
    account: str


def session(user: User) -> dict:
    return {"access_token": create_token(user), "token_type": "bearer", "user": user.public()}


@router.post("/login")
def login(payload: LoginRequest):
    user = authenticate(payload.username, payload.password)
    if user is None:
        raise unauthorized("Wrong username or password.")
    return session(user)


@router.get("/demo-accounts")
def demo_accounts():
    """The one-click accounts of the public demo, or none when DEMO_ACCOUNTS is off."""
    if not settings.demo_accounts:
        return {"accounts": []}
    return {"accounts": [{"account": key, **user.public()} for key, user in DEMO_ACCOUNTS.items()]}


@router.post("/demo")
def demo_login(payload: DemoLoginRequest):
    user = DEMO_ACCOUNTS.get(payload.account) if settings.demo_accounts else None
    if user is None:
        raise HTTPException(status_code=404, detail="Demo accounts are not available.")
    return session(user)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user.public()
