"""Fill `food_items.gtin14` and `food_items.name_normalized`.

WHY A SCRIPT AND NOT A MIGRATION
Both columns derive from `services/gtin.py` and `services/food_text.py`. A
migration is a frozen historical record; importing code that keeps changing
would mean re-running an old revision produces different output than it did
the first time. These values must instead be RECOMPUTED whenever the
normaliser changes, which is a script's job, not a migration's.

Migration d3e6a9c14b52 filled the static licence metadata for exactly that
reason -- a seven-row mapping that will never change -- and deliberately left
these two columns to this script.

WHAT IT WRITES: `gtin14` and `name_normalized`. Nothing else, ever.
`barcode` and `name` are READ as inputs and never modified; `names_i18n`,
`search_text`, `source_licence` and `verification_tier` are not referenced.
There is exactly one SET clause in this file.

SAFETY POSTURE
Dry-run is the default. Writing requires BOTH `--apply` and `--expect-db`,
and the expected name is compared against `current_database()` inside the
same connection that performs the writes -- a check made on a different
connection is a stale observation. A non-loopback host is refused outright
unless `--allow-remote` says otherwise.

The database URL is never printed. The target is reported as host:port/db.

RESUMABILITY IS AN OPTIMISATION, NOT A CORRECTNESS MECHANISM
Progress is a keyset cursor persisted after each committed batch. Lose the
state file and the next run is slower, never wrong: every row is compared to
its target before being written, so re-scanning finished rows costs reads and
writes nothing.

THE COMPLETION PREDICATE IS THE CURSOR, NOT THE DATA. It cannot be a SQL
predicate: NULL is the legitimate target for `gtin14` on every row whose
barcode fails validation, and '' is the legitimate target for
`name_normalized` on a name made entirely of punctuation. `WHERE gtin14 IS
NULL OR name_normalized = ''` would re-select those rows on every pass and
never terminate -- the same non-termination trap that `ifct` set for the
backfill in d3e6a9c14b52.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# app.db is DELIBERATELY NOT IMPORTED. Its init_db() calls create_all, which
# is what silently created a stray food_aliases table in the live database
# during Phase 3a and broke the migration chain. This script owns its engine.
from app.config import get_settings
from app.services.food_text import normalize
from app.services.gtin import (
    VALID_LENGTHS,
    has_valid_check_digit,
    is_restricted,
    normalize_gtin,
)

VERSION = "1.0"

#: Revisions this script is known to be correct against.
#:
#: A SET, not a minimum. When a later migration lands, ADD its revision here
#: after checking that these two columns still mean what they mean. Do not
#: loosen the comparison -- the guard exists so the script cannot run against
#: a schema it does not understand.
#:
#: f6a9c2e47d85 (workout programming tables) was checked and added: it is
#: purely additive, creating nine new tables and altering nothing. It issues
#: no ALTER TABLE, no DML, and does not reference food_items at all, so
#: gtin14 and name_normalized still mean exactly what they meant at
#: e4f7b0d25c63.
#:
#: a7c31d9b6e02 (gyms, stations, set_logs.station_id) was checked and added:
#: it creates two new tables and adds two nullable columns plus an index to
#: set_logs. It contains no reference to food_items, food_aliases, gtin14 or
#: name_normalized, and performs no DML, so both guarded columns are
#: untouched and still mean what they meant at e4f7b0d25c63.
EXPECTED_REVISIONS = frozenset(
    {"e4f7b0d25c63", "f6a9c2e47d85", "a7c31d9b6e02"}
)

REQUIRED_COLUMNS = frozenset({"gtin14", "name_normalized"})

LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", None})

DEFAULT_BATCH = 2_000

#: OUTSIDE THE REPOSITORY, by default. A cursor file inside the working tree
#: gets committed by accident or wiped by a clean checkout.
DEFAULT_STATE = pathlib.Path(tempfile.gettempdir()) / "trace_backfill_gtin_name.json"

SAFETY_NOTICE = """\
safety contract:
  * dry-run is the DEFAULT; writing requires --apply AND --expect-db
  * only gtin14 and name_normalized are ever written
  * barcode, name, names_i18n, search_text, source_licence and
    verification_tier are never modified
  * non-loopback hosts are refused unless --allow-remote is given
  * the database URL, and therefore the password, is never printed
"""


@dataclass
class Counters:
    scanned: int = 0
    updated: int = 0
    skipped: int = 0
    gtin_valid: int = 0
    gtin_rejected: int = 0
    missing: int = 0
    bad_check: int = 0
    bad_length: int = 0
    restricted: int = 0
    other_reject: int = 0
    name_changed: int = 0
    errors: int = 0
    batches: int = 0
    samples: list[tuple] = field(default_factory=list)


def reject_reason(raw: Optional[str]) -> str:
    """Why did normalize_gtin refuse this barcode?

    Uses gtin.py's own public helpers rather than re-deriving the rules, so
    the two can never disagree about what "invalid" means. This is reporting
    only -- the accept/reject decision belongs to normalize_gtin alone.
    """
    if raw is None or not isinstance(raw, str):
        return "missing"
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return "missing"
    if len(digits) not in VALID_LENGTHS:
        return "bad_length"
    if not has_valid_check_digit(digits):
        return "bad_check"
    if is_restricted(digits.rjust(14, "0")):
        return "restricted"
    return "other"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def load_state(path: pathlib.Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A missing or corrupt cursor is not an error: the run simply starts
        # from the beginning and skips everything already correct.
        return {}


def save_state(path: pathlib.Path, cursor: str, counters: Counters) -> None:
    payload = {
        "last_id": cursor,
        "batches": counters.batches,
        "scanned": counters.scanned,
        "updated": counters.updated,
        "version": VERSION,
    }
    try:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:  # noqa: BLE001 -- never abort a good run over this
        print(f"  warning: could not write state file: {exc.__class__.__name__}")


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


class Refused(RuntimeError):
    """A precondition failed. Nothing has been written."""


async def preflight(conn, args: argparse.Namespace, host: str | None, port: int | None) -> str:
    """Verify the target IN THE CONNECTION THAT WILL DO THE WRITING.

    Checking on a separate connection proves only what was true a moment ago
    on some other session. During Phase 3a a guard written that way would have
    dropped the production database; this one is deliberately co-located with
    the work.
    """
    db = await conn.scalar(text("SELECT current_database()"))

    row = (await conn.execute(text(
        "SELECT inet_server_addr()::text, inet_server_port()"
    ))).first()
    server_addr, server_port = (row[0], row[1]) if row else (None, None)

    print("target")
    print(f"  database          : {db}")
    print(f"  host:port         : {host}:{port}")
    # inet_server_addr() is NULL over a unix socket, which is loopback by
    # definition. Reported, not treated as an error.
    print(f"  server reports    : {server_addr or 'unix socket'}:{server_port or port}")

    if host not in LOOPBACK and not args.allow_remote:
        raise Refused(
            f"host {host!r} is not loopback. Pass --allow-remote to override, "
            "but be certain this is not production."
        )

    cols = set((await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='food_items' "
        "AND column_name IN ('gtin14','name_normalized')"
    ))).scalars().all())
    missing = REQUIRED_COLUMNS - cols
    if missing:
        raise Refused(
            f"food_items is missing {sorted(missing)} -- run the Phase 3a "
            "migrations first."
        )

    rev = await conn.scalar(text("SELECT version_num FROM alembic_version"))
    print(f"  alembic revision  : {rev}")
    if rev not in EXPECTED_REVISIONS:
        raise Refused(
            f"schema revision {rev!r} is not one this script is known to be "
            f"correct against ({sorted(EXPECTED_REVISIONS)}). Add the new "
            "revision to EXPECTED_REVISIONS after checking the columns still "
            "mean the same thing."
        )

    if args.apply:
        if args.expect_db != db:
            raise Refused(
                f"--expect-db {args.expect_db!r} does not match the connected "
                f"database {db!r}. Refusing to write."
            )
        print(f"  mode              : APPLY (writes enabled, --expect-db {db})")
    else:
        print("  mode              : DRY RUN (no writes)")

    return db


# ---------------------------------------------------------------------------
# The work
# ---------------------------------------------------------------------------

_READ = text(
    """
    SELECT id, barcode, name, gtin14, name_normalized
      FROM food_items
     WHERE id > :cursor
     ORDER BY id
     LIMIT :batch
    """
)


def build_update(changes: list[tuple[str, Optional[str], str]]) -> tuple[Any, dict]:
    """One UPDATE per batch, carrying only the rows that actually change.

    EXPLICIT CAST(...) RATHER THAN `:param::text`. SQLAlchemy's text() parses
    `:name` bind parameters itself, and a `::` cast immediately after one is
    ambiguous to that parser. CAST() is unambiguous in both languages.

    The cast is not cosmetic either: an all-NULL gtin14 batch sends the
    parameter as `unknown`, and Postgres cannot assign `unknown` to a text
    column inside a VALUES join.
    """
    rows, params = [], {}
    for i, (row_id, gtin, name_norm) in enumerate(changes):
        rows.append(
            f"(CAST(:i{i} AS text), CAST(:g{i} AS text), CAST(:n{i} AS text))"
        )
        params[f"i{i}"] = row_id
        params[f"g{i}"] = gtin
        params[f"n{i}"] = name_norm

    sql = text(
        "UPDATE food_items AS f "
        "   SET gtin14 = v.gtin14, "
        "       name_normalized = v.name_normalized "
        f"  FROM (VALUES {', '.join(rows)}) AS v(id, gtin14, name_normalized) "
        " WHERE f.id = v.id"
    )
    return sql, params


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    url = settings.DATABASE_URL          # never printed, never logged
    parts = urlsplit(url)
    host, port = parts.hostname, parts.port

    state_path = pathlib.Path(args.state) if args.state else DEFAULT_STATE

    if args.restart:
        cursor = ""
    elif args.resume_from is not None:
        cursor = args.resume_from
    else:
        cursor = load_state(state_path).get("last_id", "") or ""

    print(f"backfill_gtin_and_name {VERSION}")
    print(f"  state file        : {state_path}")
    print(f"  starting cursor   : {cursor!r}")
    print(f"  batch size        : {args.batch}")

    # AUTOCOMMIT so each batch UPDATE is its own committed transaction. A
    # single enclosing transaction would make the batching cosmetic and hold
    # row locks over the whole run.
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    counters = Counters()
    started = time.perf_counter()

    try:
        async with engine.connect() as conn:
            db = await preflight(conn, args, host, port)

            if not args.apply:
                # Belt and braces: a coding mistake cannot write in dry run.
                await conn.execute(text("SET default_transaction_read_only = on"))

            # Session-scoped under AUTOCOMMIT: set once, applies to every
            # batch. Fail fast rather than queueing behind a conflicting lock.
            await conn.execute(text("SET lock_timeout = '5s'"))

            print()
            while True:
                if args.limit is not None and counters.scanned >= args.limit:
                    break

                take = args.batch
                if args.limit is not None:
                    take = min(take, args.limit - counters.scanned)

                rows = (await conn.execute(
                    _READ, {"cursor": cursor, "batch": take}
                )).mappings().all()
                if not rows:
                    break

                changes: list[tuple[str, Optional[str], str]] = []
                for r in rows:
                    counters.scanned += 1
                    try:
                        gtin = normalize_gtin(r["barcode"])
                        name_norm = normalize(r["name"] or "")
                    except Exception:  # noqa: BLE001
                        # ONE BAD ROW MUST NOT END THE RUN. Both functions are
                        # property-tested never to raise; this is the second
                        # layer, because the input is 578,773 uncontrolled
                        # crowd-sourced strings.
                        counters.errors += 1
                        continue

                    if gtin is None:
                        counters.gtin_rejected += 1
                        reason = reject_reason(r["barcode"])
                        if reason == "missing":
                            counters.missing += 1
                        elif reason == "bad_length":
                            counters.bad_length += 1
                        elif reason == "bad_check":
                            counters.bad_check += 1
                        elif reason == "restricted":
                            counters.restricted += 1
                        else:
                            counters.other_reject += 1
                    else:
                        counters.gtin_valid += 1

                    if name_norm != (r["name_normalized"] or ""):
                        counters.name_changed += 1

                    gtin_differs = gtin != r["gtin14"]
                    name_differs = name_norm != (r["name_normalized"] or "")
                    if gtin_differs or name_differs:
                        changes.append((r["id"], gtin, name_norm))
                        if len(counters.samples) < args.sample:
                            counters.samples.append(
                                (r["id"], r["barcode"], gtin, r["name"], name_norm)
                            )
                    else:
                        counters.skipped += 1

                if changes and args.apply:
                    sql, params = build_update(changes)
                    await conn.execute(sql, params)   # AUTOCOMMIT: committed here
                    counters.updated += len(changes)
                elif changes:
                    counters.updated += len(changes)  # would-be, dry run

                counters.batches += 1
                cursor = rows[-1]["id"]

                # ONLY AFTER THE COMMIT. A crash between the two re-processes
                # one batch, which is a no-op because those rows now match.
                if args.apply:
                    save_state(state_path, cursor, counters)

                if counters.batches % 25 == 0:
                    print(f"  ... {counters.scanned:,} scanned, "
                          f"{counters.updated:,} {'updated' if args.apply else 'would update'}")
    finally:
        await engine.dispose()

    _report(counters, args, time.perf_counter() - started)
    return 0


def _report(counters: Counters, args: argparse.Namespace, elapsed: float) -> None:
    verb = "updated" if args.apply else "would update"
    print()
    if counters.samples:
        print(f"sample ({len(counters.samples)})")
        for _id, raw, gtin, name, norm in counters.samples:
            print(f"  {str(raw)[:16]:16} -> {str(gtin):16}   "
                  f"{str(name)[:28]:28} -> {norm[:28]}")
        print()
    print("results")
    print(f"  rows scanned          {counters.scanned:>10,}")
    print(f"  rows {verb:<16} {counters.updated:>10,}")
    print(f"  already correct       {counters.skipped:>10,}")
    print(f"  gtin14 valid          {counters.gtin_valid:>10,}")
    print(f"  gtin14 rejected       {counters.gtin_rejected:>10,}")
    print(f"    missing             {counters.missing:>10,}")
    print(f"    bad check digit     {counters.bad_check:>10,}")
    print(f"    invalid length      {counters.bad_length:>10,}")
    print(f"    restricted prefix   {counters.restricted:>10,}")
    print(f"    other               {counters.other_reject:>10,}")
    print(f"  name_normalized diff  {counters.name_changed:>10,}")
    print(f"  errors                {counters.errors:>10,}")
    print(f"  batches               {counters.batches:>10,}")
    print(f"  elapsed               {elapsed:>10.1f}s")
    if not args.apply:
        print("\n  DRY RUN -- nothing was written. Re-run with "
              "--apply --expect-db <name> to write.")
    elif counters.updated:
        print("\n  Consider VACUUM (ANALYZE) food_items: this rewrote "
              f"{counters.updated:,} row versions.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="backfill_gtin_and_name",
        description=(
            "Fill food_items.gtin14 and food_items.name_normalized from the "
            "shared pure services. Resumable, batched, dry-run by default."
        ),
        epilog=SAFETY_NOTICE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version",
                   version=f"backfill_gtin_and_name {VERSION}\n\n{SAFETY_NOTICE}")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="read-only; the default")
    mode.add_argument("--apply", action="store_true",
                      help="perform writes; requires --expect-db")
    p.add_argument("--expect-db", metavar="NAME",
                   help="must equal current_database(); mandatory with --apply")
    p.add_argument("--allow-remote", action="store_true",
                   help="permit a non-loopback host")
    p.add_argument("--batch", type=int, default=DEFAULT_BATCH,
                   help=f"rows per committed batch (default {DEFAULT_BATCH})")
    p.add_argument("--limit", type=int, default=None,
                   help="stop after N rows scanned")
    p.add_argument("--sample", type=int, default=10,
                   help="example transformations to print (default 10)")
    p.add_argument("--state", metavar="PATH", default=None,
                   help=f"cursor file (default {DEFAULT_STATE})")
    p.add_argument("--resume-from", metavar="ID", default=None,
                   help="start after this id, ignoring the state file")
    p.add_argument("--restart", action="store_true",
                   help="ignore stored state and start from the beginning")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.apply and not args.expect_db:
        # Refused BEFORE a connection is opened. The point of --expect-db is
        # that a write cannot happen by momentum.
        parser.error("--apply requires --expect-db NAME (e.g. --expect-db trace)")
    if args.batch < 1:
        parser.error("--batch must be at least 1")

    try:
        return asyncio.run(run(args))
    except Refused as exc:
        print(f"\nREFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
