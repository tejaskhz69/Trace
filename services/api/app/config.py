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
    GEMINI_API_KEY: str | None = None
    VISION_MODEL_FAST: str = "gemini-3.5-flash"
    VISION_MODEL_ACCURATE: str = "gemini-3.7-flash"
    VISION_ESCALATION_CONFIDENCE: float = 0.75

    # --- AI Trainer chat ----------------------------------------------------
    # A single unauthenticated Q&A endpoint (the login-screen "ask a quick
    # question" box) -- not the vision pipeline, so its own model setting
    # rather than repurposing VISION_MODEL_FAST for an unrelated feature.
    CHAT_MODEL: str = "gemini-3.5-flash"

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
