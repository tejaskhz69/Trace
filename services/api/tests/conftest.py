"""Shared fixtures for the integration test bench.

CRITICAL: this must repoint DATABASE_URL at the dedicated `trace_test`
database BEFORE any `app.*` module is imported anywhere in the test session
-- `app.config.get_settings()` is `@lru_cache`d and `app.db` builds its engine
at import time, so if a real env var isn't set until later, tests would
silently run against whatever DATABASE_URL is really configured (in this
project, a live Neon database with real user data). pytest imports
conftest.py in a directory before collecting test modules in it, so doing
this at module scope here -- before the `from app...` imports below -- is
what makes it safe.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values

# DATABASE_URL normally lives only in services/api/.env, not a real shell env
# var -- pydantic-settings reads the file itself when Settings() first runs.
# Reading it here with dotenv_values (no side effects on app state) is what
# lets us compute the swapped-in trace_test URL BEFORE that first read
# happens, then set it as a real env var so it takes precedence.
_env_path = Path(__file__).resolve().parents[1] / ".env"
_raw_url = os.environ.get("DATABASE_URL") or dotenv_values(_env_path).get("DATABASE_URL", "")
if _raw_url:
    parts = urlsplit(_raw_url)
    os.environ["DATABASE_URL"] = urlunsplit(
        (parts.scheme, parts.netloc, "/trace_test", parts.query, parts.fragment)
    )

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app import models  # noqa: F401  -- registers every table on SQLModel.metadata
from app.config import get_settings
from app.db import get_session
from app.main import app as fastapi_app

settings = get_settings()


def _fail_fast_if_not_test_db() -> None:
    """Belt-and-suspenders: refuse to run against anything but trace_test."""
    if not settings.DATABASE_URL.rstrip("/").endswith("/trace_test"):
        raise RuntimeError(
            f"Refusing to run integration tests against {settings.DATABASE_URL!r} "
            "-- expected the trace_test database. Aborting before touching any data."
        )


@pytest.fixture(scope="session")
async def db_engine():
    _fail_fast_if_not_test_db()
    engine = create_async_engine(
        settings.DATABASE_URL,
        connect_args={"ssl": "require"} if settings.db_requires_ssl else {},
    )
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables(db_engine):
    """Truncate every table before each test so tests never leak state."""
    names = ", ".join(f'"{t.name}"' for t in SQLModel.metadata.sorted_tables)
    async with db_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def db_session(db_engine):
    """Direct DB access for a test to seed data outside the HTTP surface."""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def client(db_engine):
    """An httpx client wired straight into the FastAPI app over ASGI --
    no real socket, no separate server process, same DB-session override
    the real app uses via dependency injection."""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_session_override():
        async with factory() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = _get_session_override
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()
