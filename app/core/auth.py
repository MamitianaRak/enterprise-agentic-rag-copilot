"""JWT bearer authentication and the access checks every endpoint relies on.

The token only carries the username: roles, domains and groups are read again on each request,
so revoking a right takes effect immediately instead of when the token expires.
"""
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import get_settings
from app.services.users import User, get_user

settings = get_settings()
ALGORITHM = "HS256"

bearer = HTTPBearer(auto_error=False)


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": user.username, "iat": now, "exp": now + timedelta(minutes=settings.token_ttl_minutes)}
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def unauthorized(detail: str = "Sign in to continue.") -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> User:
    if credentials is None:
        raise unauthorized()
    try:
        claims = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise unauthorized("Your session has expired. Sign in again.")
    except jwt.InvalidTokenError:
        raise unauthorized("Invalid token.")
    user = get_user(claims.get("sub", ""), include_demo=settings.demo_accounts)
    if user is None:
        raise unauthorized("This account no longer exists.")
    return user


def require_domain(user: User, domain: str) -> None:
    if domain not in user.domains:
        raise HTTPException(status_code=403, detail=f"Your account has no access to the {domain} assistant.")


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Only an administrator can change the knowledge base.")
    return user
