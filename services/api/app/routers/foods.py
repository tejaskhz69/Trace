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

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, select as sa_select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select

from ..config import get_settings
from ..db import get_session
from ..models import FoodItem, FoodSource, User
from ..services.search_rank import (
    ARM_ALIAS,
    alias_candidate,
    direct_candidate,
    rank,
)
from ..schemas import (
    BarcodeResolveResponse,
    CustomFoodRequest,
    FoodItemPublic,
    FoodSearchResponse,
)
from ..services.licensing import licence_for
from ..services.food_sources import ResolvedFood, resolve_barcode_remote, search_remote
from .auth import current_user

settings = get_settings()

router = APIRouter(prefix="/api/foods", tags=["foods"])

LOCAL_RESULT_FLOOR = 5  # below this many local hits, ask the remote sources

#: Per-arm overfetch. Each arm pulls this multiple of `limit` so ranking
#: has something to choose between; a shared limit would let one arm
#: starve the other before the merge ever ran.
ARM_OVERFETCH = 4
#: Hard ceiling per arm, so a term matching thousands of aliases still
#: does bounded work.
MAX_ARM_FETCH = 200

# Minimum word_similarity for a fuzzy hit.
#
# THIS WINDOW IS TIGHTER THAN IT LOOKS -- measured, not guessed:
#
#   'panner tika' -> 'paneer tikka'        0.471   must MATCH (real typo)
#   'poha'        -> 'sambar powder mtr'   0.400   must MISS  (trigram noise)
#
# 0.45 is the midpoint. Raising it to 0.5 breaks two-word typos; lowering it
# to 0.4 starts returning unrelated foods. If you change this, re-run
# test_search_still_tolerates_typos_after_the_fix -- it exists to catch
# exactly that, and the exact-substring arm below is what carries the
# ordinary, correctly-spelled case.
#
# APPLIED VIA `SET LOCAL pg_trgm.word_similarity_threshold`, per transaction,
# rather than as a bind parameter in the WHERE clause -- that is what lets the
# `<%` operator use the GIN index. Postgres's own default for this GUC is 0.6,
# so a value that fails to apply makes search stricter rather than erroring.
WORD_SIMILARITY_FLOOR = 0.45


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


def _public(item: FoodItem,
            prov: tuple[str, Optional[str]]) -> FoodItemPublic:
    """Serialise one result, attaching provenance and per-row licensing.

    LICENCE IS PER ROW, NEVER GLOBAL. The catalogue mixes ODbL (Open Food
    Facts), public-domain (USDA) and user-curated data. A single blanket
    notice would misattribute two thirds of it, so the row carries its own
    licence, tier and upstream URL and the UI renders what it is given.

    Falls back to `licensing.licence_for(source)` only when the column is
    unset -- which is fail-closed ('unknown'), not a guess.
    """
    arm, alias_text = prov
    out = FoodItemPublic.model_validate(item, from_attributes=True)
    licence = getattr(item, "source_licence", None) or licence_for(
        getattr(item.source, "value", item.source)
    )
    out.source_licence = licence if isinstance(licence, str) else licence.value
    out.verification_tier = getattr(item, "verification_tier", None)
    out.source_url = getattr(item, "source_url", None)
    out.matched_via = arm
    out.matched_alias = alias_text
    return out


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

    # WORD similarity, not whole-string similarity.
    #
    # `search_text` is a blob: name + brand + category + tags. Comparing a
    # short query against the whole blob scores low by construction, so
    # `similarity()` made a food HARDER to find the more metadata it had --
    # exactly backwards. Measured before the fix:
    #
    #   'biryani'   vs 'chicken biryani indian north rice biriya...'  0.216
    #   'dal tadka' vs 'dal tadka indian north dal yellow dal to...'  0.263
    #
    # Both fell under the 0.3 default threshold, so searching "biryani"
    # returned nothing while "Chicken biryani" sat in the table, approved.
    #
    # `word_similarity(q, text)` scores the query against the best-matching
    # word sequence INSIDE the blob instead. Same two queries now score 1.00,
    # and typo tolerance is unaffected ('panner tika' -> 'Paneer tikka', 0.83).
    #
    # THE `<%` OPERATOR, NOT A COMPARISON ON word_similarity().
    #
    # This used to read `word_similarity(:q, search_text) >= :floor`, on the
    # reasoning that `<%` consults `pg_trgm.word_similarity_threshold` and
    # search must not depend on a GUC that differs between a developer's
    # Postgres and Neon. The reasoning was right; the conclusion cost us the
    # index.
    #
    # Postgres registers an index strategy for the OPERATOR, not for the
    # return value of the function. A function result can only be computed
    # row by row -- and because this arm sits in an OR, a disjunction is only
    # index-usable when EVERY arm is, so the non-indexable arm dragged the
    # perfectly good ILIKE down with it. The whole query went sequential.
    # Measured on 578,773 rows before this fix:
    #
    #   Seq Scan on food_items, 252,997 rows removed by filter ....  8,962 ms
    #   Bitmap Heap Scan via ix_food_search_trgm ....................   358 ms
    #
    # `SET LOCAL` below gets the determinism back without giving up the
    # index: the threshold is pinned per transaction, so it no longer depends
    # on server config, and it cannot leak to another request sharing the
    # connection. `a <% b` is defined as
    # `word_similarity(a, b) >= <that threshold>`, so this is the same
    # comparison -- verified by identical hit counts on every query measured.
    #
    # THE FAILURE MODE TO KNOW ABOUT: if that SET LOCAL ever stops applying,
    # the threshold falls back to Postgres's 0.6 default and search silently
    # gets STRICTER -- no error, just quietly worse typo tolerance.
    # `test_search_threshold_is_actually_applied` exists to fail loudly there.
    #
    # The CAST is required: asyncpg sends the parameter as `unknown`, and
    # `<%` has no unknown-typed variant.
    # `set_config(..., is_local => true)` rather than the `SET LOCAL` statement:
    # SET is a utility command, not a planned one, so it cannot take a bind
    # parameter -- `SET LOCAL ... = $1` is a syntax error. set_config is an
    # ordinary function call with identical transaction-scoped semantics, and
    # it keeps the threshold parameterised instead of interpolated into SQL.
    await session.execute(
        text(
            "SELECT set_config('pg_trgm.word_similarity_threshold', :floor, true)"
        ),
        {"floor": str(WORD_SIMILARITY_FLOOR)},
    )

    # TWO ARMS IN ONE ROUND TRIP.
    #
    # The direct arm is the original query, unchanged in its WHERE and in what
    # it can match. The alias arm joins `food_aliases`, which is what finally
    # lets 'avalakki' and 'sambhar' find the right food -- before it existed
    # they returned confidently wrong results, because no row in the catalogue
    # carried a regional name.
    #
    # UNION ALL, not two round trips and not a correlated subquery: one
    # statement, no N+1.
    #
    # MEASURED PLANS (578,773 food_items, 1,353 food_aliases):
    #   direct 'dosa'  -> Bitmap Index Scan ix_food_search_trgm     132 ms
    #   alias  'panir' -> Seq Scan on food_aliases                   18 ms
    #   alias  'mix'   -> Seq Scan on food_aliases                   53 ms
    #
    # The alias arm currently seq-scans, and that is CORRECT: food_aliases is
    # 1,520 kB, so the planner reads the whole thing for less than the index
    # would cost. `ix_alias_normalized_trgm` is verified usable -- forcing
    # enable_seqscan=off produces a Bitmap Index Scan on it -- so the plan
    # flips on its own as the table grows. Neither arm ever seq-scans
    # food_items, which is the scan that actually matters.
    #
    # EACH ARM IS BOUNDED SEPARATELY. A shared LIMIT would let one arm starve
    # the other -- a query matching 5,000 aliases would crowd out every direct
    # hit before ranking ever ran. Overfetching per arm and then ranking in
    # Python is what makes the merge correct; the factor is small and capped so
    # the work stays bounded regardless of how popular a term is.
    fetch = min(MAX_ARM_FETCH, max(limit * ARM_OVERFETCH, ARM_OVERFETCH))

    sql = text(
        """
        WITH direct AS (
            SELECT f.*,
                   word_similarity(:q, f.search_text) AS sim,
                   'direct'      AS arm,
                   NULL::text    AS normalized,
                   NULL::text    AS alias_type,
                   1.0::float8   AS confidence
            FROM food_items f
            WHERE (
                f.moderation_status = 'approved'
                -- ...OR it is the caller's own. `create_custom_food` files a
                -- user's food as 'pending' and calls it "private to its
                -- author", but this clause used to filter on 'approved' alone
                -- -- so the author could not find their own food either, and a
                -- private library that nobody can search is not a library.
                -- Scoped to the caller, so one person's pending row stays
                -- invisible to everyone else exactly as before.
                OR f.created_by_user_id = :uid
              )
              AND (
                f.search_text ILIKE :contains
                OR CAST(:q AS text) <% f.search_text
              )
            ORDER BY
              (f.search_text ILIKE :prefix) DESC,
              (f.search_text ILIKE :contains) DESC,
              sim DESC,
              f.log_count DESC,
              f.data_quality DESC
            LIMIT :fetch
        ),
        aliased AS (
            SELECT f.*,
                   word_similarity(:q, a.normalized) AS sim,
                   'alias'    AS arm,
                   a.normalized AS normalized,
                   a.alias_type AS alias_type,
                   a.confidence AS confidence
            FROM food_aliases a
            JOIN food_items f ON f.id = a.food_item_id
            -- Retired aliases must never resurface. `is_active` is the
            -- moderation switch; a row is deactivated rather than deleted so
            -- the correction history survives.
            WHERE a.is_active
              AND (
                f.moderation_status = 'approved'
                OR f.created_by_user_id = :uid
              )
              AND (
                a.normalized ILIKE :contains
                OR CAST(:q AS text) <% a.normalized
              )
            ORDER BY
              (a.normalized ILIKE :prefix) DESC,
              sim DESC,
              a.confidence DESC,
              f.log_count DESC
            LIMIT :fetch
        )
        SELECT * FROM direct
        UNION ALL
        SELECT * FROM aliased
        """
    )
    rows = (
        await session.execute(
            sql,
            {
                "q": needle,
                "uid": user.id,
                "prefix": f"{needle}%",
                "contains": f"%{needle}%",
                # `floor` is gone from this statement -- the threshold now
                # lives in the SET LOCAL above, which is what makes the
                # comparison indexable.
                "fetch": fetch,
            },
        )
    ).mappings().all()

    # Ranking and de-duplication happen in `services/search_rank.py`, which is
    # pure and exhaustively tested. The router stays thin: it fetches, hands
    # over, and maps back.
    candidates = [
        alias_candidate(r) if r["arm"] == ARM_ALIAS else direct_candidate(r)
        for r in rows
    ]
    ranked = rank(needle, candidates, limit=limit)

    # One row per food_item_id, so a food reachable through three aliases is
    # one result rather than three.
    by_id = {}
    for r in rows:
        by_id.setdefault(str(r["id"]), r)

    # Column names the adapters in services/search_rank.py read, plus the
    # arm marker. They are NOT food_items columns and must not be handed to
    # the FoodItem constructor.
    _COMPUTED = {"sim", "arm", "normalized", "alias_type", "confidence"}
    items: list[FoodItem] = []
    provenance: dict[str, tuple[str, Optional[str]]] = {}
    for hit in ranked:
        row = by_id[hit.food_item_id]
        items.append(FoodItem(**{k: v for k, v in row.items()
                                 if k not in _COMPUTED}))
        provenance[hit.food_item_id] = (
            hit.arm, hit.matched_text if hit.via_alias else None
        )
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
        results=[_public(i, provenance.get(i.id, ("direct", None))) for i in items],
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


@router.post("/parse")
async def parse_meal_text(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    text: str = Body(embed=True, max_length=500),
) -> dict:
    """Describe a meal in words; get portioned foods back.

        "two rotis and a bowl of dal tadka"
            -> Roti          x2, 40 g each
               Dal tadka     1 bowl, 200 g

    WHY THIS IS THE ONE PAID FEATURE WORTH THE MONEY
    Everything else a metered provider sells, we already have for free and
    often better: Open Food Facts beats it on non-US barcodes, USDA beats it
    on raw ingredients. Quantity and unit parsing is the exception -- it is
    genuinely hard, and there is no free equivalent. It is also the same shift
    the voice workout logger makes on the training side: describe what you
    did, don't fill in a form.

    RESULTS ARE CACHED INTO OUR OWN TABLE. Every food that comes back is
    written to `food_items`, so the second person to log "dal tadka" is served
    from Postgres and costs nothing. That is what turns a per-call bill into a
    fixed one.

    NOTHING IS LOGGED HERE. This returns candidates for the user to confirm,
    exactly like the photo scan and the voice logger -- a parser that silently
    logged "two rotis" as four would corrupt the intake history, and intake is
    half of the adaptive TDEE.
    """
    from ..services import paid_sources

    if not paid_sources.available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Describing a meal in words needs a nutrition-parsing provider, "
                "which isn't configured. Use search or the photo scan instead."
            ),
        )

    try:
        foods = await paid_sources.parse_meal(text)
    except paid_sources.PaidBudgetExhausted as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    items = []
    for hit in foods:
        try:
            items.append(await persist_resolved(session, hit))
        except Exception:  # noqa: BLE001 - a write failure must not lose the parse
            await session.rollback()

    return {
        "query": text,
        "count": len(items),
        "items": [FoodItemPublic.model_validate(i, from_attributes=True) for i in items],
        "message": None
        if items
        else "Couldn't work out what that was. Try naming the foods more plainly.",
    }


@router.get("/sources/status")
async def sources_status(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    """What data sources are live, and how much of today's paid budget is left.

    Exposed because a metered integration fails in a way that is invisible
    from the outside: a bad key, an exhausted budget and "this food genuinely
    does not exist" all look identical at the call site. This is how you tell
    them apart without reading logs.
    """
    from ..services import paid_sources

    return {
        "free": {
            "openfoodfacts": True,
            "usda": bool(settings.USDA_FDC_API_KEY),
            "local_catalogue": True,
        },
        # The client shows this in the search placeholder. It is read live
        # rather than hardcoded because the number moved from 12,959 to
        # 273,316 in one ingestion run, and a stale "Search 12,000 foods"
        # undersells the catalogue to the exact user deciding whether to
        # bother typing.
        "catalogue_size": await session.scalar(
            sa_select(func.count(FoodItem.id))
        ),
        "paid": {
            "nutritionix": paid_sources.available(),
            "budget": paid_sources.budget_status(),
        },
    }
