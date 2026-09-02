"""Phone + one-time code sign-in.

WHY THIS IS THE PRIMARY LOGIN PATH ON MOBILE
Passwords are a Western convention. In India, people log into Swiggy, Zomato,
HealthifyMe and every bank with a number and a code, and expect to. A phone
number is also a better identity key for this market than an email: it is
stable, it is the thing people actually remember, and it deletes an entire
class of support load -- there is no "forgot password" flow because there is
no password to forget.

THE THREE THINGS THAT MAKE OTP SAFE, AND ALL THREE ARE REQUIRED

  1. THE CODE IS HASHED AT REST. It is a short-lived credential exactly like a
     password. A database leak must not hand someone a list of live codes for
     numbers they can immediately sign in as.

  2. GUESSES ARE BOUNDED. A 6-digit code is one-in-a-million per attempt,
     which is only strong if attempts are few. Unbounded retries reduce it to
     a few thousand requests -- trivial. Five attempts, then the challenge is
     dead and a new code must be sent.

  3. SENDS ARE BOUNDED, PER NUMBER AND PER IP. This is the one people forget,
     and it arrives as an invoice. Every SMS costs real money, so an
     unthrottled send endpoint is a way for a stranger to spend our balance --
     "SMS pumping" is an entire fraud category where the attacker owns a cut
     of the delivery fee. Rate limiting here is a financial control, not a
     politeness.

ENUMERATION
`start_challenge` behaves identically whether or not the number has an
account. Replying "no account with that number" turns this endpoint into a
free tool for checking whether a given person uses Trace.

DEV MODE IS EXPLICIT, NOT IMPLICIT
With no SMS provider configured the code is written to the log and returned in
the response ONLY when DEBUG is on, so the flow is fully testable locally. It
refuses to do that in production -- an accidental deploy without credentials
must fail loudly, not quietly hand every caller a valid code.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

CODE_LENGTH = 6
CODE_TTL_MINUTES = 5

# Guessing budget for one challenge.
MAX_ATTEMPTS = 5

# Sends allowed for one number inside the window. Someone who genuinely did
# not get the SMS needs two or three; anything past that is either a broken
# number or an attack.
MAX_SENDS_PER_WINDOW = 5
SEND_WINDOW_MINUTES = 60

# Per-IP ceiling over the same window, which is what actually stops a script
# cycling through numbers. One phone is cheap to rotate; addresses less so.
MAX_SENDS_PER_IP = 20

# The longest a NATIONAL (country-code-less) number gets anywhere. Used to
# tell "919876543210" — a full Indian number typed without the plus — from
# "9198765432", a national number that merely starts with the same digits.
MAX_NATIONAL_DIGITS = 10


class PhoneAuthError(Exception):
    """Message is safe to show a user."""


@dataclass
class Challenge:
    phone: str
    code: str
    code_hash: str
    expires_at: datetime


def normalise_phone(raw: str, default_country: str | None = None) -> str:
    """Put a number into E.164, or refuse it.

    Stored one way and one way only. "+919876543210", "09876543210" and
    "98765 43210" are the same person, and storing them as three different
    strings would create three accounts and make the unique constraint
    useless.
    """
    if not raw:
        raise PhoneAuthError("Enter a mobile number.")

    cleaned = re.sub(r"[^\d+]", "", raw.strip())
    cc = (default_country or settings.DEFAULT_PHONE_COUNTRY_CODE or "").strip()

    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]

    if not cleaned.startswith("+"):
        # Drop a leading trunk zero first. "09876543210" in India is
        # "+919876543210", NOT "+9109876543210" -- keeping the zero is the
        # classic bug in this function.
        cleaned = cleaned.lstrip("0")
        if not cc:
            raise PhoneAuthError(
                "Include your country code, for example +91 98765 43210."
            )
        cc_digits = cc.lstrip("+")
        # People routinely type the country code without the plus:
        # "919876543210". Blindly prefixing turns that into
        # "+91919876543210" and creates a second account for the same person.
        #
        # The test is LENGTH, not just the prefix, because a real Indian
        # mobile can itself begin with 91 ("9198765432"). No national number
        # exceeds MAX_NATIONAL_DIGITS, so anything longer that starts with the
        # country code must already carry it.
        if not (
            cleaned.startswith(cc_digits) and len(cleaned) > MAX_NATIONAL_DIGITS
        ):
            cleaned = f"{cc_digits}{cleaned}"
        cleaned = "+" + cleaned

    digits = cleaned[1:]
    if not digits.isdigit():
        raise PhoneAuthError("That doesn't look like a mobile number.")
    # E.164 permits at most 15 digits including the country code; below ~8 it
    # cannot be a real mobile number anywhere.
    if not (8 <= len(digits) <= 15):
        raise PhoneAuthError("That doesn't look like a mobile number.")

    return "+" + digits


def generate_code() -> str:
    """A cryptographically random code.

    `secrets`, never `random`. The latter is a Mersenne Twister seeded from
    the clock: observing a handful of codes lets an attacker predict the rest,
    which turns a one-in-a-million guess into a certainty.
    """
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


def hash_code(phone: str, code: str) -> str:
    """Salted with the phone number and the server secret.

    The phone number in the digest means one stolen hash cannot be replayed
    against a different number, and JWT_SECRET means an attacker with only the
    database still cannot build a rainbow table for a six-digit space -- which
    is otherwise a million entries and takes seconds.
    """
    msg = f"{phone}:{code}".encode()
    return hmac.new(settings.JWT_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def verify_code(phone: str, code: str, code_hash: str) -> bool:
    """Constant-time compare, so timing cannot leak the code."""
    return hmac.compare_digest(hash_code(phone, code), code_hash)


def new_challenge(phone: str) -> Challenge:
    code = generate_code()
    return Challenge(
        phone=phone,
        code=code,
        code_hash=hash_code(phone, code),
        expires_at=datetime.now(UTC) + timedelta(minutes=CODE_TTL_MINUTES),
    )


def sms_configured() -> bool:
    return bool(
        settings.SMS_PROVIDER
        and (
            (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN)
            or settings.MSG91_AUTH_KEY
        )
    )


def message_for(code: str) -> str:
    # The app name must be in the body: iOS and Android autofill the code from
    # the notification, and both match on the sender/app string. Without it the
    # user has to leave the app to read the SMS, which is where people drop.
    return (
        f"{code} is your Trace verification code. "
        f"It expires in {CODE_TTL_MINUTES} minutes. Never share it."
    )


async def send_sms(phone: str, code: str) -> bool:
    """Deliver the code. Returns False on failure rather than raising.

    A delivery failure must not tell the caller whether the number exists, so
    the router reports success either way and the user retries.
    """
    body = message_for(code)
    provider = (settings.SMS_PROVIDER or "").lower()

    if not sms_configured():
        if settings.is_production:
            # Refuse loudly. Silently "succeeding" in production would leave
            # every user stuck on the code screen with no code coming.
            log.error("No SMS provider configured; phone sign-in cannot work.")
            return False
        log.warning("[DEV] SMS not configured. Code for %s is %s", phone, code)
        return True

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == "twilio":
                r = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/"
                    f"{settings.TWILIO_ACCOUNT_SID}/Messages.json",
                    auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                    data={
                        "To": phone,
                        "From": settings.TWILIO_FROM_NUMBER,
                        "Body": body,
                    },
                )
            elif provider == "msg91":
                # MSG91 is materially cheaper for Indian numbers than Twilio,
                # which is why it is worth supporting a second provider at all.
                r = await client.post(
                    "https://control.msg91.com/api/v5/flow/",
                    headers={"authkey": settings.MSG91_AUTH_KEY or ""},
                    json={
                        "template_id": settings.MSG91_TEMPLATE_ID,
                        "short_url": "0",
                        "recipients": [
                            {"mobiles": phone.lstrip("+"), "otp": code}
                        ],
                    },
                )
            else:
                log.error("Unknown SMS_PROVIDER %r", provider)
                return False

            if r.status_code >= 400:
                # Never log the code or the full number alongside an error.
                log.error(
                    "SMS send failed (%s) for %s: %s",
                    r.status_code,
                    mask(phone),
                    r.text[:200],
                )
                return False
            return True
    except httpx.HTTPError as exc:
        log.error("SMS send errored for %s: %s", mask(phone), exc)
        return False


def mask(phone: str) -> str:
    """Last four digits only. Enough to confirm the right number on screen,
    and safe to write to a log."""
    return f"••••{phone[-4:]}" if len(phone) >= 4 else "••••"


def expose_code_in_response() -> bool:
    """Whether to hand the code back in the API response.

    Dev convenience ONLY, and gated on both DEBUG and the absence of a real
    provider. Returning a live code to any caller in production would make the
    whole flow decorative.
    """
    return settings.DEBUG and not settings.is_production and not sms_configured()
