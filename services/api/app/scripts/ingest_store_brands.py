#!/usr/bin/env python3
"""Import supermarket private-label products from Open Food Facts.

WHY A SEPARATE SCRIPT FROM ingest_openfoodfacts.py
That one streams the 9 GB full dump and filters by country. This one asks the
OFF search index for specific brands, which means it runs in minutes over a
normal connection with nothing to download. For the store-brand problem that
is the right trade: we want ~60k specific products, not 4M general ones.

    python -m app.scripts.ingest_store_brands                  # everything
    python -m app.scripts.ingest_store_brands --countries us   # US only
    python -m app.scripts.ingest_store_brands --dry-run        # count, no write

WHICH ENDPOINT AND WHY
`world.openfoodfacts.org/api/v2/search` is heavily rate-limited (~10 req/min)
and, at the time of writing, frequently returns an HTML "temporarily
unavailable" page under load -- which a naive client parses as a JSON error
and reports as "brand not found". `search.openfoodfacts.org` is the
Search-a-licious index built for exactly this query shape and answers in tens
of milliseconds.

WHAT THE INDEX DOES NOT CARRY
Serving sizes and category tags are not in the search index, so rows imported
here get a plain 100 g serving and no category. That is a real limitation and
it is why `--enrich` exists: it re-fetches the full product for rows we kept,
at the cost of one request each. Without it, a Kirkland protein bar imports
with correct per-100 g nutrition but no "1 bar (60 g)" serving, and the user
has to type the grams.

EVERY ROW IS VALIDATED
Public nutrition data has a ~30% defect rate and store-brand entries are
crowd-typed, so they are worse than average. `nutrition_validator.validate`
quarantines anything whose macros cannot sum to its calories, and the report
at the end tells you how many were dropped. A silently-imported bad panel
becomes a wrong calorie count in someone's diary for months.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..db import SessionLocal
from ._schema_guard import require_tables
from ..models import FoodItem, FoodSource
from ..services.food_sources import _off_to_resolved  # noqa: PLC2701
from ..services.nutrition_validator import Verdict, validate
from .data.store_brands import brand_slugs, summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest.store")
settings = get_settings()

SEARCH_URL = "https://search.openfoodfacts.org/search"
PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"

# The index caps page_size; 100 is the documented maximum and anything larger
# is silently truncated, which would look like "this brand only has 100
# products" rather than an error.
PAGE_SIZE = 100

# Stop paging a single brand here. A few tags (`coop`, `u`) are extremely
# broad and would otherwise pull tens of thousands of loosely-related rows.
MAX_PAGES_PER_BRAND = 90

# Below this, OFF's own completeness score says the entry is a stub -- usually
# a name and a photo with no panel. Importing those adds search noise and no
# nutrition.
MIN_COMPLETENESS = 0.15

BATCH_SIZE = 500
CONCURRENCY = 6


def _normalise(hit: dict[str, Any]) -> dict[str, Any]:
    """Make a search-index hit look like a full OFF product document.

    The index returns `brands` as a LIST; the shared mapper expects the
    comma-joined STRING the product API returns, and would raise
    AttributeError on a list. Normalising here keeps the mapper single-source
    rather than teaching it about two payload shapes.
    """
    out = dict(hit)
    brands = hit.get("brands")
    if isinstance(brands, list):
        out["brands"] = ", ".join(str(b).strip() for b in brands if b)
    return out


def _validated_quality(resolved) -> float | None:
    """Run the panel through the quarantine checks. None means: drop it."""
    result = validate(
        {
            "calories": resolved.calories,
            "protein_g": resolved.protein_g,
            "carbs_g": resolved.carbs_g,
            "fat_g": resolved.fat_g,
            "fiber_g": resolved.fiber_g,
            "sugar_g": resolved.sugar_g,
            "saturated_fat_g": resolved.saturated_fat_g,
            "sodium_mg": resolved.sodium_mg,
        },
        source_quality=resolved.data_quality,
    )
    if result.verdict is Verdict.quarantine:
        return None
    return result.quality_score


async def fetch_brand(
    client: httpx.AsyncClient, slug: str
) -> list[dict[str, Any]]:
    """Page through one brand tag. Returns raw hits."""
    hits: list[dict[str, Any]] = []
    page = 1
    while page <= MAX_PAGES_PER_BRAND:
        try:
            r = await client.get(
                SEARCH_URL,
                params={
                    "q": f"brands_tags:{slug}",
                    "page_size": PAGE_SIZE,
                    "page": page,
                },
            )
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("  %s page %s failed: %s", slug, page, exc)
            break

        batch = data.get("hits") or []
        if not batch:
            break
        hits.extend(batch)
        if page == 1 and data.get("count"):
            log.info("  %-30s %s products", slug, data["count"])
        if page >= (data.get("page_count") or 1):
            break
        page += 1
    return hits


async def enrich(client: httpx.AsyncClient, code: str) -> dict[str, Any] | None:
    """Fetch the full product so we get a real serving size and categories."""
    try:
        r = await client.get(PRODUCT_URL.format(code=code))
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    return data.get("product") if data.get("status") == 1 else None


async def flush(batch: list[dict[str, Any]]) -> int:
    if not batch:
        return 0
    # A single INSERT ... ON CONFLICT cannot touch the same row twice, and two
    # retailers can legitimately surface the same barcode. Last one wins.
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in batch:
        unique[(row["source"], row["source_id"])] = row

    async with SessionLocal() as session:
        stmt = pg_insert(FoodItem).values(list(unique.values()))
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
                "sodium_mg": stmt.excluded.sodium_mg,
                "saturated_fat_g": stmt.excluded.saturated_fat_g,
                "serving_sizes": stmt.excluded.serving_sizes,
                "search_text": stmt.excluded.search_text,
                "data_quality": stmt.excluded.data_quality,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)
        await session.commit()
    return len(unique)


def _search_text(name: str, brand: str | None, retailer: str) -> str:
    """Include the RETAILER, not just the brand.

    Someone who bought a tub at Costco searches "costco protein" long before
    they remember the words "Kirkland Signature". Indexing the store name is
    what makes that search work, and it is the single most useful thing this
    script adds over a generic OFF import.
    """
    return " ".join(p for p in (name, brand or "", retailer) if p).lower()


async def run(args: argparse.Namespace) -> None:
    countries = (
        {c.strip().lower() for c in args.countries.split(",")}
        if args.countries
        else None
    )
    slugs = brand_slugs(countries)
    if args.limit_brands:
        slugs = slugs[: args.limit_brands]

    log.info("Registry: %s", summary())
    log.info("Importing %s brand tags%s", len(slugs),
             f" for {sorted(countries)}" if countries else "")

    if not args.dry_run:
        # Seeds insert data; migrations own schema. This line used to
        # call create_all, which changed the schema behind Alembic's
        # back and broke the next upgrade.
        await require_tables("food_items")

    now = datetime.now(timezone.utc)
    stats = {"hits": 0, "unusable": 0, "quarantined": 0, "thin": 0, "written": 0}
    empty_slugs: list[str] = []
    batch: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    sem = asyncio.Semaphore(CONCURRENCY)

    headers = {"User-Agent": settings.OFF_USER_AGENT}
    async with httpx.AsyncClient(timeout=45.0, headers=headers) as client:

        async def one(slug: str, retailer: str) -> tuple[str, str, list[dict]]:
            async with sem:
                return slug, retailer, await fetch_brand(client, slug)

        tasks = [one(slug, retailer) for slug, retailer, _ in slugs]
        for coro in asyncio.as_completed(tasks):
            slug, retailer, hits = await coro
            if not hits:
                empty_slugs.append(slug)
                continue

            for hit in hits:
                stats["hits"] += 1
                code = str(hit.get("code") or "")
                if not code or code in seen_codes:
                    continue
                seen_codes.add(code)

                if float(hit.get("completeness") or 0) < MIN_COMPLETENESS:
                    stats["thin"] += 1
                    continue

                product = _normalise(hit)
                if args.enrich:
                    full = await enrich(client, code)
                    if full:
                        product = full

                resolved = _off_to_resolved(product)
                if resolved is None:
                    stats["unusable"] += 1
                    continue

                quality = _validated_quality(resolved)
                if quality is None:
                    stats["quarantined"] += 1
                    continue

                batch.append(
                    {
                        "source": FoodSource.off.value,
                        "source_id": resolved.source_id,
                        "name": resolved.name[:250],
                        "brand": (resolved.brand or retailer)[:120],
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
                        "names_i18n": {},
                        "data_quality": quality,
                        "search_text": _search_text(
                            resolved.name, resolved.brand, retailer
                        )[:2000],
                        "updated_at": now,
                    }
                )

                if len(batch) >= BATCH_SIZE and not args.dry_run:
                    stats["written"] += await flush(batch)
                    batch = []

    if batch and not args.dry_run:
        stats["written"] += await flush(batch)
    elif batch:
        stats["written"] = len(batch)

    log.info("-" * 62)
    log.info("hits seen        %s", stats["hits"])
    log.info("too incomplete   %s", stats["thin"])
    log.info("no usable panel  %s", stats["unusable"])
    log.info("QUARANTINED      %s   (failed validation)", stats["quarantined"])
    log.info("WRITTEN          %s%s", stats["written"],
             "  [dry run -- nothing saved]" if args.dry_run else "")
    if empty_slugs:
        # Not an error. OFF brand tagging is crowd-sourced, so a slug can
        # simply be unused in a country. Printing them is how the registry
        # gets corrected over time.
        log.info("no results for %s tag(s): %s", len(empty_slugs),
                 ", ".join(sorted(empty_slugs)))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--countries", help="Comma-separated: us,uk,fr,de,es,it,nl,ch,se,pl")
    p.add_argument("--limit-brands", type=int, default=0)
    p.add_argument(
        "--enrich",
        action="store_true",
        help="Re-fetch each kept product for real serving sizes (much slower)",
    )
    p.add_argument("--dry-run", action="store_true")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
