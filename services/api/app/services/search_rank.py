"""Two-arm search ranking: direct food matches plus alias-assisted matches.

THE PROBLEM THIS SOLVES
Search can only match `food_items.search_text`, so a regional or misspelled
name reaches nothing. Verified against the 1,353 imported aliases, the arm now
carries queries the direct arm cannot answer:

    dosai        -> Plain dosa      (regional,    0.9)
    panir        -> Paneer          (misspelling, 0.6)
    kanda poha   -> Poha            (regional,    0.9)

Note what is NOT there: `avalakki` was never imported, because the curated Poha
row lists `kanda poha` and nothing else. The alias layer only knows what the
catalogue told it -- it does not invent regional names, and coverage is exactly
as good as `names_i18n` plus the generated variants.

WHY THE MERGE IS A PURE FUNCTION
Ranking is where a search feature is won or lost, and it is also the part that
is miserable to test through a database. Everything here operates on plain
dataclasses, so every ordering rule below has a test that states it directly
instead of asserting on whatever Postgres happened to return.

THE INVARIANT THAT MATTERS MOST
With an empty alias arm, `rank()` must reproduce the existing ordering exactly.
`food_aliases` has zero rows today, and this code ships before it has any, so
"no aliases" is not an edge case -- it is the production case on day one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .food_text import normalize

#: Arm names. Direct = matched on the food's own text; alias = matched via a
#: `food_aliases` row.
ARM_DIRECT = "direct"
ARM_ALIAS = "alias"

#: Match tiers, best first. The integer IS the sort key, so a lower number must
#: always mean a better match.
TIER_EXACT = 0
TIER_PREFIX = 1
TIER_SUBSTRING = 2
TIER_FUZZY = 3

TIER_NAMES = {
    TIER_EXACT: "exact",
    TIER_PREFIX: "prefix",
    TIER_SUBSTRING: "substring",
    TIER_FUZZY: "fuzzy",
}

#: An alias match is never allowed to outrank a direct EXACT match.
#:
#: Concretely: searching "poha" must return the food actually named Poha ahead
#: of a food that merely carries "poha" as a low-confidence generated alias.
#: The arm is therefore a tiebreak WITHIN a tier, never across tiers -- which
#: is why it sits after `tier` and not before it in the sort key.
ARM_ORDER = {ARM_DIRECT: 0, ARM_ALIAS: 1}


@dataclass(frozen=True)
class Candidate:
    """One row from either arm, before merging."""

    food_item_id: str
    name: str
    #: The text this candidate matched on: the food's own normalised name for
    #: the direct arm, the alias's `normalized` for the alias arm. This is the
    #: IDENTITY, and only it can produce an exact match.
    matched_text: str
    #: Extra text the row is also searchable in -- `food_items.search_text`,
    #: a blob of name + brand + category + tags.
    #:
    #: WHY EXACT IS NOT ALLOWED FROM HERE
    #: The live query ranks prefix and substring against search_text, so
    #: ignoring it would silently reorder today's results. But an exact hit on
    #: a blob is meaningless -- "poha" == "poha indian breakfast rice" is never
    #: true, and a one-word food whose blob happens to equal the query would
    #: outrank the food actually named that. Exact stays identity-only.
    haystack: str = ""
    arm: str = ARM_DIRECT
    similarity: float = 0.0
    log_count: int = 0
    data_quality: float = 0.0
    alias_type: str | None = None
    alias_confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.arm not in ARM_ORDER:
            raise ValueError("unknown arm: %r" % self.arm)


@dataclass(frozen=True)
class Ranked:
    """One merged, de-duplicated result."""

    food_item_id: str
    name: str
    tier: int
    arm: str
    matched_text: str
    similarity: float
    log_count: int
    data_quality: float
    alias_type: str | None = None
    alias_confidence: float = 1.0
    #: Every other way this same food was reached, best-first. Kept for
    #: debugging and for the "matched via ..." line the UI can show; it is
    #: never used for ordering.
    also_matched: tuple[str, ...] = field(default=())

    @property
    def tier_name(self) -> str:
        return TIER_NAMES[self.tier]

    @property
    def via_alias(self) -> bool:
        return self.arm == ARM_ALIAS


def match_tier(query_normalized: str, matched_text: str) -> int:
    """Classify how well `matched_text` answers the query.

    Both arguments are expected already normalised. Substring is deliberately
    ranked below prefix: "dosa" should surface "Dosa" before "Masala dosa".
    """
    if not query_normalized or not matched_text:
        return TIER_FUZZY
    if matched_text == query_normalized:
        return TIER_EXACT
    if matched_text.startswith(query_normalized):
        return TIER_PREFIX
    if query_normalized in matched_text:
        return TIER_SUBSTRING
    return TIER_FUZZY


def tier_for(query_normalized: str, cand: Candidate) -> int:
    """Best tier this candidate can claim, across identity and haystack."""
    tier = match_tier(query_normalized, cand.matched_text)
    if tier == TIER_EXACT or not cand.haystack:
        return tier
    other = match_tier(query_normalized, cand.haystack)
    if other == TIER_EXACT:          # demoted: a blob cannot be an identity
        other = TIER_PREFIX
    return min(tier, other)


def _sort_key(r: Ranked) -> tuple:
    """The total ordering. Every component is explicit, and the final
    `food_item_id` guarantees a total order so two runs never differ."""
    return (
        r.tier,                     # exact < prefix < substring < fuzzy
        ARM_ORDER[r.arm],           # direct before alias, within a tier
        -r.alias_confidence,        # a hand-curated alias before a generated one
        -r.similarity,              # trigram score
        -r.log_count,               # popularity
        -r.data_quality,            # better-sourced data
        r.food_item_id,             # total order -> determinism
    )


def rank(query: str, candidates: list[Candidate],
         limit: int | None = None) -> list[Ranked]:
    """Merge both arms into one ordered, de-duplicated result list.

    Collapsing is by `food_item_id`: a food reachable both directly and through
    two aliases is ONE result, represented by its strongest match. Returning it
    three times would push three other foods off the page.
    """
    q = normalize(query)

    scored: list[Ranked] = []
    for cand in candidates:
        scored.append(Ranked(
            food_item_id=cand.food_item_id,
            name=cand.name,
            tier=tier_for(q, cand),
            arm=cand.arm,
            matched_text=cand.matched_text,
            similarity=cand.similarity,
            log_count=cand.log_count,
            data_quality=cand.data_quality,
            alias_type=cand.alias_type,
            # A direct match has no alias confidence to speak of; pinning it to
            # 1.0 keeps the comparison meaningful instead of letting a missing
            # value sort direct hits below generated aliases.
            alias_confidence=(
                cand.alias_confidence if cand.arm == ARM_ALIAS else 1.0
            ),
        ))

    scored.sort(key=_sort_key)

    best: dict[str, Ranked] = {}
    extras: dict[str, list[str]] = {}
    for r in scored:
        if r.food_item_id not in best:
            best[r.food_item_id] = r
            extras[r.food_item_id] = []
        elif r.matched_text != best[r.food_item_id].matched_text:
            extras[r.food_item_id].append(r.matched_text)

    merged = [
        Ranked(**{**vars(w), "also_matched": tuple(extras[fid])})
        for fid, w in best.items()
    ]
    merged.sort(key=_sort_key)
    return merged[:limit] if limit is not None else merged


def direct_candidate(row, query_normalized: str = "") -> Candidate:
    """Adapt a `food_items` row (mapping or object) to a Candidate.

    Kept here rather than in the router so the adapter is testable too.
    """
    get = row.get if hasattr(row, "get") else (lambda k, d=None: getattr(row, k, d))
    name = get("name", "") or ""
    return Candidate(
        food_item_id=str(get("id", "")),
        name=name,
        # Prefer the backfilled column; fall back for rows that predate it.
        matched_text=get("name_normalized", "") or normalize(name),
        haystack=get("search_text", "") or "",
        arm=ARM_DIRECT,
        similarity=float(get("sim", 0.0) or 0.0),
        log_count=int(get("log_count", 0) or 0),
        data_quality=float(get("data_quality", 0.0) or 0.0),
    )


def alias_candidate(row) -> Candidate:
    """Adapt a `food_aliases` join row to a Candidate."""
    get = row.get if hasattr(row, "get") else (lambda k, d=None: getattr(row, k, d))
    return Candidate(
        food_item_id=str(get("food_item_id", "") or get("id", "")),
        name=get("name", "") or "",
        matched_text=get("normalized", "") or "",
        haystack=get("search_text", "") or "",
        arm=ARM_ALIAS,
        similarity=float(get("sim", 0.0) or 0.0),
        log_count=int(get("log_count", 0) or 0),
        data_quality=float(get("data_quality", 0.0) or 0.0),
        alias_type=get("alias_type", None),
        alias_confidence=float(get("confidence", 1.0) or 1.0),
    )
