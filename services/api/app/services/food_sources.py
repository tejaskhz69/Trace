"""Multi-source food resolution.

WHY THIS FILE EXISTS
--------------------
Scanning "Pintola High Protein Oats" and getting nothing is not a database-size
problem -- that product *is* in Open Food Facts under barcode 8906136651951,
with full macros (25 g protein, 54.6 g carbs, 8 g fat, 9.6 g fibre per 100 g,
50 g serving). If your app returned nothing, your barcode lookup only queried
your own seeded table and stopped there.

The fix is a **resolution chain**, not a bigger seed file:

    1. Local DB        (instant, offline-capable, gets better over time)
    2. Open Food Facts (~4M products globally, crowd-sourced, strong on
                        packaged goods including Indian brands)
    3. USDA FoodData Central Branded (~1.9M US products, high data quality)
    4. AI nutrition-label OCR fallback (user photographs the label)
    5. Manual entry -> queued for moderation -> becomes local DB row

Every remote hit is **written back to the local DB**, so the second user to
scan that product gets an instant local hit. Your database grows from real
usage rather than from a scraping project.

RATE LIMITS / ETIQUETTE
-----------------------
Open Food Facts asks for a descriptive User-Agent and rate-limits to roughly
100 req/min for product reads and 10 req/min for search. Set OFF_USER_AGENT to
something identifying with a contact address. For production scale, run the
bulk import (scripts/ingest_openfoodfacts.py) and use the live API only as a
miss-handler.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import get_settings
from ..models import FoodSource

log = logging.getLogger(__name__)
settings = get_settings()

# OFF nutriment keys -> our fields. OFF is inconsistent about which of these
# is populated, so we try several in order.
_ENERGY_KEYS = ("energy-kcal_100g", "energy-kcal", "energy_100g")
_TIMEOUT = httpx.Timeout(6.0, connect=3.0)


@dataclass
class ResolvedFood:
    name: str
    brand: str | None
    barcode: str | None
    source: FoodSource
    source_id: str | None
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    sugar_g: float
    sodium_mg: float
    saturated_fat_g: float
    serving_sizes: list[dict[str, Any]]
    is_liquid: bool
    countries: list[str]
    data_quality: float
    raw: dict[str, Any]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
        # OFF occasionally carries absurd values from bad crowd edits.
        return f if 0 <= f < 100_000 else default
    except (TypeError, ValueError):
        return default


def _parse_serving_grams(serving_size: str | None) -> float | None:
    """'50 g', '30g (2 tbsp)', '250 ml' -> 50.0 / 30.0 / 250.0"""
    if not serving_size:
        return None
    import re

    m = re.search(r"(\d+(?:\.\d+)?)\s*(g|gram|ml|mL)", serving_size)
    if m:
        return float(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Open Food Facts
# ---------------------------------------------------------------------------


_OFF_FIELDS = ",".join(
    [
        "code",
        "product_name",
        "product_name_en",
        "generic_name",
        "brands",
        "quantity",
        "serving_size",
        "serving_quantity",
        "countries_tags",
        "categories_tags",
        "nutriments",
        "completeness",
        "image_front_small_url",
    ]
)


def _off_to_resolved(product: dict[str, Any]) -> ResolvedFood | None:
    n = product.get("nutriments") or {}

    kcal = 0.0
    for k in _ENERGY_KEYS:
        if k in n:
            kcal = _f(n[k])
            if k == "energy_100g" and kcal > 0:
                kcal = kcal / 4.184  # kJ -> kcal
            if kcal > 0:
                break

    name = (
        product.get("product_name_en")
        or product.get("product_name")
        or product.get("generic_name")
        or ""
    ).strip()
    if not name:
        return None

    # Reject rows with no usable nutrition -- a name-only hit is worse than a
    # miss, because the user logs it and gets 0 kcal silently.
    protein = _f(n.get("proteins_100g"))
    carbs = _f(n.get("carbohydrates_100g"))
    fat = _f(n.get("fat_100g"))
    if kcal <= 0:
        # Reconstruct from macros if energy is missing but macros aren't.
        derived = protein * 4 + carbs * 4 + fat * 9
        if derived <= 0:
            return None
        kcal = derived

    serving_g = _parse_serving_grams(product.get("serving_size")) or _f(
        product.get("serving_quantity"), 0
    )
    servings: list[dict[str, Any]] = [
        {"name": "100 g", "grams": 100.0, "is_default": serving_g <= 0}
    ]
    if serving_g and serving_g > 0:
        label = (product.get("serving_size") or f"{serving_g:g} g").strip()
        servings.insert(0, {"name": label, "grams": serving_g, "is_default": True})

    categories = product.get("categories_tags") or []
    is_liquid = any(
        t in categories
        for t in ("en:beverages", "en:drinks", "en:milks", "en:juices")
    )

    completeness = _f(product.get("completeness"), 0.4)

    return ResolvedFood(
        name=name,
        brand=(product.get("brands") or "").split(",")[0].strip() or None,
        barcode=str(product.get("code") or "") or None,
        source=FoodSource.off,
        source_id=str(product.get("code") or ""),
        calories=round(kcal, 1),
        protein_g=round(protein, 2),
        carbs_g=round(carbs, 2),
        fat_g=round(fat, 2),
        fiber_g=round(_f(n.get("fiber_100g")), 2),
        sugar_g=round(_f(n.get("sugars_100g")), 2),
        sodium_mg=round(_f(n.get("sodium_100g")) * 1000, 1),
        saturated_fat_g=round(_f(n.get("saturated-fat_100g")), 2),
        serving_sizes=servings,
        is_liquid=is_liquid,
        countries=[
            c.replace("en:", "") for c in (product.get("countries_tags") or [])
        ],
        # Crowd-sourced: trust it, but below a verified government dataset.
        data_quality=round(min(0.75, 0.35 + completeness * 0.4), 2),
        raw=product,
    )


async def off_lookup_barcode(
    client: httpx.AsyncClient, barcode: str
) -> ResolvedFood | None:
    url = f"{settings.OFF_BASE_URL}/api/v2/product/{barcode}.json"
    try:
        r = await client.get(url, params={"fields": _OFF_FIELDS})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("OFF barcode lookup failed for %s: %s", barcode, exc)
        return None

    if data.get("status") != 1 or not data.get("product"):
        return None
    return _off_to_resolved(data["product"])


async def off_search(
    client: httpx.AsyncClient, query: str, limit: int = 20, country: str | None = None
) -> list[ResolvedFood]:
    """Text search against OFF.

    NOTE: OFF's search endpoint is rate-limited far more aggressively than
    product reads (~10 req/min). Only call this on a local-DB miss, and cache
    the results.
    """
    params: dict[str, Any] = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": limit,
        "fields": _OFF_FIELDS,
        "sort_by": "popularity_key",
    }
    if country:
        params["tagtype_0"] = "countries"
        params["tag_contains_0"] = "contains"
        params["tag_0"] = country

    try:
        r = await client.get(f"{settings.OFF_BASE_URL}/cgi/search.pl", params=params)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("OFF search failed for %r: %s", query, exc)
        return []

    out = []
    for p in data.get("products", []) or []:
        resolved = _off_to_resolved(p)
        if resolved:
            out.append(resolved)
    return out


# ---------------------------------------------------------------------------
# USDA FoodData Central
# ---------------------------------------------------------------------------

_USDA_NUTRIENT_MAP = {
    1008: "calories",       # Energy (kcal)
    1003: "protein_g",
    1005: "carbs_g",
    1004: "fat_g",
    1079: "fiber_g",
    2000: "sugar_g",
    1093: "sodium_mg",
    1258: "saturated_fat_g",
}


def _usda_to_resolved(food: dict[str, Any]) -> ResolvedFood | None:
    values: dict[str, float] = {}
    for nut in food.get("foodNutrients", []) or []:
        nid = nut.get("nutrientId") or (nut.get("nutrient") or {}).get("id")
        if nid in _USDA_NUTRIENT_MAP:
            values[_USDA_NUTRIENT_MAP[nid]] = _f(
                nut.get("value") or nut.get("amount")
            )

    if not values.get("calories"):
        return None

    name = (food.get("description") or "").strip()
    if not name:
        return None

    serving_g = _f(food.get("servingSize"), 0)
    unit = (food.get("servingSizeUnit") or "g").lower()
    servings = [{"name": "100 g", "grams": 100.0, "is_default": serving_g <= 0}]
    if serving_g > 0 and unit in ("g", "ml"):
        servings.insert(
            0,
            {
                "name": f"{serving_g:g} {unit}",
                "grams": serving_g,
                "is_default": True,
            },
        )

    return ResolvedFood(
        name=name,
        brand=(food.get("brandOwner") or food.get("brandName") or None),
        barcode=str(food.get("gtinUpc") or "") or None,
        source=FoodSource.usda,
        source_id=str(food.get("fdcId") or ""),
        calories=round(values.get("calories", 0), 1),
        protein_g=round(values.get("protein_g", 0), 2),
        carbs_g=round(values.get("carbs_g", 0), 2),
        fat_g=round(values.get("fat_g", 0), 2),
        fiber_g=round(values.get("fiber_g", 0), 2),
        sugar_g=round(values.get("sugar_g", 0), 2),
        sodium_mg=round(values.get("sodium_mg", 0), 1),
        saturated_fat_g=round(values.get("saturated_fat_g", 0), 2),
        serving_sizes=servings,
        is_liquid=unit == "ml",
        countries=["united-states"],
        # Government-curated: higher trust than crowd-sourced OFF.
        data_quality=0.9 if food.get("dataType") == "Foundation" else 0.8,
        raw=food,
    )


async def usda_lookup_barcode(
    client: httpx.AsyncClient, barcode: str
) -> ResolvedFood | None:
    if not settings.USDA_FDC_API_KEY:
        return None
    try:
        r = await client.get(
            f"{settings.USDA_BASE_URL}/foods/search",
            params={
                "api_key": settings.USDA_FDC_API_KEY,
                "query": barcode,
                "dataType": "Branded",
                "pageSize": 5,
            },
        )
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("USDA barcode lookup failed for %s: %s", barcode, exc)
        return None

    for food in data.get("foods", []) or []:
        if str(food.get("gtinUpc") or "").lstrip("0") == barcode.lstrip("0"):
            return _usda_to_resolved(food)
    return None


async def usda_search(
    client: httpx.AsyncClient, query: str, limit: int = 20
) -> list[ResolvedFood]:
    if not settings.USDA_FDC_API_KEY:
        return []
    try:
        r = await client.get(
            f"{settings.USDA_BASE_URL}/foods/search",
            params={
                "api_key": settings.USDA_FDC_API_KEY,
                "query": query,
                "dataType": "Foundation,SR Legacy,Branded",
                "pageSize": limit,
            },
        )
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("USDA search failed for %r: %s", query, exc)
        return []

    out = []
    for food in data.get("foods", []) or []:
        resolved = _usda_to_resolved(food)
        if resolved:
            out.append(resolved)
    return out


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------


async def resolve_barcode_remote(barcode: str) -> tuple[ResolvedFood | None, str]:
    """Try every remote source in parallel; prefer the highest data quality.

    Running them concurrently rather than sequentially keeps p95 under ~1.5 s
    even when one source is slow, which is what makes the target
    "<1 second scan-to-log" achievable on a local-DB miss.
    """
    headers = {"User-Agent": settings.OFF_USER_AGENT}
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers) as client:
        results = await asyncio.gather(
            off_lookup_barcode(client, barcode),
            usda_lookup_barcode(client, barcode),
            return_exceptions=True,
        )

    candidates: list[tuple[ResolvedFood, str]] = []
    for res, label in zip(results, ("openfoodfacts", "usda")):
        if isinstance(res, ResolvedFood):
            candidates.append((res, label))

    if not candidates:
        return None, "none"

    best, label = max(candidates, key=lambda c: c[0].data_quality)
    return best, label


async def search_remote(
    query: str, limit: int = 20, country: str | None = None
) -> list[ResolvedFood]:
    headers = {"User-Agent": settings.OFF_USER_AGENT}
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers) as client:
        off, usda = await asyncio.gather(
            off_search(client, query, limit, country),
            usda_search(client, query, limit),
            return_exceptions=True,
        )

    out: list[ResolvedFood] = []
    for res in (off, usda):
        if isinstance(res, list):
            out.extend(res)

    # De-duplicate on (name, brand) and keep the highest-quality record.
    seen: dict[tuple[str, str], ResolvedFood] = {}
    for r in out:
        key = (r.name.lower().strip(), (r.brand or "").lower().strip())
        if key not in seen or r.data_quality > seen[key].data_quality:
            seen[key] = r

    return sorted(seen.values(), key=lambda r: -r.data_quality)[:limit]
