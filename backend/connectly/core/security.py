"""Password hashing (Argon2id), session tokens (HS256 JWT) and sign-in throttling."""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from connectly.core.config import Settings, get_settings

log = logging.getLogger(__name__)

_hasher = PasswordHash((Argon2Hasher(),))
# Used to spend the same time on unknown e-mail addresses as on known ones.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))
ALGORITHM = "HS256"
MIN_PASSWORD_LENGTH = 12
_dev_secret: str | None = None


class InsecureConfiguration(RuntimeError):
    pass


def signing_key(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if settings.secret_key:
        if len(settings.secret_key) < 32:
            raise InsecureConfiguration("CONNECTLY_SECRET_KEY must be at least 32 characters")
        return settings.secret_key
    if settings.is_production:
        raise InsecureConfiguration("CONNECTLY_SECRET_KEY is required when environment=production")
    global _dev_secret
    if _dev_secret is None:
        _dev_secret = secrets.token_urlsafe(48)
        log.warning(
            "CONNECTLY_SECRET_KEY is not set: using a random key for this process. "
            "Sign-ins end when the server restarts."
        )
    return _dev_secret


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    try:
        return _hasher.verify(password, password_hash)
    except Exception:  # malformed hash
        return False


def password_problems(password: str, email: str | None = None) -> list[str]:
    """Reasons a new password is not acceptable (empty list if it is)."""
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > 256:
        problems.append("must be at most 256 characters")
    if len(set(password)) < 5:
        problems.append("uses too few different characters")
    if email and email.split("@")[0].lower() in password.lower() and len(email.split("@")[0]) > 2:
        problems.append("must not contain your e-mail name")
    return problems


def create_token(user_id: int, role: str, token_version: int, settings: Settings | None = None):
    settings = settings or get_settings()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "tv": token_version,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": "connectly-intelligence",
    }
    return jwt.encode(payload, signing_key(settings), algorithm=ALGORITHM), expires


def decode_token(token: str, settings: Settings | None = None) -> dict:
    """Raises jwt.PyJWTError if the token is invalid or expired."""
    return jwt.decode(
        token,
        signing_key(settings),
        algorithms=[ALGORITHM],
        issuer="connectly-intelligence",
        options={"require": ["sub", "exp", "iat", "tv"]},
    )


class RateLimiter:
    """Sliding-window counter per key, in process memory.

    Account lockout (stored in the database) is the main defence; this limits how many
    accounts one address can try. With several server processes each keeps its own count.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float) -> bool:
        """Record an attempt; False if the key is over its limit."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self._hits) > 10_000:  # bound memory under a spray of addresses
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    del self._hits[k]
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_limiter = RateLimiter()
