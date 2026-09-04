"""Measure `/api/foods/search` against the real catalogue, without touching it.

WHY A SCRIPT AND NOT A TEST
A test asserting "search takes under 200 ms" is a test that fails on a laptop
with a cold page cache and passes on a warm one, so it gets marked flaky and
then deleted. The numbers below are for a human to read before and after a
change; the properties that must never regress (one round trip, bounded fetch,
no N+1) are asserted in `tests/test_search_performance.py` instead, where they
can be checked without a stopwatch.

SAFETY
Everything runs inside `SET TRANSACTION READ ONLY`, so Postgres itself rejects
a write even if this file is later edited to attempt one, and the target
database name is checked before a single statement is sent. Nothing here is
importable by the API: `app/scripts/` is not on the request path.

    python -m app.scripts.bench_search --expect-db trace
    python -m app.scripts.bench_search --expect-db trace --explain
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ..routers.foods import (
    ARM_OVERFETCH,
    MAX_ARM_FETCH,
    SEARCH_SQL,
    WORD_SIMILARITY_FLOOR,
)
from ..services.search_rank import ARM_ALIAS, alias_candidate, direct_candidate, rank

#: The query shapes that actually occur, each chosen for a different reason.
#: A benchmark over one query measures one plan; these seven measure the plans
#: that differ from each other.
QUERIES: tuple[tuple[str, str], ...] = (
    ("dosa", "common direct term, short, many substring hits"),
    ("panir", "alias-only: no food is named this, Paneer is reached via an alias"),
    ("mix", "broad: matches many aliases and a great many search_text blobs"),
    ("plain dosa", "exact canonical name of a curated row"),
    ("chick", "prefix of a very common word"),
    ("tikka", "substring, mid-token in most rows that contain it"),
    ("zzzqqxnotafood", "no results: the floor case, all cost and no payoff"),
)

#: A uuid that matches no user. The `created_by_user_id = :uid` arm is then
#: always false, which is the ordinary case: almost every search is against
#: the public catalogue. Using a real id would drag one person's private rows
#: into a published measurement.
NOBODY = "00000000-0000-0000-0000-000000000000"


def _database_url(expect_db: str) -> str:
    raw = dotenv_values(Path(__file__).resolve().parents[2] / ".env").get(
        "DATABASE_URL", ""
    )
    if not raw:
        raise SystemExit("DATABASE_URL is not set")
    parts = urlsplit(raw)
    name = parts.path.lstrip("/")
    if name != expect_db:
        # Never echoes the URL: the password lives in it.
        raise SystemExit(
            f"refusing to run: connected database is {name!r}, expected {expect_db!r}"
        )
    return urlunsplit(parts)


def _scan_summary(plan: dict) -> list[str]:
    """Flatten a plan tree into 'NodeType on relation via index' lines.

    The question this exists to answer is narrow -- did anything sequentially
    scan food_items -- so it reports scans and drops the joins and sorts.
    """
    out: list[str] = []

    def walk(node: dict) -> None:
        kind = node.get("Node Type", "")
        if "Scan" in kind:
            rel = node.get("Relation Name") or node.get("Alias") or "?"
            idx = node.get("Index Name")
            rows = node.get("Actual Rows")
            ms = node.get("Actual Total Time")
            line = f"{kind} on {rel}" + (f" using {idx}" if idx else "")
            out.append(f"{line}  ({rows} rows, {ms:.1f} ms)")
        for child in node.get("Plans", []) or []:
            walk(child)

    walk(plan)
    return out


async def _run(expect_db: str, limit: int, repeats: int, explain: bool) -> None:
    engine = create_async_engine(_database_url(expect_db), pool_pre_ping=False)
    fetch = min(MAX_ARM_FETCH, max(limit * ARM_OVERFETCH, ARM_OVERFETCH))

    print(
        f"catalogue benchmark - db={expect_db} - limit={limit} - "
        f"ARM_OVERFETCH={ARM_OVERFETCH} - MAX_ARM_FETCH={MAX_ARM_FETCH} - "
        f"per-arm fetch={fetch} - floor={WORD_SIMILARITY_FLOOR} - "
        f"{repeats} timed runs each"
    )
    print()
    header = (
        f"{'query':<16}{'db ms':>9}{'rank ms':>9}{'total':>8}"
        f"{'direct':>8}{'alias':>7}{'final':>7}"
    )
    print(header)
    print("-" * len(header))

    async with engine.connect() as conn:
        # READ ONLY for the whole session, not per statement: a stray write
        # anywhere below is refused by the server, not by my care.
        await conn.execute(text("SET TRANSACTION READ ONLY"))
        await conn.execute(
            text("SELECT set_config('pg_trgm.word_similarity_threshold', :f, false)"),
            {"f": str(WORD_SIMILARITY_FLOOR)},
        )
        n_items = await conn.scalar(text("SELECT count(*) FROM food_items"))
        n_alias = await conn.scalar(text("SELECT count(*) FROM food_aliases"))

        plans: list[tuple[str, list[str]]] = []
        for q, why in QUERIES:
            needle = q.strip().lower()
            params = {
                "q": needle,
                "uid": NOBODY,
                "prefix": f"{needle}%",
                "contains": f"%{needle}%",
                "fetch": fetch,
            }

            # Warm the cache once, untimed. Timing a cold buffer pool measures
            # the disk, not the query.
            await conn.execute(SEARCH_SQL, params)

            db_ms: list[float] = []
            rank_ms: list[float] = []
            rows: list = []
            ranked: list = []
            for _ in range(repeats):
                t0 = time.perf_counter()
                rows = (await conn.execute(SEARCH_SQL, params)).mappings().all()
                t1 = time.perf_counter()
                cands = [
                    alias_candidate(r) if r["arm"] == ARM_ALIAS else direct_candidate(r)
                    for r in rows
                ]
                ranked = rank(needle, cands, limit=limit)
                t2 = time.perf_counter()
                db_ms.append((t1 - t0) * 1000)
                rank_ms.append((t2 - t1) * 1000)

            direct_n = sum(1 for r in rows if r["arm"] == "direct")
            alias_n = len(rows) - direct_n
            d, k = statistics.median(db_ms), statistics.median(rank_ms)
            print(
                f"{q:<16}{d:>9.1f}{k:>9.2f}{d + k:>8.1f}"
                f"{direct_n:>8}{alias_n:>7}{len(ranked):>7}   {why}"
            )

            if explain:
                raw = await conn.execute(
                    text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(SEARCH_SQL)),
                    params,
                )
                doc = raw.scalar()
                if isinstance(doc, str):
                    doc = json.loads(doc)
                plans.append((q, _scan_summary(doc[0]["Plan"])))

        # Explicit rollback even though nothing wrote: leaves no
        # idle-in-transaction connection behind if this is run in a loop.
        await conn.rollback()

    print()
    print(f"food_items={n_items:,}  food_aliases={n_alias:,}")

    if explain:
        print()
        print("=== scan nodes (EXPLAIN ANALYZE) ===")
        for q, scans in plans:
            print()
            print(repr(q))
            for s in scans:
                bad = s.startswith("Seq Scan on food_items")
                print(f"   {s}{'  <-- SEQ SCAN ON food_items' if bad else ''}")

    await engine.dispose()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expect-db", default="trace")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--explain", action="store_true")
    a = ap.parse_args()
    asyncio.run(_run(a.expect_db, a.limit, a.repeats, a.explain))


if __name__ == "__main__":
    main()
