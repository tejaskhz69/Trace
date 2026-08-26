"""One rule, one implementation: seeds insert data, migrations own schema.

WHY THIS EXISTS
Every seed and ingest script here used to open with `await init_db()`, which
calls `SQLModel.metadata.create_all`. That was harmless when the project had
no migrations and actively dangerous once it did:

* it creates whatever tables the current models declare, so a *data* command
  silently performs a *schema* change;
* it does not stamp Alembic, so the database ends up holding tables Alembic
  believes it has not created yet;
* the next `alembic upgrade head` then fails with "relation already exists",
  and the person running it has no idea which command did it.

The failure surfaces days later, in the wrong place, to somebody who did not
cause it. So a seed no longer creates anything. It checks that the schema it
needs is already there and says exactly what to do if it is not.

`sync_schema.py` deliberately still calls `create_all` -- that script's whole
job is schema, and it says so.
"""

from __future__ import annotations

from sqlalchemy import inspect

from ..db import engine


async def require_tables(*tables: str) -> None:
    """Exit with a clear instruction if any required table is missing.

    Raises SystemExit rather than returning a flag: there is no sensible way
    for a seed to continue against a schema that is not there, and a partial
    run is worse than no run.
    """
    if not tables:
        return

    def _missing(sync_conn) -> list[str]:
        inspector = inspect(sync_conn)
        return [t for t in tables if not inspector.has_table(t)]

    async with engine.connect() as conn:
        missing = await conn.run_sync(_missing)

    if missing:
        noun = "table" if len(missing) == 1 else "tables"
        raise SystemExit(
            f"{', '.join(missing)} {noun} missing "
            f"— run alembic upgrade head first"
        )
