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
from app.models import PROGRAMMABLE_EXERCISES_VIEW
from app.main import app as fastapi_app

settings = get_settings()


def _fail_fast_if_not_test_db() -> None:
    """Belt-and-suspenders: refuse to run against anything but trace_test."""
    if not settings.DATABASE_URL.rstrip("/").endswith("/trace_test"):
        raise RuntimeError(
            f"Refusing to run integration tests against {settings.DATABASE_URL!r} "
            "-- expected the trace_test database. Aborting before touching any data."
        )


async def _refuse_if_the_test_schema_has_drifted(conn) -> None:
    """`create_all` builds missing tables. It never alters existing ones.

    So a trace_test database that predates a model change keeps the old
    columns forever, and nothing says so. That stayed invisible while every
    query happened to use the old columns; the moment something read a new
    one it surfaced as `column a.movement_detail does not exist`, raised
    inside this session-scoped fixture, i.e. as 282 errors naming a column
    rather than one error naming the cause.

    A dropped-and-rebuilt test database is the fix, which is destructive and
    therefore a human's call. This refuses and says which columns are
    missing, in the spirit of the backfill's EXPECTED_REVISIONS guard: a
    cheap refusal that forces someone to look beats a clever repair.
    """
    live: dict[str, set[str]] = {}
    rows = await conn.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public'"
    ))
    for table, column in rows:
        live.setdefault(table, set()).add(column)

    drift = []
    for name, table in SQLModel.metadata.tables.items():
        if name not in live:
            continue  # create_all has it covered
        missing = {c.name for c in table.columns} - live[name]
        if missing:
            drift.append(f"{name}: missing {sorted(missing)}")

    if drift:
        raise RuntimeError(
            "The trace_test schema has drifted from models.py:\n  "
            + "\n  ".join(drift)
            + "\n\ncreate_all cannot repair this -- it only creates tables "
            "that are absent. Drop the affected tables (or the whole "
            "trace_test database) and let the next run rebuild them."
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
        await _refuse_if_the_test_schema_has_drifted(conn)
        # Views are not in SQLModel.metadata, so create_all cannot make
        # this one. Generation reads it instead of joining by hand.
        await conn.execute(text("DROP VIEW IF EXISTS programmable_exercises"))
        await conn.execute(text(PROGRAMMABLE_EXERCISES_VIEW))
    yield engine
    await engine.dispose()


# Fixtures that mean "this test touches the database". A test that requests
# none of them cannot leak state, so it does not need a truncate.
_DB_FIXTURES = frozenset({"db_engine", "db_session", "client"})


@pytest.fixture(autouse=True)
async def _clean_tables(request):
    """Truncate every table before each test so tests never leak state.

    ONLY for tests that actually touch the database. This used to depend on
    `db_engine` unconditionally, which meant every pure-function test in
    test_engines/test_strength/test_maintenance paid ~2 s to connect and
    TRUNCATE a table set it never read -- turning a suite of arithmetic into
    a multi-minute run, which is how a test suite stops being run at all.
    """
    if not (_DB_FIXTURES & set(request.fixturenames)):
        yield
        return

    engine = request.getfixturevalue("db_engine")
    names = ", ".join(f'"{t.name}"' for t in SQLModel.metadata.sorted_tables)
    async with engine.begin() as conn:
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
