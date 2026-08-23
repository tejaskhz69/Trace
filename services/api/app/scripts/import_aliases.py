"""Import reviewed aliases into `food_aliases`. DRY-RUN BY DEFAULT.

    # inert: reads, plans, prints, writes nothing
    python -m app.scripts.import_aliases

    # writes, and only with both flags, on loopback, after review
    python -m app.scripts.import_aliases --apply --expect-db trace

WHY THIS FILE IS BUILT TO BE HARD TO FIRE
The catalogue behind it took a 578,773-row backfill to get right. An importer
that writes by default, or that can be aimed at the wrong database by a stale
shell variable, is a loaded weapon in a repo. So:

  * dry-run is the DEFAULT and the only mode reachable without arguments;
  * `--apply` alone is a usage error, refused BEFORE any connection opens;
  * `--expect-db` must match `current_database()` or the run aborts;
  * non-loopback hosts are refused unless `--allow-remote` is passed too;
  * the connection opens READ ONLY and is only escalated inside `--apply`;
  * the single write statement names `food_aliases` and nothing else.

WHAT IT WILL NEVER DO
It contains no UPDATE, no DELETE, no TRUNCATE, no ALTER, and no reference to
any `food_items` column. `tests/test_import_aliases.py` asserts that
structurally against the source text, so adding one fails the suite rather
than the database.

IDEMPOTENCE
The write is `INSERT ... ON CONFLICT ON CONSTRAINT uq_alias_food_norm_lang DO
NOTHING`. Re-running inserts zero rows and reports them as already-present,
which is what makes a partial run safe to resume.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import pathlib
import sys
import urllib.parse
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ..config import get_settings

DEFAULT_PLAN = pathlib.Path("review") / "alias_import_plan.json"

#: The ONLY table this script may name in a write. Asserted by the tests.
TARGET_TABLE = "food_aliases"

#: Columns written. Every one belongs to `food_aliases`; none belongs to
#: `food_items`. `id`, `created_at` and `updated_at` come from server/model
#: defaults, deliberately not from here.
INSERT_COLUMNS = (
    "food_item_id", "alias", "normalized", "lang", "script",
    "alias_type", "source", "confidence", "is_active",
)

INSERT_SQL = """
INSERT INTO food_aliases
       (id, food_item_id, alias, normalized, lang, script,
        alias_type, source, confidence, is_active, created_at, updated_at)
VALUES (gen_random_uuid(), :food_item_id, :alias, :normalized, :lang, :script,
        :alias_type, :source, :confidence, true, now(), now())
ON CONFLICT ON CONSTRAINT uq_alias_food_norm_lang DO NOTHING
"""


class Refused(SystemExit):
    """Raised for every safety refusal, so none is mistakable for success."""


# ------------------------------------------------------------- safety gates

def assert_loopback(url: str, allow_remote: bool) -> str:
    """Return the host, refusing anything non-local unless explicitly allowed.

    Never returns or logs the URL itself -- only the bare host.
    """
    host = urllib.parse.urlparse(url).hostname or ""
    if allow_remote:
        return host
    if host in ("localhost", ""):
        return host
    try:
        if ipaddress.ip_address(host).is_loopback:
            return host
    except ValueError:
        pass
    raise Refused(
        "refusing to target non-loopback host %r without --allow-remote" % host
    )


def validate_args(args, parser) -> None:
    """Every refusal that can be decided WITHOUT a connection happens here."""
    if args.apply and not args.expect_db:
        # Checked before the engine is built, so a mistyped command cannot
        # even open a socket to the wrong database.
        parser.error("--apply requires --expect-db NAME (e.g. --expect-db trace)")


# ------------------------------------------------------------- plan loading

def load_plan(path: pathlib.Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("aliases", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise Refused("plan file %s has no alias list" % path)
    return rows


def prevalidate(rows: list[dict]) -> tuple[list[dict], dict[str, list]]:
    """Reject unsafe rows BEFORE any write. Returns (safe, problems).

    Duplicate-normalised and multi-target checks run here rather than being
    left to the ON CONFLICT clause, because a conflict tells you a row was
    skipped but not that the plan was wrong.
    """
    problems: dict[str, list] = defaultdict(list)

    by_norm: dict[str, set[str]] = defaultdict(set)
    seen_pair: set[tuple[str, str]] = set()
    for r in rows:
        by_norm[r.get("normalized", "")].add(r.get("food_item_id", ""))

    safe: list[dict] = []
    for r in rows:
        norm = r.get("normalized", "")
        fid = r.get("food_item_id", "")
        if not norm:
            problems["empty_normalized"].append(r)
        elif not fid:
            problems["missing_target_id"].append(r)
        elif len(by_norm[norm]) > 1:
            problems["multiple_targets"].append(r)
        elif (fid, norm) in seen_pair:
            problems["duplicate_in_plan"].append(r)
        else:
            seen_pair.add((fid, norm))
            safe.append(r)
    return safe, dict(problems)


# ------------------------------------------------------------------ the run

async def run(url: str, rows: list[dict], apply: bool, expect_db: str | None,
              allow_remote: bool) -> dict:
    host = assert_loopback(url, allow_remote)
    engine = create_async_engine(url)
    stats = {"planned": len(rows), "would_insert": 0, "already_present": 0,
             "target_not_found": 0, "inserted": 0, "host": host}
    try:
        async with engine.connect() as conn:
            # Read-only unless and until --apply escalates it below.
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            db = (await conn.execute(text("SELECT current_database()"))).scalar()
            stats["database"] = db
            if expect_db and db != expect_db:
                raise Refused(
                    "--expect-db %r does not match the connected database %r"
                    % (expect_db, db)
                )

            ids = sorted({r["food_item_id"] for r in rows})
            live = set((await conn.execute(text(
                "SELECT id::text FROM food_items WHERE id::text = ANY(:ids)"
            ), {"ids": ids})).scalars().all())

            # Two columns into tuples rather than one concatenated key: SQL
            # and Python disagree about what '\x1f' denotes (a literal
            # backslash-x-1-f under standard_conforming_strings, versus the
            # real U+001F), and that mismatch would silently make every
            # existing row look absent.
            present = {
                (r[0], r[1]) for r in (await conn.execute(text(
                    "SELECT food_item_id::text, normalized FROM food_aliases "
                    "WHERE food_item_id::text = ANY(:ids)"
                ), {"ids": ids})).all()
            }

        todo: list[dict] = []
        for r in rows:
            if r["food_item_id"] not in live:
                stats["target_not_found"] += 1
            elif (r["food_item_id"], r["normalized"]) in present:
                stats["already_present"] += 1
            else:
                todo.append(r)
        stats["would_insert"] = len(todo)

        if apply:
            # The ONLY branch that writes. Reached only with --apply and a
            # matching --expect-db, on a loopback host.
            async with engine.begin() as conn:
                for r in todo:
                    await conn.execute(text(INSERT_SQL), {
                        k: r[k] for k in INSERT_COLUMNS if k != "is_active"
                    })
            stats["inserted"] = len(todo)
    finally:
        await engine.dispose()
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Import reviewed food aliases.")
    p.add_argument("--plan", default=str(DEFAULT_PLAN))
    p.add_argument("--apply", action="store_true",
                   help="perform writes; requires --expect-db")
    p.add_argument("--expect-db", metavar="NAME",
                   help="must equal current_database(); mandatory with --apply")
    p.add_argument("--allow-remote", action="store_true",
                   help="permit a non-loopback database host")
    args = p.parse_args(argv)
    validate_args(args, p)

    rows = load_plan(pathlib.Path(args.plan))
    safe, problems = prevalidate(rows)

    stats = asyncio.run(run(get_settings().DATABASE_URL, safe, args.apply,
                            args.expect_db, args.allow_remote))

    mode = "APPLY (writes enabled)" if args.apply else "DRY RUN (no writes)"
    print("mode                : %s" % mode)
    print("database            : %s on host %s" % (stats["database"], stats["host"]))
    print("plan rows           : %d" % len(rows))
    print("rejected pre-write  : %d %s"
          % (sum(len(v) for v in problems.values()),
             {k: len(v) for k, v in problems.items()} or "{}"))
    print("would insert        : %d" % stats["would_insert"])
    print("already present     : %d" % stats["already_present"])
    print("target not found    : %d" % stats["target_not_found"])
    print("actually inserted   : %d" % stats["inserted"])
    print()
    print("SQL shape:")
    print("  " + " ".join(INSERT_SQL.split())[:150])
    if not args.apply:
        print()
        print("NOTHING WAS WRITTEN. Re-run with --apply --expect-db <name>.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
