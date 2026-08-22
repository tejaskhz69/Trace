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

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..config import get_settings
from ..db import get_session
from ..models import PhoneChallenge, RefreshToken, User
from ..services import phone_auth, social_auth
from ..schemas import (
    AuthResponse,
    LoginRequest,
    PhoneStartRequest,
    PhoneVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    SocialSignInRequest,
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

settings = get_settings()

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


# ---------------------------------------------------------------------------
# Sign in with Google / Apple
# ---------------------------------------------------------------------------


@router.get("/providers")
async def providers() -> dict:
    """Which social buttons the client should actually render.

    Showing a provider the server cannot complete is worse than showing none:
    the user taps, a browser opens, they authorise, and then land back in an
    app that has no way to turn that into an account. The client asks first
    and hides what is not configured.
    """
    return {"providers": social_auth.configured_providers()}


@router.post("/social", response_model=AuthResponse)
async def social_sign_in(
    payload: SocialSignInRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthResponse:
    """Turn a verified Google/Apple identity into a Trace session.

    THE TOKEN IS NOT TRUSTED UNTIL IT IS VERIFIED. Anyone can POST this
    endpoint with a string they wrote themselves; `social_auth.verify` checks
    the signature against the provider's published keys AND that the audience
    is one of our own client IDs, which is what stops a valid token issued to
    somebody else's app from logging into a Trace account.

    ACCOUNT LINKING IS BY VERIFIED EMAIL. Signing in with Google on an address
    that already has a password account lands in that same account rather than
    creating a duplicate. This is only safe because the provider asserts the
    address is verified -- linking on an unverified one would let anyone claim
    an existing account by signing up to a provider with its address.
    """
    try:
        identity = social_auth.verify(payload.provider, payload.id_token)
    except social_auth.SocialAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    if not identity.email:
        # Apple only sends the email on the first authorization. A user who
        # revoked and re-authorised gets a token with no email, and we have
        # nothing to key the account on.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "That sign-in did not include an email address. In Settings › "
                "Apple ID › Sign in with Apple, remove Trace and try again."
            ),
        )
    if not identity.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{identity.provider.capitalize()} has not verified that email "
                f"address, so it cannot be used to sign in."
            ),
        )

    email = _normalise_email(identity.email)
    user = await session.scalar(select(User).where(User.email == email))

    if user is None:
        user = User(
            email=email,
            # No password: this account has no password path until the user
            # sets one. A random hash is stored rather than an empty string so
            # a password login attempt fails the bcrypt compare normally
            # instead of hitting a special case.
            password_hash=hash_password(secrets.token_urlsafe(32)),
            display_name=payload.display_name or identity.name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif payload.display_name and not user.display_name:
        # Apple sends the full name exactly once, on the very first
        # authorization, and never again. Capture it if we somehow have it and
        # the account does not.
        user.display_name = payload.display_name
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return await _issue_tokens(session, user, payload.device_label)


# ---------------------------------------------------------------------------
# Phone + one-time code
# ---------------------------------------------------------------------------


@router.post("/phone/start")
async def phone_start(
    payload: PhoneStartRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Send a one-time code. Deliberately says nothing about who exists.

    THE RESPONSE IS IDENTICAL whether or not that number has an account.
    Replying "no account with that number" would turn this into a free tool
    for checking whether a given person uses Trace -- a privacy leak with no
    upside, since the next screen asks for the code either way.

    THE TWO RATE LIMITS BELOW ARE FINANCIAL CONTROLS, NOT POLITENESS. Every
    SMS costs real money, so an unthrottled send endpoint is a way for a
    stranger to spend our balance. "SMS pumping" is an entire fraud category
    built on exactly this endpoint, and it arrives as an invoice.
    """
    try:
        phone = phone_auth.normalise_phone(payload.phone, payload.country_code)
    except phone_auth.PhoneAuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=phone_auth.SEND_WINDOW_MINUTES)
    ip = request.client.host if request.client else None

    sent_to_number = (
        await session.scalar(
            select(func.count(PhoneChallenge.id)).where(
                PhoneChallenge.phone == phone,
                PhoneChallenge.created_at >= window_start,
            )
        )
    ) or 0
    if sent_to_number >= phone_auth.MAX_SENDS_PER_WINDOW:
        raise HTTPException(
            status_code=429,
            detail="Too many codes requested for that number. Try again in an hour.",
        )

    if ip:
        sent_from_ip = (
            await session.scalar(
                select(func.count(PhoneChallenge.id)).where(
                    PhoneChallenge.request_ip == ip,
                    PhoneChallenge.created_at >= window_start,
                )
            )
        ) or 0
        if sent_from_ip >= phone_auth.MAX_SENDS_PER_IP:
            raise HTTPException(
                status_code=429, detail="Too many requests. Try again later."
            )

    # Any earlier live challenge for this number is retired. Two valid codes at
    # once doubles the guessing surface for no benefit, and "which code did I
    # get" is a confusing state for the user as well.
    await session.execute(
        update(PhoneChallenge)
        .where(
            PhoneChallenge.phone == phone,
            PhoneChallenge.consumed_at.is_(None),  # type: ignore[union-attr]
            PhoneChallenge.expires_at > now,
        )
        .values(consumed_at=now)
    )

    challenge = phone_auth.new_challenge(phone)
    session.add(
        PhoneChallenge(
            phone=phone,
            code_hash=challenge.code_hash,
            expires_at=challenge.expires_at,
            request_ip=ip,
        )
    )
    await session.commit()

    delivered = await phone_auth.send_sms(phone, challenge.code)
    if not delivered and settings.is_production:
        raise HTTPException(
            status_code=503,
            detail="We couldn't send the code right now. Try again in a moment.",
        )

    body: dict = {
        "sent": True,
        "phone": phone_auth.mask(phone),
        "expires_in": phone_auth.CODE_TTL_MINUTES * 60,
        "length": phone_auth.CODE_LENGTH,
    }
    if phone_auth.expose_code_in_response():
        # Development only, and only when no SMS provider is configured.
        # See phone_auth.expose_code_in_response for why this cannot leak.
        body["dev_code"] = challenge.code
        body["dev_note"] = "Returned because DEBUG is on and no SMS provider is set."
    elif not phone_auth.sms_configured():
        # NO PROVIDER, AND NO DEV CODE EITHER. Nothing is going to arrive.
        #
        # This endpoint used to return a bare {"sent": true} here, which sent
        # the user to a code screen to wait for an SMS that could not exist --
        # reported, accurately, as "I can't log in with my phone number".
        # Claiming success for a message we never sent is the one thing this
        # response must not do.
        #
        # It stays a 200 rather than a 503 because the challenge WAS created
        # and is genuinely usable: the code is in the server log, which is all
        # a developer needs. `undeliverable` is what the client keys off to
        # explain that rather than spin.
        body["undeliverable"] = True
        body["dev_note"] = (
            "No SMS provider is configured, so no message was sent. The code "
            "is in the server log. Set SMS_PROVIDER (twilio or msg91) to "
            "deliver it, or DEBUG=true to have it returned here."
        )
    return body


@router.post("/phone/verify", response_model=AuthResponse)
async def phone_verify(
    payload: PhoneVerifyRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthResponse:
    """Check the code and hand back a session, creating the account if new.

    SIGN-IN AND SIGN-UP ARE THE SAME ACTION HERE, on purpose. A verified phone
    number IS the account, so asking someone whether they are new is asking
    them to remember something they should not have to.
    """
    try:
        phone = phone_auth.normalise_phone(payload.phone, payload.country_code)
    except phone_auth.PhoneAuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    challenge = (
        await session.execute(
            select(PhoneChallenge)
            .where(
                PhoneChallenge.phone == phone,
                PhoneChallenge.consumed_at.is_(None),  # type: ignore[union-attr]
            )
            .order_by(PhoneChallenge.created_at.desc())  # type: ignore[union-attr]
            .limit(1)
        )
    ).scalars().first()

    # ONE generic message for "no challenge", "expired" and "out of attempts".
    # Distinguishing them tells an attacker which numbers are mid-flow.
    expired = HTTPException(
        status_code=401,
        detail="That code has expired or is no longer valid. Request a new one.",
    )
    if challenge is None or challenge.expires_at <= now:
        raise expired
    if challenge.attempts >= phone_auth.MAX_ATTEMPTS:
        raise expired

    if not phone_auth.verify_code(phone, payload.code.strip(), challenge.code_hash):
        challenge.attempts += 1
        # Burn the challenge on the final failure rather than leaving it alive
        # at the limit, where it would sit absorbing requests.
        if challenge.attempts >= phone_auth.MAX_ATTEMPTS:
            challenge.consumed_at = now
        session.add(challenge)
        await session.commit()
        remaining = max(0, phone_auth.MAX_ATTEMPTS - challenge.attempts)
        raise HTTPException(
            status_code=401,
            detail=(
                f"That code isn't right. {remaining} attempt"
                f"{'' if remaining == 1 else 's'} left."
                if remaining
                else "Too many wrong attempts. Request a new code."
            ),
        )

    # SINGLE USE. Consumed before the session is issued, so a replayed request
    # cannot mint a second session from one code.
    challenge.consumed_at = now
    session.add(challenge)

    user = await session.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(
            # A phone account has no email yet. A deterministic placeholder
            # satisfies the NOT NULL unique constraint without inventing a
            # plausible-looking address somebody else might actually own; the
            # profile screen asks for a real one later.
            email=f"{phone.lstrip('+')}@phone.trace.local",
            password_hash=hash_password(secrets.token_urlsafe(32)),
            phone=phone,
            phone_verified_at=now,
            display_name=payload.display_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif user.phone_verified_at is None:
        user.phone_verified_at = now
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        await session.commit()

    return await _issue_tokens(session, user, payload.device_label)
