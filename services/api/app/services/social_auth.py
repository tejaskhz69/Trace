"""Verify a Google or Apple identity token, so it can become a Trace session.

WHAT THIS IS ACTUALLY DOING, AND WHY IT MATTERS
The phone hands us a string it says came from Google. We must not believe it.
Anyone can POST this endpoint with a token they wrote themselves, and if we
decode it without checking the signature, "sign in as anyone@gmail.com"
becomes a one-line attack. So every token is verified against the provider's
own published public keys before a single field inside it is trusted.

THREE CHECKS, ALL REQUIRED, AND SKIPPING ANY ONE IS A REAL VULNERABILITY

  signature   proves the provider minted it. Without this the token is just
              base64 the attacker chose.
  audience    proves it was minted FOR US. A valid Google token issued to a
              different app is still perfectly signed -- accepting it lets
              any other developer's app log into Trace accounts. This is the
              check people most often forget.
  issuer/exp  proves it is current and from the right provider.

`jwt.decode(..., options={"verify_signature": False})` appears nowhere in this
file, and should never be added to it.

WHY WE VERIFY LOCALLY RATHER THAN CALLING A TOKENINFO ENDPOINT
Google offers an endpoint that validates a token for you. It also adds a
network round trip to every login, rate-limits, and goes down. The public keys
change a few times a year and are cacheable, so local verification is faster
and has fewer moving parts.

EMAIL IS THE LINKING KEY, AND ONLY WHEN THE PROVIDER SAYS IT IS VERIFIED
Signing in with Google when a password account already exists on that address
should land in the same account, not a duplicate. That is only safe because
Google asserts the address is verified -- linking on an UNVERIFIED email would
let someone claim an account by signing up to a provider with that address.

APPLE'S PRIVATE RELAY IS A REAL ADDRESS, NOT A BROKEN ONE
Apple users can hide behind `...@privaterelay.appleid.com`. It is stable per
app and mail delivered to it reaches them, so it is a perfectly good account
key. Do not reject it.

APPLE SENDS THE NAME EXACTLY ONCE
The full name arrives only on the very first authorization, in the client's
credential object -- never in the token, and never again. If it is not
captured then, it is gone for good, which is why `display_name` travels as a
separate field on the request rather than being read out of the token.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

from ..config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

APPLE_JWKS = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"

# Providers rotate signing keys a few times a year, so caching is safe and
# saves a round trip on every single login. PyJWKClient handles the cache and
# refetches when it sees an unknown `kid`.
_JWK_CLIENTS: dict[str, PyJWKClient] = {}

# Tolerance for clock skew between the phone, the provider and this server.
LEEWAY_S = 30


class SocialAuthError(Exception):
    """Verification failed. The message is safe to show a user."""


@dataclass
class SocialIdentity:
    provider: str
    subject: str           # the provider's stable user id
    email: str | None
    email_verified: bool
    name: str | None
    picture: str | None


def _jwk_client(url: str) -> PyJWKClient:
    client = _JWK_CLIENTS.get(url)
    if client is None:
        client = PyJWKClient(url, cache_keys=True, lifespan=3600)
        _JWK_CLIENTS[url] = client
    return client


def google_audiences() -> list[str]:
    """Every client ID that may legitimately appear in `aud`.

    A native app has a DIFFERENT client ID per platform, and the token carries
    whichever one requested it. Accepting only the web ID is why "Google
    sign-in works in the simulator but not on my phone".
    """
    return [
        c
        for c in (
            settings.GOOGLE_CLIENT_ID_IOS,
            settings.GOOGLE_CLIENT_ID_ANDROID,
            settings.GOOGLE_CLIENT_ID_WEB,
            settings.GOOGLE_CLIENT_ID_EXPO,
        )
        if c
    ]


def apple_audiences() -> list[str]:
    return [c for c in (settings.APPLE_CLIENT_ID, settings.APPLE_BUNDLE_ID) if c]


def _verify(token: str, *, jwks_url: str, issuer: str | set[str], audiences: list[str]) -> dict[str, Any]:
    if not audiences:
        raise SocialAuthError(
            "This sign-in method is not configured on the server yet."
        )
    try:
        key = _jwk_client(jwks_url).get_signing_key_from_jwt(token).key
    except Exception as exc:  # network, malformed token, unknown kid
        log.warning("JWKS lookup failed for %s: %s", jwks_url, exc)
        raise SocialAuthError("Could not verify that sign-in. Try again.") from exc

    last: Exception | None = None
    # PyJWT takes a single audience, and the token carries exactly one. Trying
    # each configured client ID is how one endpoint serves iOS, Android and web
    # without the client having to tell us which it is.
    for aud in audiences:
        try:
            return jwt.decode(
                token,
                key=key,
                algorithms=["RS256", "ES256"],
                audience=aud,
                issuer=issuer if isinstance(issuer, str) else None,
                leeway=LEEWAY_S,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.InvalidAudienceError as exc:
            last = exc
            continue
        except jwt.ExpiredSignatureError as exc:
            raise SocialAuthError("That sign-in expired. Try again.") from exc
        except jwt.InvalidTokenError as exc:
            raise SocialAuthError("That sign-in could not be verified.") from exc

    log.warning("Token audience matched none of %s configured client IDs", len(audiences))
    raise SocialAuthError("That sign-in was issued for a different app.") from last


def verify_google(id_token: str) -> SocialIdentity:
    claims = _verify(
        id_token,
        jwks_url=GOOGLE_JWKS,
        issuer=set(GOOGLE_ISSUERS),  # type: ignore[arg-type]
        audiences=google_audiences(),
    )
    # PyJWT cannot check a set of issuers, so this one is checked by hand.
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise SocialAuthError("That sign-in did not come from Google.")

    return SocialIdentity(
        provider="google",
        subject=str(claims["sub"]),
        email=(claims.get("email") or "").strip().lower() or None,
        # Google sends this as a bool OR the string "true" depending on the
        # flow. Treating the string as falsy would reject every real login.
        email_verified=str(claims.get("email_verified", "")).lower() in ("true", "1"),
        name=claims.get("name"),
        picture=claims.get("picture"),
    )


def verify_apple(id_token: str) -> SocialIdentity:
    claims = _verify(
        id_token,
        jwks_url=APPLE_JWKS,
        issuer=APPLE_ISSUER,
        audiences=apple_audiences(),
    )
    return SocialIdentity(
        provider="apple",
        subject=str(claims["sub"]),
        email=(claims.get("email") or "").strip().lower() or None,
        email_verified=str(claims.get("email_verified", "")).lower() in ("true", "1"),
        # Never in the token. The client sends it separately, first time only.
        name=None,
        picture=None,
    )


def verify(provider: str, id_token: str) -> SocialIdentity:
    p = (provider or "").strip().lower()
    if p == "google":
        return verify_google(id_token)
    if p == "apple":
        return verify_apple(id_token)
    raise SocialAuthError(f"{provider} sign-in is not supported.")


def configured_providers() -> list[str]:
    """Which buttons the client should actually offer.

    Showing a provider we cannot complete is worse than not showing it: the
    user taps, a browser opens, and they end up somewhere with no way back
    into the app.
    """
    out = []
    if google_audiences():
        out.append("google")
    if apple_audiences():
        out.append("apple")
    return out
