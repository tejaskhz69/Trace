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

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, or_, text
from sqlalchemy import select as sa_select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..config import get_settings
from ..db import get_session
from ..models import FoodItem, FoodSource, User
from ..schemas import (
    BarcodeResolveResponse,
    CustomFoodRequest,
    FoodItemPublic,
    FoodSearchResponse,
)
from ..services import gtin
from ..services.food_sources import ResolvedFood, resolve_barcode_remote, search_remote
from ..services.licensing import (
    DISPLAY_NAMES,
    Licence,
    attribution_line,
    display_name_for,
    licence_for,
)
from ..services.search_rank import (
    ARM_ALIAS,
    alias_candidate,
    direct_candidate,
    rank,
)
from .auth import current_user

settings = get_settings()
log = logging.getLogger(__name__)

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


# THE DIRECT ARM IS A CASCADE, AND THAT IS THE WHOLE PERFORMANCE STORY.
#
# It used to be one scan over `contains OR fuzzy`, ordered by
#   (prefix DESC, contains DESC, sim DESC, log_count DESC, data_quality DESC).
#
# Read that sort key again: the first two components are BOOLEANS, and they
# outrank `sim`. So every prefix match sorts above every non-prefix match, and
# every substring match above every fuzzy-only one -- unconditionally. Which
# means that once the prefix set alone contains `fetch` rows, NOTHING in the
# substring or fuzzy sets can reach the returned page. The old query computed
# them anyway.
#
# Measured on the live catalogue (578,773 rows), for 'mix':
#
#   prefix    ILIKE 'mix%'      1,576 rows
#   substring ILIKE '%mix%'    18,645 rows
#   fuzzy     'mix' <% ...     77,095 rows
#
# The old plan bitmap-OR'd the last two into ~123,000 candidate rows, visited
# every one in the heap (268 MB of buffer reads) and evaluated
# `word_similarity` on all of them -- to return 100 rows that were all drawn
# from the first 1,576.
#
# So: evaluate the stages in order and stop as soon as one fills the quota.
# Each later stage carries `(SELECT count(*) FROM <earlier>) < :fetch`, which
# Postgres plans as a one-time InitPlan filter -- when it is false the scan
# beneath it reports "never executed" and costs nothing.
#
# MEASURED on the live catalogue, interleaved A/B, median of 7 runs each
# (interleaved because measuring all of A then all of B lets cache state
# invert a 30% difference on the wide queries):
#
#   query             before      after
#   dosa               47 ms      47 ms
#   panir           1,540 ms   1,263 ms
#   mix             8,319 ms   1,153 ms     <- 7.2x
#   plain dosa        697 ms     707 ms
#   chick           1,593 ms     901 ms     <- 1.8x
#   tikka              69 ms      48 ms
#   zzzqqxnotafood     37 ms      30 ms
#   TOTAL          12,302 ms   4,148 ms     <- 3.0x
#
# Nothing regressed: the narrow queries, where all three stages have to run
# and this does three scans where the old plan did one, come out level.
#
# `panir` and `plain dosa` barely move, and that is expected rather than a
# failure: both have almost no substring matches (2 and 1), so the fuzzy stage
# has to run, and its cost is the heap visit it forces -- a GIN trigram bitmap
# is lossy, so every candidate row must be fetched to recheck `<%` against
# `search_text`, and food_items is 641 MB. Fixing THOSE two needs an ordered
# (GiST k-NN) trigram index so the top matches can be walked in similarity
# order without visiting the rest. That is a migration, not a query rewrite,
# and is deliberately out of scope here.
#
# WHY THIS RETURNS THE SAME RESULTS
# The stages partition the old WHERE clause -- `NOT ILIKE :prefix` and
# `NOT ILIKE :contains` make them disjoint -- and the final ORDER BY re-applies
# the original key over their union. Verified against the old statement on the
# live catalogue by comparing the MULTISET OF SORT KEYS, not ids: identical for
# every query measured. Ids differ for some queries only where rows tie on
# every component of the key, which the old statement broke arbitrarily and
# this one breaks by `f.id` -- see the note on determinism below.
#
# ILIKE IS KEPT DELIBERATELY. `search_text` is lowercase in all 578,773 rows
# today, so plain LIKE would return the same rows and measured ~12% faster.
# That 12% is inside this machine's run-to-run noise, and nothing in the schema
# ENFORCES the lowercase invariant -- one ingestion script writing mixed case
# would make LIKE silently miss rows, with no error. Not worth it.
#
# `f.id` IS A TIEBREAK, AND IT FIXES A REAL BUG. Without a total order, rows
# tied on every sort component are returned in whatever order the executor
# produced them, and under a parallel plan that varies BETWEEN RUNS: the old
# statement returns a different result set for 'mix' on three consecutive
# executions of the same query. `services/search_rank.rank()` was already
# total; the SQL that chooses which candidates it even sees was not.
#
# TWO ARMS, STILL ONE ROUND TRIP.
#
# The alias arm joins `food_aliases`, which is what lets 'panir' and 'sambhar'
# find the right food -- before it existed they returned confidently wrong
# results, because no row in the catalogue carried a regional name.
#
# UNION ALL, not two round trips and not a correlated subquery: one statement,
# no N+1. The alias arm still seq-scans `food_aliases` and that is CORRECT --
# the table is 1,520 kB, so the planner reads all of it for less than the index
# would cost, and `ix_alias_normalized_trgm` is verified usable (forcing
# enable_seqscan=off produces a Bitmap Index Scan on it), so the plan flips on
# its own as the table grows. It costs 15-20 ms and is not the bottleneck.
#
# EACH ARM IS BOUNDED SEPARATELY. A shared LIMIT would let one arm starve the
# other -- a query matching 5,000 aliases would crowd out every direct hit
# before ranking ever ran.
#
# Module-level so the benchmark script measures THIS statement rather than a
# copy that can drift from it. See app/scripts/bench_search.py.

SEARCH_SQL = text(
    """
    WITH prefix_hits AS MATERIALIZED (
        SELECT f.*, word_similarity(:q, f.search_text) AS sim
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
          AND f.search_text ILIKE :prefix
        ORDER BY sim DESC, f.log_count DESC, f.data_quality DESC, f.id
        LIMIT :fetch
    ),
    substring_hits AS MATERIALIZED (
        SELECT f.*, word_similarity(:q, f.search_text) AS sim
        FROM food_items f
        -- The gate. False => the scan below is never executed.
        WHERE (SELECT count(*) FROM prefix_hits) < :fetch
          AND (
            f.moderation_status = 'approved'
            OR f.created_by_user_id = :uid
          )
          AND f.search_text ILIKE :contains
          -- Disjoint from the stage above, so the union cannot spend two of
          -- its `fetch` slots on one row.
          AND f.search_text NOT ILIKE :prefix
        ORDER BY sim DESC, f.log_count DESC, f.data_quality DESC, f.id
        LIMIT :fetch
    ),
    fuzzy_hits AS MATERIALIZED (
        SELECT f.*, word_similarity(:q, f.search_text) AS sim
        FROM food_items f
        WHERE (SELECT count(*) FROM prefix_hits)
              + (SELECT count(*) FROM substring_hits) < :fetch
          AND (
            f.moderation_status = 'approved'
            OR f.created_by_user_id = :uid
          )
          AND CAST(:q AS text) <% f.search_text
          AND f.search_text NOT ILIKE :contains
        ORDER BY sim DESC, f.log_count DESC, f.data_quality DESC, f.id
        LIMIT :fetch
    ),
    direct AS (
        SELECT u.*,
               'direct'      AS arm,
               NULL::text    AS normalized,
               NULL::text    AS alias_type,
               1.0::float8   AS confidence
        FROM (
            SELECT * FROM prefix_hits
            UNION ALL
            SELECT * FROM substring_hits
            UNION ALL
            SELECT * FROM fuzzy_hits
        ) u
        -- The ORIGINAL sort key, re-applied over the union. Recomputing the
        -- two booleans here costs nothing (at most 3 x :fetch rows reach this
        -- point) and avoids carrying a stage marker through to the wire,
        -- where the row adapters would have to know to ignore it.
        ORDER BY
          (u.search_text ILIKE :prefix) DESC,
          (u.search_text ILIKE :contains) DESC,
          u.sim DESC,
          u.log_count DESC,
          u.data_quality DESC,
          u.id
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
          f.log_count DESC,
          f.id
        LIMIT :fetch
    )
    SELECT * FROM direct
    UNION ALL
    SELECT * FROM aliased
    """
)


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
        "updated_at": datetime.now(UTC),
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
            prov: tuple[str, str | None] = ("direct", None)) -> FoodItemPublic:
    """Serialise one food. THE ONLY WAY a FoodItem becomes a FoodItemPublic.

    LICENCE IS PER ROW, NEVER GLOBAL. The catalogue mixes ODbL (Open Food
    Facts), public-domain (USDA) and user-curated data. A single blanket
    notice would misattribute two thirds of it, so the row carries its own
    licence, tier and upstream URL and the UI renders what it is given.

    Falls back to `licensing.licence_for(source)` only when the column is
    unset -- which is fail-closed ('unknown'), not a guess.

    WHY EVERY ENDPOINT MUST COME THROUGH HERE
    It used to be only /search. The other five paths called
    `FoodItemPublic.model_validate(...)` directly and therefore returned no
    attribution at all -- including `/barcode/{barcode}`, which is the single
    most Open-Food-Facts-heavy route in the app: scanning a packaged product
    is exactly how an ODbL row reaches a screen. The credit was correct
    wherever it appeared and absent wherever somebody had forgotten it, which
    is the worst of both. `prov` defaults so there is no reason left to
    bypass this function.
    """
    arm, alias_text = prov
    out = FoodItemPublic.model_validate(item, from_attributes=True)
    source = getattr(item.source, "value", item.source)
    licence = getattr(item, "source_licence", None) or licence_for(source)
    out.source_licence = licence if isinstance(licence, str) else licence.value
    out.verification_tier = getattr(item, "verification_tier", None)
    out.source_url = getattr(item, "source_url", None)
    out.matched_via = arm
    out.matched_alias = alias_text

    # ATTRIBUTION TEXT IS COMPOSED HERE, NOT IN THE CLIENT.
    #
    # The wording and the source->licence mapping that produces it now travel
    # together, so a source added to the API can never render as "SOURCE
    # UNKNOWN" on a client that has not shipped yet. `attribution` is None --
    # not an empty string -- for our own curated and user rows, which is how
    # the UI knows to render nothing at all rather than an empty notice.
    #
    # The stored licence is passed through: a row whose `source_licence` says
    # 'unknown' must SAY 'licence not recorded' rather than inherit ODbL from
    # the source table.
    #
    # The Licence() coercion is guarded: `source_licence` is a plain text
    # column, so a hand-edited or future value that is not a Licence member
    # must degrade to "we do not know" rather than 500 a search.
    try:
        parsed = Licence(out.source_licence)
    except ValueError:
        parsed = Licence.unknown

    # AN UNMAPPED SOURCE SENDS NEITHER FIELD, ON PURPOSE.
    #
    # The client reads `source_name` as "this response carries composed
    # attribution" and `attribution: null` as "nothing to credit". Sending a
    # placeholder name with a null sentence would therefore make an unknown
    # source render as SILENTLY OURS -- the one reading that is definitely
    # wrong. Sending nothing makes the client fall back to its own table,
    # which reports "SOURCE UNKNOWN". `test_every_source_is_mapped` means this
    # branch should be unreachable; it is here because "unreachable" and
    # "safe when reached" are different properties.
    out.source_name = display_name_for(source) if source in DISPLAY_NAMES else None
    out.attribution = attribution_line(source, parsed)
    return out


@router.get("/search", response_model=FoodSearchResponse)
async def search_foods(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=25, le=50),
    country: str | None = Query(default=None, description="e.g. 'india'"),
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

    # The two-arm statement itself is `SEARCH_SQL`, defined above.
    fetch = min(MAX_ARM_FETCH, max(limit * ARM_OVERFETCH, ARM_OVERFETCH))
    rows = (
        await session.execute(
            SEARCH_SQL,
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
    provenance: dict[str, tuple[str, str | None]] = {}
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
            except Exception:
                await session.rollback()
        source_label = "local+remote"

    took = int((time.perf_counter() - started) * 1000)
    return FoodSearchResponse(
        query=q,
        results=[_public(i, provenance.get(i.id, ("direct", None))) for i in items],
        took_ms=took,
        source=source_label,
    )


#: How long a "this barcode is not in any source" answer stays believed.
#:
#: WITHOUT THIS, EVERY MISS IS PERMANENTLY EXPENSIVE. A barcode nobody has
#: catalogued -- a regional snack, an own-label, anything Open Food Facts
#: covers thinly -- costs two upstream HTTP calls and, once both miss, a
#: metered Nutritionix call. The same shopper scanning the same shelf twice
#: pays that twice. Misses are also the COMMON case for exactly the products
#: this app cares about most.
#:
#: Ten minutes, not a day: Open Food Facts is crowd-sourced and a product can
#: appear minutes after somebody adds it -- often the same user who just
#: failed to find it. Long enough to cover a shopping trip, short enough that
#: "I added it, why can't I see it" never happens.
#:
#: DELIBERATELY IN-PROCESS AND NEGATIVE-ONLY. Positive results are already
#: persisted as `food_items` rows by `persist_resolved`, so caching those here
#: would be a second, staler copy of a thing the database already owns. And an
#: in-process dict needs no schema change, no eviction daemon, and cannot
#: outlive a deploy -- a cache that survives a bad deploy is a liability.
NEGATIVE_CACHE_TTL_S = 600
#: Bounded so a scan-happy client cannot grow this without limit.
NEGATIVE_CACHE_MAX = 4096

#: gtin14 -> monotonic timestamp of the miss. Keyed on the NORMALISED code,
#: never the raw scan: UPC-A and EAN-13 of one product must share one entry.
_barcode_misses: dict[str, float] = {}


def _miss_is_fresh(gtin14: str) -> bool:
    seen = _barcode_misses.get(gtin14)
    if seen is None:
        return False
    if time.monotonic() - seen > NEGATIVE_CACHE_TTL_S:
        _barcode_misses.pop(gtin14, None)
        return False
    return True


def _record_miss(gtin14: str) -> None:
    if len(_barcode_misses) >= NEGATIVE_CACHE_MAX:
        # Drop the oldest quarter rather than clearing everything: a full
        # flush would re-expose the whole shelf a user just scanned.
        for stale in sorted(_barcode_misses, key=_barcode_misses.get)[
            : NEGATIVE_CACHE_MAX // 4
        ]:
            _barcode_misses.pop(stale, None)
    _barcode_misses[gtin14] = time.monotonic()


#: What to tell the user for each way a scan can fail to identify a product.
#: Every one of these names a DIFFERENT next action, which is the entire point
#: of distinguishing them.
_REFUSAL_MESSAGES = {
    gtin.STATUS_NOT_NUMERIC: (
        "That doesn't look like a product barcode. Try searching by name.",
    ),
    gtin.STATUS_BAD_LENGTH: (
        "That scan came out incomplete. Hold steady and try again, or search "
        "by name.",
    ),
    gtin.STATUS_BAD_CHECK_DIGIT: (
        "That barcode didn't scan cleanly — it may be damaged or curved. Try "
        "again, or search by name.",
    ),
    gtin.STATUS_RESTRICTED: (
        "That's an in-store label, not a product barcode — it only means "
        "something inside that shop. Search by name, or snap the nutrition "
        "label instead.",
    ),
}


@router.get("/barcode/{barcode}", response_model=BarcodeResolveResponse)
async def resolve_barcode(
    barcode: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    symbology: str | None = Query(
        default=None,
        description="What the scanner decoded, e.g. 'upc_e'. Disambiguates "
        "UPC-E from EAN-8, which share a length but not a meaning.",
    ),
) -> BarcodeResolveResponse:
    """Resolve a scanned barcode. Validate -> local -> Open Food Facts -> USDA.

    Try it with 8906136651951 (Pintola High Protein Oats Dark Chocolate) --
    a local-only implementation returns nothing; this chain returns the
    product with 25 g protein / 100 g and a 50 g serving size.

    VALIDATION HAPPENS BEFORE ANY I/O, AND IT DID NOT USED TO.
    This endpoint accepted any 6-to-14-digit string and sent it straight to
    two external APIs. `services/gtin.py` -- GS1 mod-10, the restricted and
    coupon prefix ranges, the length gate -- has existed and been tested all
    along, and the scan path simply never called it. The consequences were
    not theoretical:

      * an in-store deli sticker ('02...') is not globally unique, so two
        supermarkets issue the same number for different things. Looking one
        up invites a confident match on somebody else's product, which is the
        one failure a food database must not have.
      * a 6, 9, 10 or 11-digit string is a truncated or mistyped scan. There
        is no such GTIN. It was still worth two HTTP round trips.
      * a bad check digit means the symbol was misread. Same.

    LOOKUP IS BY `gtin14`, NOT BY THE RAW STRING.
    The old query matched `barcode IN {code, code.lstrip('0'), code.zfill(13)}`
    -- string juggling that folds UPC-A onto EAN-13 and nothing else, against
    a column holding whatever each source happened to send. `gtin14` is the
    normalised form, is populated for 504,850 of the 565,839 rows that carry a
    barcode, and is indexed (`ix_food_gtin14`). The legacy variant match is
    kept as a fallback for the rows the backfill could not normalise, so this
    strictly widens what resolves.
    """
    raw = barcode.strip()
    status, gtin14 = gtin.classify(raw, symbology)

    if gtin14 is None:
        # Malformed: not numeric, wrong length, or a failed check digit.
        # 200, not 400. This is a well-formed request about a barcode that
        # turned out not to be a product identifier -- the client needs to
        # render an explanation, not catch an exception. A 4xx here would also
        # be indistinguishable, at the client, from an expired token.
        return BarcodeResolveResponse(
            found=False,
            barcode=raw,
            status=status,
            gtin14=None,
            retryable=True,
            resolved_from=None,
            message=_REFUSAL_MESSAGES[status][0],
        )

    # RESTRICTED CODES ARE LOCAL-ONLY, NOT REFUSED.
    #
    # A number-system-2 or -4 code is retailer-scoped: the same digits mean
    # different products in different chains. Sending one to Open Food Facts
    # is how a user gets confidently shown somebody else's product, which is
    # the failure this whole module exists to prevent.
    #
    # But refusing it outright is also wrong, and measurably so: 1,079 rows
    # already in the catalogue carry one, and they are real own-label groceries
    # somebody took the trouble to record. Answering from OUR catalogue is not
    # a guess about a global identifier -- it is returning the row we hold.
    #
    # So: look locally, never remotely, and say plainly what the identity is
    # worth if nothing matches.
    local_only = status == gtin.STATUS_RESTRICTED

    # Normalised first, raw variants second. The variant set is what the old
    # implementation matched on and exists only for rows without a gtin14.
    legacy_variants = {raw, raw.lstrip("0"), raw.zfill(13)}
    local = await session.scalar(
        select(FoodItem).where(
            or_(
                FoodItem.gtin14 == gtin14,  # type: ignore[arg-type]
                FoodItem.barcode.in_(list(legacy_variants)),  # type: ignore[union-attr]
            )
        )
    )
    if local:
        return BarcodeResolveResponse(
            found=True,
            barcode=raw,
            # The status still says `restricted` on a hit. The client shows the
            # product, but the identity is retailer-scoped and the response
            # does not pretend otherwise.
            status=status,
            gtin14=gtin14,
            retryable=False,
            item=_public(local),
            resolved_from="local",
        )

    if local_only:
        return BarcodeResolveResponse(
            found=False,
            barcode=raw,
            status=gtin.STATUS_RESTRICTED,
            gtin14=gtin14,
            # Re-scanning an in-store label is not a recovery, it is a loop.
            # Nothing about pointing the camera at it again will change the
            # fact that no global source can answer for it.
            retryable=False,
            resolved_from=None,
            message=_REFUSAL_MESSAGES[gtin.STATUS_RESTRICTED][0],
        )

    if _miss_is_fresh(gtin14):
        return BarcodeResolveResponse(
            found=False,
            barcode=raw,
            status="not_found",
            gtin14=gtin14,
            retryable=True,
            resolved_from="cache",
            message=(
                "We couldn't find this product. Snap the nutrition label and "
                "we'll read it for you, or add it manually -- it'll be "
                "available to everyone next time."
            ),
        )

    try:
        resolved, label = await resolve_barcode_remote(raw)
    except asyncio.CancelledError:
        # The client hung up. Never swallow this -- doing so breaks task
        # cancellation and leaves the request handler running for nobody.
        raise
    except Exception as exc:
        # AN OUTAGE IS NOT A MISSING PRODUCT, and must never be cached as one.
        # Reporting "we couldn't find it" during an Open Food Facts outage
        # teaches the user their product does not exist and sends them off to
        # type eleven numbers by hand.
        #
        # LOGGED WITH A TRACEBACK, deliberately. The catch has to be broad --
        # a scan must degrade rather than 500 -- but a broad catch also
        # swallows OUR bugs and presents them to the user as somebody else's
        # outage. `log.exception` is what makes the difference visible in the
        # logs: a TypeError here is a defect, not a provider being down. This
        # is not hypothetical; it caught a malformed test fixture during
        # development, reported as `upstream_error` with a cheerful message.
        log.exception("Barcode lookup failed upstream for %s: %s", gtin14, exc)
        return BarcodeResolveResponse(
            found=False,
            barcode=raw,
            status="upstream_error",
            gtin14=gtin14,
            retryable=True,
            resolved_from=None,
            message="Couldn't reach the product database. Try again in a moment.",
        )

    if resolved is None:
        _record_miss(gtin14)
        return BarcodeResolveResponse(
            found=False,
            barcode=raw,
            status="not_found",
            gtin14=gtin14,
            retryable=True,
            resolved_from=None,
            message=(
                "We couldn't find this product. Snap the nutrition label and "
                "we'll read it for you, or add it manually -- it'll be "
                "available to everyone next time."
            ),
        )

    item = await persist_resolved(session, resolved)
    # A product that has just been catalogued is no longer a miss.
    _barcode_misses.pop(gtin14, None)
    return BarcodeResolveResponse(
        found=True,
        barcode=raw,
        status=gtin.STATUS_OK,
        gtin14=gtin14,
        retryable=False,
        item=_public(item),
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
    return _public(item)


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
    return [_public(FoodItem(**dict(r))) for r in rows]


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
        except Exception:
            await session.rollback()

    return {
        "query": text,
        "count": len(items),
        "items": [_public(i) for i in items],
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
