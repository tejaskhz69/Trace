#!/usr/bin/env python3
"""Turn a recipe YAML into a truth row -- or say exactly why it cannot yet.

    python recipe_calc.py recipes/fo-009-white-sauce-pasta.yaml

A `recipe`-tier row is only worth as much as its arithmetic is inspectable.
This prints every line of that arithmetic so the number in manifest.csv can
be audited later, and it REFUSES to emit a truth value while any field is
still null. Filling a blank with a plausible guess is the exact failure
score.py exists to catch; doing it here instead would just move the lie
upstream.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml --break-system-packages")

MACROS = ("kcal", "protein", "carbs", "fat")


def scale(per100g: dict, grams: float) -> dict:
    return {m: per100g.get(m, 0.0) * grams / 100.0 for m in MACROS}


def add(a: dict, b: dict) -> dict:
    return {m: a[m] + b[m] for m in MACROS}


def fmt(label: str, grams: float | None, v: dict, width: int = 30) -> str:
    g = f"{grams:6.0f} g" if grams is not None else " " * 8
    return (f"  {label:<{width}}{g}  {v['kcal']:7.0f} kcal"
            f"   P {v['protein']:5.1f}  C {v['carbs']:5.1f}  F {v['fat']:5.1f}")


def main(path: Path) -> int:
    r = yaml.safe_load(path.read_text())
    print(f"\n{r['dish']}\n" + "=" * 74)

    total = dict.fromkeys(MACROS, 0.0)
    unweighed = []
    print("\nFIXED PART")
    for ing in r["ingredients"]:
        g = ing.get("grams")
        if g is None:
            # An unweighed ingredient is carried as a band and blocks the row.
            # Folding in its midpoint would look like arithmetic and BE a guess.
            lo, hi = ing["grams_low"], ing["grams_high"]
            unweighed.append((ing, lo, hi))
            print(fmt(f"{ing['name']}  UNWEIGHED", None,
                      scale(ing["per100g"], (lo + hi) / 2))
                  + f"   <- band {lo}-{hi} g")
            continue
        v = scale(ing["per100g"], g)
        total = add(total, v)
        print(fmt(ing["name"], g, v))
    print("  " + "-" * 70)
    print(fmt("subtotal", None, total))

    # Oil: a band, not a point, until it is measured once.
    oil = r["oil"]
    print("\nOIL -- band, not a point value")
    bands = {}
    for key, label in (("grams_low", "low"), ("grams_typical", "typical"),
                       ("grams_high", "high")):
        g = oil[key]
        bands[label] = scale(oil["per100g"], g)
        print(fmt(f"{oil['name']}  ({label})", g, bands[label]))
    oil_swing = bands["high"]["kcal"] - bands["low"]["kcal"]

    missing = []
    state = r["pasta"].get("state")
    frac = r.get("plate_fraction")
    for ing, lo, hi in unweighed:
        swing = (hi - lo) * ing["per100g"]["kcal"] / 100
        missing.append(f"{ing['name']}  (band is {swing:.0f} kcal wide)")
    if state not in ("dry", "cooked"):
        missing.append("pasta.state  (dry | cooked)")
    if not isinstance(frac, (int, float)):
        missing.append("plate_fraction  (1.0 = whole batch, 0.25 = one of four)")

    print("\nPASTA -- both branches, because the answer changes everything")
    for st in ("dry", "cooked"):
        v = scale(r["pasta"][st], r["pasta"]["grams"])
        batch = add(add(total, v), bands["typical"])
        print(fmt(f"400 g {st}", r["pasta"]["grams"], v))
        print(fmt(f"  -> batch total ({st})", None, batch))

    print("\n" + "=" * 74)
    print(f"  Oil uncertainty across the whole band: {oil_swing:.0f} kcal")
    print("  That is a rounding error here. It is NOT in most Indian dishes --")
    print("  which is precisely why this row is a useful control.")

    if missing:
        print(f"\n  REFUSING to emit truth_kcal. Still unknown:")
        for m in missing:
            print(f"    - {m}")
        print("\n  " + oil["measure_protocol"].strip().replace("\n", "\n  "))
        print()
        return 1

    v = scale(r["pasta"][state], r["pasta"]["grams"])
    batch = add(add(total, v), bands["typical"])
    plate = {m: batch[m] * frac for m in MACROS}
    print(fmt(f"TRUTH ({frac:.2f} of batch)", None, plate))
    print(f"\n  truth_kcal = {plate['kcal']:.0f}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else
                       "recipes/fo-009-white-sauce-pasta.yaml")))
