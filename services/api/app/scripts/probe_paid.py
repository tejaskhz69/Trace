#!/usr/bin/env python3
"""Verify a metered nutrition provider against a real key, in one command.

    python -m app.scripts.probe_paid
    python -m app.scripts.probe_paid --query "two rotis and a bowl of dal"
    python -m app.scripts.probe_paid --barcode 0049000042566

WHY THIS EXISTS RATHER THAN "just try the app"
A metered integration fails in a way that is invisible from the outside. A bad
key, an exhausted budget, a renamed response field and "this food genuinely
does not exist" all produce the same thing at the call site: a miss. This
script separates them, and prints the RAW response shape so a schema change is
obvious rather than showing up as silent zeros in someone's diary.

IT COSTS REAL CALLS. Three by default. That is the point -- it is verifying
the billed path, not a mock.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from ..config import get_settings
from ..services import paid_sources

settings = get_settings()


def _line(label: str, value: object) -> None:
    print(f"  {label:<22} {value}")


async def run(args: argparse.Namespace) -> None:
    print("=" * 66)
    print("PAID NUTRITION PROVIDER PROBE")
    print("=" * 66)

    if not paid_sources.available():
        print("\nNot configured.\n")
        print("  Set these in services/api/.env, then re-run:")
        print("    NUTRITIONIX_APP_ID=...")
        print("    NUTRITIONIX_APP_KEY=...")
        print("\n  Free developer tier: https://developer.nutritionix.com")
        print("\n  This is a SUPPORTED state -- the app already serves 273,000")
        print("  foods from free sources and skips this tier entirely.\n")
        return

    # Never print the key. Length and last four are enough to tell two keys
    # apart in a screenshot without leaking one.
    key = settings.NUTRITIONIX_APP_KEY or ""
    _line("app id", settings.NUTRITIONIX_APP_ID)
    _line("app key", f"{len(key)} chars, ends {key[-4:]}")
    _line("daily budget", settings.PAID_LOOKUPS_PER_DAY)

    # --- 1. credentials --------------------------------------------------
    print("\n[1] Credentials")
    health = await paid_sources.health_check()
    _line("ok", health["ok"])
    _line("detail", health["detail"])
    if not health["ok"]:
        print("\n  A 401/403 here means the key is wrong. Check the server log:")
        print("  a rejected key is logged explicitly so it cannot be mistaken")
        print("  for 'no such food'.\n")
        return

    # --- 2. natural language ---------------------------------------------
    print(f"\n[2] Natural language  ->  {args.query!r}")
    foods = await paid_sources.parse_meal(args.query)
    if not foods:
        print("  No foods parsed.")
    for f in foods:
        _line(
            f.name[:20],
            f"{f.calories:.0f} kcal/100g  P{f.protein_g:.0f} C{f.carbs_g:.0f} "
            f"F{f.fat_g:.0f}  serving={f.serving_sizes[0]['name']!r}",
        )

    # --- 3. barcode ------------------------------------------------------
    if args.barcode:
        print(f"\n[3] Barcode  ->  {args.barcode}")
        hit = await paid_sources.lookup_barcode(args.barcode)
        _line("found", bool(hit))
        if hit:
            _line("name", f"{hit.brand or ''} {hit.name}".strip())
            _line("per 100 g", f"{hit.calories:.0f} kcal")

    # --- 4. raw shape ----------------------------------------------------
    if args.raw and foods:
        print("\n[4] Raw response keys (watch these for schema drift)")
        print(json.dumps(sorted(foods[0].raw.keys()), indent=2)[:900])

    print(f"\nBudget after probe: {paid_sources.budget_status()}\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--query",
        default="two rotis and a bowl of dal tadka",
        help="Natural-language meal to parse.",
    )
    p.add_argument("--barcode", default=None, help="Also test a UPC lookup.")
    p.add_argument("--raw", action="store_true", help="Print raw response keys.")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
