from collections.abc import Callable, Iterator

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from connectly.core.config import get_settings
from connectly.core.security import decode_token
from connectly.models import User

bearer = HTTPBearer(auto_error=False, description="Session token from /api/v1/auth/login")


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.sessionmaker()
    try:
        yield session
    finally:
        session.close()


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _unauthorised(detail: str = "sign in required") -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def current_user_allow_password_change(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    """The signed-in user, even if they still have to change a temporary password."""
    if creds is None:
        raise _unauthorised()
    try:
        claims = decode_token(creds.credentials)
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _unauthorised("session expired or invalid") from None
    user = session.get(User, user_id)
    if user is None or not user.is_active or user.token_version != claims.get("tv"):
        raise _unauthorised("session expired or invalid")
    return user


def current_user(user: User = Depends(current_user_allow_password_change)) -> User:
    if user.must_change_password:
        raise HTTPException(403, "change your temporary password before continuing")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"this action needs one of these roles: {', '.join(roles)}")
        return user

    return dep


require_admin = require_roles("admin")
require_researcher = require_roles("admin", "researcher")
