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
MIN_HIGH_CONF = 10          # label OR weighed -- see validate()
MIN_INDIAN = 12
MIN_HIGH_FAT = 8
MIN_ADVERSARIAL = 3

G, R, Y, X = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
OK, BAD, WARN = f"{G}PASS{X}", f"{R}FAIL{X}", f"{Y}WARN{X}"


def is_placeholder(path: Path) -> bool:
    """True if this is one of the shipped placeholder cards, not a photograph.

    The cards are flat rendered panels: one exact RGB value covers most of the
    frame. A real photograph -- even of a white plate under one lamp -- has
    sensor noise and lighting gradient, so no single exact triple gets close.
    A 40% threshold sits in a very wide gap between the two populations.

    Falls back to reporting "not a placeholder" if Pillow is missing, because
    a missing library must not silently mark real work as fake.
    """
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            # Downsample first: the test is about large flat regions, and this
            # makes it fast enough to run over the whole set every time.
            im.thumbnail((160, 160))
            pixels = list(im.convert("RGB").tobytes())
            pixels = [tuple(pixels[i:i+3]) for i in range(0, len(pixels), 3)]
    except Exception:  # noqa: BLE001 - an unreadable file is a different problem
        return False
    if not pixels:
        return False
    from collections import Counter
    most_common = Counter(pixels).most_common(1)[0][1]
    return most_common / len(pixels) > 0.40


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

    # 2. Enough high-confidence rows to say anything at all.
    #    `label` (packaged food shot with its own panel) is actually BETTER
    #    truth than `weighed`, because the manufacturer measured the cooking
    #    fat you cannot see. A dorm-collected set will be mostly label rows,
    #    and that is fine -- it is the `recipe` and `estimate` tiers that
    #    weaken a conclusion, not `label`.
    high_conf = [r for r in filled if r["truth_source"] in ("label", "weighed")]
    if len(high_conf) < MIN_HIGH_CONF:
        problems += 1
        print(f"{BAD}  Only {len(high_conf)} label/weighed rows "
              f"(need {MIN_HIGH_CONF})")
        print("       Ready-to-eat pouches and packaged food carry a printed")
        print("       panel -- that is label-tier truth with no cooking.")
    else:
        n_lab = sum(1 for r in high_conf if r["truth_source"] == "label")
        print(f"{OK}  {len(high_conf)} high-confidence rows "
              f"({n_lab} label, {len(high_conf)-n_lab} weighed)")

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

    # 4. Files exist AND are real photographs.
    #
    #    An earlier version of this script counted any file as a photo, which
    #    meant a set built entirely from the shipped placeholder cards could
    #    report "25/25 PASS" while containing no food at all. That is the same
    #    failure this script exists to prevent -- refusing a guessed number in
    #    truth_kcal and then accepting a guessed image is not a coherent
    #    position. Placeholders are now detected and counted as missing.
    if PHOTOS.exists():
        present = {r["file"] for r in rows if (PHOTOS / r["file"]).exists()}
        absent = [r["file"] for r in rows if r["file"] not in present]
        placeholders = sorted(f for f in present if is_placeholder(PHOTOS / f))
        real = len(present) - len(placeholders)

        extra = [
            p.name for p in PHOTOS.iterdir()
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
            and p.name not in {r["file"] for r in rows}
        ]

        ok = real == len(rows)
        print(f"{OK if ok else BAD}  Real photos: {real}/{len(rows)}")
        if placeholders:
            print(f"       {len(placeholders)} are still the shipped placeholder cards:")
            for f in placeholders[:4]:
                print(f"       {f}")
            if len(placeholders) > 4:
                print(f"       ... and {len(placeholders) - 4} more")
        if absent:
            print(f"       {len(absent)} missing: {', '.join(absent[:4])}")
        if extra:
            print(f"{WARN}  {len(extra)} photos not in the manifest: {', '.join(extra[:4])}")
        if not ok:
            problems += 1
    else:
        print(f"{WARN}  photos/ does not exist yet")

    print("-" * 58)
    if problems:
        print(f"{R}Not ready.{X} Fix the above before running the eval.\n")
    else:
        print(f"{G}Ready to run.{X}\n")
    return 1 if problems else 0


def adversarial_ok(got: dict) -> bool:
    """Did the model behave correctly on a row whose truth is unknowable?

    Three ways to pass, in descending order of how much we want to see them:

      1. It refused outright. Product invariant 3 -- refusing to answer beats
         answering wrong. This is the behaviour these rows exist to measure.
      2. It widened the band past +/-20% of the point estimate.
      3. It dropped confidence below 0.6.

    `refused` is read BY NAME off the result dict, which means it has to
    survive the whole chain: the model sets it, `vision._sanitize()` keeps it,
    `eval_vision.py` writes it into results.json, and this function reads it.
    Break any link and the clause silently evaluates to None -- an explicit
    refusal then scores identically to a confident guess, which is the exact
    thing we are trying to detect. `tests/test_eval_contract.py` in the API
    guards the chain; this function exists as a named thing so it can.
    """
    band = got.get("kcal_high", 0) - got.get("kcal_low", 0)
    conf = got.get("confidence", 1.0)
    return bool(
        got.get("refused")
        or band > 0.4 * float(got.get("kcal", 1))
        or conf < 0.6
    )


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
            good = adversarial_ok(got)
            why = "refused" if got.get("refused") else f"band ±{band/2:.0f}"
            print(f"    {OK if good else BAD}  {row['file']:<32} "
                  f"{why:<12} conf {conf:.2f}")

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
