"""Deterministic alias generation for the Phase 3a food identity layer.

WHY THIS IS A SERVICE AND NOT A SCRIPT
Everything here is a pure function over plain dataclasses: same input, same
output, no clock, no uuid, no network, no database. The script in
`app/scripts/generate_aliases.py` is the only part that touches I/O. That split
is what makes the review artifact reproducible -- a reviewer can regenerate it
and diff it byte-for-byte against the one they approved, which is the whole
point of having a review gate before rows reach `food_aliases`.

WHY RULE-BASED AND NOT A MODEL CALL
An LLM cannot satisfy "deterministic". Every alias below comes from an explicit
rule that can be named in the `reason` field and argued with. `source='ai'`
still marks machine-derived rows, because the model's own docstring is right
that a machine-derived alias must never raise a food's `verification_tier` --
the provenance matters regardless of which kind of machine produced it.

NOTHING HERE WRITES TO THE DATABASE. Generation and insertion are separate
steps on purpose.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .food_text import detect_script, normalize

GENERATOR_VERSION = "1.0"

# Vocabulary pinned by ck_alias_type / ck_alias_source in models.FoodAlias.
# Kept as module constants so drift between here and the CHECK constraint is a
# failing test rather than a failed INSERT at the end of a long run.
ALIAS_TYPES = frozenset(
    {"canonical", "regional", "transliteration",
     "colloquial", "misspelling", "brand_variant"}
)
ALIAS_SOURCES = frozenset({"curated", "import", "ai", "user"})

# ----------------------------------------------------------------- brands

#: The 12 approved Indian brand families, each with an explicit word-boundary
#: pattern. Substring matching is NOT sufficient: ILIKE '%ITC%' matches 1,335
#: rows in the live catalogue -- "switch", "Mitchell", "kitchen" -- against a
#: few dozen genuine ITC products. The \b anchors are the difference between a
#: usable brand filter and garbage.
#:
#: `require_india` exists because "Nestle" and "Tata" are global marks. Nestle
#: alone matches 581 rows worldwide, most of which are not Nestle India
#: products and must not receive Indian-romanisation variants.
BRAND_FAMILIES: dict[str, tuple[str, bool]] = {
    "Amul": (r"\bamul\b", False),
    "Britannia": (r"\bbritannia\b", False),
    "Haldiram's": (r"\bhaldiram'?s?\b", False),
    "Parle": (r"\bparle\b", False),
    "MTR": (r"\bmtr\b", False),
    "Tata": (r"\btata\b", True),
    "Nestle India": (r"\bnestl[eé]\b", True),
    "Mother Dairy": (r"\bmother\s+dairy\b", False),
    "Aachi": (r"\baachi\b", False),
    "Everest": (r"\beverest\b", False),
    "Dabur": (r"\bdabur\b", False),
    "ITC": (r"\bitc\b", False),
}

_BRAND_RE = {
    fam: re.compile(pat, re.IGNORECASE) for fam, (pat, _) in BRAND_FAMILIES.items()
}

#: Sorted so iteration order never depends on dict insertion order.
BRAND_ORDER: tuple[str, ...] = tuple(sorted(BRAND_FAMILIES))

_INDIA_HINT = re.compile(r"\b(india|indian|bharat)\b", re.IGNORECASE)

# ------------------------------------------------------------ broad aliases

#: An alias that is only one of these is a category, not an identity. Attaching
#: "curry" to one specific curry makes that row win a search it has no claim
#: to, which is worse than the row not being found at all.
GENERIC_TERMS = frozenset({
    "bar", "biscuit", "biscuits", "bread", "cake", "candy", "cereal", "cheese",
    "chicken", "chips", "chocolate", "chutney", "coffee", "cookie", "cookies",
    "cream", "curd", "curry", "dal", "dessert", "drink", "egg", "fish", "flour",
    "fried", "fry", "ghee", "gravy", "juice", "masala", "meal", "meat", "milk",
    "mix", "mutton", "noodles", "oil", "paneer", "paste", "pickle", "powder",
    "pudding", "rice", "roti", "sabzi", "salad", "sauce", "seeds", "snack",
    "soup", "spice", "sweet", "tea", "vegetable", "water", "wheat", "yogurt",
})

#: Below this, a latin alias is more likely an abbreviation collision than a
#: name. 'idli' (4) is real; 'idl' is not.
MIN_LATIN_ALIAS_LEN = 4

#: Aliases held back from import pending a human call, keyed by normalised
#: form, with the reason recorded here rather than in a commit message.
#:
#: These are NOT deleted and NOT rejected. They stay in the review artifact
#: classified as `excluded_pending_review`, because silently dropping a
#: candidate is how a review gate stops being a review gate -- the next
#: reviewer would have no way to know the decision was ever made.
#:
#: This is a decision log, not a rule. Anything appearing here should
#: eventually be either promoted (the rule was right) or fixed at the rule
#: level (the rule was wrong).
EXCLUDED_PENDING_REVIEW: dict[str, str] = {
    "chiselings classic": (
        "romanisation of 'Cheeselings', a Parle brand coinage rather than an "
        "Indic word -- the ee->i rule should not have fired on it. The "
        "canonical 'cheeselings classic' and the brand-prefixed form are "
        "unaffected and remain import-ready."
    ),
}

# -------------------------------------------------- romanisation variants

#: Single-substitution romanisation alternates, applied one rule at a time so
#: the output stays bounded and explicable. Combining rules would produce
#: alu -> aalu -> ... and an unreviewable blow-up.
#:
#: DELIBERATELY one-directional (simplifying). Generating both directions
#: doubles the count for no recall gain, since search normalises the query and
#: the alias through the same function.
ROMAN_VARIANTS: tuple[tuple[str, str], ...] = (
    ("aa", "a"), ("ee", "i"), ("oo", "u"), ("ii", "i"), ("uu", "u"),
    ("kh", "k"), ("gh", "g"), ("bh", "b"), ("dh", "d"), ("th", "t"),
    ("ph", "f"), ("ksh", "x"), ("z", "j"),
)
MAX_VARIANTS_PER_FOOD = 6

#: Tokens the romanisation rules must not touch.
#:
#: WHY A PER-TOKEN GATE AND NOT A PER-FOOD ONE
#: Gating on "is this an Indian food" is not enough, because Indian brands sell
#: English-named products. Measured on the live catalogue, the whole-string
#: version produced `cookies`->`cukies`, `hide seek`->`hide sik`,
#: `beef dripping`->`bif dripping` and `noodles`->`nudles`: pure noise that a
#: reviewer would have to reject one at a time. Skipping English tokens keeps
#: `palak paneer`->`palak panir` while dropping all four of those.
ENGLISH_TOKENS = frozenset({
    "and", "beef", "biscuit", "bottle", "box", "butter", "cheese", "choco",
    "choose", "classic", "coffee", "combo", "cool", "cookie", "cookies",
    "cracker", "crackers", "cream", "creme", "deep", "deluxe", "family",
    "feed", "food", "free", "good", "green", "health", "healthy", "hide",
    "honey", "jar", "keep", "light", "minute", "minutes", "need", "noodles",
    "original", "pack", "plus", "pool", "pouch", "premium", "proof", "refill",
    "room", "school", "seeds", "seek", "sheet", "smooth", "soon", "special",
    "speed", "spoon", "sweet", "three", "tin", "toffee", "tooth", "value",
    "week", "white", "with", "without", "wood",
})

#: The skip set is ENGLISH_TOKENS ALONE. It must NOT be unioned with
#: GENERIC_TERMS: the two lists answer different questions. GENERIC_TERMS is
#: "too broad to stand as an alias"; this is "not an Indic word". `paneer`,
#: `ghee` and `sabzi` sit in the first and must stay romanisable -- panir, ghi
#: and sabji are exactly the spellings users type. The English category words
#: that DO need protecting (cheese, coffee, noodles, seeds) are listed above
#: explicitly instead.
ROMAN_SKIP: frozenset[str] = ENGLISH_TOKENS

_INDIAN_CUISINE = re.compile(r"^indian", re.IGNORECASE)


# -------------------------------------------------------------- datatypes

@dataclass(frozen=True, order=True)
class FoodRecord:
    """The projection of `food_items` this generator is allowed to see.

    Deliberately narrow: nutrition columns are irrelevant to naming, and not
    accepting them means a bug here cannot possibly corrupt them.
    """

    id: str
    name: str
    brand: str | None = None
    source: str = "curated"
    cuisine: str | None = None
    category: str | None = None
    countries: tuple[str, ...] = ()
    curated_aliases: tuple[str, ...] = ()


@dataclass(frozen=True, order=True)
class AliasCandidate:
    food_item_id: str
    normalized: str
    alias: str
    alias_type: str
    source: str
    confidence: float
    script: str
    lang: str
    rule: str
    reason: str

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True, order=True)
class Finding:
    kind: str
    severity: str
    normalized: str
    detail: str
    food_item_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["food_item_ids"] = list(self.food_item_ids)
        return d


@dataclass
class Report:
    accepted: list[AliasCandidate] = field(default_factory=list)
    #: The subset of `accepted` safe to INSERT without a further human
    #: call: exactly one target, no ambiguity.
    import_ready: list[AliasCandidate] = field(default_factory=list)
    rejected: list[AliasCandidate] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    input_digest: str = ""
    #: food_item_id -> name, so the artifact can state target identity
    #: without a second database read.
    names: dict = field(default_factory=dict)
    #: Where the input came from, filled in by the caller that did the I/O.
    #: The generator itself cannot know this without taking a dependency on
    #: the database, which is exactly what it is built to avoid.
    sources: dict = field(default_factory=dict)


# ---------------------------------------------------------------- helpers

def brand_family(brand: str | None, *, countries: Sequence[str] = (),
                 name: str = "") -> str | None:
    """Return the approved brand family for `brand`, or None.

    Word-boundary matched, and India-gated for the two global marks. Iterates
    BRAND_ORDER so a product matching two families resolves identically on
    every run.
    """
    if not brand:
        return None
    for fam in BRAND_ORDER:
        pattern, require_india = BRAND_FAMILIES[fam]
        if not _BRAND_RE[fam].search(brand):
            continue
        if require_india:
            haystack = " ".join([brand, name, *countries])
            if not _INDIA_HINT.search(haystack):
                continue
        return fam
    return None


def collapse_possessive(text: str) -> str:
    """Collapse Haldiram's -> Haldirams BEFORE normalize().

    normalize() maps the apostrophe to a space, so the raw string yields
    'haldiram s' -- a stray one-letter token that pollutes trigram matching and
    that no user will ever type. Stripping the apostrophe first is the fix.
    """
    return re.sub(r"(\w)'s\b", r"\1s", text)


def norm(text: str) -> str:
    """The project's normalize(), with the possessive fix applied first."""
    return normalize(collapse_possessive(text))


def is_indian(rec: FoodRecord) -> bool:
    return bool(
        (rec.cuisine and _INDIAN_CUISINE.match(rec.cuisine))
        or brand_family(rec.brand, countries=rec.countries, name=rec.name)
    )


def spelling_variants(normalized: str,
                      skip: frozenset[str] = ROMAN_SKIP) -> list[str]:
    """One-substitution romanisation alternates, deduped, order-stable.

    Substitutions apply PER TOKEN and only to tokens outside `skip`, so an
    English word sitting next to an Indic one is left alone: 'hide seek cashew'
    keeps its spelling while 'palak paneer' still yields 'palak panir'. Tokens
    containing digits are skipped too -- pack sizes are not words.
    """
    tokens = normalized.split()
    eligible = [
        i for i, t in enumerate(tokens)
        if t not in skip and not any(ch.isdigit() for ch in t)
    ]
    if not eligible:
        return []

    out: list[str] = []
    seen = {normalized}
    for old, new in ROMAN_VARIANTS:
        cand = list(tokens)
        changed = False
        for i in eligible:
            if old in cand[i]:
                cand[i] = cand[i].replace(old, new)
                changed = True
        if not changed:
            continue
        joined = re.sub(r"\s+", " ", " ".join(cand)).strip()
        if joined and joined not in seen:
            seen.add(joined)
            out.append(joined)
        if len(out) >= MAX_VARIANTS_PER_FOOD:
            break
    return out


def strip_brand(normalized_name: str, family: str | None) -> str:
    """Remove brand tokens from an already-normalised product name."""
    if not family:
        return normalized_name
    pattern, _ = BRAND_FAMILIES[family]
    stripped = re.sub(pattern, " ", normalized_name, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(s|ltd|limited|india|pvt)\b", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def is_broad(normalized: str) -> tuple[bool, str]:
    """Is this alias too generic to identify one food? -> (verdict, reason)."""
    if not normalized:
        return True, "empty after normalisation"
    tokens = normalized.split()
    if len(normalized) < MIN_LATIN_ALIAS_LEN:
        return True, "shorter than %d characters" % MIN_LATIN_ALIAS_LEN
    if len(tokens) == 1 and tokens[0] in GENERIC_TERMS:
        return True, "'%s' is a category, not a food" % tokens[0]
    if tokens and all(t in GENERIC_TERMS for t in tokens):
        return True, "every token is a generic category term"
    return False, ""


# ------------------------------------------------------------- generation

def _candidate(rec: FoodRecord, alias: str, alias_type: str, source: str,
               confidence: float, rule: str, reason: str) -> AliasCandidate:
    normalized = norm(alias)
    return AliasCandidate(
        food_item_id=rec.id,
        normalized=normalized,
        alias=alias.strip(),
        alias_type=alias_type,
        source=source,
        confidence=confidence,
        script=detect_script(alias),
        # We know the script but never the language: 'poha' could be tagged hi,
        # mr or gu with equal justification. '' means unspecified, which the
        # uq_alias_food_norm_lang constraint is explicitly built to tolerate.
        lang="",
        rule=rule,
        reason=reason,
    )


def generate_for_food(rec: FoodRecord) -> list[AliasCandidate]:
    """Every alias candidate for one food, in a stable rule order.

    Emits duplicates and junk freely -- filtering is `generate`'s job, and
    keeping the rules independent is what makes each one testable alone.
    """
    out: list[AliasCandidate] = []
    indian = is_indian(rec)
    family = brand_family(rec.brand, countries=rec.countries, name=rec.name)

    # 1. The name itself. Always canonical, always curated: it is already the
    #    food's identity, not a guess about it.
    out.append(_candidate(
        rec, rec.name, "canonical", "curated", 1.0,
        "canonical_name", "the food's own name",
    ))

    # 2. Aliases a human already wrote into names_i18n. Curated provenance,
    #    just below the canonical name.
    for alias in rec.curated_aliases:
        out.append(_candidate(
            rec, alias, "regional" if indian else "colloquial", "curated", 0.9,
            "curated_alias", "listed in names_i18n.aliases",
        ))

    # 3. Brand handling. Two directions, and they are not equivalent:
    #    the brandless residue is how a user actually searches ("aloo bhujia"),
    #    while brand+product is how the packet reads.
    if family:
        base = norm(rec.name)
        residue = strip_brand(base, family)
        if residue and residue != base:
            out.append(_candidate(
                rec, residue, "brand_variant", "ai", 0.75,
                "brand_stripped",
                "product name with the '%s' brand tokens removed" % family,
            ))
        fam_norm = norm(family)
        if fam_norm and fam_norm not in base:
            out.append(_candidate(
                rec, "%s %s" % (fam_norm, residue or base), "brand_variant",
                "ai", 0.7, "brand_prefixed",
                "brand family '%s' prefixed to the product name" % family,
            ))

    # 4. Romanisation alternates, Indian foods only. Applying these to
    #    "smoothie" would yield "smootie"; restricting by cuisine/brand is what
    #    keeps the rule from vandalising the western catalogue.
    if indian:
        seeds = [norm(rec.name)]
        seeds += [norm(a) for a in rec.curated_aliases]
        emitted: set[str] = set()
        for seed in seeds:
            if not seed:
                continue
            for variant in spelling_variants(seed):
                if variant in emitted:
                    continue
                emitted.add(variant)
                out.append(_candidate(
                    rec, variant, "misspelling", "ai", 0.6,
                    "romanisation_variant",
                    "single-substitution romanisation alternate of '%s'" % seed,
                ))
    return out


def _digest(records: Sequence[FoodRecord]) -> str:
    """Fingerprint of the exact input set, so a diff in the artifact can be
    attributed to a rule change rather than a changed catalogue."""
    h = hashlib.sha256()
    for rec in sorted(records, key=lambda r: r.id):
        h.update(repr(dataclasses.astuple(rec)).encode("utf-8"))
    return "sha256:" + h.hexdigest()


def generate(records: Iterable[FoodRecord],
             existing_food_names: frozenset[str] = frozenset(),
             known_food_ids: frozenset[str] | None = None) -> Report:
    """Generate, validate and sort every alias candidate.

    `existing_food_names` is an optional set of `food_items.name_normalized`
    values. When supplied, an alias that collides with a DIFFERENT food's name
    is flagged: 'poha' as an alias is useless if a food is already literally
    called Poha, because the alias would fight its own catalogue.

    `known_food_ids` is an optional set of live `food_items.id` values. When
    supplied, any candidate pointing outside it is rejected as a missing
    target. That check exists because `food_aliases.food_item_id` carries an FK
    with ON DELETE CASCADE: a stale id does not corrupt anything, it simply
    fails the INSERT and aborts the batch. Catching it here turns a failed
    import into a review note.
    """
    records = sorted(records, key=lambda r: r.id)
    raw: list[AliasCandidate] = []
    for rec in records:
        raw.extend(generate_for_food(rec))
    #: Captured before the missing-target filter reassigns `raw`, so
    #: accepted + rejected always reconciles against it.
    total_candidates = len(raw)

    name_by_id = {r.id: r.name for r in records}
    own_names = {norm(r.name) for r in records}

    accepted: list[AliasCandidate] = []
    rejected: list[AliasCandidate] = []
    findings: list[Finding] = []

    # -- missing target ----------------------------------------------------
    if known_food_ids is not None:
        still: list[AliasCandidate] = []
        for cand in raw:
            if cand.food_item_id in known_food_ids:
                still.append(cand)
            else:
                rejected.append(cand)
                findings.append(Finding(
                    kind="missing_target", severity="block",
                    normalized=cand.normalized,
                    detail="alias '%s' targets food_item_id %s, which is not "
                           "in the catalogue" % (cand.alias, cand.food_item_id),
                    food_item_ids=(cand.food_item_id,),
                ))
        raw = still

    # -- empty ------------------------------------------------------------
    for cand in raw:
        if not cand.normalized:
            rejected.append(cand)
            findings.append(Finding(
                kind="empty", severity="block", normalized="",
                detail="alias %r on %r normalises to the empty string"
                       % (cand.alias, name_by_id.get(cand.food_item_id, "?")),
                food_item_ids=(cand.food_item_id,),
            ))

    survivors = [c for c in raw if c.normalized]

    # -- duplicate: same (food, normalized) would break uq_alias_food_norm_lang
    by_key: dict[tuple[str, str], list[AliasCandidate]] = defaultdict(list)
    for cand in survivors:
        by_key[(cand.food_item_id, cand.normalized)].append(cand)

    deduped: list[AliasCandidate] = []
    for key in sorted(by_key):
        group = sorted(by_key[key], key=lambda c: (-c.confidence, c.rule))
        winner = group[0]
        deduped.append(winner)
        if len(group) > 1:
            rejected.extend(group[1:])
            # Two shapes of duplicate, reported separately because they mean
            # different things to a reviewer. Identical raw text is a rule
            # overlap; differing raw text that normalises the same ("Poha" vs
            # "poha!" vs " POHA ") is a data-entry inconsistency upstream in
            # names_i18n, and is worth seeing on its own.
            raw_texts = {c.alias for c in group}
            if len(raw_texts) == 1:
                kind, detail = "duplicate", (
                    "%d rules produced the identical alias '%s' for %r; kept "
                    "the %s rule (confidence %.2f), dropped %s"
                    % (len(group), key[1], name_by_id.get(key[0], "?"),
                       winner.rule, winner.confidence,
                       ", ".join(sorted(c.rule for c in group[1:]))))
            else:
                kind, detail = "case_or_punctuation_variant", (
                    "%d spellings differing only by case, whitespace or "
                    "punctuation collapse to '%s' for %r: %s; kept the %s rule"
                    % (len(raw_texts), key[1], name_by_id.get(key[0], "?"),
                       ", ".join(repr(t) for t in sorted(raw_texts)),
                       winner.rule))
            findings.append(Finding(
                kind=kind, severity="warn", normalized=key[1],
                detail=detail, food_item_ids=(key[0],),
            ))

    # -- broad -------------------------------------------------------------
    kept: list[AliasCandidate] = []
    for cand in deduped:
        broad, why = is_broad(cand.normalized)
        if broad and cand.rule != "canonical_name":
            rejected.append(cand)
            findings.append(Finding(
                kind="broad", severity="block", normalized=cand.normalized,
                detail="'%s' rejected for %r: %s"
                       % (cand.normalized,
                          name_by_id.get(cand.food_item_id, "?"), why),
                food_item_ids=(cand.food_item_id,),
            ))
        else:
            kept.append(cand)

    # -- ambiguous: one alias, several foods --------------------------------
    # NOT auto-rejected. 'kadala curry' legitimately naming two regional
    # variants is a judgement call for the reviewer, not for a rule. It is
    # however withheld from import -- see `import_ready` below.
    targets: dict[str, set[str]] = defaultdict(set)
    for cand in kept:
        targets[cand.normalized].add(cand.food_item_id)

    ambiguous_norms: set[str] = set()
    for normalized in sorted(targets):
        ids = targets[normalized]
        if len(ids) <= 1:
            continue
        ambiguous_norms.add(normalized)
        distinct_names = {
            norm(name_by_id.get(i, i)) for i in ids
        }
        # An alias hitting several rows that all carry the SAME name is not
        # alias ambiguity -- it is duplicate rows in the catalogue (20 rows
        # named "Milo", 13 "Nesquik"). Reported as its own kind so the
        # data-quality backlog stays separate from the naming decision.
        if len(distinct_names) == 1:
            kind, severity = "duplicate_catalogue_row", "deferred"
            detail = ("'%s' maps to %d catalogue rows that all share one "
                      "name (%s) -- duplicate rows, not alias ambiguity"
                      % (normalized, len(ids),
                         name_by_id.get(sorted(ids)[0], "?")))
        else:
            kind, severity = "ambiguous", "review"
            detail = ("'%s' maps to %d different foods: %s"
                      % (normalized, len(ids),
                         "; ".join(sorted(name_by_id.get(i, i) for i in ids))))
        findings.append(Finding(kind=kind, severity=severity,
                                normalized=normalized, detail=detail,
                                food_item_ids=tuple(sorted(ids))))

    # -- bare brand names ---------------------------------------------------
    # A brand is not a food. 'aachi' naming all seven Aachi products, or
    # 'gits' all seven Gits mixes, would make the brand match every item it
    # sells. These come from names_i18n already in the catalogue, not from the
    # rules here -- which is why the test is structural (the alias IS the
    # brand) rather than a hand-maintained blocklist.
    #
    # Scoped to the multi-target case on purpose: a single-product brand alias
    # is unambiguous and harmless, and a brand-QUALIFIED alias ('aachi idli')
    # is never touched because it does not equal the brand.
    brand_by_id = {r.id: r.brand for r in records}
    surviving: list[AliasCandidate] = []
    for cand in kept:
        brand = brand_by_id.get(cand.food_item_id)
        bare = bool(brand) and cand.normalized == norm(brand or "")
        if (bare and cand.rule == "curated_alias"
                and len(targets[cand.normalized]) > 1):
            rejected.append(cand)
            findings.append(Finding(
                kind="bare_brand", severity="block",
                normalized=cand.normalized,
                detail="'%s' is the bare brand name and maps to %d products; "
                       "importing it would match every item that brand sells"
                       % (cand.normalized, len(targets[cand.normalized])),
                food_item_ids=(cand.food_item_id,),
            ))
        else:
            surviving.append(cand)
    kept = surviving

    # -- collides with another food's own name ------------------------------
    catalogue = existing_food_names | own_names
    for cand in kept:
        if cand.rule == "canonical_name":
            continue
        if cand.normalized in catalogue and cand.normalized != norm(
                name_by_id.get(cand.food_item_id, "")):
            findings.append(Finding(
                kind="shadows_food_name", severity="review",
                normalized=cand.normalized,
                detail="alias '%s' on %r is already the name of a different "
                       "food in the catalogue"
                       % (cand.normalized,
                          name_by_id.get(cand.food_item_id, "?")),
                food_item_ids=(cand.food_item_id,),
            ))

    # -- explicitly held back -----------------------------------------------
    for cand in kept:
        if cand.normalized in EXCLUDED_PENDING_REVIEW:
            findings.append(Finding(
                kind="excluded_pending_review", severity="review",
                normalized=cand.normalized,
                detail="'%s' (%s, from %r) held back: %s"
                       % (cand.normalized, cand.rule,
                          name_by_id.get(cand.food_item_id, "?"),
                          EXCLUDED_PENDING_REVIEW[cand.normalized]),
                food_item_ids=(cand.food_item_id,),
            ))

    accepted = sorted(kept)
    rejected = sorted(rejected)
    findings = sorted(findings)

    # -- import-ready -------------------------------------------------------
    # The subset safe to INSERT without a further human call. Everything here
    # has exactly one target; anything ambiguous stays in `accepted` for
    # review but is withheld, because picking one of several targets by rule
    # is exactly the guess this project refuses to make.
    import_ready = sorted(
        c for c in accepted
        if c.normalized not in ambiguous_norms
        and len(targets[c.normalized]) == 1
        and c.normalized not in EXCLUDED_PENDING_REVIEW
    )

    by_kind = _tally(findings, "kind")
    counts = {
        "input_foods": len(records),
        "candidates_generated": total_candidates,
        "accepted": len(accepted),
        "import_ready": len(import_ready),
        "withheld_from_import": len(accepted) - len(import_ready),
        "rejected": len(rejected),
        "findings": len(findings),
        "import_ready_before_exclusions": (
            len(import_ready) + by_kind.get("excluded_pending_review", 0)),
        "excluded_pending_review": by_kind.get("excluded_pending_review", 0),
        "ambiguous_candidates": by_kind.get("ambiguous", 0),
        "bare_brand_exclusions": by_kind.get("bare_brand", 0),
        "duplicate_catalogue_collisions":
            by_kind.get("duplicate_catalogue_row", 0),
        # Named roll-ups. `findings_by_kind` already carries these, but a
        # reviewer should not have to know which kind names map to which
        # question -- and a missing key there reads as 0, not as absent.
        "duplicates": (by_kind.get("duplicate", 0)
                       + by_kind.get("case_or_punctuation_variant", 0)),
        "duplicates_exact": by_kind.get("duplicate", 0),
        "duplicates_after_normalisation":
            by_kind.get("case_or_punctuation_variant", 0),
        "collisions": (by_kind.get("ambiguous", 0)
                       + by_kind.get("duplicate_catalogue_row", 0)
                       + by_kind.get("shadows_food_name", 0)),
        "collisions_multiple_targets": (by_kind.get("ambiguous", 0)
                                        + by_kind.get("duplicate_catalogue_row", 0)),
        "collisions_with_food_names": by_kind.get("shadows_food_name", 0),
        "missing_targets": by_kind.get("missing_target", 0),
        "broad_aliases": by_kind.get("broad", 0),
        "empty_aliases": by_kind.get("empty", 0),
        "by_alias_type": _tally(accepted, "alias_type"),
        "by_source": _tally(accepted, "source"),
        "by_rule": _tally(accepted, "rule"),
        "findings_by_kind": by_kind,
    }
    return Report(accepted=accepted, import_ready=import_ready,
                  rejected=rejected, findings=findings, counts=counts,
                  input_digest=_digest(records), names=dict(name_by_id))


def _tally(items: Sequence, attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        key = getattr(item, attr)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


# ------------------------------------------------------------- serialising

def report_to_dict(report: Report) -> dict:
    """The review artifact.

    Carries NO timestamp on purpose. A wall-clock field would make two runs of
    identical input differ, which would destroy the one property that makes
    this reviewable: regenerate, diff, and any change is a real change.
    """
    ready = {(c.food_item_id, c.normalized) for c in report.import_ready}
    withheld = {
        f.normalized for f in report.findings
        if f.kind in ("ambiguous", "duplicate_catalogue_row")
    }

    def record(cand: AliasCandidate, status: str) -> dict:
        """One artifact row, with an explicit reason for its disposition.

        `review_classification` exists so no candidate is ever merely absent
        from a list -- every one states what happened to it and why.
        """
        d = cand.as_dict()
        d["target_name"] = report.names.get(cand.food_item_id, "")
        d["status"] = status
        is_ready = (status == "accepted"
                    and (cand.food_item_id, cand.normalized) in ready)
        d["import_ready"] = is_ready
        if status == "rejected":
            d["review_classification"] = "rejected"
            d["exclusion_reason"] = None
        elif cand.normalized in EXCLUDED_PENDING_REVIEW:
            d["review_classification"] = "excluded_pending_review"
            d["exclusion_reason"] = EXCLUDED_PENDING_REVIEW[cand.normalized]
        elif cand.normalized in withheld:
            d["review_classification"] = "withheld_ambiguous"
            d["exclusion_reason"] = (
                "alias maps to more than one catalogue target; deferred to a "
                "human decision rather than guessed"
            )
        elif is_ready:
            d["review_classification"] = "import_ready"
            d["exclusion_reason"] = None
        else:
            d["review_classification"] = "withheld_other"
            d["exclusion_reason"] = None
        return d

    return {
        "generator_version": GENERATOR_VERSION,
        "input_digest": report.input_digest,
        "sources": report.sources,
        "counts": report.counts,
        "findings": [f.as_dict() for f in report.findings],
        "aliases": [record(c, "accepted") for c in report.accepted],
        "import_ready": [record(c, "accepted") for c in report.import_ready],
        "rejected": [record(c, "rejected") for c in report.rejected],
    }


def report_to_json(report: Report) -> str:
    return json.dumps(report_to_dict(report), indent=2, sort_keys=True,
                      ensure_ascii=False) + "\n"
