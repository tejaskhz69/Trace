"""Async database engine and session management."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, text

from .config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    connect_args={"ssl": "require"} if settings.db_requires_ssl else {},
    # Railway's Postgres plugin has a modest connection cap. pool_pre_ping
    # avoids handing out connections the proxy has already reaped, which
    # otherwise surfaces as random "connection was closed" 500s.
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=280,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create extensions and tables.

    For a real deployment, replace create_all with Alembic migrations. This is
    fine up to the first schema change you need to ship without data loss.
    """
    async with engine.begin() as conn:
        # pg_trgm powers typo-tolerant food search.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        await conn.run_sync(SQLModel.metadata.create_all)
