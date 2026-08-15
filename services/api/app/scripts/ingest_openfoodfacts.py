#!/usr/bin/env python3
"""Bulk-import Open Food Facts into the local catalogue.

WHY BULK IMPORT AT ALL
----------------------
The live API is fine as a miss-handler, but it is rate-limited (~100 req/min
for product reads, ~10/min for search) and adds 300-800 ms to a scan. Bulk
importing the products your users are likely to scan means the common path is
a local index lookup in single-digit milliseconds, and the API only fires for
the long tail.

SOURCE
------
Open Food Facts publishes a full JSONL dump (~4M products) and a Parquet
export on Hugging Face. The JSONL is the easiest to stream without loading
everything into memory:

    https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz

Licensing: Open Database License (ODbL) for the database, Database Contents
License for the contents. You MUST attribute Open Food Facts and, if you
redistribute a modified database, share it back under the same licence. Using
it inside your app and attributing it in your credits screen is fine; check
with a lawyer before you build a proprietary derived database you resell.

USAGE
-----
    # Everything (~4M rows, expect 1-3 hours and ~6 GB of Postgres)
    python -m app.scripts.ingest_openfoodfacts --dump openfoodfacts-products.jsonl.gz

    # Just India + a global core -- the sane first import (~250k rows)
    python -m app.scripts.ingest_openfoodfacts \\
        --dump openfoodfacts-products.jsonl.gz \\
        --countries india,united-states,united-kingdom \\
        --min-completeness 0.35

    # Stream straight from the URL without saving 9 GB to disk
    python -m app.scripts.ingest_openfoodfacts --stream-url
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import SessionLocal, init_db
from ..models import FoodItem, FoodSource
from ..services.food_sources import _off_to_resolved  # noqa: PLC2701

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest.off")

DUMP_URL = "https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz"
BATCH_SIZE = 2_000


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as fh:  # type: ignore[operator]
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def iter_jsonl_url(url: str) -> Iterator[dict[str, Any]]:
    """Stream and decompress on the fly -- no 9 GB temp file."""
    import httpx

    with httpx.stream("GET", url, timeout=None, follow_redirects=True) as r:
        r.raise_for_status()
        decompressor = gzip.GzipFile(fileobj=_ByteStream(r.iter_bytes()))
        for raw in decompressor:
            try:
                yield json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue


class _ByteStream:
    """Adapt an iterator of chunks into a file-like object for GzipFile."""

    def __init__(self, chunks):
        self._chunks = chunks
        self._buf = b""

    def read(self, n: int = -1) -> bytes:
        while n < 0 or len(self._buf) < n:
            try:
                self._buf += next(self._chunks)
            except StopIteration:
                break
        if n < 0:
            out, self._buf = self._buf, b""
            return out
        out, self._buf = self._buf[:n], self._buf[n:]
        return out


def should_keep(
    product: dict[str, Any],
    countries: set[str] | None,
    min_completeness: float,
) -> bool:
    if countries:
        tags = {
            t.replace("en:", "") for t in (product.get("countries_tags") or [])
        }
        if not (tags & countries):
            return False
    try:
        if float(product.get("completeness") or 0) < min_completeness:
            return False
    except (TypeError, ValueError):
        return False
    # Must have a barcode -- that's the whole point of importing this dataset.
    return bool(product.get("code"))


def build_search_text(name: str, brand: str | None, categories: list[str]) -> str:
    parts = [name, brand or ""]
    parts.extend(c.replace("en:", "").replace("-", " ") for c in (categories or [])[:5])
    return " ".join(p for p in parts if p).lower()


async def flush(batch: list[dict[str, Any]]) -> int:
    if not batch:
        return 0
    async with SessionLocal() as session:
        stmt = pg_insert(FoodItem).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_food_source",
            set_={
                "name": stmt.excluded.name,
                "brand": stmt.excluded.brand,
                "barcode": stmt.excluded.barcode,
                "calories": stmt.excluded.calories,
                "protein_g": stmt.excluded.protein_g,
                "carbs_g": stmt.excluded.carbs_g,
                "fat_g": stmt.excluded.fat_g,
                "fiber_g": stmt.excluded.fiber_g,
                "sugar_g": stmt.excluded.sugar_g,
                "serving_sizes": stmt.excluded.serving_sizes,
                "search_text": stmt.excluded.search_text,
                "data_quality": stmt.excluded.data_quality,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)
        await session.commit()
    return len(batch)


async def run(args: argparse.Namespace) -> None:
    await init_db()

    countries = (
        {c.strip().lower() for c in args.countries.split(",")} if args.countries else None
    )

    source = (
        iter_jsonl_url(DUMP_URL) if args.stream_url else iter_jsonl(Path(args.dump))
    )

    seen = kept = written = 0
    batch: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for product in source:
        seen += 1
        if seen % 100_000 == 0:
            log.info("scanned=%s kept=%s written=%s", seen, kept, written)

        if not should_keep(product, countries, args.min_completeness):
            continue

        resolved = _off_to_resolved(product)
        if resolved is None:
            continue

        kept += 1
        batch.append(
            {
                "source": FoodSource.off.value,
                "source_id": resolved.source_id,
                "name": resolved.name[:250],
                "brand": (resolved.brand or None) and resolved.brand[:120],
                "barcode": resolved.barcode,
                "calories": resolved.calories,
                "protein_g": resolved.protein_g,
                "carbs_g": resolved.carbs_g,
                "fat_g": resolved.fat_g,
                "fiber_g": resolved.fiber_g,
                "sugar_g": resolved.sugar_g,
                "sodium_mg": resolved.sodium_mg,
                "saturated_fat_g": resolved.saturated_fat_g,
                "serving_sizes": resolved.serving_sizes,
                "is_liquid": resolved.is_liquid,
                "countries": resolved.countries,
                "data_quality": resolved.data_quality,
                "search_text": build_search_text(
                    resolved.name, resolved.brand, product.get("categories_tags") or []
                )[:2000],
                "updated_at": now,
            }
        )

        if len(batch) >= BATCH_SIZE:
            written += await flush(batch)
            batch = []

        if args.limit and kept >= args.limit:
            break

    written += await flush(batch)
    log.info("DONE scanned=%s kept=%s written=%s", seen, kept, written)


def main() -> None:
    p = argparse.ArgumentParser(description="Import Open Food Facts into Trace.")
    p.add_argument("--dump", help="Path to openfoodfacts-products.jsonl.gz")
    p.add_argument("--stream-url", action="store_true", help="Stream from OFF instead")
    p.add_argument(
        "--countries",
        help="Comma-separated country tags to keep, e.g. india,united-states",
    )
    p.add_argument("--min-completeness", type=float, default=0.25)
    p.add_argument("--limit", type=int, default=0, help="Stop after N kept rows")
    args = p.parse_args()

    if not args.dump and not args.stream_url:
        p.error("Pass --dump PATH or --stream-url")

    asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
