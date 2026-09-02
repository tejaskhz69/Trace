"""Password hashing and JWT issuance/verification.

Two bugs live here in almost every broken RN-login-in-production story:

1. **bcrypt's 72-byte limit.** bcrypt silently truncates input over 72 bytes.
   Some libraries raise instead. If a user's password + your pepper exceeds it,
   signup succeeds and login fails, or vice versa, depending on library
   version. We pre-hash with SHA-256 so the input to bcrypt is always a fixed
   64-char hex string. Do this from day one -- retrofitting requires a password
   reset for every user.

2. **A rotating JWT_SECRET.** See config.py. If the secret is generated at
   import time, every deploy or container restart invalidates all outstanding
   tokens. On Railway, containers restart on redeploy, on crash, and on plan
   changes -- so users appear to be "randomly logged out" or get a 401 from a
   token the app just received.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt

from .config import get_settings

TokenType = Literal["access", "refresh"]


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def _prehash(password: str) -> bytes:
    """SHA-256 the password to a fixed length before bcrypt.

    Guarantees a 64-byte input regardless of how long the user's password is,
    sidestepping bcrypt's 72-byte truncation entirely.
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    settings = get_settings()
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(_prehash(password), salt).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


# A precomputed hash of a value nobody will ever use as a password. Verifying
# against it costs the same CPU as verifying a real user, which is the point.
_DUMMY_HASH: str | None = None


def dummy_verify() -> None:
    """Burn the same CPU as a real verify when the email doesn't exist.

    Without this, "email not found" returns in ~1 ms while "wrong password"
    returns in ~250 ms, and anyone can enumerate your user base by timing.
    """
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("trace-timing-equalisation-placeholder")
    verify_password("x", _DUMMY_HASH)


# ---------------------------------------------------------------------------
# JWTs
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def create_token(
    user_id: str,
    token_type: TokenType,
    extra: dict[str, Any] | None = None,
) -> tuple[str, datetime]:
    settings = get_settings()
    if token_type == "access":
        expires = _now() + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
    else:
        expires = _now() + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)

    payload: dict[str, Any] = {
        "sub": user_id,
        "type": token_type,
        "iat": int(_now().timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_urlsafe(16),
        **(extra or {}),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expires


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Raises jwt.PyJWTError subclasses on any problem."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["exp", "sub", "type"]},
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(
            f"expected {expected_type} token, got {payload.get('type')}"
        )
    return payload


def hash_refresh_token(token: str) -> str:
    """Store only the hash of a refresh token."""
    settings = get_settings()
    return hmac.new(
        settings.JWT_SECRET.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()
