"""Barcode coverage probe: Indian shelf vs the rest of the world.

WHY THIS EXISTS
Barcode scanning either works or it doesn't, and which one you get depends
entirely on whether the product is in the upstream database. Open Food Facts
has excellent European coverage and patchy Indian coverage, so a barcode
feature that tests fine in Berlin returns "not found" on half a Bangalore
kirana shop. That is a product failure, not a bug, and you only see it if you
measure coverage per market rather than per function.

This probes the real upstream (no key needed) and reports:

  - hit rate per market
  - which fields came back, because a hit with no nutrition is still a miss
    from the user's point of view
  - the exact barcodes that missed, so they can be seeded by hand

It deliberately does NOT touch the local DB or need the API running. It tests
the thing that actually varies: upstream coverage.

Run:
    python -m app.scripts.eval_barcode
    python -m app.scripts.eval_barcode --market IN
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

import httpx

from ..config import get_settings
from ..services.food_sources import off_lookup_barcode


@dataclass(frozen=True)
class Probe:
    barcode: str
    label: str
    market: str


# !!! THESE BARCODES ARE UNVERIFIED AND THE `label` FIELD IS UNTRUSTWORTHY !!!
#
# They were written from memory, and a check against Open Food Facts showed
# the GS1 company prefix was right almost every time while the item-reference
# digits were wrong -- 7622210449283 is LU "Prince", not Oreo; 8000500310427
# is Nutella Biscuits, not Kinder Bueno. Both are the right manufacturer.
# That is the predictable failure mode of recalled barcodes: the prefix is
# shared across a brand's catalogue and sticks, the trailing digits don't.
#
# WHY THAT BREAKS THE COVERAGE NUMBER
# A wrong barcode that happens to resolve still counts as a hit. A wrong
# barcode that resolves to nothing is reported as "not in Open Food Facts" --
# indistinguishable from genuine missing coverage. So an unverified probe set
# UNDERSTATES coverage by an unknown amount, and the per-market comparison
# this script prints is not evidence until the codes are verified.
#
# TO MAKE THIS TRUSTWORTHY
# Scan real packets with a phone and paste the digits in, replacing `label`
# with whatever Open Food Facts returns for that code (run with --show-names).
# Until then, treat the output as a smoke test of the lookup path, not as a
# coverage measurement.
PROBES: list[Probe] = [
    # --- India: the coverage that actually decides whether this ships here ---
    Probe("8906136651951", "Yoga Bar 20g Protein Bar", "IN"),
    Probe("8901491101837", "Lay's India Magic Masala", "IN"),
    Probe("8901058000108", "Maggi 2-Minute Noodles", "IN"),
    Probe("8901719110018", "Britannia Good Day Cashew", "IN"),
    Probe("8901030865305", "Amul Butter 100g", "IN"),
    Probe("8901725121112", "Haldiram's Aloo Bhujia", "IN"),
    Probe("8904004400014", "Paper Boat Aamras", "IN"),
    Probe("8901063142107", "Parle-G Original", "IN"),
    # --- Europe: OFF's home turf, the control group -----------------------
    Probe("3017620422003", "Nutella 400g", "FR"),
    Probe("5449000000996", "Coca-Cola 330ml", "BE"),
    Probe("7622210449283", "Oreo Original", "DE"),
    Probe("8000500310427", "Kinder Bueno", "IT"),
    # --- US / UK / APAC ---------------------------------------------------
    Probe("028400642255", "Doritos Nacho Cheese", "US"),
    Probe("038000138416", "Kellogg's Corn Flakes", "US"),
    Probe("5000159484695", "Snickers Bar", "GB"),
    Probe("8888077101010", "Milo Malaysia", "MY"),
    Probe("4902201416894", "Kit Kat Japan", "JP"),
]


async def probe_one(client: httpx.AsyncClient, p: Probe) -> dict:
    try:
        resolved = await off_lookup_barcode(client, p.barcode)
    except Exception as exc:  # a network blip is a probe result, not a crash
        return {"probe": p, "ok": False, "why": f"error: {type(exc).__name__}"}

    if resolved is None:
        return {"probe": p, "ok": False, "why": "not in Open Food Facts"}

    if not resolved.calories:
        # Present but useless: this is the case that silently ships a zero
        # into someone's diary, so it counts as a miss.
        return {"probe": p, "ok": False, "why": "found, but no kcal", "name": resolved.name}

    return {
        "probe": p,
        "ok": True,
        "name": resolved.name,
        "kcal": resolved.calories,
        "protein": resolved.protein_g,
        "quality": resolved.data_quality,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", help="Only probe one market, e.g. IN")
    ap.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds between requests. Below ~1s Open Food Facts starts 429ing.",
    )
    args = ap.parse_args()

    probes = [p for p in PROBES if not args.market or p.market == args.market]

    settings = get_settings()
    # SERIALISED, not gathered. Open Food Facts rate-limits hard, and
    # off_lookup_barcode() swallows the 429 and returns None -- which reads
    # identically to "product not found". Firing these concurrently produces
    # a coverage report that is mostly measuring your own request rate.
    async with httpx.AsyncClient(
        timeout=20.0, headers={"User-Agent": settings.OFF_USER_AGENT}
    ) as client:
        results = []
        for i, p in enumerate(probes):
            if i:
                await asyncio.sleep(args.delay)
            results.append(await probe_one(client, p))

    by_market: dict[str, list[dict]] = {}
    for r in results:
        by_market.setdefault(r["probe"].market, []).append(r)

    print(f"\n{'BARCODE':<16} {'MARKET':<7} {'PRODUCT':<32} RESULT")
    print("-" * 92)
    for r in results:
        p = r["probe"]
        if r["ok"]:
            outcome = f"OK  {r['kcal']:.0f} kcal/100g  ({r['name'][:28]})"
        else:
            outcome = f"--  {r['why']}"
        print(f"{p.barcode:<16} {p.market:<7} {p.label[:32]:<32} {outcome}")

    print("\nCoverage by market")
    print("-" * 40)
    overall_hit = 0
    for market in sorted(by_market):
        rows = by_market[market]
        hit = sum(1 for r in rows if r["ok"])
        overall_hit += hit
        pct = 100 * hit / len(rows)
        bar = "#" * int(pct / 5)
        print(f"  {market:<4} {hit:>2}/{len(rows):<3} {pct:5.1f}%  {bar}")

    total_pct = 100 * overall_hit / len(results) if results else 0.0
    print(f"\n  ALL  {overall_hit:>2}/{len(results):<3} {total_pct:5.1f}%")

    print(
        "\n  NOT EVIDENCE YET: these barcodes are unverified (see the note above\n"
        "  PROBES). A code with wrong digits that resolves to nothing is counted\n"
        "  as missing coverage, so these percentages are a floor, not a measure.\n"
        "  Verify by scanning real packets before quoting any of this."
    )

    misses = [r for r in results if not r["ok"]]
    if misses:
        print("\nSeed these by hand -- every one is a user who scans and gets nothing:")
        for r in misses:
            print(f"  {r['probe'].barcode}  {r['probe'].label}  ({r['why']})")


if __name__ == "__main__":
    asyncio.run(main())
