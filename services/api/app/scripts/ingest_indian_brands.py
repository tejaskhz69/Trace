#!/usr/bin/env python3
"""Brand-targeted import of Indian packaged foods from the Open Food Facts dump.

WHY BY BARCODE PREFIX, NOT BRAND NAME
-------------------------------------
Brand-name matching in Open Food Facts is unreliable: the same company appears
as "MTR", "MTR Foods", "M.T.R.", "Mtr Foods Pvt Ltd", and misspelt variants.
The GS1 company prefix is assigned by GS1 India and is stable, so every product
a company registers carries it. Filtering the dump on prefix gets you the whole
catalogue including SKUs whose brand field was typed badly or left blank.

Prefixes below were confirmed against real products in OFF (Aug 2026).

EVERY ROW IS VALIDATED
----------------------
Rows that fail `nutrition_validator` are written to a quarantine file rather
than the catalogue. Public Indian food data has a high defect rate -- in a
manual sweep of ~55 products across 12 brands, roughly a third had at least one
implausible value, including one (MTR Rava Idli) whose protein was wrong by 7x.
Importing that unchecked would silently corrupt users' logs.

USAGE
    # Download the dump once (~9 GB uncompressed)
    wget https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz

    python -m app.scripts.ingest_indian_brands --dump openfoodfacts-products.jsonl.gz
    python -m app.scripts.ingest_indian_brands --dump ... --brand MTR --dry-run
    python -m app.scripts.ingest_indian_brands --dump ... --all-india
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import SessionLocal
from ._schema_guard import require_tables
from ..models import FoodItem, FoodSource
from ..services import nutrition_validator as nv
from ..services.food_sources import _off_to_resolved  # noqa: PLC2701
from .ingest_openfoodfacts import iter_jsonl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest.brands")

BATCH_SIZE = 500

# GS1 company prefixes. India's country prefix is 890; the digits after it
# identify the company.
BRAND_PREFIXES: dict[str, list[str]] = {
    "MTR": ["8901042"],
    "Gits": ["8901155"],
    "Aachi": ["8906021", "8904209"],
    "Sakthi": ["8906002"],
    "Eastern": ["8901440", "8902850"],
    "Nirapara": ["8904010"],
    "Double Horse": ["8904011"],
    "Brahmins": ["8906014"],
    "Melam": ["8901743"],
    "Anil": ["8906042"],
    "Bambino": ["8904287"],
    "Pintola": ["8906136"],
    # Widen as you discover more. Log every barcode miss in production and
    # mine that log for prefixes worth adding -- it's demand-ranked for free.
    "Priya": ["785018"],          # US-registered (UPC), not an 890 prefix
}

PREFIX_TO_BRAND: dict[str, str] = {
    p: brand for brand, prefixes in BRAND_PREFIXES.items() for p in prefixes
}


# ---------------------------------------------------------------------------
# Category inference -- drives which validation band applies
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("batter", ("batter", "idli dosa batter")),
    ("vermicelli", ("vermicelli", "semiya", "seviyan", "noodle")),
    ("sweet_powder", ("chukku kappi", "sukku malli", "panakam", "jaggery coffee")),
    ("sweet_mix", ("gulab jamun", "jamun", "payasam", "kheer", "halwa",
                   "rasgulla", "sweet mix", "dessert", "mysore pak")),
    ("masala", ("masala", "powder", "podi", "chutney powder", "sambar powder",
                "rasam powder", "curry powder", "spice", "chilli")),
    ("flour", ("podi", "flour", "atta", "maida", "rice powder", "puttu",
               "idiyappam", "pathiri", "besan")),
    ("dry_mix", ("mix", "instant", "ready", "premix")),
]


def infer_category(name: str, categories_tags: list[str]) -> str | None:
    haystack = " ".join([name.lower(), *[t.lower() for t in categories_tags or []]])
    # Order matters: "sambar powder" must hit masala before flour.
    for category, keywords in CATEGORY_KEYWORDS:
        if any(k in haystack for k in keywords):
            return category
    return None


def infer_is_salted(name: str, category: str | None) -> bool:
    lowered = name.lower()
    if any(s in lowered for s in ("gulab", "jamun", "payasam", "kheer",
                                 "halwa", "sweet", "sugar")):
        return False
    return category in ("dry_mix", "masala", "prepared", "batter")


def parse_ingredients(product: dict[str, Any]) -> list[tuple[str, float]] | None:
    """Pull (ingredient, percent) pairs where OFF has estimated them.

    This is what powers the ingredient-consistency check that caught the MTR
    rava idli protein error.
    """
    out: list[tuple[str, float]] = []
    for ing in product.get("ingredients") or []:
        name = (ing.get("text") or ing.get("id") or "").replace("en:", "").strip()
        pct = ing.get("percent") or ing.get("percent_estimate")
        if name and pct:
            try:
                out.append((name, float(pct)))
            except (TypeError, ValueError):
                continue
    return out or None


def matches(barcode: str, wanted_prefixes: set[str] | None, all_india: bool) -> str | None:
    """Return the brand name if this barcode is one we want."""
    if all_india and barcode.startswith("890"):
        for prefix, brand in PREFIX_TO_BRAND.items():
            if barcode.startswith(prefix):
                return brand
        return "Other (India)"
    for prefix, brand in PREFIX_TO_BRAND.items():
        if wanted_prefixes and prefix not in wanted_prefixes:
            continue
        if barcode.startswith(prefix):
            return brand
    return None


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


async def flush(rows: list[dict]) -> int:
    if not rows:
        return 0
    async with SessionLocal() as session:
        stmt = pg_insert(FoodItem).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_food_source",
            set_={
                k: getattr(stmt.excluded, k)
                for k in (
                    "name", "brand", "barcode", "calories", "protein_g",
                    "carbs_g", "fat_g", "fiber_g", "sugar_g",
                    "saturated_fat_g", "sodium_mg", "serving_sizes",
                    "names_i18n", "data_quality", "is_verified",
                    "moderation_status", "search_text", "updated_at",
                )
            },
        )
        await session.execute(stmt)
        await session.commit()
    return len(rows)


async def run(args: argparse.Namespace) -> None:
    if not args.dry_run:
        # Seeds insert data; migrations own schema. This line used to
        # call create_all, which changed the schema behind Alembic's
        # back and broke the next upgrade.
        await require_tables("food_items")

    wanted = None
    if args.brand:
        if args.brand not in BRAND_PREFIXES:
            raise SystemExit(
                f"Unknown brand {args.brand!r}. Known: {', '.join(BRAND_PREFIXES)}"
            )
        wanted = set(BRAND_PREFIXES[args.brand])

    now = datetime.now(timezone.utc)
    rows: list[dict] = []
    quarantine: list[dict] = []
    stats = {"scanned": 0, "matched": 0, "accepted": 0, "quarantined": 0,
             "unparseable": 0}
    per_brand: dict[str, int] = {}
    seen_panels: list[dict] = []

    for product in iter_jsonl(Path(args.dump)):
        stats["scanned"] += 1
        if stats["scanned"] % 250_000 == 0:
            log.info("scanned=%(scanned)s matched=%(matched)s "
                     "accepted=%(accepted)s quarantined=%(quarantined)s", stats)

        barcode = str(product.get("code") or "")
        if not barcode:
            continue

        brand = matches(barcode, wanted, args.all_india)
        if brand is None:
            continue
        stats["matched"] += 1

        resolved = _off_to_resolved(product)
        if resolved is None:
            stats["unparseable"] += 1
            continue

        nutriments = {
            "calories": resolved.calories,
            "protein_g": resolved.protein_g,
            "carbs_g": resolved.carbs_g,
            "fat_g": resolved.fat_g,
            "fiber_g": resolved.fiber_g,
            "sugar_g": resolved.sugar_g,
            "saturated_fat_g": resolved.saturated_fat_g,
            "sodium_mg": resolved.sodium_mg,
        }
        category = infer_category(resolved.name, product.get("categories_tags") or [])

        result = nv.validate(
            nutriments,
            category=category,
            ingredients=parse_ingredients(product),
            is_salted=infer_is_salted(resolved.name, category),
            source_quality=resolved.data_quality,
        )

        seen_panels.append({"id": barcode, "brand": brand, **nutriments})

        if not result.is_servable:
            stats["quarantined"] += 1
            quarantine.append(
                {
                    "barcode": barcode,
                    "brand": brand,
                    "name": resolved.name,
                    "category": category,
                    "nutriments": nutriments,
                    "errors": [
                        {"code": i.code, "message": i.message,
                         "field": i.field, "observed": i.observed,
                         "expected": i.expected}
                        for i in result.issues
                        if i.severity is not nv.Severity.info
                    ],
                }
            )
            continue

        stats["accepted"] += 1
        per_brand[brand] = per_brand.get(brand, 0) + 1

        rows.append(
            {
                "source": FoodSource.off.value,
                "source_id": resolved.source_id,
                "name": resolved.name[:250],
                "brand": (resolved.brand or brand)[:120],
                "barcode": barcode,
                "calories": resolved.calories,
                "protein_g": resolved.protein_g,
                "carbs_g": resolved.carbs_g,
                "fat_g": resolved.fat_g,
                "fiber_g": resolved.fiber_g,
                "sugar_g": resolved.sugar_g,
                "saturated_fat_g": resolved.saturated_fat_g,
                "sodium_mg": resolved.sodium_mg,
                "serving_sizes": resolved.serving_sizes,
                "is_liquid": resolved.is_liquid,
                "countries": resolved.countries or ["india"],
                "cuisine": "indian",
                "category": category,
                "names_i18n": {
                    "aliases": [brand.lower(), resolved.name.lower()],
                    "basis": "as_sold",
                    "validation": [i.code for i in result.issues],
                },
                "data_quality": result.quality_score,
                "is_verified": False,
                "moderation_status": "approved",
                "search_text": " ".join(
                    [resolved.name, brand, category or ""]
                ).lower()[:2000],
                "updated_at": now,
            }
        )

        if len(rows) >= BATCH_SIZE and not args.dry_run:
            await flush(rows)
            rows = []

    if not args.dry_run:
        await flush(rows)

    # Duplicate-panel sweep, per brand -- catches generic panels reused
    # across SKUs (Eastern reuses one block across four products).
    by_brand: dict[str, list[dict]] = {}
    for p in seen_panels:
        by_brand.setdefault(p["brand"], []).append(p)
    for brand, items in by_brand.items():
        dupes = nv.flag_duplicate_panels(items, threshold=3)
        for fp, ids in dupes.items():
            log.warning(
                "%s: %d SKUs share one identical panel (%s...). Likely a "
                "generic block reused, not %d measurements -- downgrade these.",
                brand, len(ids), ", ".join(ids[:4]), len(ids),
            )

    log.info("=" * 66)
    log.info("scanned=%(scanned)s matched=%(matched)s accepted=%(accepted)s "
             "quarantined=%(quarantined)s unparseable=%(unparseable)s", stats)
    for brand, count in sorted(per_brand.items(), key=lambda x: -x[1]):
        log.info("  %-16s %d", brand, count)

    if quarantine:
        out = Path(args.quarantine_file)
        out.write_text(json.dumps(quarantine, indent=2, ensure_ascii=False))
        log.warning(
            "Wrote %d quarantined products to %s. Review these -- each one is "
            "a product your users can scan but will get wrong data for.",
            len(quarantine), out,
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", required=True,
                    help="Path to openfoodfacts-products.jsonl.gz")
    ap.add_argument("--brand", default=None,
                    help=f"One of: {', '.join(BRAND_PREFIXES)}")
    ap.add_argument("--all-india", action="store_true",
                    help="Import every 890-prefixed product, not just the "
                         "brands we know")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quarantine-file", default="quarantine.json")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
