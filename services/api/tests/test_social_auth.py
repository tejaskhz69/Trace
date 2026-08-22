"""Spec for Google/Apple sign-in.

These are security tests, not feature tests. Every one of them corresponds to
a way an attacker signs in as somebody else if the check is missing.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services import social_auth
from app.services.social_auth import SocialAuthError

# A throwaway key pair standing in for the provider's signing key.
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUB = _KEY.public_key()

OUR_CLIENT = "111.apps.googleusercontent.com"
OTHER_CLIENT = "999.apps.googleusercontent.com"


def _token(**over) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": OUR_CLIENT,
        "sub": "google-user-1",
        "email": "lifter@example.com",
        "email_verified": True,
        "name": "Test Lifter",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(over)
    return jwt.encode(claims, _KEY, algorithm="RS256")


@pytest.fixture(autouse=True)
def _stub_provider(monkeypatch):
    """Serve our test public key instead of fetching Google's JWKS."""

    class _Key:
        key = _PUB

    class _Client:
        def get_signing_key_from_jwt(self, token):
            return _Key()

    monkeypatch.setattr(social_auth, "_jwk_client", lambda url: _Client())
    monkeypatch.setattr(social_auth, "google_audiences", lambda: [OUR_CLIENT])
    monkeypatch.setattr(social_auth, "apple_audiences", lambda: [OUR_CLIENT])


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_a_properly_signed_token_yields_an_identity():
    ident = social_auth.verify_google(_token())
    assert ident.provider == "google"
    assert ident.email == "lifter@example.com"
    assert ident.email_verified is True
    assert ident.subject == "google-user-1"


def test_the_email_is_lowercased_for_account_matching():
    """iOS auto-capitalises. A provider echoing 'Lifter@Example.com' must not
    create a second account beside the password one."""
    ident = social_auth.verify_google(_token(email="Lifter@Example.COM"))
    assert ident.email == "lifter@example.com"


def test_google_string_true_counts_as_verified():
    """Google sends email_verified as a bool OR the string 'true' depending on
    the flow. Treating the string as falsy rejects every real login."""
    assert social_auth.verify_google(_token(email_verified="true")).email_verified


# ---------------------------------------------------------------------------
# The attacks
# ---------------------------------------------------------------------------


def test_a_token_signed_with_the_wrong_key_is_rejected():
    """Without the signature check the token is just base64 the attacker
    chose, and 'sign in as anyone@gmail.com' is a one-liner."""
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    forged = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": OUR_CLIENT,
            "sub": "x",
            "email": "victim@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
        },
        attacker,
        algorithm="RS256",
    )
    with pytest.raises(SocialAuthError):
        social_auth.verify_google(forged)


def test_a_token_issued_for_a_different_app_is_rejected():
    """THE CHECK PEOPLE FORGET. A Google token minted for someone else's app
    is perfectly signed; accepting it lets any other developer log into Trace
    accounts."""
    with pytest.raises(SocialAuthError, match="different app"):
        social_auth.verify_google(_token(aud=OTHER_CLIENT))


def test_an_expired_token_is_rejected():
    now = int(time.time())
    with pytest.raises(SocialAuthError, match="expired"):
        social_auth.verify_google(_token(iat=now - 7200, exp=now - 3600))


def test_a_token_from_the_wrong_issuer_is_rejected():
    with pytest.raises(SocialAuthError):
        social_auth.verify_google(_token(iss="https://evil.example.com"))


def test_an_unsigned_none_algorithm_token_is_rejected():
    """The classic JWT attack: alg=none with the signature stripped."""
    forged = jwt.encode({"sub": "x", "aud": OUR_CLIENT}, key="", algorithm="none")
    with pytest.raises(SocialAuthError):
        social_auth.verify_google(forged)


def test_garbage_is_rejected_rather_than_crashing():
    with pytest.raises(SocialAuthError):
        social_auth.verify_google("not-a-jwt-at-all")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_an_unconfigured_provider_refuses_rather_than_accepting_anything(
    monkeypatch,
):
    """With no client IDs there is no audience to check against. Verifying
    'successfully' in that state would accept every token on earth."""
    monkeypatch.setattr(social_auth, "google_audiences", lambda: [])
    with pytest.raises(SocialAuthError, match="not configured"):
        social_auth.verify_google(_token())


def test_any_of_the_platform_client_ids_is_accepted(monkeypatch):
    """A native Google app has a different client ID per platform, and the
    token carries whichever requested it. Only accepting the web ID is why
    'it works in the simulator but not on my phone'."""
    monkeypatch.setattr(
        social_auth, "google_audiences", lambda: [OTHER_CLIENT, OUR_CLIENT]
    )
    assert social_auth.verify_google(_token(aud=OUR_CLIENT)).subject == "google-user-1"


def test_an_unknown_provider_is_refused():
    with pytest.raises(SocialAuthError, match="not supported"):
        social_auth.verify("facebook", _token())


def test_configured_providers_lists_only_what_can_actually_complete(monkeypatch):
    monkeypatch.setattr(social_auth, "google_audiences", lambda: [OUR_CLIENT])
    monkeypatch.setattr(social_auth, "apple_audiences", lambda: [])
    assert social_auth.configured_providers() == ["google"]


# ---------------------------------------------------------------------------
# Apple's quirks
# ---------------------------------------------------------------------------


def _apple_token(**over) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://appleid.apple.com",
        "aud": OUR_CLIENT,
        "sub": "apple-user-1",
        "email": "abc123@privaterelay.appleid.com",
        "email_verified": "true",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(over)
    return jwt.encode(claims, _KEY, algorithm="RS256")


def test_apple_private_relay_is_a_valid_address_not_a_broken_one():
    """It is stable per app and mail reaches the user, so it is a perfectly
    good account key. Rejecting it locks out everyone who chose Hide My Email.
    """
    ident = social_auth.verify_apple(_apple_token())
    assert ident.email.endswith("@privaterelay.appleid.com")
    assert ident.email_verified is True


def test_apple_tokens_never_carry_a_name():
    """Apple sends it once, in the client credential, never in the token --
    which is why display_name travels as its own request field."""
    assert social_auth.verify_apple(_apple_token()).name is None
