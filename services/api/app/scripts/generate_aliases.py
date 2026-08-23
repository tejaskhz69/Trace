"""Generate the Phase 3a alias review artifact. READS ONLY.

    python -m app.scripts.generate_aliases --out generated_aliases.json

WHAT THIS DOES NOT DO
It does not INSERT. It does not UPDATE. It does not create `food_aliases` rows.
It selects a narrow projection of `food_items`, hands it to the pure functions
in `app/services/alias_gen.py`, and writes JSON to disk. Importing the aliases
is a separate, later step behind a human review of that file.

The read-only guarantee is not merely a convention here: the connection issues
`SET TRANSACTION READ ONLY` before touching anything, so Postgres itself will
reject a write even if a future edit to this file introduces one by accident.

SELECTION
  * the 347 curated dishes  (source = 'curated')
  * products from the 12 approved Indian brand families, matched with
    word-boundary regex rather than LIKE -- see BRAND_FAMILIES for why that
    distinction is worth 1,300 false positives on ITC alone.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ..config import get_settings
from ..services.alias_gen import (
    BRAND_FAMILIES,
    BRAND_ORDER,
    FoodRecord,
    generate,
    report_to_json,
)

DEFAULT_OUT = pathlib.Path("review") / "generated_aliases.json"

#: Postgres POSIX regex is case-insensitive via `~*`; the patterns in
#: BRAND_FAMILIES use \b, which Postgres spells \y. Translating here rather
#: than storing two dialects keeps one source of truth for the brand list.
def _pg_pattern(py_pattern: str) -> str:
    return py_pattern.replace(r"\b", r"\y")


SELECT_CURATED = """
    SELECT id::text AS id, name, brand, source::text AS source,
           cuisine, category, countries::text AS countries,
           names_i18n::text AS names_i18n
      FROM food_items
     WHERE source::text = 'curated'
"""

SELECT_BRANDS = """
    SELECT id::text AS id, name, brand, source::text AS source,
           cuisine, category, countries::text AS countries,
           names_i18n::text AS names_i18n
      FROM food_items
     WHERE brand IS NOT NULL AND brand <> ''
       AND ({clauses})
"""


def _to_record(row) -> FoodRecord:
    """Map one DB row onto the generator's narrow input dataclass."""
    try:
        names = json.loads(row.names_i18n) if row.names_i18n else {}
    except (ValueError, TypeError):
        names = {}
    aliases = names.get("aliases") if isinstance(names, dict) else None
    if not isinstance(aliases, list):
        aliases = []
    try:
        countries = json.loads(row.countries) if row.countries else []
    except (ValueError, TypeError):
        countries = []
    if not isinstance(countries, list):
        countries = []
    return FoodRecord(
        id=row.id,
        name=row.name or "",
        brand=row.brand,
        source=row.source,
        cuisine=row.cuisine,
        category=row.category,
        countries=tuple(str(c) for c in countries),
        # Sorted: names_i18n is JSONB and Postgres does not promise array order
        # stability across dumps. Sorting here is what keeps the artifact
        # deterministic across a restore.
        curated_aliases=tuple(sorted(str(a) for a in aliases if str(a).strip())),
    )


async def collect(url: str, expect_db: str | None, limit: int | None,
                  with_catalogue: bool):
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            # Postgres-enforced, not convention-enforced.
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            db = (await conn.execute(text("SELECT current_database()"))).scalar()
            if expect_db and db != expect_db:
                raise SystemExit(
                    "--expect-db %r does not match the connected database %r"
                    % (expect_db, db)
                )

            rows = list((await conn.execute(text(SELECT_CURATED))).all())
            curated_n = len(rows)

            clauses = " OR ".join(
                "brand ~* :p%d" % i for i in range(len(BRAND_ORDER))
            )
            params = {
                "p%d" % i: _pg_pattern(BRAND_FAMILIES[fam][0])
                for i, fam in enumerate(BRAND_ORDER)
            }
            brand_rows = list(
                (await conn.execute(text(SELECT_BRANDS.format(clauses=clauses)),
                                    params)).all()
            )
            rows.extend(brand_rows)

            catalogue: frozenset[str] = frozenset()
            if with_catalogue:
                catalogue = frozenset(
                    (await conn.execute(text(
                        "SELECT DISTINCT name_normalized FROM food_items "
                        "WHERE name_normalized <> ''"
                    ))).scalars().all()
                )

        records = [_to_record(r) for r in rows]
        # Deduplicate by id: a curated dish carrying an approved brand would
        # otherwise be generated for twice.
        seen: dict[str, FoodRecord] = {}
        for rec in records:
            seen.setdefault(rec.id, rec)
        records = sorted(seen.values(), key=lambda r: r.id)
        if limit:
            records = records[:limit]
        return records, curated_n, len(brand_rows), catalogue, db
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=str(DEFAULT_OUT),
                   help="review artifact path (default review/generated_aliases.json)")
    p.add_argument("--expect-db", metavar="NAME",
                   help="abort unless current_database() equals NAME")
    p.add_argument("--limit", type=int, default=None,
                   help="cap the number of foods (for smoke runs)")
    p.add_argument("--check-catalogue", action="store_true",
                   help="also flag aliases that shadow another food's name; "
                        "reads all 578k name_normalized values")
    args = p.parse_args(argv)

    url = get_settings().DATABASE_URL
    records, curated_n, brand_n, catalogue, db = asyncio.run(
        collect(url, args.expect_db, args.limit, args.check_catalogue)
    )

    report = generate(
        records,
        existing_food_names=catalogue,
        # Trivially satisfied here -- every id came from this SELECT -- but
        # passing it keeps the guard wired up for the fixture path, where a
        # hand-written input file CAN name a food that no longer exists.
        known_food_ids=frozenset(r.id for r in records),
    )
    report.sources = {
        "curated_dishes": curated_n,
        "brand_family_rows": brand_n,
        "foods_after_dedupe": len(records),
        "brand_families": list(BRAND_ORDER),
        "brand_family_count": len(BRAND_ORDER),
        "catalogue_names_checked": len(catalogue),
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report_to_json(report), encoding="utf-8")

    c = report.counts
    print("database            : %s (read-only transaction)" % db)
    print("curated dishes      : %d" % curated_n)
    print("brand-family rows   : %d" % brand_n)
    print("foods after dedupe  : %d" % c["input_foods"])
    print("candidates generated: %d" % c["candidates_generated"])
    print("accepted            : %d" % c["accepted"])
    print("rejected            : %d" % c["rejected"])
    print("findings            : %d  %s" % (c["findings"], c["findings_by_kind"]))
    print("by alias_type       : %s" % c["by_alias_type"])
    print("by rule             : %s" % c["by_rule"])
    print("input digest        : %s" % report.input_digest)
    print("written             : %s" % out.resolve())
    print()
    print("NOTHING WAS INSERTED. Review the artifact before any import step.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
