"""Measure the catalogue's defect rate -- twice, with and without the sodium bug.

WHY TWICE
---------
`check_sodium` used to fire `sodium_near_zero_on_salted_product` on any panel
under 50 mg sodium, because `is_salted` defaulted to True with no evidence
that the product contained salt. Raw chicken, plain rice, whole milk, olive
oil and boiled lentils all tripped it. Four warnings compound into
`too_many_warnings`, which is an error, which is a quarantine -- so a single
unevidenced assumption could carry an otherwise-sound row over the line.

That means every defect figure this project has quoted, including the August
"1 in 3 Indian products are defective" claim, is part food problem and part
artefact, with no way to tell which from a single number. So run it both ways
and subtract:

  RUN A   is_salted=True for every row  -- the behaviour as it shipped
  RUN B   is_salted derived from name / ingredients / category

The delta is the number of rows the default was condemning on its own.

WHY ARM A IS A FROZEN FILE AND NOT A SET OF FLAGS
It was flags, once, and that was a mistake. While the sodium default was the
only difference, `is_salted=True` reproduced August exactly. Then the Atwater
check was fixed and the change applied to BOTH arms, so Arm A quietly became
"August's sodium bug with September's energy model" -- a baseline for a
question nobody asked, and the drift was only visible because the numbers
moved. `tests/frozen/nutrition_validator_august.py` cannot drift.

The one addition that file carries over true August -- the schema pre-check --
is inert here: it only rejects a record with no `calories`, and every row
either arm judges has one. The `unreadable` count is reported for both arms so
that this is checked rather than assumed.

THIS SCRIPT NEVER WRITES.
The connection is opened read-only at the transaction level, so a stray
INSERT would raise rather than land. Nothing here proposes a migration and
nothing here repairs a row -- a defective row a user searches for is more
useful than an absent one, because the absence is invisible and the defect is
fixable.

WHAT A SWEEP OF `food_items` CAN AND CANNOT MEASURE
---------------------------------------------------
Every importer DROPS a quarantined row rather than storing it -- `ingest_usda`
returns None, `ingest_store_brands` skips, `paid_sources` returns None. So the
catalogue holds only rows that already passed the gate, and re-running the
validator over it answers "how many stored rows would the new gate treat
differently", NOT "how defective is the incoming data".

The August "1 in 3" figure is a claim about the SECOND question, so it cannot
be reproduced from stored rows alone. `--usda` therefore re-reads the cached
FDC release and judges the stream as it arrives, which is the same population
the original figure was drawn from. The equivalent for the Indian claim needs
the Open Food Facts dump, which is not cached locally.

Usage:
    python -m app.scripts.audit_catalogue --usda           # cached FDC release
    python -m app.scripts.audit_catalogue                  # full DB sweep
    python -m app.scripts.audit_catalogue --sample 20000   # reproducible sample
    python -m app.scripts.audit_catalogue --json out.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import pathlib
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ..config import get_settings
from ..services import nutrition_validator as nv


def _load_august_validator():
    """Load the frozen August validator BY PATH, not as a package import.

    Arm A must be the code that actually shipped, not a reconstruction of it
    from arguments about which flags to pass. Reproducing old behaviour by
    setting `is_salted=True` on the current validator worked while sodium was
    the only difference; it stopped working the moment `check_atwater` changed
    underneath both arms, and the drift was invisible until the numbers moved.

    Loading by path keeps `tests/frozen/` off the import graph entirely, so
    application code cannot reach the deliberately-buggy copy even by mistake.
    """
    import importlib.util

    here = pathlib.Path(__file__).resolve()
    frozen = here.parents[2] / "tests" / "frozen" / "nutrition_validator_august.py"
    if not frozen.exists():
        raise SystemExit(
            f"The frozen August validator is missing: {frozen}\n"
            "Arm A cannot be reconstructed by argument -- see its header."
        )
    spec = importlib.util.spec_from_file_location(
        "_frozen_nutrition_validator_august", frozen
    )
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves its own module out of sys.modules while the class
    # body executes, so the entry has to exist BEFORE exec_module, not after.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


august = _load_august_validator()

#: The canonical panel fields, which are exactly the FoodItem columns the
#: validator reads. Named once so the SELECT and the dict cannot drift apart.
PANEL_FIELDS = (
    "calories",
    "protein_g",
    "carbs_g",
    "fat_g",
    "fiber_g",
    "sugar_g",
    "sodium_mg",
    "saturated_fat_g",
)

#: GS1 India. Company prefixes issued to Indian members all begin 890.
INDIA_GS1 = "890"

#: How many rows to pull per round trip.
BATCH = 5_000


def mask(url: str) -> str:
    """Never print a credential, not even into a log nobody reads."""
    return re.sub(r"://([^:/@]+):([^@]*)@", r"://\1:****@", url)


# ---------------------------------------------------------------------------
# Accumulator
# ---------------------------------------------------------------------------


@dataclass
class Tally:
    """Everything one run of the validator produced, in one place."""

    label: str
    verdicts: Counter = field(default_factory=Counter)
    by_source: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    by_india: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    codes: Counter = field(default_factory=Counter)
    #: How many warnings a row collected, so the `too_many_warnings` threshold
    #: can be argued about with numbers instead of intuition.
    warning_counts: Counter = field(default_factory=Counter)
    #: Rows whose ONLY complaint was the near-zero-sodium one.
    sodium_only: int = 0
    salt_evidence: Counter = field(default_factory=Counter)

    def add(self, result: Any, source: str, indian: bool) -> None:
        """Accepts a result from either arm -- the frozen module has its own
        Severity enum, so severities are compared by VALUE, never by identity."""
        v = result.verdict.value
        self.verdicts[v] += 1
        self.by_source[source][v] += 1
        self.by_india["india" if indian else "rest"][v] += 1

        warnings = 0
        for issue in result.issues:
            self.codes[issue.code] += 1
            if issue.severity.value == "warning":
                warnings += 1
        self.warning_counts[warnings] += 1

        codes = {i.code for i in result.issues}
        if codes == {"sodium_near_zero_on_salted_product"}:
            self.sodium_only += 1

    def rate(self, total: int) -> float:
        """Share of rows that are not cleanly servable."""
        bad = total - self.verdicts.get("accept", 0)
        return bad / total if total else 0.0

    def defect_rate(self, total: int) -> float:
        """Share quarantined outright -- the '1 in 3' sense of 'defective'."""
        return self.verdicts.get("quarantine", 0) / total if total else 0.0


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


async def stream_rows(conn, sample: int | None, seed: float) -> Iterable[Any]:
    """Yield rows in batches. Report-only: the transaction is read-only."""
    cols = ", ".join(PANEL_FIELDS)
    where = ""
    if sample:
        # Deterministic so Run A and Run B see identical rows, and so the
        # whole audit can be repeated and checked.
        await conn.execute(text("SELECT setseed(:s)"), {"s": seed})
        where = ""

    order = " ORDER BY random()" if sample else ""
    limit = f" LIMIT {int(sample)}" if sample else ""
    sql = (
        f"SELECT id, name, source, category, barcode, gtin14, data_quality, "
        f"{cols} FROM food_items{where}{order}{limit}"
    )
    result = await conn.stream(text(sql))
    async for partition in result.partitions(BATCH):
        for row in partition:
            yield row


def judge(
    panel: dict[str, float],
    *,
    name: str | None,
    category: str | None,
    quality: float,
    carb_convention: str = nv.CARB_UNKNOWN,
) -> tuple[Any, nv.ValidationResult, bool | None]:
    """Run both validators over one panel. Returns (run A, run B, evidence)."""
    # Arm A: the frozen August module. Its own defaults ARE the bug -- the
    # sodium assumption and the flat 4/4/9 sum together -- so nothing is
    # passed to re-create them.
    a = august.validate(panel, category=category, source_quality=quality)
    b = nv.validate(
        panel, category=category, name=name, source_quality=quality,
        carb_convention=carb_convention,
    )
    return a, b, nv.infer_is_salted(name=name, category=category)


# ---------------------------------------------------------------------------
# Offline: the cached USDA release, judged as it arrives
# ---------------------------------------------------------------------------


def audit_usda_cache(run_a: Tally, run_b: Tally) -> int:
    """Judge the incoming FDC stream, not the rows that survived the gate.

    This is the population the August defect figure was drawn from, and it is
    reachable with no database at all because `ingest_usda` caches the release
    zips on disk.
    """
    from .ingest_usda import CACHE, CATEGORY_MAP, SOURCE_QUALITY, parse_dataset

    total = 0
    for dataset in ("foundation", "sr_legacy", "survey"):
        path = CACHE / f"{dataset}.zip"
        if not path.exists():
            print(f"  {dataset}: not cached, skipped")
            continue
        print(f"  {dataset}: parsing {path.name} ...")
        foods = parse_dataset(path, dataset)
        quality = SOURCE_QUALITY.get(dataset, 0.8)

        for food in foods:
            n = food["n"]
            kcal = n.get("calories")
            # `to_row` rejects these before validating, so they are not part
            # of the population either figure describes.
            if kcal is None or kcal <= 0 or kcal > 900:
                continue
            panel = {
                "calories": kcal,
                "protein_g": n.get("protein_g", 0.0),
                "carbs_g": n.get("carbs_g", 0.0),
                "fat_g": n.get("fat_g", 0.0),
                "fiber_g": n.get("fiber_g", 0.0),
                "sugar_g": n.get("sugar_g", 0.0),
                "saturated_fat_g": n.get("saturated_fat_g", 0.0),
                "sodium_mg": n.get("sodium_mg", 0.0),
            }
            _, category = CATEGORY_MAP.get(food["usda_category"], (None, None))
            a, b, evidence = judge(
                panel, name=food["name"], category=category, quality=quality,
                carb_convention=nv.CARB_TOTAL,
            )
            run_b.salt_evidence[str(evidence)] += 1
            run_a.add(a, dataset, False)
            run_b.add(b, dataset, False)
            total += 1
        print(f"  {dataset}: {total:,} rows judged so far")
    return total


def is_indian(barcode: str | None, gtin14: str | None) -> bool:
    if barcode and barcode.startswith(INDIA_GS1):
        return True
    # GTIN-14 is zero-padded on the left, so the 890 sits inside it.
    if gtin14 and gtin14.lstrip("0").startswith(INDIA_GS1):
        return True
    return False


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a proportion.

    Wilson rather than normal-approximation: the intervals here sit near 0 for
    some sources, where the normal approximation runs off the end of the scale
    and reports a negative lower bound.
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:5.2f}%" if whole else "    -"


VERDICT_ORDER = ("accept", "accept_with_corrections", "unverifiable",
                 "quarantine", "unreadable")


def print_run(t: Tally, total: int) -> None:
    print(f"\n{'=' * 72}\n{t.label}\n{'=' * 72}")
    print(f"{'verdict':<26} {'rows':>10}  share")
    for v in VERDICT_ORDER:
        n = t.verdicts.get(v, 0)
        print(f"  {v:<24} {n:>10,}  {pct(n, total)}")

    print("\n  by source")
    print(f"    {'source':<18} {'rows':>9} {'accept':>9} {'corr':>9} "
          f"{'quar':>9} {'unread':>8}  quarantine rate")
    for src in sorted(t.by_source, key=lambda s: -sum(t.by_source[s].values())):
        c = t.by_source[src]
        n = sum(c.values())
        print(f"    {src:<18} {n:>9,} {c.get('accept', 0):>9,} "
              f"{c.get('accept_with_corrections', 0):>9,} "
              f"{c.get('quarantine', 0):>9,} {c.get('unreadable', 0):>8,}"
              f"  {pct(c.get('quarantine', 0), n)}")

    print("\n  Indian GS1 (barcode 890...) vs the rest")
    for key in ("india", "rest"):
        c = t.by_india.get(key, Counter())
        n = sum(c.values())
        if not n:
            continue
        q = c.get("quarantine", 0)
        lo, hi = wilson(q, n)
        print(f"    {key:<8} {n:>9,} rows   quarantined {q:>8,}  {pct(q, n)}"
              f"   [95% CI {100 * lo:.2f}-{100 * hi:.2f}%]")
        notclean = n - c.get("accept", 0)
        lo2, hi2 = wilson(notclean, n)
        print(f"             {'':>9}   not clean   {notclean:>8,}  "
              f"{pct(notclean, n)}   [95% CI {100 * lo2:.2f}-{100 * hi2:.2f}%]")

    print("\n  top 10 failing checks")
    for code, n in t.codes.most_common(10):
        print(f"    {code:<44} {n:>10,}")

    print("\n  warnings per row")
    for w in sorted(t.warning_counts):
        if w == 0:
            continue
        print(f"    {w} warning(s): {t.warning_counts[w]:>10,}")
    print(f"    rows whose ONLY complaint was near-zero sodium: "
          f"{t.sodium_only:,}")


def print_delta(a: Tally, b: Tally, total: int) -> None:
    print(f"\n{'=' * 72}\nDELTA -- total validator contamination, August to now"
          f"\n{'=' * 72}")
    print(f"{'verdict':<26} {'run A':>10} {'run B':>10} {'change':>10}")
    for v in VERDICT_ORDER:
        na, nb = a.verdicts.get(v, 0), b.verdicts.get(v, 0)
        print(f"  {v:<24} {na:>10,} {nb:>10,} {nb - na:>+10,}")

    qa, qb = a.verdicts.get("quarantine", 0), b.verdicts.get("quarantine", 0)
    print(f"\n  Rows quarantined by the sodium default alone: {qa - qb:,}"
          f"  ({pct(qa - qb, total)} of the catalogue)")

    ia = a.by_india.get("india", Counter())
    ib = b.by_india.get("india", Counter())
    ni = sum(ia.values())
    if ni:
        print(f"\n  Indian rows ({ni:,}):")
        for label, c in (("run A", ia), ("run B", ib)):
            q = c.get("quarantine", 0)
            nc = ni - c.get("accept", 0)
            print(f"    {label}: quarantined {q:>7,} ({pct(q, ni)})   "
                  f"not clean {nc:>7,} ({pct(nc, ni)})")
        print(f"    the August figure was '1 in 3' = 33.3%")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run(
    sample: int | None, seed: float, json_path: str | None, usda: bool = False
) -> int:
    run_a = Tally("ARM A -- the frozen August validator "
                  "(sodium assumption + flat 4/4/9)")
    run_b = Tally("ARM B -- current")
    total = 0

    if usda:
        print("Source: the cached USDA FDC release (no database needed).")
        print("Mode: REPORT ONLY -- nothing is written anywhere.")
        total = audit_usda_cache(run_a, run_b)
        if not total:
            print("No cached USDA release found. Nothing to audit.")
            return 1
        report(run_a, run_b, total, sample=None, seed=seed,
               json_path=json_path, salt_source="name + category")
        return 0

    settings = get_settings()
    print(f"DB: {mask(settings.DATABASE_URL)}")
    print("Mode: REPORT ONLY -- the transaction is read-only, nothing is written.")

    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with engine.connect() as conn:
            # Belt and braces: a write in here raises instead of landing.
            await conn.execute(text("SET TRANSACTION READ ONLY"))

            async for row in stream_rows(conn, sample, seed):
                m = row._mapping
                panel = {f: float(m[f]) for f in PANEL_FIELDS if m[f] is not None}
                name = m["name"]
                category = m["category"]
                source = str(m["source"])
                indian = is_indian(m["barcode"], m["gtin14"])
                quality = float(m["data_quality"] or 0.5)

                # RUN A restores the old default exactly; RUN B derives it.
                # `ingredients_text` is unavailable here -- food_items has no
                # column for it, so run B gets name and category only.
                a, b, evidence = judge(
                    panel, name=name, category=category, quality=quality
                )
                run_b.salt_evidence[str(evidence)] += 1

                run_a.add(a, source, indian)
                run_b.add(b, source, indian)
                total += 1
                if total % 50_000 == 0:
                    print(f"  ... {total:,} rows", file=sys.stderr)
    finally:
        await engine.dispose()

    report(run_a, run_b, total, sample=sample, seed=seed,
           json_path=json_path, salt_source="name + category")
    return 0


def report(
    run_a: Tally,
    run_b: Tally,
    total: int,
    *,
    sample: int | None,
    seed: float,
    json_path: str | None,
    salt_source: str,
) -> None:
    print(f"\nRows examined: {total:,}"
          + (f"  (random sample, seed {seed})" if sample else "  (full sweep)"))

    print(f"\nSalt evidence available for run B (from {salt_source}):")
    for k in ("True", "False", "None"):
        n = run_b.salt_evidence.get(k, 0)
        label = {"True": "salted (attested)", "False": "not salted",
                 "None": "no evidence -- check stays silent"}[k]
        print(f"  {label:<38} {n:>10,}  {pct(n, total)}")

    print_run(run_a, total)
    print_run(run_b, total)
    print_delta(run_a, run_b, total)

    if json_path:
        payload = {
            "rows": total,
            "sample": sample,
            "seed": seed if sample else None,
            "runs": {
                t.label: {
                    "verdicts": dict(t.verdicts),
                    "by_source": {k: dict(v) for k, v in t.by_source.items()},
                    "by_india": {k: dict(v) for k, v in t.by_india.items()},
                    "codes": dict(t.codes),
                    "warning_counts": dict(t.warning_counts),
                    "sodium_only": t.sodium_only,
                }
                for t in (run_a, run_b)
            },
            "salt_evidence": dict(run_b.salt_evidence),
        }
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nWrote {json_path}")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, default=None,
                    help="audit a random sample of N rows instead of all")
    ap.add_argument("--seed", type=float, default=0.42,
                    help="setseed() value, so a sample is reproducible")
    ap.add_argument("--json", dest="json_path", default=None,
                    help="also write the raw counts here")
    ap.add_argument("--usda", action="store_true",
                    help="audit the cached FDC release instead of the database")
    args = ap.parse_args()
    return asyncio.run(
        run(args.sample, args.seed, args.json_path, usda=args.usda)
    )


if __name__ == "__main__":
    raise SystemExit(main())
