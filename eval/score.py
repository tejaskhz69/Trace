#!/usr/bin/env python3
"""Validate the eval set, then score a run against it.

    python score.py --validate                 # before you shoot / after you fill it in
    python score.py --results results.json     # after a run

WHY VALIDATION COMES FIRST
--------------------------
The failure mode this guards against is not a bug, it's a lie: an eval set
that quietly contains guessed truth values will report excellent accuracy and
tell you nothing. `estimate` rows are refused here rather than warned about,
because a warning gets scrolled past.

The second guard is stratification. Twenty-five photos that are all easy
single-plate shots will also report excellent accuracy. The set has to contain
the cases that break these models -- hidden fat, no scale reference, many
components -- or the number is decoration.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
PHOTOS = HERE / "photos"

# Ordered best-to-worst. Anything below the cut is not evidence.
TRUTH_TIERS = ["label", "weighed", "recipe", "menu", "estimate"]
SCORABLE = {"label", "weighed", "recipe", "menu"}

# Minimums. Below these the report is not meaningful -- see docstring.
MIN_TOTAL = 20
MIN_WEIGHED = 10
MIN_INDIAN = 12
MIN_HIGH_FAT = 8
MIN_ADVERSARIAL = 3

G, R, Y, X = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
OK, BAD, WARN = f"{G}PASS{X}", f"{R}FAIL{X}", f"{Y}WARN{X}"


def load() -> list[dict]:
    with open(HERE / "manifest.csv", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def validate(rows: list[dict]) -> int:
    problems = 0
    print(f"\n{len(rows)} rows in manifest.csv\n" + "-" * 58)

    filled = [r for r in rows if (r.get("truth_kcal") or "").strip()]
    print(f"       truth_kcal filled: {len(filled)}/{len(rows)}")

    # 1. No guessed truth in the scored set.
    guessed = [
        r for r in filled
        if r["truth_source"] == "estimate" and r.get("adversarial") != "yes"
    ]
    if guessed:
        problems += 1
        print(f"{BAD}  {len(guessed)} scorable rows have truth_source=estimate")
        for r in guessed[:5]:
            print(f"       {r['file']}")
        print("       Scoring a model's guess against your guess measures")
        print("       agreement, not accuracy. Weigh them or drop them.")
    else:
        print(f"{OK}  No guessed truth in the scored set")

    # 2. Enough weighed rows to say anything about Indian home food.
    weighed = [r for r in filled if r["truth_source"] == "weighed"]
    if len(weighed) < MIN_WEIGHED:
        problems += 1
        print(f"{BAD}  Only {len(weighed)} weighed rows (need {MIN_WEIGHED})")
        print("       Weighed Indian home meals are the whole point. Ten of")
        print("       these beat fifty guessed photos.")
    else:
        print(f"{OK}  {len(weighed)} weighed rows")

    # 3. Stratification -- an easy set flatters the model.
    for name, n, floor in [
        ("Indian rows", sum(1 for r in rows if r["cuisine"].startswith("indian")), MIN_INDIAN),
        ("high hidden-fat", sum(1 for r in rows if r["hidden_fat"] == "high"), MIN_HIGH_FAT),
        ("adversarial", sum(1 for r in rows if r.get("adversarial") == "yes"), MIN_ADVERSARIAL),
    ]:
        if n < floor:
            problems += 1
            print(f"{BAD}  {name}: {n} (need {floor})")
        else:
            print(f"{OK}  {name}: {n}")

    # 4. Files actually exist.
    if PHOTOS.exists():
        missing = [r["file"] for r in rows if not (PHOTOS / r["file"]).exists()]
        extra = [
            p.name for p in PHOTOS.iterdir()
            if p.is_file() and p.name not in {r["file"] for r in rows}
        ]
        print(f"{BAD if missing else OK}  Photos present: "
              f"{len(rows) - len(missing)}/{len(rows)}"
              + (f"  missing: {', '.join(missing[:4])}" if missing else ""))
        if extra:
            print(f"{WARN}  {len(extra)} photos not in the manifest: {', '.join(extra[:4])}")
        if missing:
            problems += 1
    else:
        print(f"{WARN}  photos/ does not exist yet")

    print("-" * 58)
    if problems:
        print(f"{R}Not ready.{X} Fix the above before running the eval.\n")
    else:
        print(f"{G}Ready to run.{X}\n")
    return 1 if problems else 0


def score(rows: list[dict], results_path: Path) -> int:
    results = {r["file"]: r for r in json.loads(results_path.read_text())}
    scored, refused = [], []

    for row in rows:
        truth = (row.get("truth_kcal") or "").strip()
        got = results.get(row["file"])
        if not got:
            continue

        # Adversarial rows are graded on behaviour, not on the number: the
        # pass condition is a wider range and lower confidence, or a refusal.
        if row.get("adversarial") == "yes":
            refused.append((row, got))
            continue
        if not truth or row["truth_source"] not in SCORABLE:
            continue

        t, p = float(truth), float(got["kcal"])
        scored.append({
            "file": row["file"],
            "cuisine": row["cuisine"],
            "hidden_fat": row["hidden_fat"],
            "tier": row["truth_source"],
            "truth": t,
            "pred": p,
            "err_pct": (p - t) / t * 100,
            "in_range": got.get("kcal_low", p) <= t <= got.get("kcal_high", p),
        })

    if not scored:
        print("No scorable results. Did you fill in truth_kcal?")
        return 1

    errs = [s["err_pct"] for s in scored]
    bias = statistics.mean(errs)
    mape = statistics.mean(abs(e) for e in errs)
    cover = sum(s["in_range"] for s in scored) / len(scored) * 100

    print(f"\n{len(scored)} scored\n" + "=" * 58)
    print(f"  Mean error (bias) {bias:+6.1f}%   <- negative = undercounting")
    print(f"  MAPE              {mape:6.1f}%")
    print(f"  Range coverage    {cover:6.0f}%   <- target ~80-90%")
    print(f"\n  NIH benchmark for existing apps: about -33% bias.")
    print(f"  {'BEATING' if abs(bias) < 33 else 'NOT beating'} the incumbents on bias.\n")

    print("  By hidden fat (the axis that actually breaks these models)")
    for lvl in ("low", "med", "high"):
        g = [s["err_pct"] for s in scored if s["hidden_fat"] == lvl]
        if g:
            print(f"    {lvl:<5} n={len(g):<3} bias {statistics.mean(g):+6.1f}%")

    print("\n  By cuisine")
    for c in sorted({s["cuisine"] for s in scored}):
        g = [s["err_pct"] for s in scored if s["cuisine"] == c]
        print(f"    {c:<16} n={len(g):<3} bias {statistics.mean(g):+6.1f}%")

    if refused:
        print(f"\n  Adversarial ({len(refused)}) -- graded on behaviour, not accuracy")
        for row, got in refused:
            band = got.get("kcal_high", 0) - got.get("kcal_low", 0)
            conf = got.get("confidence", 1.0)
            good = got.get("refused") or band > 0.4 * float(got.get("kcal", 1)) or conf < 0.6
            print(f"    {OK if good else BAD}  {row['file']:<32} "
                  f"band ±{band/2:.0f} conf {conf:.2f}")

    print("\n  Worst 5")
    for s in sorted(scored, key=lambda s: -abs(s["err_pct"]))[:5]:
        print(f"    {s['err_pct']:+7.1f}%  {s['file']:<34} "
              f"{s['truth']:.0f} -> {s['pred']:.0f}")
    print()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--results", type=Path)
    a = ap.parse_args()
    rows = load()
    sys.exit(score(rows, a.results) if a.results else validate(rows))


if __name__ == "__main__":
    main()
