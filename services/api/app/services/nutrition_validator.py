"""Plausibility validation for imported nutrition data.

WHY THIS EXISTS
---------------
Public food databases are full of transcription errors, and a wrong entry is
strictly worse than a missing one: a missing entry costs the user 20 seconds
of manual entry, a wrong entry silently corrupts their whole week and produces
a bogus strength verdict.

Real examples found in Open Food Facts / USDA Branded while building the Indian
brand catalogue (Aug 2026):

  * MTR Rava Idli (8901042954516) lists 1.5 g protein/100 g. The product is
    80% semolina; semolina alone is ~12 g protein/100 g. True value ~10-12 g.
    Wrong by a factor of ~7 -- and protein is the exact input the strength
    adjudication engine depends on.
  * Aachi Rice Idli (8904209305541) lists 133 kcal/100 g. A dry idli mix is
    330-360. That is an AS-PREPARED panel filed as if it were as-sold.
  * Gits Sambar Mix: 5,480 mg sodium/100 g (13.7 g salt).
  * Eastern Rice Rava: 46.7 g fibre/100 g. Physically impossible.
  * Bambino Multigrain Vermicelli: sodium "16.29 g" -- a mg/g unit error.
  * Four different Eastern SKUs share one identical macro block: a generic
    panel copy-pasted across products.

Every check below exists because of one of those.

DESIGN
------
Pure functions, no I/O. Returns a verdict plus structured issues; the caller
decides whether to accept, quarantine, or auto-correct. Nothing is silently
mutated -- an auto-correction is always reported so it can be audited.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Atwater factors (kcal per gram)
KCAL_PROTEIN = 4.0
KCAL_CARB = 4.0
KCAL_FAT = 9.0
KCAL_FIBRE = 2.0  # partially fermented; EU uses 2 kcal/g

#: FIBRE ENERGY IS A RANGE, NOT A NUMBER. Insoluble fibre passes through and
#: yields nothing; soluble fibre is fermented to short-chain fatty acids and
#: yields around 2 kcal/g. Regulators split the difference differently: the EU
#: assigns 2, the US counts fibre inside total carbohydrate at 4. So fibre
#: contributes somewhere between these, and pretending otherwise is what makes
#: bran look defective.
KCAL_FIBRE_LOW = 2.0
KCAL_FIBRE_HIGH = 4.0

#: Which convention a source uses for `carbs_g`. MEASURED, not assumed:
#:
#:   usda        "Carbohydrate, by difference" (nutrient 205) INCLUDES fibre.
#:               Verified on the cached FDC release -- of 7,931 fibre-bearing
#:               rows, ZERO had fibre > carbs, which could not hold if carbs
#:               excluded it.
#:   off         Open Food Facts follows EU label wording, where fibre is
#:               declared separately and carbohydrate is available carbohydrate.
#:               NOT yet verified against our corpus -- see `unknown`.
#:   unknown     The honest default. The expected-energy band is widened to
#:               span both conventions rather than guessing one.
#:
#: THIS IS A DATA-MODEL BUG, recorded here rather than papered over: both
#: conventions land in the same `carbs_g` column and nothing on the row says
#: which. Until a column records it, `unknown` is the correct answer for any
#: row whose importer did not say.
CARB_TOTAL = "total"          # carbs_g includes fibre (USDA)
CARB_AVAILABLE = "available"  # carbs_g excludes fibre (EU labelling)
CARB_UNKNOWN = "unknown"

ATWATER_TOLERANCE = 0.15   # 15% drift before we complain
ATWATER_HARD_LIMIT = 0.35  # beyond this the row is unusable


class Severity(str, Enum):
    info = "info"          # noted, does not block
    warning = "warning"    # accept but downgrade data_quality
    error = "error"        # quarantine: do not serve to users
    #: WE CANNOT ASSESS THIS, which is not the same as "this is wrong".
    #:
    #: A check that cannot model what a food contains must say so rather than
    #: convict it. Beer does not reconcile at 4/4/9 because ethanol carries
    #: 7 kcal/g, and that is a fact about the check, not about the beer.
    #: Never counts toward `too_many_warnings` -- compounding unverifiables
    #: means we know less, not that the row is worse.
    unverifiable = "unverifiable"


class Verdict(str, Enum):
    accept = "accept"
    accept_with_corrections = "accept_with_corrections"
    quarantine = "quarantine"
    #: The panel could not be READ -- required fields absent, or present under
    #: names this validator does not recognise. Distinct from `quarantine`,
    #: which is a claim ABOUT the nutrition. Collapsing the two makes a
    #: field-name bug indistinguishable from bad data, and every downstream
    #: defect rate then partly measures the importer instead of the food.
    unreadable = "unreadable"
    #: The panel was read and nothing in it looks wrong, but at least one
    #: check could not be applied. Servable -- the row is usable data, it is
    #: simply less checked than an `accept`. Distinct from `quarantine` for
    #: the same reason `unreadable` is: a defect rate that counts these has
    #: stopped measuring food and started measuring our own coverage.
    unverifiable = "unverifiable"


@dataclass
class Issue:
    code: str
    severity: Severity
    message: str
    field: str | None = None
    observed: Any = None
    expected: Any = None


@dataclass
class ValidationResult:
    verdict: Verdict
    issues: list[Issue] = field(default_factory=list)
    quality_score: float = 0.5
    #: Populated on every result. Non-None `schema.aliased` on an `unreadable`
    #: verdict is the signature of a caller using label wording.
    schema: "SchemaReport | None" = None

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.error]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.warning]

    @property
    def unverifiable(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.unverifiable]

    @property
    def is_servable(self) -> bool:
        # `unreadable` is not servable -- we know nothing about it at all.
        # `unverifiable` IS servable: the data is fine, one check could not be
        # applied to it, and withholding beer because we cannot audit ethanol
        # would be the same mistake in the other direction.
        return self.verdict in (
            Verdict.accept,
            Verdict.accept_with_corrections,
            Verdict.unverifiable,
        )


# ---------------------------------------------------------------------------
# Category expectation bands
# ---------------------------------------------------------------------------
# (kcal_min, kcal_max, protein_min, protein_max, fat_min)
# fat_min catches the "rice flour has 0.0 g fat" rounding artefact.

CATEGORY_BANDS: dict[str, dict[str, tuple[float, float]]] = {
    # Dry cereal/pulse flours and instant mixes, AS SOLD
    "dry_mix": {"kcal": (300, 430), "protein": (5, 25), "carbs": (45, 90), "fat": (0.3, 25)},
    "flour": {"kcal": (320, 400), "protein": (5, 15), "carbs": (65, 92), "fat": (0.3, 6)},
    "vermicelli": {"kcal": (320, 400), "protein": (7, 15), "carbs": (65, 85), "fat": (0.2, 5)},
    # Spice blends -- wide, because oil-roasted podis are legitimately fatty
    "masala": {"kcal": (250, 560), "protein": (5, 25), "carbs": (10, 65), "fat": (3, 45)},
    # Jaggery/sugar-dominant powders: chukku kappi, sukku malli, panakam mix.
    # These are NOT savoury masalas and must not be judged against that band.
    "sweet_powder": {"kcal": (280, 420), "protein": (0, 10), "carbs": (70, 100), "fat": (0, 6)},
    # Sweet mixes
    "sweet_mix": {"kcal": (350, 500), "protein": (5, 20), "carbs": (50, 80), "fat": (5, 25)},
    # Wet batters
    "batter": {"kcal": (120, 220), "protein": (4, 18), "carbs": (20, 40), "fat": (0.1, 6)},
    # Prepared/cooked dishes
    "prepared": {"kcal": (30, 400), "protein": (0.5, 35), "carbs": (0, 70), "fat": (0, 40)},
}

# Ingredient-class protein floors. If an ingredient making up >=50% of the
# product has a known protein content, the product cannot fall far below it.
# This is what catches the MTR rava idli case.
INGREDIENT_PROTEIN: dict[str, float] = {
    "semolina": 12.0, "sooji": 12.0, "rava": 12.0, "suji": 12.0,
    "wheat": 11.0, "atta": 11.0, "maida": 10.0,
    "rice": 7.0, "rice flour": 6.5,
    "urad": 24.0, "black gram": 24.0,
    "bengal gram": 20.0, "chana": 20.0, "gram flour": 22.0, "besan": 22.0,
    "toor": 22.0, "arhar": 22.0, "moong": 24.0, "green gram": 24.0,
    "ragi": 7.0, "finger millet": 7.0,
    "oats": 13.0,
    "milk solids": 26.0, "khoya": 20.0, "skimmed milk powder": 35.0,
    "soy": 40.0, "soya": 40.0,
    "coconut": 3.3,
    "sugar": 0.0, "jaggery": 0.0, "starch": 0.0, "tapioca": 0.0, "sago": 0.0,
}


# ---------------------------------------------------------------------------
# Salt evidence
#
# WHY THIS EXISTS
# `check_sodium` asks "is a near-zero sodium figure a contradiction?" That is
# only a fair question if the product contains salt. The parameter used to
# default to True, so the check fired on raw chicken, plain rice, milk, olive
# oil and boiled lentils -- foods whose low sodium is the correct answer.
#
# The rule now is EVIDENCE OR SILENCE. Three states, not two: True (salt is
# attested), False (salt is attested absent), None (we do not know, so we do
# not fire). A false positive on a curated whole food is far more expensive
# than a missed low-sodium claim, because it teaches people to click through
# the moderation queue.
# ---------------------------------------------------------------------------

#: Names for salt as they appear in ingredient declarations, including the
#: Indian-language forms that an English-only list would miss.
SALT_TERMS: tuple[str, ...] = (
    "salt", "common salt", "edible common salt", "table salt",
    "iodised salt", "iodized salt", "iodised common salt",
    "sea salt", "rock salt", "black salt", "pink salt",
    "sodium chloride", "nacl",
    "namak", "kala namak", "sendha namak", "saindhava lavana", "lavana",
    "uppu", "upu",
    # MSG is included deliberately: it is used only in savoury products and at
    # levels that move the sodium figure. Sodium benzoate and the like are NOT
    # included -- they are preservatives at fractions of a percent and imply
    # nothing about the sodium total.
    "monosodium glutamate", "msg", "ajinomoto",
)

#: Phrases that mean the opposite even though they contain the word "salt".
#: These MUST be tested before SALT_TERMS -- "unsalted butter" contains "salt".
SALT_NEGATIONS: tuple[str, ...] = (
    "unsalted", "un-salted", "no added salt", "no salt added", "without salt",
    "salt free", "salt-free", "saltfree",
    "sodium free", "sodium-free", "low sodium", "low-sodium", "reduced sodium",
)

#: Categories where salt is present as a matter of course, used only when the
#: ingredient list is absent. Deliberately SHORT.
#:
#: What is missing from this list is the point of it. `meat` is not here: the
#: USDA importer maps both "beef products" (raw) and "sausages and luncheon
#: meats" (cured) onto it, so the category cannot separate a raw brisket from
#: a slice of ham. `bakery` is not here for the same reason -- it carries both
#: bread and cake. `snack` covers sweet and savoury alike. `spice` is pure
#: turmeric as often as it is chaat masala. Where a category cannot answer the
#: question, it must not be allowed to guess.
SALTED_CATEGORIES: frozenset[str] = frozenset({
    # Indian mixes -- the vocabulary in CATEGORY_BANDS above
    "dry_mix", "masala", "prepared", "batter", "podi", "namkeen", "pickle",
    "savoury_mix", "chutney",
    # Global vocabulary written by ingest_usda.CATEGORY_MAP
    "soup",          # "soups, sauces, and gravies"
    "fast_food", "restaurant",
})

#: A sweet product is not salted whatever its category says. Gulab jamun mix
#: and rava idli mix are both `dry_mix`; only one of them contains salt.
SWEET_NAME_TERMS: tuple[str, ...] = (
    "gulab", "jamun", "payasam", "kheer", "halwa", "halva", "sheera",
    "sweet", "sugar", "mithai", "barfi", "burfi", "ladoo", "laddu", "laddoo",
    "jalebi", "rasgulla", "rasagulla", "rasmalai", "peda", "chikki",
    "dessert", "custard", "ice cream", "kulfi", "syrup", "jam", "honey",
    "chocolate", "cocoa", "brownie", "cake mix", "basundi", "shrikhand",
)

#: Pure spices and single-spice powders. These sit in `masala` and `spice`
#: alongside genuinely salted blends, and they contain no salt at all --
#: garam masala runs about 50 mg sodium per 100 g, which is exactly the value
#: the check would have condemned.
PURE_SPICE_NAME_TERMS: tuple[str, ...] = (
    "garam masala", "turmeric", "haldi", "chilli powder", "chili powder",
    "red chilli", "mirchi", "coriander powder", "dhania powder",
    "cumin", "jeera powder", "pepper powder", "black pepper",
    "cinnamon", "dalchini", "cardamom", "elaichi", "clove", "laung",
    "asafoetida", "hing", "fenugreek", "methi", "kasuri methi",
    "mustard seed", "rai", "bay leaf", "tej patta", "amchur", "amchoor",
    "saffron", "kesar", "nutmeg", "jaiphal", "mace", "star anise",
    "curry leaf", "curry leaves", "poppy seed", "sesame seed",
)

#: Foods that are salted regardless of how they were categorised. Narrow on
#: purpose: every entry here is a food with no meaningful unsalted variant in
#: normal commerce.
SALTED_NAME_TERMS: tuple[str, ...] = (
    "pickle", "achar", "namkeen", "bhujia", "sev ", "papad", "appalam",
    "chips", "crisps", "wafers", "ketchup", "soy sauce", "soya sauce",
    "fish sauce", "instant noodles", "cup noodles", "ramen", "bouillon",
    "stock cube", "soup mix", "olives", "anchov", "salami", "pepperoni",
    "bacon", " ham", "sausage", "frankfurter", "cured", "brined",
    "chaat masala", "sambar powder", "rasam powder", "idli podi",
    "cheese", "bread", "pav", "bun",
)


def _contains(haystack: str, terms: tuple[str, ...]) -> bool:
    return any(t in haystack for t in terms)


def _names_salt(text: str) -> bool:
    """Salt-term test that will not fire on a word that merely contains one.

    Padding the haystack lets short entries such as "msg" and "nacl" be matched
    as whole tokens rather than as fragments of a longer word.
    """
    padded = f" {text} "
    for t in SALT_TERMS:
        t = t.strip()
        if " " in t:
            if t in text:
                return True
        elif f" {t} " in padded or f" {t}," in padded or f" {t}." in padded:
            return True
    return False


def infer_is_salted(
    *,
    name: str | None = None,
    category: str | None = None,
    ingredients: list[tuple[str, float]] | None = None,
    ingredients_text: str | None = None,
) -> bool | None:
    """Decide whether a product contains salt, or admit that we cannot.

    Returns True (salt attested), False (attested absent, or a sweet), or None
    (no evidence -- the sodium contradiction check stays silent).

    Evidence is taken in order of strength:

      1. THE INGREDIENT LIST, where one exists. If it names salt, a near-zero
         sodium figure is a real contradiction. If a list exists and salt is
         not on it, that is evidence of absence, not merely of ignorance.
      2. THE NAME, for the cases a category cannot resolve: a sweet in a
         savoury category, a pure spice in a blend category.
      3. THE CATEGORY, which is the weakest signal and the last one tried.
      4. Otherwise None.

    NOTE ON WHAT IS AVAILABLE IN PRACTICE: `food_items` has no ingredients
    column and never has, so step 1 is reachable only at ingest time, while
    the source record is still in hand. Anything auditing stored rows gets
    steps 2 and 3 only.
    """
    text = " ".join(
        part.lower()
        for part in (
            ingredients_text or "",
            " ".join(nm for nm, _ in (ingredients or [])),
        )
        if part
    ).strip()

    if text:
        if _contains(text, SALT_NEGATIONS):
            return False
        if _names_salt(text):
            return True
        # A list was supplied and salt is not on it. That is an answer.
        return False

    lowered = (name or "").lower().strip()
    if lowered:
        if _contains(lowered, PURE_SPICE_NAME_TERMS):
            return False
        if _contains(lowered, SALT_NEGATIONS):
            return False
        if _contains(lowered, SWEET_NAME_TERMS):
            return False
        if _contains(lowered, SALTED_NAME_TERMS):
            return True

    if category and category in SALTED_CATEGORIES:
        return True

    return None


def _band(category: str | None) -> dict[str, tuple[float, float]] | None:
    if not category:
        return None
    return CATEGORY_BANDS.get(category)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_macro_sum(n: dict[str, float]) -> list[Issue]:
    """Protein + carbs + fat cannot exceed 100 g per 100 g."""
    total = n.get("protein_g", 0) + n.get("carbs_g", 0) + n.get("fat_g", 0)
    if total > 100.5:
        return [
            Issue(
                "macro_sum_exceeds_100",
                Severity.error,
                f"Macros sum to {total:.1f} g per 100 g, which is impossible.",
                observed=round(total, 1),
                expected="<= 100",
            )
        ]
    if total < 5 and n.get("calories", 0) > 100:
        return [
            Issue(
                "macros_missing",
                Severity.error,
                f"Only {total:.1f} g of macros accounted for, but "
                f"{n.get('calories', 0):.0f} kcal declared. Panel is incomplete.",
                observed=round(total, 1),
            )
        ]
    return []


#: Things that carry energy the 4/4/9 sum cannot see. Detected from name and
#: category because there is no column for any of them.
#:
#: These do not excuse a row from checking. They move a FAILING check from
#: "this row is wrong" to "we cannot tell", which is the only honest reading
#: when the arithmetic was never applicable in the first place.
UNMODELLED_ENERGY: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # ORDER MATTERS. "Vinegar, red wine" is an acid problem, not an alcohol
    # one, so the acid terms get first refusal; a table wine matches nothing
    # here and falls through to alcohol correctly.
    (
        "organic_acid",
        "citric and malic acid yield about 2.5 kcal/g",
        ("lemon", "lemons", "lime", "limes", "citrus", "vinegar", "cranberry",
         "cranberries", "rhubarb", "tamarind", "gooseberry", "kombucha",
         "pickled", "kimchi", "sauerkraut", "amla", "kokum", "verjuice"),
    ),
    (
        "alcohol",
        "ethanol carries 7 kcal/g and appears in no macro column",
        ("alcoholic", "alcohol", "ethyl", "beer", "lager", "ale", "stout",
         "porter", "wine", "sake", "liquor", "liqueur", "whisky", "whiskey",
         "vodka", "rum", "gin", "brandy", "tequila", "bourbon", "cider",
         "mead", "cocktail", "martini", "daiquiri", "margarita", "schnapps",
         "vermouth", "sherry", "port wine", "champagne"),
    ),
    (
        "polyol",
        "sugar alcohols yield about 2.4 kcal/g, not 4",
        ("sugar free", "sugar-free", "sugarfree", "no sugar", "low calorie",
         "reduced calorie", "diet", "sweetener", "aspartame", "sucralose",
         "saccharin", "stevia", "erythritol", "xylitol", "sorbitol",
         "maltitol", "isomalt", "mannitol", "polyol", "sugar alcohol",
         "sugar alcohols"),
    ),
    (
        "unusual_fibre",
        "fibre yields 2-4 kcal/g depending on fermentability",
        ("bran", "psyllium", "inulin", "chicory root", "baobab", "husk",
         "cellulose", "high fiber", "high fibre", "added fiber",
         "added fibre", "resistant starch", "oligosaccharide"),
    ),
    (
        "gelling_agent",
        "gelatin, pectin and gums are not counted consistently",
        ("gelatin", "gelatine", "jellyfish", "agar", "pectin", "carrageenan",
         "xanthan", "guar gum", "collagen", "aspic"),
    ),
)

#: Compiled once. WORD BOUNDARIES, not substrings.
#:
#: Substring matching made "ale," match "Kale, frozen", "rum," match "Fish,
#: drum, freshwater", and "sour" match every Sweet And Sour Pork row in the
#: survey release. A marker only bites a row that ALSO fails the energy band,
#: so none of those had visibly misfired yet -- but the effect of a false
#: marker is to EXCUSE a defect, and a check that quietly stops catching
#: things is worse than one that never caught them.
_MARKER_PATTERNS: tuple[tuple[str, str, "re.Pattern[str]"], ...] = tuple(
    (
        marker,
        why,
        re.compile(
            r"(?<![a-z])(?:" + "|".join(re.escape(t) for t in terms) + r")(?![a-z])"
        ),
    )
    for marker, why, terms in UNMODELLED_ENERGY
)


def unmodelled_energy_marker(
    name: str | None, category: str | None
) -> tuple[str, str] | None:
    """Does this row contain energy the macro sum cannot account for?

    Returns (marker, why) or None. Name and category only -- we have no
    column for alcohol, polyols or acidity, and inferring one from the
    numbers would be circular: the numbers are what is in question.
    """
    haystack = " ".join(
        part.lower() for part in (name or "", category or "") if part
    )
    if not haystack:
        return None
    for marker, why, pattern in _MARKER_PATTERNS:
        if pattern.search(haystack):
            return marker, why
    return None


def expected_energy_band(
    n: dict[str, float], carb_convention: str = CARB_UNKNOWN
) -> tuple[float, float]:
    """Energy the macros can account for, as a RANGE.

    A point estimate would be a lie twice over: fibre's energy yield is a
    genuine range, and we do not always know whether `carbs_g` already
    contains the fibre. The band spans both, so a row is only ever flagged
    for a gap no reading of its own numbers can close.

    This is the same posture the rest of the product takes -- a photo scan
    returns low/point/high rather than one confident number.
    """
    protein = n.get("protein_g", 0.0) or 0.0
    carbs = n.get("carbs_g", 0.0) or 0.0
    fat = n.get("fat_g", 0.0) or 0.0
    fibre = n.get("fiber_g", 0.0) or 0.0

    base = protein * KCAL_PROTEIN + fat * KCAL_FAT
    if fibre <= 0:
        return base + carbs * KCAL_CARB, base + carbs * KCAL_CARB

    # carbs INCLUDES fibre: the fibre share yields 2-4 instead of a flat 4.
    total_lo = base + max(0.0, carbs - fibre) * KCAL_CARB + fibre * KCAL_FIBRE_LOW
    total_hi = base + max(0.0, carbs - fibre) * KCAL_CARB + fibre * KCAL_FIBRE_HIGH
    # carbs EXCLUDES fibre: the fibre is additional energy on top.
    avail_lo = base + carbs * KCAL_CARB + fibre * KCAL_FIBRE_LOW
    avail_hi = base + carbs * KCAL_CARB + fibre * KCAL_FIBRE_HIGH

    if carb_convention == CARB_TOTAL:
        return total_lo, total_hi
    if carb_convention == CARB_AVAILABLE:
        return avail_lo, avail_hi
    # Unknown: span both rather than pick one.
    return min(total_lo, avail_lo), max(total_hi, avail_hi)


def check_atwater(
    n: dict[str, float],
    *,
    name: str | None = None,
    category: str | None = None,
    carb_convention: str = CARB_UNKNOWN,
) -> list[Issue]:
    """Declared energy must match what the macros can account for.

    Three outcomes, not two. The row reconciles; the row does not reconcile
    and nothing explains why (a defect); or the row does not reconcile and it
    contains something this sum was never able to model (`energy_unexplained`,
    which asserts nothing about the food).
    """
    stated = n.get("calories", 0)
    lo, hi = expected_energy_band(n, carb_convention)

    if stated <= 0 and hi <= 0:
        # A FILLED-IN TABLE THAT READS ZERO, which is a measurement, not a
        # gap. Water, black coffee, plain tea, sparkling water, diet soda and
        # sugar-free gum all declare a real panel of zeroes.
        #
        # The schema pre-check has already established that `calories` is
        # PRESENT; a record missing it never reaches this function. So a zero
        # here was declared, not defaulted, and "no data" and "no calories"
        # stay the different facts that `food_sources._off_to_resolved` says
        # they are.
        return []

    if stated <= 0:
        # Zero energy but macros that carry some. That is a contradiction
        # rather than a legitimate zero, and still worth catching.
        return [
            Issue(
                "energy_missing_but_macros_present",
                Severity.error,
                f"No energy declared, but the macros account for "
                f"{lo:.0f}-{hi:.0f} kcal. One of the two is wrong.",
                field="calories",
                observed=stated,
                expected=f"{lo:.0f}-{hi:.0f}",
            )
        ]

    if hi <= 0:
        return [Issue("no_macros", Severity.error, "No macros declared.")]

    # Drift is measured to the NEAREST EDGE. Anything inside the band is
    # accounted for, and there is nothing to explain.
    if lo <= stated <= hi:
        return []
    nearest = lo if stated < lo else hi
    drift = abs(nearest - stated) / stated

    if drift <= ATWATER_TOLERANCE:
        return []

    marker = unmodelled_energy_marker(name, category)
    span = f"{lo:.0f}-{hi:.0f}" if hi > lo else f"{lo:.0f}"

    if marker is not None:
        # The arithmetic was never applicable. Say that, and say why, rather
        # than convicting a correct row.
        what, why = marker
        return [
            Issue(
                "energy_unexplained",
                Severity.unverifiable,
                f"Macros account for {span} kcal but {stated:.0f} kcal is "
                f"declared. This row looks like it contains {what} -- {why} -- "
                f"so the macro sum cannot settle the question either way.",
                field="calories",
                observed=round(drift, 3),
                expected=span,
            )
        ]

    if drift > ATWATER_HARD_LIMIT:
        return [
            Issue(
                "atwater_mismatch_severe",
                Severity.error,
                f"Macros account for {span} kcal but {stated:.0f} kcal is "
                f"declared ({drift:.0%} beyond the band). One of them is wrong.",
                observed=round(drift, 3),
                expected=span,
            )
        ]
    return [
        Issue(
            "atwater_mismatch",
            Severity.warning,
            f"Macros account for {span} kcal vs {stated:.0f} declared "
            f"({drift:.0%} beyond the band).",
            observed=round(drift, 3),
            expected=span,
        )
    ]


def check_category_band(n: dict[str, float], category: str | None) -> list[Issue]:
    """Compare against what this class of product physically can be.

    Catches Aachi Rice Idli at 133 kcal/100 g -- an as-prepared panel filed as
    a dry mix.
    """
    band = _band(category)
    if band is None:
        return []

    issues: list[Issue] = []
    for key, field_name in (
        ("kcal", "calories"),
        ("protein", "protein_g"),
        ("carbs", "carbs_g"),
        ("fat", "fat_g"),
    ):
        if key not in band:
            continue
        lo, hi = band[key]
        value = n.get(field_name)
        if value is None:
            continue

        if value < lo:
            # A dry mix reading like a cooked dish is the classic mislabel.
            likely_prepared = (
                category in ("dry_mix", "flour", "vermicelli", "sweet_mix")
                and field_name == "calories"
                and value < lo * 0.6
            )
            issues.append(
                Issue(
                    "below_category_band_likely_as_prepared"
                    if likely_prepared
                    else "below_category_band",
                    Severity.error if likely_prepared else Severity.warning,
                    (
                        f"{field_name}={value:g} is far below the {category} range "
                        f"({lo:g}-{hi:g}). This panel is probably AS-PREPARED, not as-sold."
                    )
                    if likely_prepared
                    else f"{field_name}={value:g} is below the {category} range ({lo:g}-{hi:g}).",
                    field=field_name,
                    observed=value,
                    expected=f"{lo:g}-{hi:g}",
                )
            )
        elif value > hi:
            issues.append(
                Issue(
                    "above_category_band",
                    Severity.warning,
                    f"{field_name}={value:g} is above the {category} range ({lo:g}-{hi:g}).",
                    field=field_name,
                    observed=value,
                    expected=f"{lo:g}-{hi:g}",
                )
            )
    return issues


def check_ingredient_consistency(
    n: dict[str, float], ingredients: list[tuple[str, float]] | None
) -> list[Issue]:
    """Cross-check declared protein against the ingredient list.

    ingredients: [(name, percent_of_product), ...]

    THIS IS THE CHECK THAT CATCHES MTR RAVA IDLI. An 80%-semolina product
    cannot contain 1.5 g protein per 100 g: semolina alone contributes
    0.80 x 12 = 9.6 g.
    """
    if not ingredients:
        return []

    expected_protein = 0.0
    matched_pct = 0.0
    for name, pct in ingredients:
        key = name.lower().strip()
        for ing, protein in INGREDIENT_PROTEIN.items():
            if ing in key:
                expected_protein += protein * (pct / 100.0)
                matched_pct += pct
                break

    if matched_pct < 40:
        return []  # not enough of the product identified to judge

    declared = n.get("protein_g", 0)
    # Allow generous slack: processing losses, unmatched minor ingredients.
    floor = expected_protein * 0.6

    if declared < floor:
        return [
            Issue(
                "protein_contradicts_ingredients",
                Severity.error,
                (
                    f"Declared protein {declared:g} g/100 g contradicts the "
                    f"ingredient list ({matched_pct:.0f}% identified implies "
                    f"~{expected_protein:.1f} g). Almost certainly a "
                    f"transcription error."
                ),
                field="protein_g",
                observed=declared,
                expected=f">={floor:.1f}",
            )
        ]
    return []


#: Foods that genuinely exceed 8,000 mg sodium per 100 g.
#:
#: The g/mg unit error is a real failure and this check should keep catching
#: it. But "no food contains this much sodium" is false, and it was false for
#: a whole shelf of them: table salt is 38,758 mg/100 g, a stock cube around
#: 24,000, MSG about 12,000, dried salted fish and jellyfish 7,000-10,000.
#: Calling those transcription errors quarantined correct rows, and because
#: every importer drops a quarantined row rather than storing it, the effect
#: was to delete real foods from the catalogue.
EXTREME_SODIUM_TERMS: tuple[str, ...] = (
    "salt", "namak", "uppu", "sodium chloride", "table salt", "rock salt",
    "sea salt", "black salt", "kala namak", "seasoned salt", "celery salt",
    "garlic salt", "onion salt", "curing salt",
    "bouillon", "stock cube", "stock powder", "broth cube", "consomme",
    "soy sauce", "soya sauce", "tamari", "fish sauce", "oyster sauce",
    "worcestershire", "anchovy", "anchovies", "bonito",
    "monosodium glutamate", "msg", "ajinomoto",
    "baking soda", "sodium bicarbonate", "bicarbonate of soda",
    "baking powder", "meat tenderizer", "meat tenderiser",
    # Forms the corpus actually uses: "Jellyfish, dried, salted" separates
    # the words with a comma, so "dried salted" as a phrase never matched.
    "salted", "salting", "cured", "curing", "brine", "brined", "in brine",
    "broth", "stock", "bouillon cube", "dried salted", "salt cured",
    "capers", "olives in brine", "dashi", "miso", "gochujang",
    "doenjang", "shrimp paste", "belacan", "marmite", "vegemite",
    "yeast extract", "seasoning mix", "seasoning powder", "rub,",
    "pickling spice", "papad", "appalam",
)

_EXTREME_SODIUM_RE = re.compile(
    r"(?<![a-z])(?:" + "|".join(re.escape(t) for t in EXTREME_SODIUM_TERMS)
    + r")(?![a-z])"
)


def sodium_extremity_is_explained(
    name: str | None, category: str | None
) -> bool:
    """Is there a reason this food would legitimately be this salty?

    Name and category only. Same shape as `unmodelled_energy_marker`: the
    question is never "is this value right" -- we cannot know that -- but
    "is there any reason other than a transcription error".
    """
    haystack = " ".join(
        part.lower() for part in (name or "", category or "") if part
    )
    return bool(haystack) and bool(_EXTREME_SODIUM_RE.search(haystack))


def check_sodium(
    n: dict[str, float],
    is_salted: bool | None = None,
    *,
    name: str | None = None,
    category: str | None = None,
) -> list[Issue]:
    """Sodium unit errors and rounding artefacts.

    Catches Bambino's "16.29 g" (should be mg) and the sodium=0 artefact on
    products that unambiguously contain salt.

    `is_salted` is THREE-STATE. Only True fires the near-zero contradiction.
    None means no evidence either way, and an unevidenced guess is what made
    this check condemn raw chicken, plain rice, whole milk, olive oil and
    boiled lentils -- every one of which has a genuinely low sodium figure.
    """
    issues: list[Issue] = []
    sodium = n.get("sodium_mg")
    if sodium is None:
        return issues

    # A g/mg unit error is the signature failure. If the value is absurd but
    # becomes plausible after dividing by 1000, that is what happened --
    # Bambino's "16.29 g" is really 16.29 mg.
    #
    # UNLESS the food is one that really is this salty. Salt, bouillon, soy
    # sauce, miso and dried salted fish all clear 8,000 mg honestly, and
    # dividing their sodium by 1000 produces a plausible-looking number that
    # is simply wrong. `expected` below is ADVISORY ONLY -- nothing in this
    # module or downstream of it applies a value from an Issue, and there is
    # a test pinning that.
    if sodium > 8_000 and sodium_extremity_is_explained(name, category):
        issues.append(
            Issue(
                "sodium_extreme_but_expected",
                Severity.unverifiable,
                f"Sodium {sodium:g} mg/100 g ({sodium / 400:.0f} g salt) is "
                f"extreme, but this food is one that reaches it legitimately. "
                f"We cannot confirm the figure and we will not overwrite it.",
                field="sodium_mg",
                observed=sodium,
            )
        )
    elif sodium > 8_000 and 0 < sodium / 1000 < 5_000:
        issues.append(
            Issue(
                "sodium_unit_error",
                Severity.error,
                f"Sodium {sodium:g} mg/100 g ({sodium / 400:.0f} g salt) is "
                f"implausible for this food, but {sodium / 1000:g} mg is not. "
                f"This looks like a g/mg unit error -- re-read the label. The "
                f"stored value is left exactly as it was found.",
                field="sodium_mg",
                observed=sodium,
                expected=round(sodium / 1000, 2),
            )
        )
    elif sodium > 5_000 and sodium_extremity_is_explained(name, category):
        issues.append(
            Issue(
                "sodium_extreme_but_expected",
                Severity.unverifiable,
                f"Sodium {sodium:g} mg/100 g is very high, and this food is "
                f"one that reaches it legitimately.",
                field="sodium_mg",
                observed=sodium,
            )
        )
    elif sodium > 5_000:
        issues.append(
            Issue(
                "sodium_implausibly_high",
                Severity.warning,
                f"Sodium {sodium:g} mg/100 g ({sodium / 400:.1f} g salt) is very "
                f"high even for a masala. Verify against the pack.",
                field="sodium_mg",
                observed=sodium,
            )
        )
    elif sodium < 50 and is_salted is True:
        # Catches both the flat 0 and Aachi Idli Podi's "2.3 mg" on a product
        # whose second ingredient is salt.
        issues.append(
            Issue(
                "sodium_near_zero_on_salted_product",
                Severity.warning if sodium > 0 else Severity.info,
                f"Sodium declared as {sodium:g} mg/100 g on a salted product. "
                f"A masala or savoury mix runs 800-2,500 mg. Treat as unknown "
                f"rather than as a true low-sodium claim.",
                field="sodium_mg",
                observed=sodium,
                expected=">=300",
            )
        )
    return issues


def check_fibre(n: dict[str, float]) -> list[Issue]:
    """Fibre cannot exceed carbohydrate, nor be a large share of the food."""
    fibre = n.get("fiber_g")
    if fibre is None:
        return []
    if fibre > 40:
        return [
            Issue(
                "fibre_impossible",
                Severity.error,
                f"Fibre {fibre:g} g/100 g is impossible outside pure bran.",
                field="fiber_g",
                observed=fibre,
            )
        ]
    carbs = n.get("carbs_g")
    # Note: some labels report carbs EXCLUDING fibre (EU) and some INCLUDING
    # it (US/India). Only flag when it is clearly wrong either way.
    if carbs is not None and fibre > carbs + 5:
        return [
            Issue(
                "fibre_exceeds_carbs",
                Severity.warning,
                f"Fibre ({fibre:g} g) exceeds carbohydrate ({carbs:g} g).",
                field="fiber_g",
                observed=fibre,
            )
        ]
    return []


def check_zero_fat_artefact(
    n: dict[str, float], category: str | None
) -> list[Issue]:
    """Rice/wheat flours are never truly 0.0 g fat.

    Eastern, Nirapara, Double Horse and Brahmins podis all list 0.0. It is a
    rounding artefact. Correcting it matters because 0.5-1.5 g/100 g across a
    100 g serving is 5-14 kcal, and it compounds across a day of logging.
    """
    if category not in ("flour", "vermicelli", "dry_mix"):
        return []
    fat = n.get("fat_g")
    if fat is not None and fat == 0:
        return [
            Issue(
                "zero_fat_artefact",
                Severity.info,
                "Fat declared as 0.0 g on a cereal product. Rice and wheat "
                "flours contain 0.5-1.5 g/100 g; this is label rounding.",
                field="fat_g",
                observed=0,
                expected="~0.5-1.5",
            )
        ]
    return []


def check_saturated_fat(n: dict[str, float]) -> list[Issue]:
    sat = n.get("saturated_fat_g")
    fat = n.get("fat_g")
    if sat is None or fat is None:
        return []
    if sat > fat + 0.2:
        return [
            Issue(
                "saturated_exceeds_total_fat",
                Severity.error,
                f"Saturated fat ({sat:g} g) exceeds total fat ({fat:g} g).",
                field="saturated_fat_g",
                observed=sat,
            )
        ]
    # No edible fat is under ~7% saturated. Coconut and palm oil, which
    # dominate South Indian cooking, are 50-90% saturated.
    if fat > 15 and sat / max(fat, 1e-9) < 0.05:
        return [
            Issue(
                "saturated_fat_implausibly_low",
                Severity.warning,
                f"Saturated fat {sat:g} g is only {sat / fat:.1%} of {fat:g} g "
                f"total fat. No edible oil is under ~7% saturated, and the "
                f"coconut/palm fats common here are 50-90%.",
                field="saturated_fat_g",
                observed=sat,
                expected=f">={fat * 0.07:.1f}",
            )
        ]
    return []


def check_mass_balance(n: dict[str, float], category: str | None) -> list[Issue]:
    """A dry powder is ~90% macros + fibre + ash. If far less is accounted
    for, the panel is partial and the row is not usable.

    Catches the Sakthi entries, where only ~25 g of 100 g is declared -- those
    are community estimates, not label transcriptions.
    """
    # Floors differ by class. Cereal products are almost entirely macros, so a
    # low figure means a partial panel. Spice blends legitimately carry
    # 10-25% salt plus ash and moisture that never appear on the panel, so the
    # same threshold would produce false positives on good data.
    FLOORS = {
        "dry_mix": 60.0,
        "flour": 60.0,
        "vermicelli": 60.0,
        "sweet_mix": 60.0,
        "sweet_powder": 60.0,
        "masala": 45.0,
    }
    floor = FLOORS.get(category or "")
    if floor is None:
        return []

    accounted = (
        n.get("protein_g", 0)
        + n.get("carbs_g", 0)
        + n.get("fat_g", 0)
        + n.get("fiber_g", 0)
    )
    # Carbs on Indian labels usually already include fibre, so don't
    # double-count when that is clearly the case.
    if n.get("fiber_g", 0) and n.get("fiber_g", 0) < n.get("carbs_g", 0):
        accounted -= n.get("fiber_g", 0)

    if accounted < floor:
        return [
            Issue(
                "mass_balance_incomplete",
                Severity.error,
                f"Only {accounted:.0f} g of 100 g is accounted for by macros. "
                f"A {category} should reach at least {floor:.0f} g. This panel "
                f"is partial or estimated, not a label transcription.",
                observed=round(accounted, 1),
                expected=f">={floor:.0f}",
            )
        ]
    return []


def check_sugar(n: dict[str, float]) -> list[Issue]:
    sugar = n.get("sugar_g")
    carbs = n.get("carbs_g")
    if sugar is None or carbs is None:
        return []
    if sugar > carbs + 0.5:
        return [
            Issue(
                "sugar_exceeds_carbs",
                Severity.error,
                f"Sugar ({sugar:g} g) exceeds total carbohydrate ({carbs:g} g).",
                field="sugar_g",
                observed=sugar,
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Duplicate-panel detection
# ---------------------------------------------------------------------------


def panel_fingerprint(n: dict[str, float]) -> str:
    """Hash the macro block so identical panels across SKUs can be spotted.

    Four different Eastern SKUs (idiyappam powder, white puttu podi, appam
    podi, roasted rice powder) all carry the identical 354/8/78/1/0.5/0.2
    block. That is one generic panel reused, not four measurements -- so all
    four should be treated as a category estimate with lower confidence.
    """
    parts = [
        f"{n.get('calories', 0):.1f}",
        f"{n.get('protein_g', 0):.2f}",
        f"{n.get('carbs_g', 0):.2f}",
        f"{n.get('fat_g', 0):.2f}",
        f"{n.get('fiber_g', 0):.2f}",
        f"{n.get('sugar_g', 0):.2f}",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def flag_duplicate_panels(
    products: list[dict[str, Any]], threshold: int = 3
) -> dict[str, list[str]]:
    """Return {fingerprint: [product_ids]} for panels reused >= threshold times.

    Only meaningful within a single brand -- two brands legitimately sharing a
    generic rice-flour panel is expected.
    """
    by_fp: dict[str, list[str]] = {}
    for p in products:
        fp = panel_fingerprint(p.get("nutriments", p))
        by_fp.setdefault(fp, []).append(str(p.get("id") or p.get("barcode") or "?"))
    return {fp: ids for fp, ids in by_fp.items() if len(ids) >= threshold}


# ---------------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------------


#: Field names this validator reads. These match the FoodItem columns.
REQUIRED_FIELDS = ("calories",)
KNOWN_FIELDS = frozenset({
    "calories", "protein_g", "carbs_g", "fat_g",
    "fiber_g", "sugar_g", "sodium_mg", "saturated_fat_g",
})

#: Names that MEAN one of the canonical fields but are spelled differently.
#:
#: Every entry here has been seen in the wild: label transcriptions use the
#: printed panel's wording, Open Food Facts uses its own suffixes, and USDA
#: uses yet another set. This table exists to RECOGNISE them and say so --
#: NOT to silently accept them. A caller passing `energy_kcal` has a bug, and
#: the useful thing is to name it, not to paper over it.
FIELD_ALIASES: dict[str, str] = {
    # label / panel wording
    "energy_kcal": "calories", "energy": "calories", "kcal": "calories",
    "carbohydrates_g": "carbs_g", "carbohydrate_g": "carbs_g",
    "total_fat_g": "fat_g", "total_carbohydrate_g": "carbs_g",
    "total_sugar_g": "sugar_g", "sugars_g": "sugar_g",
    "dietary_fibre_g": "fiber_g", "fibre_g": "fiber_g",
    "protein": "protein_g", "fat": "fat_g", "carbs": "carbs_g",
    # Open Food Facts
    "energy-kcal_100g": "calories", "energy_100g": "calories",
    "proteins_100g": "protein_g", "carbohydrates_100g": "carbs_g",
    "fat_100g": "fat_g", "fiber_100g": "fiber_g",
    "sugars_100g": "sugar_g", "sodium_100g": "sodium_mg",
    "saturated-fat_100g": "saturated_fat_g",
}


@dataclass
class SchemaReport:
    """What a pre-check found. `ok` means the panel is worth validating."""

    ok: bool
    missing: list[str] = field(default_factory=list)
    aliased: dict[str, str] = field(default_factory=dict)
    unknown: list[str] = field(default_factory=list)


def check_schema(nutriments: dict[str, Any]) -> SchemaReport:
    """Can this record be read at all?

    Runs BEFORE any nutritional logic. Three outcomes matter:

      * a required field is absent          -> not readable
      * a required field is present but under a recognised alias
                                            -> not readable, and we can say why
      * everything needed is present        -> proceed

    The alias case is the one that motivated this function. `energy_kcal` is
    a perfectly sensible name -- it is what the printed panel says -- and a
    caller using it is not producing bad data, they are producing data this
    validator cannot see. Reporting that as `quarantine` was wrong.
    """
    present = set(nutriments)
    aliased = {k: FIELD_ALIASES[k] for k in present if k in FIELD_ALIASES}
    unknown = sorted(present - KNOWN_FIELDS - set(FIELD_ALIASES))

    # A required field counts as missing even if an alias for it is present:
    # the value is there, but under a name nothing downstream will read.
    missing = [f for f in REQUIRED_FIELDS if f not in present]

    return SchemaReport(
        ok=not missing,
        missing=missing,
        aliased=aliased,
        unknown=unknown,
    )


def validate(
    nutriments: dict[str, float],
    *,
    category: str | None = None,
    ingredients: list[tuple[str, float]] | None = None,
    is_salted: bool | None = None,
    source_quality: float = 0.5,
    name: str | None = None,
    ingredients_text: str | None = None,
    carb_convention: str = CARB_UNKNOWN,
) -> ValidationResult:
    """Run every check and return a verdict.

    `nutriments` is per 100 g and may contain:
      calories, protein_g, carbs_g, fat_g, fiber_g, sugar_g,
      saturated_fat_g, sodium_mg

    `is_salted` defaults to None, meaning DERIVE IT from `name`, `category`,
    `ingredients` and `ingredients_text` via `infer_is_salted`. A caller that
    actually knows can still pass True or False and be believed.
    """
    schema = check_schema(nutriments)
    if not schema.ok:
        # UNREADABLE, not quarantine. Nothing has been asserted about the
        # nutrition -- we never got far enough to look at it.
        detail = f"missing {schema.missing}"
        if schema.aliased:
            pairs = ", ".join(f"{k} -> {v}" for k, v in sorted(schema.aliased.items()))
            detail += (
                f"; but recognised aliases are present ({pairs}). "
                "The value exists under a name this validator does not read -- "
                "this is a caller bug, not a bad panel."
            )
        return ValidationResult(
            verdict=Verdict.unreadable,
            issues=[Issue("unreadable_schema", Severity.error, detail,
                          observed=sorted(nutriments), expected=list(REQUIRED_FIELDS))],
            quality_score=0.0,
            schema=schema,
        )

    issues: list[Issue] = []
    issues += check_macro_sum(nutriments)
    issues += check_atwater(
        nutriments, name=name, category=category,
        carb_convention=carb_convention,
    )
    issues += check_category_band(nutriments, category)
    issues += check_ingredient_consistency(nutriments, ingredients)
    salted = (
        is_salted
        if is_salted is not None
        else infer_is_salted(
            name=name,
            category=category,
            ingredients=ingredients,
            ingredients_text=ingredients_text,
        )
    )
    issues += check_sodium(nutriments, salted, name=name, category=category)
    issues += check_fibre(nutriments)
    issues += check_saturated_fat(nutriments)
    issues += check_sugar(nutriments)
    issues += check_zero_fat_artefact(nutriments, category)
    issues += check_mass_balance(nutriments, category)

    errors = [i for i in issues if i.severity is Severity.error]
    warnings = [i for i in issues if i.severity is Severity.warning]
    unverifiable = [i for i in issues if i.severity is Severity.unverifiable]

    # Many independent warnings compound into untrustworthiness even when no
    # single check is fatal. Four separate complaints about one panel means
    # the panel is wrong, not that our thresholds are tight.
    if not errors and len(warnings) >= 4:
        issues.append(
            Issue(
                "too_many_warnings",
                Severity.error,
                f"{len(warnings)} independent checks flagged this panel. "
                f"Individually survivable, collectively not credible.",
                observed=len(warnings),
            )
        )
        errors = [i for i in issues if i.severity is Severity.error]

    if errors:
        verdict = Verdict.quarantine
        quality = 0.0
    elif warnings:
        verdict = Verdict.accept_with_corrections
        # Each warning costs 15% of the source's baseline trust.
        quality = round(max(0.15, source_quality * (0.85 ** len(warnings))), 2)
    elif unverifiable:
        # Nothing is wrong with this row. One check could not be applied to
        # it, so it is worth marginally less than a row that passed every
        # check -- a single 10% dock, NOT compounded, because two checks we
        # could not run are not evidence of two problems.
        verdict = Verdict.unverifiable
        quality = round(max(0.15, source_quality * 0.9), 2)
    else:
        verdict = Verdict.accept
        quality = source_quality

    return ValidationResult(
        verdict=verdict, issues=issues, quality_score=quality, schema=schema
    )


def explain(result: ValidationResult) -> str:
    """Human-readable summary for the moderation queue."""
    if result.verdict is Verdict.accept:
        return "Passed all checks."
    if result.verdict is Verdict.unverifiable:
        head = ("Verdict: unverifiable -- nothing looks wrong, but at least "
                "one check could not be applied.")
        return "\n".join([head] + [f"  {i.code}: {i.message}"
                                   for i in result.issues])
    if result.verdict is Verdict.unreadable:
        head = "Verdict: unreadable -- nothing was asserted about the nutrition."
        return "\n".join([head] + [f"  {i.message}" for i in result.issues])
    lines = [f"Verdict: {result.verdict.value} (quality {result.quality_score})"]
    for i in result.issues:
        lines.append(f"  [{i.severity.value:7}] {i.code}: {i.message}")
    return "\n".join(lines)
