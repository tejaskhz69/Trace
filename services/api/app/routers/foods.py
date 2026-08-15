"""Food search, barcode resolution, and custom foods.

The search strategy is "local first, remote on miss, always write back":

  * Local search uses pg_trgm similarity, so "panner tika" finds "Paneer
    Tikka" and "chapathi" finds "Chapati". Typo tolerance is not optional --
    it is the difference between a 2-tap log and a user giving up.
  * On a weak local result set we fan out to Open Food Facts + USDA, persist
    what we find, and return it in the same response. The user never sees the
    difference; your database just quietly grows into whatever your users
    actually eat.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select

from ..db import get_session
from ..models import FoodItem, FoodSource, User
from ..schemas import (
    BarcodeResolveResponse,
    CustomFoodRequest,
    FoodItemPublic,
    FoodSearchResponse,
)
from ..services.food_sources import ResolvedFood, resolve_barcode_remote, search_remote
from .auth import current_user

router = APIRouter(prefix="/api/foods", tags=["foods"])

LOCAL_RESULT_FLOOR = 5  # below this many local hits, ask the remote sources


def build_search_text(
    name: str,
    brand: str | None,
    names_i18n: dict | None,
    category: str | None,
) -> str:
    parts = [name, brand or "", category or ""]
    if names_i18n:
        for v in names_i18n.values():
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, list):
                parts.extend(str(x) for x in v)
    return " ".join(p for p in parts if p).lower()


async def persist_resolved(
    session: AsyncSession, resolved: ResolvedFood
) -> FoodItem:
    """Upsert a remote result into the local catalogue.

    ON CONFLICT DO UPDATE on (source, source_id) so re-scanning the same
    product refreshes rather than duplicating.
    """
    values = {
        "source": resolved.source.value,
        "source_id": resolved.source_id,
        "name": resolved.name,
        "brand": resolved.brand,
        "barcode": resolved.barcode,
        "calories": resolved.calories,
        "protein_g": resolved.protein_g,
        "carbs_g": resolved.carbs_g,
        "fat_g": resolved.fat_g,
        "fiber_g": resolved.fiber_g,
        "sugar_g": resolved.sugar_g,
        "sodium_mg": resolved.sodium_mg,
        "saturated_fat_g": resolved.saturated_fat_g,
        "serving_sizes": resolved.serving_sizes,
        "is_liquid": resolved.is_liquid,
        "countries": resolved.countries,
        "data_quality": resolved.data_quality,
        "is_verified": resolved.source == FoodSource.usda,
        "search_text": build_search_text(resolved.name, resolved.brand, None, None),
        "updated_at": datetime.now(timezone.utc),
    }

    stmt = (
        pg_insert(FoodItem)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_food_source",
            set_={
                k: v
                for k, v in values.items()
                if k not in ("source", "source_id")
            },
        )
        .returning(FoodItem)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()


@router.get("/search", response_model=FoodSearchResponse)
async def search_foods(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=25, le=50),
    country: Optional[str] = Query(default=None, description="e.g. 'india'"),
    remote: bool = Query(default=True, description="Fan out on a weak local result"),
) -> FoodSearchResponse:
    started = time.perf_counter()
    needle = q.strip().lower()

    # pg_trgm similarity + popularity + data quality. The 0.25 threshold is
    # loose enough for real typos and tight enough to avoid nonsense.
    sql = text(
        """
        SELECT *, similarity(search_text, :q) AS sim
        FROM food_items
        WHERE moderation_status = 'approved'
          AND (search_text % :q OR search_text ILIKE :prefix)
        ORDER BY
          (search_text ILIKE :prefix) DESC,
          sim DESC,
          log_count DESC,
          data_quality DESC
        LIMIT :limit
        """
    )
    rows = (
        await session.execute(
            sql, {"q": needle, "prefix": f"{needle}%", "limit": limit}
        )
    ).mappings().all()

    items = [FoodItem(**{k: v for k, v in r.items() if k != "sim"}) for r in rows]
    source_label = "local"

    if remote and len(items) < LOCAL_RESULT_FLOOR:
        remote_hits = await search_remote(q, limit=limit - len(items), country=country)
        known_ids = {(i.source, i.source_id) for i in items}
        for hit in remote_hits:
            if (hit.source, hit.source_id) in known_ids:
                continue
            try:
                items.append(await persist_resolved(session, hit))
            except Exception:  # noqa: BLE001 - never fail search on a write error
                await session.rollback()
        source_label = "local+remote"

    took = int((time.perf_counter() - started) * 1000)
    return FoodSearchResponse(
        query=q,
        results=[
            FoodItemPublic.model_validate(i, from_attributes=True) for i in items
        ],
        took_ms=took,
        source=source_label,
    )


@router.get("/barcode/{barcode}", response_model=BarcodeResolveResponse)
async def resolve_barcode(
    barcode: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> BarcodeResolveResponse:
    """Resolve a scanned barcode. Local -> Open Food Facts -> USDA -> miss.

    Try it with 8906136651951 (Pintola High Protein Oats Dark Chocolate) --
    a local-only implementation returns nothing; this chain returns the
    product with 25 g protein / 100 g and a 50 g serving size.
    """
    code = barcode.strip()
    if not code.isdigit() or not (6 <= len(code) <= 14):
        raise HTTPException(status_code=400, detail="Not a valid barcode.")

    # EAN-13 vs UPC-A: the same product is '0' + UPC in EAN-13 form. Check both.
    variants = {code, code.lstrip("0"), code.zfill(13)}

    local = await session.scalar(
        select(FoodItem).where(FoodItem.barcode.in_(list(variants)))  # type: ignore[union-attr]
    )
    if local:
        return BarcodeResolveResponse(
            found=True,
            barcode=code,
            item=FoodItemPublic.model_validate(local, from_attributes=True),
            resolved_from="local",
        )

    resolved, label = await resolve_barcode_remote(code)
    if resolved is None:
        return BarcodeResolveResponse(
            found=False,
            barcode=code,
            resolved_from=None,
            message=(
                "We couldn't find this product. Snap the nutrition label and "
                "we'll read it for you, or add it manually -- it'll be "
                "available to everyone next time."
            ),
        )

    item = await persist_resolved(session, resolved)
    return BarcodeResolveResponse(
        found=True,
        barcode=code,
        item=FoodItemPublic.model_validate(item, from_attributes=True),
        resolved_from=label,
    )


@router.post("/custom", response_model=FoodItemPublic, status_code=201)
async def create_custom_food(
    payload: CustomFoodRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> FoodItemPublic:
    """User-contributed food.

    Sanity-check macros against calories before accepting: a row claiming
    500 kcal with 1 g of everything is a typo, and once it's in the shared
    catalogue it poisons everyone's logs.
    """
    derived = payload.protein_g * 4 + payload.carbs_g * 4 + payload.fat_g * 9
    if payload.calories > 0 and derived > 0:
        drift = abs(derived - payload.calories) / payload.calories
        if drift > 0.30:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Those macros work out to ~{derived:.0f} kcal, but you "
                    f"entered {payload.calories:.0f}. Please double-check."
                ),
            )

    item = FoodItem(
        source=FoodSource.user,
        source_id=None,
        name=payload.name.strip(),
        brand=payload.brand,
        barcode=payload.barcode,
        calories=payload.calories,
        protein_g=payload.protein_g,
        carbs_g=payload.carbs_g,
        fat_g=payload.fat_g,
        fiber_g=payload.fiber_g,
        is_liquid=payload.is_liquid,
        serving_sizes=[s.model_dump() for s in payload.serving_sizes]
        or [{"name": "100 g", "grams": 100.0, "is_default": True}],
        created_by_user_id=user.id,
        data_quality=0.3,
        # Private to its author until a moderator approves it -- one bad public
        # entry is worse than a thousand missing ones.
        moderation_status="pending",
        search_text=build_search_text(payload.name, payload.brand, None, None),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return FoodItemPublic.model_validate(item, from_attributes=True)


@router.get("/recent", response_model=list[FoodItemPublic])
async def recent_foods(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    limit: int = Query(default=20, le=50),
) -> list[FoodItemPublic]:
    """Recently logged foods -- the fastest path to a 2-tap re-log."""
    sql = text(
        """
        SELECT f.* FROM food_items f
        JOIN (
            SELECT food_item_id, MAX(logged_at) AS last_logged
            FROM meal_logs
            WHERE user_id = :uid AND food_item_id IS NOT NULL
            GROUP BY food_item_id
        ) m ON m.food_item_id = f.id
        ORDER BY m.last_logged DESC
        LIMIT :limit
        """
    )
    rows = (
        await session.execute(sql, {"uid": user.id, "limit": limit})
    ).mappings().all()
    return [
        FoodItemPublic.model_validate(FoodItem(**dict(r)), from_attributes=True)
        for r in rows
    ]
