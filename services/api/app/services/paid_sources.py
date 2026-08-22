"""Metered third-party nutrition APIs, used as a last resort.

THE ECONOMICS ARE THE DESIGN
These providers bill per call. Nutritionix is around $50/mo for a business
plan; the India-specific ones quote per seat. An integration that simply
"calls the API when the user searches" turns a $50 line item into an unbounded
one the first time a client retries in a loop. So this module is built around
three rules, and the adapter code is the easy part:

  1. PAY ONCE PER PRODUCT, EVER. Every paid response is written into our own
     `food_items` table before it is returned. The second person to scan that
     barcode hits Postgres, not the vendor. Over any real user base the hit
     rate on a food database is enormous -- a few thousand products cover most
     of what most people eat -- so this is the difference between a fixed cost
     and a variable one.

  2. NEVER THE FIRST RESORT. The lookup order is local DB -> Open Food Facts
     -> USDA -> paid. By the time a call reaches here, three free sources have
     already missed, which is exactly the long tail worth paying for.

  3. A HARD DAILY CEILING. `PAID_LOOKUPS_PER_DAY` is a budget, not a rate
     limit. When it is spent, this module reports a miss rather than spending
     more, and the user sees "not found" -- which is what they would have seen
     anyway without the integration.

UNCONFIGURED IS A SUPPORTED STATE
No key means `available()` is False and the resolver skips this tier
entirely. Nothing errors, nothing warns on every request, and the app behaves
exactly as it does today. That matters because the free tiers already cover
273,000 foods; paid access is an upgrade, not a dependency.

WHAT NUTRITIONIX IS ACTUALLY GOOD FOR
Not barcodes -- Open Food Facts is better and free. Its two real advantages:

  US RESTAURANT CHAINS   ~1,000 chains with per-item nutrition, which is a
                         genuine gap in every free dataset.
  NATURAL LANGUAGE       "two rotis and a bowl of dal" parsed into portioned
                         foods. This is the one that changes how logging
                         feels, and it has no free equivalent.

A NOTE ON THE RESPONSE SHAPE
Field names below are read defensively, with fallbacks, because a vendor
response schema is not something this repo controls and a rename would
otherwise 500 the food search. `scripts/probe_paid.py` verifies the real
shape against a live key in one command; run it before trusting a new
provider in production.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from ..config import get_settings
from ..models import FoodSource
from .food_sources import ResolvedFood, _f  # noqa: PLC2701
from .nutrition_validator import Verdict, validate

log = logging.getLogger(__name__)
settings = get_settings()

NUTRITIONIX_BASE = "https://trackapi.nutritionix.com/v2"

# Nutritionix returns nutrients as a flat list keyed by USDA attribute id.
# These are the ones we store; the rest are dropped rather than modelled.
ATTR = {
    "calories": 208,
    "protein_g": 203,
    "carbs_g": 205,
    "fat_g": 204,
    "fiber_g": 291,
    "sugar_g": 269,
    "saturated_fat_g": 606,
    "sodium_mg": 307,
    "potassium_mg": 306,
}


class PaidBudgetExhausted(Exception):
    """Today's paid-call budget is spent. Treat as a miss, not an error."""


@dataclass
class _Budget:
    """A day's spend, held in memory.

    IN MEMORY ON PURPOSE, FOR NOW. A restart resets it, which errs toward
    spending slightly more rather than blocking a user for the rest of the day
    over a counter that survived a deploy. Move it to Redis the moment this
    runs on more than one container -- with N replicas the real ceiling is
    N x the limit, and that is a bill nobody predicted.
    """

    day: date = field(default_factory=date.today)
    used: int = 0

    def spend(self, limit: int) -> None:
        today = date.today()
        if today != self.day:
            self.day, self.used = today, 0
        if self.used >= limit:
            raise PaidBudgetExhausted(
                f"Daily paid-lookup budget of {limit} is spent."
            )
        self.used += 1

    def snapshot(self, limit: int) -> dict[str, Any]:
        today = date.today()
        used = 0 if today != self.day else self.used
        return {"date": today.isoformat(), "used": used, "limit": limit,
                "remaining": max(0, limit - used)}


_budget = _Budget()


def budget_status() -> dict[str, Any]:
    return _budget.snapshot(settings.PAID_LOOKUPS_PER_DAY)


def available() -> bool:
    """Whether a paid tier is configured at all."""
    return bool(settings.NUTRITIONIX_APP_ID and settings.NUTRITIONIX_APP_KEY)


def _headers() -> dict[str, str]:
    return {
        "x-app-id": settings.NUTRITIONIX_APP_ID or "",
        "x-app-key": settings.NUTRITIONIX_APP_KEY or "",
        "Content-Type": "application/json",
        # Without this the API answers in US units for some endpoints, which
        # would silently store ounces as grams.
        "x-remote-user-id": "0",
    }


def _nutrient(food: dict[str, Any], key: str) -> float:
    """Read one nutrient, preferring the flat `nf_*` field, then the id list.

    Both shapes appear depending on endpoint and plan. Reading only one is how
    an integration works in testing and returns zeros in production.
    """
    flat = {
        "calories": "nf_calories",
        "protein_g": "nf_protein",
        "carbs_g": "nf_total_carbohydrate",
        "fat_g": "nf_total_fat",
        "fiber_g": "nf_dietary_fiber",
        "sugar_g": "nf_sugars",
        "saturated_fat_g": "nf_saturated_fat",
        "sodium_mg": "nf_sodium",
        "potassium_mg": "nf_potassium",
    }.get(key)
    if flat and food.get(flat) is not None:
        return _f(food[flat])

    attr_id = ATTR.get(key)
    for n in food.get("full_nutrients") or []:
        if n.get("attr_id") == attr_id:
            return _f(n.get("value"))
    return 0.0


def to_resolved(food: dict[str, Any]) -> ResolvedFood | None:
    """Map one Nutritionix food onto our own shape, PER 100 G.

    THE SCALING STEP IS THE WHOLE FUNCTION. Nutritionix reports per SERVING,
    and `serving_weight_grams` is how big that serving was. Storing those
    numbers as per-100 g -- which is what a naive mapper does -- is wrong by
    whatever the serving happened to weigh, silently, in every direction.
    A 30 g serving becomes a 3.3x over-report.
    """
    name = (food.get("food_name") or "").strip()
    if not name:
        return None

    grams = _f(food.get("serving_weight_grams"))
    if grams <= 0:
        # No serving weight means the per-serving figures cannot be put on a
        # per-100 g basis at all. Guessing 100 g would be a fabrication.
        return None

    scale = 100.0 / grams
    kcal = _nutrient(food, "calories") * scale
    if kcal <= 0:
        return None

    serving_label = " ".join(
        str(x) for x in (food.get("serving_qty"), food.get("serving_unit")) if x
    ).strip()

    servings: list[dict[str, Any]] = [
        {"name": "100 g", "grams": 100.0, "is_default": False}
    ]
    if serving_label:
        servings.insert(
            0, {"name": serving_label, "grams": round(grams, 1), "is_default": True}
        )

    brand = (food.get("brand_name") or "").strip() or None

    return ResolvedFood(
        name=name[:250],
        brand=brand,
        barcode=str(food.get("upc") or "") or None,
        source=FoodSource.nutritionix,
        # Branded items carry nix_item_id; generic ones carry a USDA ndb_no.
        source_id=str(
            food.get("nix_item_id") or food.get("ndb_no") or name
        )[:120],
        calories=round(kcal, 1),
        protein_g=round(_nutrient(food, "protein_g") * scale, 2),
        carbs_g=round(_nutrient(food, "carbs_g") * scale, 2),
        fat_g=round(_nutrient(food, "fat_g") * scale, 2),
        fiber_g=round(_nutrient(food, "fiber_g") * scale, 2),
        sugar_g=round(_nutrient(food, "sugar_g") * scale, 2),
        sodium_mg=round(_nutrient(food, "sodium_mg") * scale, 1),
        saturated_fat_g=round(_nutrient(food, "saturated_fat_g") * scale, 2),
        serving_sizes=servings,
        is_liquid=bool(food.get("serving_unit", "").lower() in ("ml", "fl oz", "cup")),
        countries=["united-states"],
        # A commercial, curated source ranks above crowd-sourced OFF and below
        # USDA's laboratory values.
        data_quality=0.80,
        raw=food,
    )


def _validated(resolved: ResolvedFood) -> ResolvedFood | None:
    """Paid data is not exempt from the quarantine checks.

    Paying for a row is not evidence that it is right, and a vendor panel
    whose macros cannot account for its calories is as unusable as a
    crowd-sourced one.
    """
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
        log.info("Quarantined paid row %r: %s", resolved.name, result.issues[:1])
        return None
    resolved.data_quality = result.quality_score
    return resolved


async def _post(client: httpx.AsyncClient, path: str, body: dict) -> dict | None:
    _budget.spend(settings.PAID_LOOKUPS_PER_DAY)
    try:
        r = await client.post(
            f"{NUTRITIONIX_BASE}{path}", headers=_headers(), json=body, timeout=12.0
        )
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403):
            # Say this loudly once. A bad key otherwise looks exactly like
            # "this food does not exist", and the integration appears to
            # simply not work.
            log.error("Nutritionix rejected our credentials (%s).", r.status_code)
            return None
        if r.status_code == 429:
            log.warning("Nutritionix rate-limited us; treating as a miss.")
            return None
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Nutritionix %s failed: %s", path, exc)
        return None


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict | None:
    _budget.spend(settings.PAID_LOOKUPS_PER_DAY)
    try:
        r = await client.get(
            f"{NUTRITIONIX_BASE}{path}", headers=_headers(), params=params, timeout=12.0
        )
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403):
            log.error("Nutritionix rejected our credentials (%s).", r.status_code)
            return None
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Nutritionix %s failed: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# The three things worth paying for
# ---------------------------------------------------------------------------


async def lookup_barcode(barcode: str) -> ResolvedFood | None:
    """Last-resort barcode lookup.

    Deliberately the LAST tier. Open Food Facts is both free and better on
    non-US barcodes, so reaching here means the free sources already missed.
    """
    if not available():
        return None
    async with httpx.AsyncClient() as client:
        data = await _get(client, "/search/item", {"upc": barcode})
    if not data:
        return None
    for food in data.get("foods") or []:
        resolved = to_resolved(food)
        if resolved and (checked := _validated(resolved)):
            return checked
    return None


async def search(query: str, *, limit: int = 10) -> list[ResolvedFood]:
    """Branded and restaurant search.

    US chain restaurants are the real gap this fills -- no free dataset has
    per-item nutrition for a thousand chains, and "what did I eat at Chipotle"
    is a question free data simply cannot answer.
    """
    if not available() or not query.strip():
        return []

    async with httpx.AsyncClient() as client:
        instant = await _get(
            client, "/search/instant", {"query": query.strip(), "detailed": "true"}
        )
        if not instant:
            return []

        out: list[ResolvedFood] = []
        # `detailed=true` returns full nutrition inline for branded hits, which
        # avoids a second billed call per result. Without it this would be
        # 1 + N calls for one search.
        for food in (instant.get("branded") or [])[:limit]:
            resolved = to_resolved(food)
            if resolved and (checked := _validated(resolved)):
                out.append(checked)

        # Common (generic) hits carry no nutrition inline and need one natural
        # -language call to resolve. Only worth it if branded found nothing.
        if not out and (common := instant.get("common") or []):
            names = ", ".join(c.get("food_name", "") for c in common[:3])
            out.extend(await parse_meal(names))

    return out[:limit]


async def parse_meal(text: str) -> list[ResolvedFood]:
    """Natural language to portioned foods.

        "two rotis and a bowl of dal tadka"
            -> Roti x2 (per 100 g + a 40 g serving)
               Dal tadka (per 100 g + a 200 g serving)

    THIS IS THE ONE WITH NO FREE EQUIVALENT, and it is the feature that
    changes how logging feels -- the same shift the voice workout logger makes
    on the training side. Quantities and units are parsed by the vendor, which
    is genuinely hard and genuinely their value-add.

    Returns per-100 g rows with the spoken portion attached as the default
    serving, so the rest of the app treats them like any other food.
    """
    if not available() or not text.strip():
        return []

    async with httpx.AsyncClient() as client:
        data = await _post(client, "/natural/nutrients", {"query": text.strip()})
    if not data:
        return []

    out: list[ResolvedFood] = []
    for food in data.get("foods") or []:
        resolved = to_resolved(food)
        if resolved and (checked := _validated(resolved)):
            out.append(checked)
    return out


async def health_check() -> dict[str, Any]:
    """One cheap call, to prove the credentials work.

    Worth its own endpoint because a bad key is indistinguishable from "this
    food does not exist" at every call site.
    """
    if not available():
        return {"configured": False, "ok": False, "detail": "No API key set."}
    try:
        foods = await parse_meal("1 apple")
    except PaidBudgetExhausted as exc:
        return {"configured": True, "ok": False, "detail": str(exc)}
    return {
        "configured": True,
        "ok": bool(foods),
        "detail": f"Resolved {len(foods)} food(s)." if foods else "No result returned.",
        "budget": budget_status(),
    }
