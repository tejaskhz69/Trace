"""Application configuration.

Every setting here can be overridden by an environment variable of the same
name (case-insensitive). On Railway, set these in the service's Variables tab.

CRITICAL for Railway deploys:
  - DATABASE_URL is injected by Railway when you attach a Postgres plugin, but
    it arrives as `postgresql://`. SQLAlchemy's async engine needs
    `postgresql+asyncpg://`. We normalise it below -- forgetting this is the
    single most common cause of "the API boots locally but 500s on Railway".
  - JWT_SECRET **must** be set explicitly. If you let it default to a random
    value, every container restart (and Railway restarts often) invalidates
    every token that was ever issued, and users get silently logged out or see
    "401 Invalid token" on a password they typed correctly. This is the #1
    cause of "login works locally but not in production".
"""

from __future__ import annotations

import secrets
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Core -------------------------------------------------------------
    ENV: str = "development"
    DEBUG: bool = False

    # SQL echo is SEPARATE from DEBUG on purpose.
    #
    # They used to be the same switch, so turning DEBUG on to make phone
    # sign-in return its code locally also turned on a log line for every
    # statement the app runs -- which during a bulk import is millions of
    # lines and gigabytes of disk. DEBUG means "this is a dev machine";
    # echoing SQL is a much narrower thing to want, so it gets its own flag.
    SQL_ECHO: bool = False

    # Railway sets PORT. Bind to it, and bind to 0.0.0.0 -- binding to
    # 127.0.0.1 makes the container unreachable from Railway's proxy and
    # produces an endless "Application failed to respond" page.
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # --- Database ---------------------------------------------------------
    DATABASE_URL: str = "postgresql+asyncpg://trace:trace@localhost:5432/trace"
    DB_SSL: bool | None = None

    # --- Auth -------------------------------------------------------------
    JWT_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_MINUTES: int = 30
    REFRESH_TOKEN_TTL_DAYS: int = 60
    BCRYPT_ROUNDS: int = 12

    # --- CORS -------------------------------------------------------------
    # Native apps do not send Origin headers, so CORS is NOT what breaks a
    # React Native login (see docs/04). It only matters for Expo Web.
    CORS_ORIGINS: list[str] = ["http://localhost:8081", "http://localhost:19006"]

    # --- External data sources -------------------------------------------
    OFF_BASE_URL: str = "https://world.openfoodfacts.org"
    OFF_USER_AGENT: str = "Trace/0.1 (contact@traceapp.example)"
    USDA_FDC_API_KEY: str | None = None
    USDA_BASE_URL: str = "https://api.nal.usda.gov/fdc/v1"

    # --- Gemini -----------------------------------------------------------
    # Get a key at https://aistudio.google.com/apikey.
    #
    # MODELS ARE CHOSEN FOR FREE-TIER AVAILABILITY, verified against a real
    # key on 2026-08-15:
    #   gemini-3.5/3.6/3.7-flash  available
    #   gemini-3.1-pro-preview    free-tier quota is literally 0 -- paid only
    #   gemini-2.5-*              retired, the API returns 404
    #
    # A consumer "Gemini Pro" subscription does NOT grant API quota; the API
    # bills separately. So the escalation ladder runs Flash -> better Flash
    # rather than Flash -> Pro. That is still a real capability step, and it
    # keeps every scan inside the free tier. If you later add API billing,
    # set VISION_MODEL_ACCURATE=gemini-3.1-pro-preview and nothing else needs
    # to change.
    #
    # LATENCY IS THE BINDING CONSTRAINT ON THE FAST PASS, not accuracy -- the
    # user is standing over their plate waiting, and the second stage exists
    # precisely so the first one is allowed to be unsure. Measured on the same
    # 16 KB WebP, same prompt, same tool schema (2026-08-16):
    #
    #   gemini-3.5-flash-lite      8.3 s     <- fast pass
    #   gemini-3.1-flash-lite      8.4 s
    #   gemini-3.5-flash          20.7 s     <- was the fast pass
    #   gemini-3-flash-preview    21.1 s
    #   gemini-3.7-flash          14.8 s     <- accurate pass
    #
    # 3.5-flash was 2.5x slower than the lite model at the SAME job, which is
    # what made a two-stage scan take ~60 s end to end. Re-measure before
    # changing this; the ordering is not intuitive and is not stable across
    # model releases.
    GEMINI_API_KEY: str | None = None
    VISION_MODEL_FAST: str = "gemini-3.5-flash-lite"
    # NOT gemini-3.7-flash, which is what this used to be. Benchmarked on one
    # photo, August 2026, on our own key:
    #
    #   gemini-3.5-flash-lite  thinking=low     5.2 s   4 items
    #   gemini-3.5-flash       thinking=low     7.1 s   3 items
    #   gemini-3.6-flash       no thinking     19.9 s   3 items
    #   gemini-3.7-flash       no thinking    217.4 s   HTTP 500 "high demand"
    #   gemini-3.7-flash       thinking=low     9.5 s   HTTP 429 quota
    #
    # The escalated pass was pointed at the one model that could not answer.
    # It is the newest, so it is the most contended -- and an escalation that
    # 500s is strictly worse than no escalation, because the user waited for
    # it. 3.5-flash is a generation older, uncontended, and answers in seven
    # seconds. Re-run scripts/probe_paid.py style timing before changing this.
    VISION_MODEL_ACCURATE: str = "gemini-3.5-flash"
    VISION_ESCALATION_CONFIDENCE: float = 0.55

    # THE WHOLE SCAN MUST FIT IN THIS BUDGET, INCLUDING THE ESCALATED PASS.
    #
    # The mobile client aborts at 30 s. The old two-pass scan measured 58.6 s
    # end to end, so it could not succeed at all: every escalated scan was
    # billed, thrown away, and reported to the user as "couldn't read that
    # photo". The deadline is what makes the worst case bounded by us rather
    # than by whatever the model felt like doing today.
    VISION_DEADLINE_MS: int = 24_000

    # A single call that has not answered by here is not going to answer in
    # time to be useful. Failing fast leaves budget to fall back on.
    VISION_CALL_TIMEOUT_MS: int = 18_000

    # --- AI Trainer chat ----------------------------------------------------
    # A single unauthenticated Q&A endpoint (the login-screen "ask a quick
    # question" box) -- not the vision pipeline, so its own model setting
    # rather than repurposing VISION_MODEL_FAST for an unrelated feature.
    # Same finding as the vision models above: 3.5-flash took 57 s to answer a
    # one-paragraph question in an end-to-end run, which is unusable for a box
    # labelled "ask a quick question". The lite model answers the same prompt
    # in single-digit seconds.
    CHAT_MODEL: str = "gemini-3.5-flash-lite"

    # Voice workout logging. Audio in, structured sets out, one call.
    # The same lite model: transcription plus extraction is not a reasoning
    # task, and the user is standing in a gym waiting for it.
    VOICE_MODEL: str = "gemini-3.5-flash-lite"

    # --- Social sign-in ---------------------------------------------------
    # A native Google app has a DIFFERENT client ID per platform, and the ID
    # token carries whichever one requested it. Configuring only the web ID is
    # the reason "Google sign-in works in the simulator but not on my phone" --
    # the token verifies fine and then fails the audience check.
    #
    #   iOS      Google Cloud console -> Credentials -> OAuth client -> iOS
    #   Android  ...same, Android type, needs the SHA-1 of your signing cert
    #   Web      needed for Expo Go and Expo's auth proxy
    #   Expo     the proxy client, if you use @expo/auth-session's redirect
    #
    # Apple: APPLE_CLIENT_ID is the Services ID for web/Expo flows;
    # APPLE_BUNDLE_ID is the app's bundle identifier, which is what native
    # Sign in with Apple puts in `aud`. Set whichever you actually use -- both
    # are accepted so one server serves both flows.
    #
    # Leaving these unset is a supported state: /api/auth/providers reports an
    # empty list and the client hides the buttons rather than opening a
    # browser flow that cannot complete.
    GOOGLE_CLIENT_ID_IOS: str | None = None
    GOOGLE_CLIENT_ID_ANDROID: str | None = None
    GOOGLE_CLIENT_ID_WEB: str | None = None
    GOOGLE_CLIENT_ID_EXPO: str | None = None
    APPLE_CLIENT_ID: str | None = None
    APPLE_BUNDLE_ID: str | None = None

    # --- Phone sign-in -----------------------------------------------------
    # The primary login path on mobile. Passwords are a Western convention;
    # in India people expect a number and a code, and it deletes the entire
    # "forgot password" support surface.
    #
    # With no provider set, the code is LOGGED instead of sent so the flow is
    # fully testable in development. That is refused in production -- see
    # phone_auth.send_sms.
    #
    #   twilio  works everywhere, simplest to set up, ~$0.05/SMS to India
    #   msg91   India-specific and roughly 10x cheaper there; needs a DLT
    #           template id, which Indian telecom regulation requires
    SMS_PROVIDER: str | None = None          # "twilio" | "msg91"
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_FROM_NUMBER: str | None = None
    MSG91_AUTH_KEY: str | None = None
    MSG91_TEMPLATE_ID: str | None = None

    # Assumed when a number is typed without one. India by default, because
    # that is the launch market; a number entered with "+" always wins.
    DEFAULT_PHONE_COUNTRY_CODE: str = "+91"

    # --- Metered third-party nutrition data --------------------------------
    # Unset by default, and that is a fully supported state: the free tiers
    # already cover ~273,000 foods, so this is an upgrade rather than a
    # dependency. With no key the paid tier is skipped entirely -- no errors,
    # no warnings on every request.
    #
    # Sign up at https://developer.nutritionix.com. The free developer tier is
    # ~200 calls/day, which is plenty to verify the integration; the business
    # plan is around $50/mo.
    #
    # What it is actually worth paying for is NOT barcodes -- Open Food Facts
    # is free and better on non-US products. It is US restaurant chains
    # (~1,000 of them, a real gap in every free dataset) and natural-language
    # parsing ("two rotis and a bowl of dal"), which has no free equivalent.
    NUTRITIONIX_APP_ID: str | None = None
    NUTRITIONIX_APP_KEY: str | None = None

    # A BUDGET, not a rate limit. These providers bill per call, so a runaway
    # client loop is a real invoice. When the day's allowance is spent the
    # paid tier reports a miss -- which is what the user would have seen
    # anyway without the integration.
    #
    # Held in memory, so it resets on restart and is PER CONTAINER. With N
    # replicas the true ceiling is N x this number; move the counter to Redis
    # before scaling out.
    PAID_LOOKUPS_PER_DAY: int = 500

    # --- Rate limiting ----------------------------------------------------
    RATE_LIMIT_PER_MINUTE: int = 100
    FREE_TIER_SCANS_PER_DAY: int = 3

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        """Railway/Heroku hand you `postgres://` or `postgresql://`.

        asyncpg needs the explicit driver in the scheme. Normalise rather than
        making every developer remember.
        """
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg takes ssl as a connect() argument, not a URL parameter.
        # Strip the whole query string; db.py re-applies TLS.
        if "?" in v:
            v = v.split("?")[0]
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def db_requires_ssl(self) -> bool:
        """Hosted Postgres needs TLS; a local container does not."""
        if self.DB_SSL is not None:
            return self.DB_SSL
        host = self.DATABASE_URL.split("@")[-1].lower()
        return not host.startswith(("localhost", "127.0.0.1", "[::1]"))

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production and "JWT_SECRET" not in _explicit_env():
        # Fail loudly rather than silently logging everyone out on restart.
        raise RuntimeError(
            "JWT_SECRET must be set explicitly in production. Without it a new "
            "random secret is generated on every container start, which "
            "invalidates every previously issued token."
        )
    return settings


def _explicit_env() -> set[str]:
    import os

    return set(os.environ.keys())
