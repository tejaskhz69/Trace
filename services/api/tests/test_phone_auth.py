"""Spec for phone + one-time code sign-in.

Almost every test here is a security test. An OTP endpoint is an abuse target
in two distinct ways -- someone guessing a code, and someone spending our SMS
balance -- and each assertion below pins one of the guards against those.
"""

from __future__ import annotations

import pytest
from sqlmodel import select

from app.models import PhoneChallenge, User
from app.services import phone_auth
from app.services.phone_auth import (
    MAX_ATTEMPTS,
    MAX_SENDS_PER_WINDOW,
    PhoneAuthError,
    hash_code,
    normalise_phone,
    verify_code,
)

PHONE = "+919876543210"


@pytest.fixture(autouse=True)
def _dev_mode(monkeypatch):
    """Put the service in its development posture.

    `dev_code` is only returned when DEBUG is on AND no SMS provider is set --
    that combination is the real behaviour under test, so it is arranged here
    rather than depending on whatever happens to be in .env.
    """
    monkeypatch.setattr(phone_auth.settings, "DEBUG", True)
    monkeypatch.setattr(phone_auth.settings, "ENV", "development")
    monkeypatch.setattr(phone_auth, "sms_configured", lambda: False)


async def _start(client, phone=PHONE) -> str:
    """Request a code and return it (dev mode hands it back)."""
    res = await client.post("/api/auth/phone/start", json={"phone": phone})
    assert res.status_code == 200, res.text
    body = res.json()
    assert "dev_code" in body, "DEBUG dev_code missing — is DEBUG off in .env?"
    return body["dev_code"]


# ---------------------------------------------------------------------------
# Normalisation — one number, one identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["+919876543210", "+91 98765 43210", "09876543210", "9876543210", "919876543210"],
)
def test_every_way_of_writing_a_number_normalises_to_one_identity(raw):
    """Storing these as different strings would create several accounts for
    one person and make the unique constraint useless."""
    assert normalise_phone(raw, "+91") == PHONE


def test_a_leading_trunk_zero_is_dropped_not_kept():
    """The classic bug: '09876543210' becoming '+9109876543210'."""
    assert normalise_phone("09876543210", "+91") == PHONE


def test_a_number_with_no_country_code_and_no_default_is_refused(monkeypatch):
    """With no default configured there is nothing to prefix, and guessing a
    country would silently create an account for a number in another one."""
    monkeypatch.setattr(phone_auth.settings, "DEFAULT_PHONE_COUNTRY_CODE", "")
    with pytest.raises(PhoneAuthError, match="country code"):
        normalise_phone("9876543210", "")


@pytest.mark.parametrize("bad", ["", "123", "+1", "abcdefghij", "+" + "9" * 20])
def test_nonsense_is_refused(bad):
    with pytest.raises(PhoneAuthError):
        normalise_phone(bad, "+91")


# ---------------------------------------------------------------------------
# The code itself
# ---------------------------------------------------------------------------


def test_codes_are_cryptographically_random():
    """`random` is a Mersenne Twister seeded from the clock -- observing a few
    codes lets an attacker predict the rest. 200 draws should not collide much.
    """
    codes = {phone_auth.generate_code() for _ in range(200)}
    assert len(codes) > 190


def test_the_hash_is_bound_to_the_phone_number():
    """One stolen hash must not be replayable against a different number."""
    assert hash_code("+911111111111", "123456") != hash_code("+912222222222", "123456")


def test_verification_accepts_the_right_code_and_rejects_others():
    h = hash_code(PHONE, "123456")
    assert verify_code(PHONE, "123456", h) is True
    assert verify_code(PHONE, "123457", h) is False


def test_the_stored_value_is_not_the_code():
    """A database leak must not hand over a list of live codes."""
    assert "123456" not in hash_code(PHONE, "123456")


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


async def test_a_correct_code_creates_an_account_and_returns_a_session(client):
    code = await _start(client)
    res = await client.post(
        "/api/auth/phone/verify", json={"phone": PHONE, "code": code}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["access_token"]
    assert body["refresh_token"]


async def test_signing_in_twice_reuses_the_same_account(client, db_session):
    """Sign-in and sign-up are the same action; a second code must not create
    a duplicate user."""
    for _ in range(2):
        code = await _start(client)
        res = await client.post(
            "/api/auth/phone/verify", json={"phone": PHONE, "code": code}
        )
        assert res.status_code == 200, res.text

    users = (
        await db_session.execute(select(User).where(User.phone == PHONE))
    ).scalars().all()
    assert len(users) == 1


async def test_the_response_never_echoes_the_full_number(client):
    """Masked on screen so a shoulder-surfer learns nothing, and so logs and
    screenshots stay safe."""
    res = await client.post("/api/auth/phone/start", json={"phone": PHONE})
    assert res.json()["phone"] == "••••3210"


# ---------------------------------------------------------------------------
# Guessing
# ---------------------------------------------------------------------------


async def test_a_wrong_code_is_rejected(client):
    await _start(client)
    res = await client.post(
        "/api/auth/phone/verify", json={"phone": PHONE, "code": "000000"}
    )
    assert res.status_code == 401


async def test_guesses_are_bounded(client):
    """A 6-digit code is one-in-a-million per try -- strong only if the number
    of tries is small. Unbounded retries reduce it to a few thousand
    requests."""
    real = await _start(client)
    wrong = "000000" if real != "000000" else "111111"

    for _ in range(MAX_ATTEMPTS):
        await client.post(
            "/api/auth/phone/verify", json={"phone": PHONE, "code": wrong}
        )

    # Even the CORRECT code must now fail: the challenge is burnt.
    res = await client.post(
        "/api/auth/phone/verify", json={"phone": PHONE, "code": real}
    )
    assert res.status_code == 401


async def test_a_code_cannot_be_used_twice(client):
    """Otherwise a replayed request mints a second session from one code."""
    code = await _start(client)
    first = await client.post(
        "/api/auth/phone/verify", json={"phone": PHONE, "code": code}
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/auth/phone/verify", json={"phone": PHONE, "code": code}
    )
    assert second.status_code == 401


async def test_requesting_a_new_code_retires_the_old_one(client):
    """Two live codes at once doubles the guessing surface for no benefit."""
    first = await _start(client)
    second = await _start(client)
    assert first != second

    stale = await client.post(
        "/api/auth/phone/verify", json={"phone": PHONE, "code": first}
    )
    assert stale.status_code == 401

    fresh = await client.post(
        "/api/auth/phone/verify", json={"phone": PHONE, "code": second}
    )
    assert fresh.status_code == 200


async def test_an_expired_code_is_rejected(client, db_session):
    from datetime import datetime, timedelta, timezone

    code = await _start(client)
    challenge = (
        await db_session.execute(select(PhoneChallenge).where(PhoneChallenge.phone == PHONE))
    ).scalars().first()
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.add(challenge)
    await db_session.commit()

    res = await client.post(
        "/api/auth/phone/verify", json={"phone": PHONE, "code": code}
    )
    assert res.status_code == 401


async def test_verifying_with_no_challenge_at_all_fails_generically(client):
    """"No challenge", "expired" and "out of attempts" share one message --
    distinguishing them tells an attacker which numbers are mid-flow."""
    res = await client.post(
        "/api/auth/phone/verify", json={"phone": "+919999999999", "code": "123456"}
    )
    assert res.status_code == 401
    assert "expired or is no longer valid" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Spending our money
# ---------------------------------------------------------------------------


async def test_sends_to_one_number_are_capped(client):
    """SMS pumping: every send costs real money, so an unthrottled resend is a
    way for a stranger to spend our balance. This guard is a financial
    control, not politeness."""
    for _ in range(MAX_SENDS_PER_WINDOW):
        res = await client.post("/api/auth/phone/start", json={"phone": PHONE})
        assert res.status_code == 200

    blocked = await client.post("/api/auth/phone/start", json={"phone": PHONE})
    assert blocked.status_code == 429


async def test_the_rate_limit_message_does_not_reveal_whether_the_user_exists(
    client,
):
    for _ in range(MAX_SENDS_PER_WINDOW):
        await client.post("/api/auth/phone/start", json={"phone": PHONE})
    blocked = await client.post("/api/auth/phone/start", json={"phone": PHONE})
    detail = blocked.json()["detail"].lower()
    assert "account" not in detail
    assert "registered" not in detail


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------


async def test_start_looks_identical_for_known_and_unknown_numbers(client):
    """Otherwise this endpoint becomes a free tool for checking whether a
    given person uses Trace."""
    known = "+919876543210"
    code = await _start(client, known)
    await client.post("/api/auth/phone/verify", json={"phone": known, "code": code})

    a = await client.post("/api/auth/phone/start", json={"phone": known})
    b = await client.post("/api/auth/phone/start", json={"phone": "+919812345678"})

    assert a.status_code == b.status_code == 200
    assert set(a.json()) - {"dev_code"} == set(b.json()) - {"dev_code"}


# ---------------------------------------------------------------------------
# Production safety
# ---------------------------------------------------------------------------


def test_the_dev_code_is_never_exposed_in_production(monkeypatch):
    """Returning a live code to any caller would make the whole flow
    decorative."""
    monkeypatch.setattr(phone_auth.settings, "DEBUG", True)
    monkeypatch.setattr(phone_auth.settings, "ENV", "production")
    assert phone_auth.expose_code_in_response() is False


def test_the_dev_code_is_not_exposed_once_a_provider_is_configured(monkeypatch):
    monkeypatch.setattr(phone_auth.settings, "DEBUG", True)
    monkeypatch.setattr(phone_auth.settings, "ENV", "development")
    monkeypatch.setattr(phone_auth, "sms_configured", lambda: True)
    assert phone_auth.expose_code_in_response() is False


def test_the_sms_body_names_the_app_so_the_phone_can_autofill():
    """iOS and Android autofill the code from the notification by matching the
    app string. Without it the user must leave the app to read the SMS, which
    is exactly where people drop out."""
    body = phone_auth.message_for("123456")
    assert "123456" in body
    assert "Trace" in body


def test_a_national_number_that_starts_with_the_country_code_is_not_mangled():
    """"9198765432" is a 10-digit national number that happens to begin "91".
    Treating those two digits as the country code would drop them and produce
    a different person's number. Length is what disambiguates."""
    assert normalise_phone("9198765432", "+91") == "+919198765432"


def test_a_full_number_typed_without_the_plus_is_not_double_prefixed():
    """People routinely type "919876543210". Blindly prefixing gives
    "+91919876543210" and creates a second account for the same person."""
    assert normalise_phone("919876543210", "+91") == "+919876543210"
