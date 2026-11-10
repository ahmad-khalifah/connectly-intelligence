"""Sign-in, the current account, password changes and account administration."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from connectly.api.deps import (
    client_ip,
    current_user_allow_password_change,
    get_session,
    require_admin,
)
from connectly.core.config import get_settings
from connectly.core.security import (
    create_token,
    hash_password,
    login_limiter,
    password_problems,
    verify_password,
)
from connectly.models import ROLES, Organisation, User
from connectly.services import audit

router = APIRouter(prefix="/api/v1", tags=["auth"])

Role = Literal[ROLES]  # type: ignore[valid-type]
BAD_CREDENTIALS = "e-mail or password is incorrect"
TOO_MANY = "too many sign-in attempts; wait a few minutes and try again"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool
    organisation_id: int | None
    last_login_at: datetime | None
    created_at: datetime


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class UserCreateIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    role: Role
    organisation_id: int | None = None


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    role: Role | None = None
    is_active: bool | None = None
    organisation_id: int | None = None


class TemporaryPasswordOut(BaseModel):
    user: UserOut
    temporary_password: str = Field(description="Shown once. Give it to the user privately.")


USER_FIELDS = ("email", "full_name", "role", "is_active", "organisation_id")


def normalise_email(email: str) -> str:
    return email.strip().lower()


def temporary_password() -> str:
    return secrets.token_urlsafe(12)


def _token(user: User) -> TokenOut:
    token, expires = create_token(user.id, user.role, user.token_version)
    return TokenOut(access_token=token, expires_at=expires, user=UserOut.model_validate(user))


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, session: Session = Depends(get_session)) -> TokenOut:
    settings = get_settings()
    ip = client_ip(request)
    if not login_limiter.hit(f"ip:{ip}", settings.login_ip_limit, settings.login_ip_window_seconds):
        raise HTTPException(429, TOO_MANY)
    email = normalise_email(body.email)
    user = session.scalar(select(User).where(User.email == email))
    now = datetime.now(UTC)
    if user is not None and user.locked_until and user.locked_until > now:
        raise HTTPException(429, TOO_MANY)
    ok = verify_password(body.password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        if user is not None:
            user.failed_logins += 1
            locked = user.failed_logins >= settings.login_max_failures
            if locked:
                user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
                user.failed_logins = 0
            audit.record(
                session,
                user.email,
                "login_failed",
                "user",
                user.id,
                "account locked" if locked else None,
                ip=ip,
            )
            session.commit()
        raise HTTPException(401, BAD_CREDENTIALS)
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    audit.record(session, user, "login", "user", user.id, ip=ip)
    session.commit()
    return _token(user)


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user_allow_password_change)) -> User:
    return user


@router.post("/auth/change-password", response_model=TokenOut)
def change_password(
    body: PasswordChangeIn,
    request: Request,
    user: User = Depends(current_user_allow_password_change),
    session: Session = Depends(get_session),
) -> TokenOut:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "current password is incorrect")
    problems = password_problems(body.new_password, user.email)
    if body.new_password == body.current_password:
        problems.append("must differ from the current password")
    if problems:
        raise HTTPException(422, "new password " + "; ".join(problems))
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.token_version += 1  # signs out every other session
    audit.record(session, user, "password_changed", "user", user.id, ip=client_ip(request))
    session.commit()
    return _token(user)


@router.post("/auth/logout-all", status_code=204)
def logout_all(
    request: Request,
    user: User = Depends(current_user_allow_password_change),
    session: Session = Depends(get_session),
) -> None:
    user.token_version += 1
    audit.record(session, user, "logout_all", "user", user.id, ip=client_ip(request))
    session.commit()


# ----------------------------------------------------------------------- administration


@router.get("/users", response_model=list[UserOut])
def list_users(
    _: User = Depends(require_admin), session: Session = Depends(get_session)
) -> list[User]:
    return list(session.scalars(select(User).order_by(User.full_name)))


def _check_organisation(session: Session, role: str, organisation_id: int | None) -> None:
    if organisation_id is None:
        return
    if role != "company":
        raise HTTPException(422, "only company accounts are linked to an organisation")
    if session.get(Organisation, organisation_id) is None:
        raise HTTPException(422, f"no organisation {organisation_id}")


def _active_admins(session: Session) -> int:
    return session.scalar(
        select(func.count()).select_from(User).where(User.role == "admin", User.is_active)
    )


@router.post("/users", response_model=TemporaryPasswordOut, status_code=201)
def create_user(
    body: UserCreateIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> TemporaryPasswordOut:
    email = normalise_email(body.email)
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "an account with this e-mail already exists")
    _check_organisation(session, body.role, body.organisation_id)
    password = temporary_password()
    user = User(
        email=email,
        full_name=body.full_name.strip(),
        role=body.role,
        organisation_id=body.organisation_id,
        password_hash=hash_password(password),
        must_change_password=True,
    )
    session.add(user)
    session.flush()
    audit.record(
        session,
        admin,
        "create",
        "user",
        user.id,
        f"created {body.role} account {email}",
        {"after": audit.snapshot(user, USER_FIELDS)},
        ip=client_ip(request),
    )
    session.commit()
    return TemporaryPasswordOut(user=UserOut.model_validate(user), temporary_password=password)


def _get_user(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, f"no user {user_id}")
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdateIn,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> User:
    user = _get_user(session, user_id)
    before = audit.snapshot(user, USER_FIELDS)
    changes = body.model_dump(exclude_unset=True)
    removing_admin = (
        user.role == "admin"
        and user.is_active
        and (changes.get("role", "admin") != "admin" or changes.get("is_active", True) is False)
    )
    if removing_admin and _active_admins(session) <= 1:
        raise HTTPException(409, "this is the only active admin account")
    new_role = changes.get("role", user.role)
    _check_organisation(session, new_role, changes.get("organisation_id", user.organisation_id))
    for k, v in changes.items():
        setattr(user, k, v.strip() if isinstance(v, str) and k == "full_name" else v)
    if new_role != "company":
        user.organisation_id = None
    if "role" in changes or changes.get("is_active") is False or "organisation_id" in changes:
        user.token_version += 1
    after = audit.snapshot(user, USER_FIELDS)
    audit.record(
        session,
        admin,
        "update",
        "user",
        user.id,
        None,
        audit.diff(before, after),
        ip=client_ip(request),
    )
    session.commit()
    return user


@router.post("/users/{user_id}/reset-password", response_model=TemporaryPasswordOut)
def reset_password(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> TemporaryPasswordOut:
    user = _get_user(session, user_id)
    password = temporary_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.token_version += 1
    user.failed_logins = 0
    user.locked_until = None
    audit.record(session, admin, "reset_password", "user", user.id, ip=client_ip(request))
    session.commit()
    return TemporaryPasswordOut(user=UserOut.model_validate(user), temporary_password=password)
