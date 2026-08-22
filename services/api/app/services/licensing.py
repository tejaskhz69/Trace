"""Which licence each nutrition source carries, and what that permits.

WHY A MODULE AND NOT A COLUMN DEFAULT
97.8% of this catalogue -- 565,814 of 578,773 rows -- comes from Open Food
Facts under the ODbL. ODbL has two obligations, and they bite at different
moments:

  ATTRIBUTION, on any public use. We are not currently meeting it. Open Food
  Facts appears nowhere in the app outside code comments; every mention is in
  a docstring no user will read. That is a compliance gap that exists today,
  before this phase adds a single row.

  SHARE-ALIKE, on public distribution of a DERIVED DATABASE. Serving nutrition
  facts through an API is ordinary use. A "download your food data" export is
  much closer to distribution, and the moment one ships, every ODbL-derived
  row in it arguably drags the whole export under ODbL.

`is_exportable` is that second obligation expressed as code rather than as a
paragraph in a README somebody has to remember. The export path asks this
module, not the other way round.

FAIL-CLOSED IS THE DESIGN
`UNKNOWN` is a real licence value, not a null, and it is NOT exportable. A
source added later without a mapping lands on UNKNOWN and is silently excluded
from exports rather than silently included in them. The parametrised test over
`FoodSource` turns that from a runtime hope into a CI failure.

IFCT IS DELIBERATELY UNKNOWN. Indian government works are not automatically
public domain, and IFCT 2017 is an ICMR-NIN publication sold as a book. Until
somebody confirms terms in writing, it maps to UNKNOWN and cannot be exported.

Pure functions, no I/O.
"""

from __future__ import annotations

from enum import Enum

from ..models import FoodSource


class Licence(str, Enum):
    """What we are permitted to do with a row's nutrition data."""

    #: US federal work. No attribution required, no share-alike.
    public_domain = "public-domain"
    #: Open Database License. Attribution required; share-alike on distribution.
    odbl = "odbl"
    #: Metered vendor feed. Redistribution prohibited by contract.
    proprietary = "proprietary"
    #: Ours or our users'. Curated dishes and user submissions.
    owned = "user"
    #: Unmapped. Fail-closed: never exported. See the module docstring.
    unknown = "unknown"


class Tier(int, Enum):
    """The plan's source-priority ladder. LOWER IS BETTER.

    An ordinal, which is the point. `data_quality` is a float smeared across
    51 distinct values between 0.29 and 0.95 -- 107,863 rows sit on 0.51 alone
    -- so it cannot express "a curated dish outranks a crowd-sourced product".
    That ordering is what stops 'sambhar' returning Everest Sambhar Masala, a
    ~350 kcal/100 g spice powder, ahead of the actual dish.
    """

    lab_verified = 1
    government = 2
    licensed_commercial = 3
    product_label = 4
    dietitian_recipe = 5
    community_verified = 6
    ai_estimate = 7


#: source -> (licence, tier, attribution or None)
#:
#: EXHAUSTIVE OVER `FoodSource` BY CONTRACT. test_licensing parametrises over
#: the enum, so adding a member without adding it here fails CI rather than
#: quietly defaulting a row to UNKNOWN in production.
LICENCE_MAP: dict[FoodSource, tuple[Licence, Tier, str | None]] = {
    FoodSource.usda: (
        Licence.public_domain,
        Tier.government,
        "USDA FoodData Central",
    ),
    FoodSource.off: (
        Licence.odbl,
        Tier.community_verified,
        "Open Food Facts (ODbL)",
    ),
    FoodSource.curated: (
        Licence.owned,
        Tier.dietitian_recipe,
        None,
    ),
    FoodSource.user: (
        Licence.owned,
        Tier.community_verified,
        None,
    ),
    FoodSource.nutritionix: (
        Licence.proprietary,
        Tier.licensed_commercial,
        "Nutritionix",
    ),
    FoodSource.ai: (
        Licence.owned,
        Tier.ai_estimate,
        None,
    ),
    # Present, mapped, and deliberately not usable. See the module docstring.
    FoodSource.ifct: (
        Licence.unknown,
        Tier.dietitian_recipe,
        "IFCT 2017 (NIN Hyderabad)",
    ),
}

_FALLBACK = (Licence.unknown, Tier.ai_estimate, None)


def licence_for(source: FoodSource) -> Licence:
    """Licence for a source. Unmapped sources fail closed to UNKNOWN."""
    return LICENCE_MAP.get(source, _FALLBACK)[0]


def tier_for(source: FoodSource) -> Tier:
    """Ranking tier for a source.

    An unmapped source sorts LAST rather than first -- a row nobody has
    classified must never outrank one somebody has.
    """
    return LICENCE_MAP.get(source, _FALLBACK)[1]


def attribution_for(source: FoodSource) -> str | None:
    """The credit line to display, or None when none is owed."""
    return LICENCE_MAP.get(source, _FALLBACK)[2]


def source_url_for(source: FoodSource, source_id: str | None, barcode: str | None) -> str | None:
    """Deep link to the upstream record, so provenance is checkable.

    The plan's rule is "do not hide the source of nutritional information".
    A licence name alone does not let a user verify a number; a URL does.
    """
    if source == FoodSource.usda and source_id:
        return f"https://fdc.nal.usda.gov/fdc-app.html#/food-details/{source_id}"
    if source == FoodSource.off and barcode:
        return f"https://world.openfoodfacts.org/product/{barcode}"
    return None


def requires_attribution(source: FoodSource) -> bool:
    """Does displaying this row oblige us to credit someone?"""
    return attribution_for(source) is not None and licence_for(source) in (
        Licence.odbl,
        Licence.proprietary,
        Licence.public_domain,
    )


def is_exportable(licence: Licence) -> bool:
    """May a row under this licence go into a user-facing bulk export?

    ODbL is excluded not because sharing is forbidden but because sharing it
    triggers share-alike on the whole derived database. That is a decision for
    a human to take deliberately, not one for an export endpoint to take by
    default at 3am.

    UNKNOWN is excluded because we cannot say what it permits, and "we are not
    sure" must resolve to no.
    """
    return licence in (Licence.public_domain, Licence.owned)


def attribution_notice() -> str:
    """The credit block for the profile screen.

    Lives here rather than in the client so the licence text and the mapping
    that produces it cannot drift apart.
    """
    return (
        "Nutrition data comes from Open Food Facts, made available under the "
        "Open Database License (ODbL), and from USDA FoodData Central, which "
        "is in the public domain. Dishes and recipes are compiled by Trace."
    )


def export_filter_summary(counts: dict[FoodSource, int]) -> dict[str, int]:
    """Split a per-source row census into exportable and withheld.

    Used by the export path to explain a shortfall to the user instead of
    silently handing back fewer rows than they expected.
    """
    exportable = withheld = 0
    for source, n in counts.items():
        if is_exportable(licence_for(source)):
            exportable += n
        else:
            withheld += n
    return {"exportable": exportable, "withheld": withheld}
