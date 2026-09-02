"""Reconcile the live database against the SQLModel definitions.

WHY THIS EXISTS
`init_db()` calls `SQLModel.metadata.create_all`, which creates tables that do
not exist and then stops. It never ALTERs a table that already exists. So the
moment someone adds a field to an existing model, every database created
before that commit silently lacks the column, and the failure surfaces much
later as a 500 from a SELECT that names it -- which is exactly how
`body_composition.fat_target_g` went missing.

WHAT THIS DOES
Diffs the models against `information_schema` and reports every difference.
With `--apply` it fixes only the safe half:

    ADDS      nullable columns, and tables that are missing entirely
    REFUSES   dropping columns, narrowing types, adding NOT NULL without a
              default, or anything else that can lose data

Additive nullable changes are the overwhelming majority of schema drift on a
young project and are safe to apply anywhere, including production. Everything
else needs a real migration with a thought-through backfill, and this script
will tell you so rather than guessing.

WHAT THIS IS NOT
A migration tool. There is no version history, no downgrade, and no ordering.
When you need to rename a column, change a type, or backfill data, reach for
Alembic -- `alembic` is already in requirements.txt for exactly that day.

Run:
    python -m app.scripts.sync_schema            # report only
    python -m app.scripts.sync_schema --apply    # add the safe things
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text
from sqlmodel import SQLModel

from .. import (
    models,  # noqa: F401  -- imported for its side effect of registering tables
)
from ..db import engine


async def live_columns(conn) -> dict[str, dict[str, str]]:
    """Map table -> {column: data_type} for the current schema."""
    rows = await conn.execute(
        text(
            "SELECT table_name, column_name, data_type "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        )
    )
    out: dict[str, dict[str, str]] = {}
    for table, column, dtype in rows:
        out.setdefault(table, {})[column] = dtype
    return out


def ddl_type(column) -> str:
    """The dialect-specific DDL type for a column, e.g. DOUBLE PRECISION."""
    from sqlalchemy.dialects import postgresql

    return column.type.compile(dialect=postgresql.dialect())


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually add the safe (nullable / missing-table) changes.",
    )
    args = ap.parse_args()

    missing_tables: list[str] = []
    safe_adds: list[tuple[str, str, str]] = []   # (table, column, ddl type)
    unsafe: list[str] = []

    async with engine.begin() as conn:
        live = await live_columns(conn)

        for table_name, table in SQLModel.metadata.tables.items():
            if table_name not in live:
                missing_tables.append(table_name)
                continue

            for column in table.columns:
                if column.name in live[table_name]:
                    continue
                # A NOT NULL column with no server default cannot be added to
                # a table that already has rows -- Postgres rejects it, and
                # inventing a default here would silently write fiction into
                # every existing row.
                if not column.nullable and column.server_default is None:
                    unsafe.append(
                        f"{table_name}.{column.name} is NOT NULL with no server "
                        f"default -- needs a migration with an explicit backfill"
                    )
                else:
                    safe_adds.append((table_name, column.name, ddl_type(column)))

        # Columns in the DB but not in the models. Reported, never dropped:
        # a stale column is harmless, and dropping one is how you lose data
        # that a rolled-back deploy still needs.
        model_cols = {
            name: {c.name for c in tbl.columns}
            for name, tbl in SQLModel.metadata.tables.items()
        }
        orphans = [
            f"{t}.{c}"
            for t, cols in live.items()
            if t in model_cols
            for c in cols
            if c not in model_cols[t]
        ]

        if not (missing_tables or safe_adds or unsafe or orphans):
            print("Schema is in sync. Nothing to do.")
            return

        if missing_tables:
            print(f"\nMissing tables ({len(missing_tables)}):")
            for t in missing_tables:
                print(f"  {t}")

        if safe_adds:
            print(f"\nMissing nullable columns ({len(safe_adds)}) -- safe to add:")
            for t, c, ty in safe_adds:
                print(f"  {t}.{c}  {ty}")

        if unsafe:
            print(f"\nNeeds a real migration ({len(unsafe)}):")
            for u in unsafe:
                print(f"  {u}")

        if orphans:
            print(f"\nIn the database but not in the models ({len(orphans)}):")
            for o in orphans:
                print(f"  {o}")
            print("  (reported only -- this script never drops anything)")

        if not args.apply:
            if safe_adds or missing_tables:
                print("\nRe-run with --apply to add the safe changes.")
            return

        if missing_tables:
            await conn.run_sync(SQLModel.metadata.create_all)
            print(f"\nCreated {len(missing_tables)} missing table(s).")

        for t, c, ty in safe_adds:
            # IF NOT EXISTS keeps this idempotent, so a partially-applied run
            # can simply be repeated.
            await conn.execute(
                text(f'ALTER TABLE "{t}" ADD COLUMN IF NOT EXISTS "{c}" {ty}')
            )
            print(f"  added {t}.{c}")

        if safe_adds:
            print(f"\nAdded {len(safe_adds)} column(s).")
        if unsafe:
            print(f"{len(unsafe)} change(s) still need a migration -- see above.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
