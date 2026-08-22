import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from alembic import context

# `app.models` is imported for its SIDE EFFECT: importing it registers every
# table on SQLModel.metadata. Without it autogenerate sees an empty metadata
# and cheerfully generates a migration that drops all 23 tables.
from app import models  # noqa: F401
from app.config import get_settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# THE DATABASE URL COMES FROM SETTINGS, NOT FROM alembic.ini.
#
# Two reasons. DATABASE_URL is a secret and lives in the gitignored .env, so
# it must never be written into a tracked file. And tests/conftest.py rewrites
# it to point at `trace_test` before any app.* module is imported -- reading it
# through get_settings() here means migrations automatically follow that
# redirect instead of running against real data.
#
# THE `%` DOUBLING IS NOT COSMETIC. set_main_option writes into a ConfigParser,
# where `%` opens an interpolation token. This project's password is
# URL-encoded and contains `%40`, so without the escape Alembic dies with
# InterpolationSyntaxError before it ever opens a connection.
config.set_main_option(
    "sqlalchemy.url", get_settings().DATABASE_URL.replace("%", "%%")
)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLModel keeps every table declared in app/models.py on this one metadata
# object, so it is the single source of truth autogenerate compares against.
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
