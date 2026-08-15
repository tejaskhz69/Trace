"""Authentication endpoints.

Contract notes that matter for the mobile client:

* Email is **normalised to lowercase and stripped** on both register and login.
  If you skip this, a user who signs up as "Tejas@Gmail.com" on iOS (where the
  keyboard auto-capitalises the first letter) cannot log in as "tejas@gmail.com".
  This is, by a wide margin, the most common "my login just doesn't work"
  bug in React Native apps -- set `autoCapitalize="none"` on the input too.

* Login accepts **JSON** (`{"email": ..., "password": ...}`), not OAuth2
  form-encoded. FastAPI tutorials use `OAuth2PasswordRequestForm`, which
  expects `application/x-www-form-urlencoded` with a field named `username`.
  If your RN client posts JSON to that endpoint you get a 422 that looks like
  a validation error about a missing `username` field. Both are supported here
  so neither client shape breaks.

* Errors are always `{"detail": "..."}` with a stable `code` so the client can
  branch without string-matching.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import RefreshToken, User
from ..schemas import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    UserPublic,
)
from ..security import (
    create_token,
    dummy_verify,
    hash_password,
    hash_refresh_token,
    decode_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# auto_error=False so current_user can raise our own {"detail": ...} shape
# instead of FastAPI's default 403 "Not authenticated".
bearer_scheme = HTTPBearer(auto_error=False)


def _normalise_email(email: str) -> str:
    return email.strip().lower()


async def _issue_tokens(
    session: AsyncSession, user: User, device_label: str | None = None
) -> AuthResponse:
    access, access_exp = create_token(user.id, "access")
    refresh, refresh_exp = create_token(user.id, "refresh")

    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh),
            expires_at=refresh_exp,
            device_label=device_label,
        )
    )
    await session.commit()

    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=int((access_exp - datetime.now(timezone.utc)).total_seconds()),
        user=UserPublic.model_validate(user, from_attributes=True),
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthResponse:
    email = _normalise_email(payload.email)

    existing = await session.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        sex=payload.sex,
        height_cm=payload.height_cm,
        starting_weight_kg=payload.weight_kg,
        goal_weight_kg=payload.goal_weight_kg,
        goal_type=payload.goal_type,
        lifting_experience_months=payload.lifting_experience_months or 0,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return await _issue_tokens(session, user, payload.device_label)


@router.post("/login", response_model=AuthResponse)
async def login(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthResponse:
    """Accepts JSON or form-encoded bodies, and `email` or `username`."""
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        body = await request.json()
    else:
        form = await request.form()
        body = dict(form)

    raw_email = body.get("email") or body.get("username")
    password = body.get("password")

    if not raw_email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password are required.",
        )

    email = _normalise_email(str(raw_email))
    user = await session.scalar(select(User).where(User.email == email))

    if user is None:
        dummy_verify()  # constant-time-ish: don't leak which emails exist
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    if not verify_password(str(password), user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    return await _issue_tokens(session, user, body.get("device_label"))


@router.post("/refresh", response_model=AuthResponse)
async def refresh_tokens(
    payload: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthResponse:
    try:
        claims = decode_token(payload.refresh_token, "refresh")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid refresh token: {exc}")

    token_hash = hash_refresh_token(payload.refresh_token)
    stored = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if stored is None or stored.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Refresh token revoked.")

    # Rotate: a refresh token is single-use.
    stored.revoked_at = datetime.now(timezone.utc)
    session.add(stored)

    user = await session.get(User, claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists.")

    return await _issue_tokens(session, user, stored.device_label)


@router.post("/logout", status_code=204)
async def logout(
    session: Annotated[AsyncSession, Depends(get_session)],
    refresh_token: Annotated[str, Body(embed=True)],
) -> None:
    stored = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(refresh_token)
        )
    )
    if stored and stored.revoked_at is None:
        stored.revoked_at = datetime.now(timezone.utc)
        session.add(stored)
        await session.commit()


# ---------------------------------------------------------------------------
# Dependency used by every protected route
# ---------------------------------------------------------------------------


async def current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> User:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing Authorization header.")

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401, detail="Authorization must be 'Bearer <token>'."
        )

    token = credentials.credentials

    try:
        claims = decode_token(token, "access")
    except jwt.ExpiredSignatureError:
        # A distinct code so the client knows to call /refresh rather than
        # dumping the user back to the login screen.
        raise HTTPException(status_code=401, detail="token_expired")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    user = await session.get(User, claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists.")
    return user


@router.get("/me", response_model=UserPublic)
async def me(user: Annotated[User, Depends(current_user)]) -> UserPublic:
    return UserPublic.model_validate(user, from_attributes=True)
