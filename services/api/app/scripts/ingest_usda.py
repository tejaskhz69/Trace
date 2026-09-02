#!/usr/bin/env python3
"""Bulk-import USDA FoodData Central into the catalogue.

WHY USDA AND NOT MORE OPEN FOOD FACTS
-------------------------------------
Open Food Facts is a *packaged goods* database: it will find your protein bar
and will never find "chicken curry". This project's differentiator is COOKED
DISHES, and the best free source of those on earth is USDA's FNDDS (Food and
Nutrient Database for Dietary Studies) -- the composite-food database behind
the US national dietary survey. It contains entries like "Chicken curry",
"Pad thai", "Lasagna with meat", "Beef and vegetable stir fry", each with a
full nutrient panel derived from measured ingredient data rather than a
manufacturer's label.

LICENCE
-------
FoodData Central is a work of the US federal government and is in the PUBLIC
DOMAIN. No attribution is required and no share-alike obligation attaches --
unlike Open Food Facts (ODbL), which does. That difference matters if you ever
build a proprietary derived dataset.

THE THREE DATASETS
------------------
    foundation  ~300 foods    tiny, highest analytical quality
    sr_legacy  ~7,800 foods   ingredients + many prepared dishes
    survey    ~7,000 foods    FNDDS -- the composite DISHES we actually want

sr_legacy + foundation is a ~10 MB download and lands ~8,000 rows in minutes.
survey is a 200 MB zip / 1.6 GB unzipped and is where the world's dishes are.

    python -m app.scripts.ingest_usda                    # legacy + foundation
    python -m app.scripts.ingest_usda --datasets survey  # the dish set
    python -m app.scripts.ingest_usda --datasets all     # everything

WHAT IS DELIBERATELY NOT IMPORTED
---------------------------------
Raw single ingredients that no one logs as a meal ("Oil, corn, industrial")
are kept, because a recipe needs them, but they are ranked below dishes by
`log_count` seeding. Baby food, pet food and pure supplement powders are
dropped -- they pollute search results for no benefit.

EVERY ROW STILL GOES THROUGH THE VALIDATOR. USDA is far cleaner than crowd-
sourced data, but "cleaner" is not "clean": unit errors and impossible panels
exist in every large nutrition dataset, and non-negotiable #6 says we
quarantine rather than serve them.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import logging
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import engine
from ..models import FoodItem, FoodSource
from ..services.nutrition_validator import Verdict, validate

log = logging.getLogger("usda")

BASE = "https://fdc.nal.usda.gov/fdc-datasets"

DATASETS: dict[str, str] = {
    "foundation": f"{BASE}/FoodData_Central_foundation_food_csv_2026-04-30.zip",
    "sr_legacy": f"{BASE}/FoodData_Central_sr_legacy_food_csv_2018-04.zip",
    "survey": f"{BASE}/FoodData_Central_survey_food_csv_2024-10-31.zip",
}

CACHE = Path(__file__).resolve().parent / "data" / "usda"

# FoodData Central nutrient numbers. These are `nutrient_nbr` in nutrient.csv
# and are stable across releases, unlike the surrogate `id` column.
NUTRIENT_NBR = {
    "208": "calories",          # Energy, kcal
    "203": "protein_g",
    "204": "fat_g",             # Total lipid (fat)
    "205": "carbs_g",           # Carbohydrate, by difference
    "291": "fiber_g",
    "269": "sugar_g",           # Sugars, total
    "307": "sodium_mg",
    "306": "potassium_mg",
    "606": "saturated_fat_g",
    "301": "calcium_mg",
    "303": "iron_mg",
}

# Micronutrients go in the JSONB blob rather than columns.
MICRO_KEYS = {"potassium_mg", "calcium_mg", "iron_mg"}

# FDC food categories we do not want polluting a meal search.
SKIP_CATEGORY_WORDS = (
    "baby food",
    "infant formula",
    "pet food",
)

# Words that mark a row as a composite DISH rather than a raw ingredient.
# Used only for ranking, never for exclusion.
DISH_HINTS = (
    " with ", " and ", "curry", "stew", "casserole", "soup", "salad",
    "sandwich", "pizza", "pasta", "stir fry", "stir-fry", "burrito", "taco",
    "sushi", "noodle", "fried rice", "biryani", "roll", "pie", "cake",
    "burger", "wrap", "bowl", "platter", "dish", "recipe",
)

# USDA's own category → our cuisine/category vocabulary. Coarse on purpose:
# a wrong specific label is worse than a right vague one.
CATEGORY_MAP = {
    "american indian/alaska native foods": ("global", "traditional"),
    "baked products": ("global", "bakery"),
    "beef products": ("global", "meat"),
    "beverages": ("global", "drink"),
    "breakfast cereals": ("global", "cereal"),
    "cereal grains and pasta": ("global", "grain"),
    "dairy and egg products": ("global", "dairy"),
    "fast foods": ("american", "fast_food"),
    "fats and oils": ("global", "fat"),
    "finfish and shellfish products": ("global", "seafood"),
    "fruits and fruit juices": ("global", "fruit"),
    "lamb, veal, and game products": ("global", "meat"),
    "legumes and legume products": ("global", "legume"),
    "meals, entrees, and side dishes": ("global", "dish"),
    "nut and seed products": ("global", "nuts"),
    "pork products": ("global", "meat"),
    "poultry products": ("global", "meat"),
    "restaurant foods": ("global", "restaurant"),
    "sausages and luncheon meats": ("global", "meat"),
    "snacks": ("global", "snack"),
    "soups, sauces, and gravies": ("global", "soup"),
    "spices and herbs": ("global", "spice"),
    "sweets": ("global", "sweet"),
    "vegetables and vegetable products": ("global", "vegetable"),
}

# USDA is analytically derived rather than label-transcribed, so it starts from
# a higher baseline trust than Open Food Facts. The validator still docks it.
SOURCE_QUALITY = {"foundation": 0.95, "sr_legacy": 0.85, "survey": 0.80}


def download(name: str, url: str, force: bool = False) -> Path:
    """Fetch a dataset zip, cached on disk."""
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / f"{name}.zip"
    if dest.exists() and not force and dest.stat().st_size > 0:
        log.info("%s: cached (%.1f MB)", name, dest.stat().st_size / 1e6)
        return dest

    log.info("%s: downloading %s", name, url)
    with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        got = 0
        tmp = dest.with_suffix(".part")
        with tmp.open("wb") as fh:
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
                got += len(chunk)
                if total:
                    pct = got / total * 100
                    print(f"\r  {name}: {got/1e6:6.1f}/{total/1e6:.1f} MB ({pct:4.1f}%)",
                          end="", flush=True)
        print()
        tmp.replace(dest)
    return dest


def _open_member(zf: zipfile.ZipFile, basename: str) -> io.TextIOWrapper | None:
    """Open one CSV by EXACT basename from inside the dated release directory.

    Exact, not suffix: these archives contain `food.csv` alongside
    `sr_legacy_food.csv` and `foundation_food.csv`, and `nutrient.csv`
    alongside `food_nutrient.csv`. A suffix match silently picks the wrong
    file and yields an empty import that looks like a data problem rather
    than a bug -- which is exactly what it did the first time.
    """
    want = basename.lower()
    for info in zf.infolist():
        if info.is_dir():
            continue
        if info.filename.rsplit("/", 1)[-1].lower() == want:
            return io.TextIOWrapper(zf.open(info), encoding="utf-8-sig", newline="")
    return None


def parse_dataset(path: Path, dataset: str) -> list[dict]:
    """Turn one FDC zip into candidate rows.

    Streams `food_nutrient.csv` rather than loading it: the survey release has
    millions of rows, and materialising them would need several gigabytes.
    """
    with zipfile.ZipFile(path) as zf:
        # --- nutrient.csv: surrogate id -> stable nutrient number ----------
        # TWO CONVENTIONS, AND THE FILE DOES NOT SAY WHICH IT USES.
        #
        # In SR Legacy, food_nutrient.nutrient_id is the surrogate `nutrient.id`
        # (energy = 1008). In FNDDS/survey it is the stable `nutrient_nbr`
        # itself (energy = 208). Assuming either one silently yields an import
        # with no calories at all — which is what happened first time: 5,372
        # foods parsed, 0 usable, and it looked like a data problem rather
        # than a bug.
        #
        # So build both maps and decide per file by sampling which one
        # actually hits.
        nutrient_fh = _open_member(zf, "nutrient.csv")
        if nutrient_fh is None:
            raise SystemExit(f"{path.name}: no nutrient.csv inside")
        by_id: dict[str, str] = {}
        by_nbr: dict[str, str] = {}
        for row in csv.DictReader(nutrient_fh):
            # nutrient_nbr is written as "208" or "208.0" depending on release.
            nbr = (row.get("nutrient_nbr") or "").strip().split(".")[0]
            if nbr in NUTRIENT_NBR:
                by_id[row["id"]] = NUTRIENT_NBR[nbr]
                by_nbr[nbr] = NUTRIENT_NBR[nbr]

        probe_fh = _open_member(zf, "food_nutrient.csv")
        if probe_fh is None:
            raise SystemExit(f"{path.name}: no food_nutrient.csv inside")
        hits_id = hits_nbr = 0
        for i, row in enumerate(csv.DictReader(probe_fh)):
            if i >= 20_000:
                break
            nid = row.get("nutrient_id", "")
            hits_id += nid in by_id
            hits_nbr += nid in by_nbr
        probe_fh.close()

        id_to_field = by_id if hits_id >= hits_nbr else by_nbr
        log.info(
            "%s: tracking %d nutrients, keyed by %s (probe: id=%d nbr=%d)",
            dataset, len(id_to_field),
            "nutrient.id" if id_to_field is by_id else "nutrient_nbr",
            hits_id, hits_nbr,
        )
        if max(hits_id, hits_nbr) == 0:
            log.error(
                "%s: neither key matched any nutrient row. The release format "
                "has changed -- inspect food_nutrient.csv before trusting this.",
                dataset,
            )

        # --- food_category.csv --------------------------------------------
        categories: dict[str, str] = {}
        cat_fh = _open_member(zf, "food_category.csv")
        if cat_fh is not None:
            for row in csv.DictReader(cat_fh):
                categories[row["id"]] = (row.get("description") or "").strip().lower()

        # --- food.csv ------------------------------------------------------
        food_fh = _open_member(zf, "food.csv")
        if food_fh is None:
            raise SystemExit(f"{path.name}: no food.csv inside")
        foods: dict[str, dict] = {}
        for row in csv.DictReader(food_fh):
            desc = (row.get("description") or "").strip()
            if not desc:
                continue
            cat = categories.get(row.get("food_category_id", ""), "")
            if any(w in cat for w in SKIP_CATEGORY_WORDS):
                continue
            if any(w in desc.lower() for w in SKIP_CATEGORY_WORDS):
                continue
            foods[row["fdc_id"]] = {
                "fdc_id": row["fdc_id"],
                "name": desc,
                "usda_category": cat,
                "n": {},
            }
        log.info("%s: %d foods", dataset, len(foods))

        # --- food_nutrient.csv (streamed) ----------------------------------
        fn_fh = _open_member(zf, "food_nutrient.csv")
        if fn_fh is None:
            raise SystemExit(f"{path.name}: no food_nutrient.csv inside")
        seen = 0
        for row in csv.DictReader(fn_fh):
            seen += 1
            field = id_to_field.get(row.get("nutrient_id", ""))
            if field is None:
                continue
            food = foods.get(row.get("fdc_id", ""))
            if food is None:
                continue
            try:
                food["n"][field] = float(row["amount"])
            except (TypeError, ValueError):
                continue
        log.info("%s: scanned %d nutrient rows", dataset, seen)

    return list(foods.values())


def to_row(food: dict, dataset: str) -> dict | None:
    """Map one parsed food onto a FoodItem row, or None if unusable."""
    n = food["n"]
    kcal = n.get("calories")
    # No energy value means no row. A dish with unknown calories is worse than
    # absent -- it looks logged and contributes nothing to the day's total.
    if kcal is None or kcal <= 0 or kcal > 900:
        return None

    nutriments = {
        "calories": kcal,
        "protein_g": n.get("protein_g", 0.0),
        "carbs_g": n.get("carbs_g", 0.0),
        "fat_g": n.get("fat_g", 0.0),
        "fiber_g": n.get("fiber_g", 0.0),
        "sugar_g": n.get("sugar_g", 0.0),
        "saturated_fat_g": n.get("saturated_fat_g", 0.0),
        "sodium_mg": n.get("sodium_mg", 0.0),
    }

    cuisine, category = CATEGORY_MAP.get(food["usda_category"], (None, None))

    result = validate(
        nutriments,
        category=category,
        source_quality=SOURCE_QUALITY.get(dataset, 0.8),
    )
    if result.verdict is Verdict.quarantine:
        return None

    name = food["name"]
    lower = name.lower()
    micro = {k: n[k] for k in MICRO_KEYS if k in n}

    # Dishes rank above raw ingredients in search. Seeding log_count is the
    # least invasive way to express that -- the search ORDER BY already uses
    # it, so no query changes are needed.
    is_dish = any(h in lower for h in DISH_HINTS)

    return {
        "source": FoodSource.usda,
        "source_id": f"usda:{food['fdc_id']}",
        "name": name[:200],
        "brand": None,
        "calories": round(kcal, 1),
        "protein_g": round(nutriments["protein_g"], 2),
        "carbs_g": round(nutriments["carbs_g"], 2),
        "fat_g": round(nutriments["fat_g"], 2),
        "fiber_g": round(nutriments["fiber_g"], 2),
        "sugar_g": round(nutriments["sugar_g"], 2),
        "sodium_mg": round(nutriments["sodium_mg"], 1),
        "saturated_fat_g": round(nutriments["saturated_fat_g"], 2),
        "micronutrients": micro,
        # MUST be set explicitly. `default_factory` on the SQLModel field is a
        # PYTHON-side default and does not run for a Core bulk insert, so
        # omitting these writes SQL NULL into columns the response schema
        # types as dict/list -- which serialises fine into the database and
        # then 500s on every search that touches the row. Silent on write,
        # fatal on read.
        "names_i18n": {},
        "serving_sizes": [],
        "cuisine": cuisine,
        "category": category,
        "countries": ["united-states"],
        "data_quality": result.quality_score,
        "is_verified": True,
        "moderation_status": "approved",
        "search_text": f"{name} {food['usda_category']}".lower(),
        "log_count": 5 if is_dish else 0,
        "updated_at": datetime.now(UTC),
    }


async def write(rows: list[dict], batch: int = 500) -> int:
    """Upsert on (source, source_id) so a re-run corrects rather than duplicates."""
    written = 0
    async with engine.begin() as conn:
        for i in range(0, len(rows), batch):
            chunk = rows[i : i + batch]
            stmt = pg_insert(FoodItem).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_food_source",
                set_={
                    k: getattr(stmt.excluded, k)
                    for k in chunk[0]
                    if k not in ("source", "source_id")
                },
            )
            await conn.execute(stmt)
            written += len(chunk)
            print(f"\r  writing {written}/{len(rows)}", end="", flush=True)
    print()
    return written


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--datasets",
        default="sr_legacy,foundation",
        help="Comma list, or 'all'. survey is the 200 MB dish set.",
    )
    ap.add_argument("--force-download", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    names = (
        list(DATASETS) if args.datasets == "all" else
        [d.strip() for d in args.datasets.split(",") if d.strip()]
    )
    unknown = [d for d in names if d not in DATASETS]
    if unknown:
        raise SystemExit(f"Unknown dataset(s): {unknown}. Choose from {list(DATASETS)}")

    all_rows: list[dict] = []
    stats: dict[str, tuple[int, int]] = {}

    for name in names:
        path = download(name, DATASETS[name], force=args.force_download)
        foods = parse_dataset(path, name)
        rows = [r for r in (to_row(f, name) for f in foods) if r is not None]
        stats[name] = (len(foods), len(rows))
        log.info(
            "%s: %d usable of %d (%d quarantined or unusable)",
            name, len(rows), len(foods), len(foods) - len(rows),
        )
        all_rows.extend(rows)

    # A food can appear in more than one dataset. Last wins, which given the
    # order above means the higher-quality dataset overwrites -- and the
    # database upsert would do the same thing anyway.
    dedup = {r["source_id"]: r for r in all_rows}
    rows = list(dedup.values())
    if args.limit:
        rows = rows[: args.limit]

    print()
    for name, (raw, ok) in stats.items():
        print(f"  {name:12} {ok:6} usable / {raw:6} parsed")
    print(f"  {'TOTAL':12} {len(rows):6} unique rows")

    if args.dry_run:
        print("\nDry run: nothing written.")
        for r in rows[:8]:
            print(f"    {r['name'][:56]:58} {r['calories']:6.0f} kcal  q={r['data_quality']}")
        return

    written = await write(rows)
    print(f"\nWrote {written} rows.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
