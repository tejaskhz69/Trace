"""The spec for source-licence mapping and export gating.

Pure -- no database. The obligation being encoded: 565,814 of 578,773 rows are
Open Food Facts under ODbL, which requires attribution on public use and
share-alike on public distribution of a derived database.
"""

from __future__ import annotations

import pytest

from app.models import FoodSource
from app.services.licensing import (
    DISPLAY_NAMES,
    LICENCE_MAP,
    Licence,
    Tier,
    attribution_for,
    attribution_line,
    display_name_for,
    attribution_notice,
    export_filter_summary,
    is_exportable,
    licence_for,
    requires_attribution,
    source_url_for,
    tier_for,
)


class TestMappingIsExhaustive:
    @pytest.mark.parametrize("source", list(FoodSource))
    def test_every_source_is_mapped(self, source):
        """THE CI GUARD.

        Adding a FoodSource member without a licence entry must fail here,
        not default a row to UNKNOWN in production three months later.
        """
        assert source in LICENCE_MAP, f"{source} has no licence mapping"

    @pytest.mark.parametrize("source", list(FoodSource))
    def test_every_source_has_a_tier(self, source):
        assert isinstance(tier_for(source), Tier)

    def test_no_source_maps_to_a_bare_string(self):
        for licence, tier, _ in LICENCE_MAP.values():
            assert isinstance(licence, Licence)
            assert isinstance(tier, Tier)


class TestLicenceMapping:
    @pytest.mark.parametrize(
        "source,licence",
        [
            (FoodSource.usda, Licence.public_domain),
            (FoodSource.off, Licence.odbl),
            (FoodSource.curated, Licence.owned),
            (FoodSource.user, Licence.owned),
            (FoodSource.nutritionix, Licence.proprietary),
            (FoodSource.ai, Licence.owned),
        ],
    )
    def test_maps(self, source, licence):
        assert licence_for(source) == licence

    def test_ifct_is_unknown_until_its_licence_is_confirmed(self):
        """Indian government works are not automatically public domain.

        IFCT 2017 is an ICMR-NIN publication sold as a book. Until terms are
        confirmed in writing it must be unusable, not merely undocumented.
        """
        assert licence_for(FoodSource.ifct) == Licence.unknown
        assert not is_exportable(licence_for(FoodSource.ifct))


class TestTierOrdering:
    def test_lower_is_better(self):
        assert Tier.government < Tier.community_verified

    def test_curated_dish_outranks_crowd_sourced_product(self):
        """THE ONE THAT FIXES 'sambhar'.

        Everest Sambhar Masala -- a ~350 kcal/100 g spice powder from Open
        Food Facts -- currently ranks above the actual dish. The dish is
        curated, tier 5; the powder is community, tier 6.
        """
        assert tier_for(FoodSource.curated) < tier_for(FoodSource.off)

    def test_government_data_outranks_everything_crowd_sourced(self):
        assert tier_for(FoodSource.usda) < tier_for(FoodSource.off)
        assert tier_for(FoodSource.usda) < tier_for(FoodSource.user)

    def test_ai_estimates_rank_last(self):
        """The plan's rule: never present an AI estimate as verified data."""
        worst = max(tier_for(s) for s in FoodSource)
        assert tier_for(FoodSource.ai) == worst


class TestFailClosed:
    def test_unmapped_source_is_unknown(self):
        class Rogue(str):
            pass

        assert licence_for(Rogue("something-new")) == Licence.unknown

    def test_unmapped_source_sorts_last_not_first(self):
        """A row nobody has classified must never outrank one somebody has."""
        class Rogue(str):
            pass

        assert tier_for(Rogue("x")) == Tier.ai_estimate

    def test_unknown_is_never_exportable(self):
        assert not is_exportable(Licence.unknown)


class TestExportGating:
    @pytest.mark.parametrize(
        "licence,allowed",
        [
            (Licence.public_domain, True),
            (Licence.owned, True),
            (Licence.odbl, False),
            (Licence.proprietary, False),
            (Licence.unknown, False),
        ],
    )
    def test_gate(self, licence, allowed):
        assert is_exportable(licence) is allowed

    def test_odbl_rows_are_withheld_from_export(self):
        """Share-alike triggers on distributing a derived database.

        Shipping ODbL rows in a user export is a deliberate decision for a
        human, not a default for an endpoint to take at 3am.
        """
        assert not is_exportable(licence_for(FoodSource.off))

    def test_export_summary_splits_the_catalogue(self):
        """The real census, so the shortfall is explainable to a user."""
        counts = {
            FoodSource.off: 565_814,
            FoodSource.usda: 12_612,
            FoodSource.curated: 347,
        }
        summary = export_filter_summary(counts)
        assert summary["exportable"] == 12_959
        assert summary["withheld"] == 565_814

    def test_empty_census_is_safe(self):
        assert export_filter_summary({}) == {"exportable": 0, "withheld": 0}


class TestAttribution:
    def test_open_food_facts_credit_names_the_licence(self):
        credit = attribution_for(FoodSource.off)
        assert credit and "Open Food Facts" in credit and "ODbL" in credit

    def test_odbl_requires_attribution(self):
        assert requires_attribution(FoodSource.off)

    def test_our_own_data_needs_no_credit(self):
        assert attribution_for(FoodSource.curated) is None
        assert not requires_attribution(FoodSource.curated)

    def test_notice_names_both_public_sources(self):
        """Rendered on the profile screen. Currently absent from the app."""
        notice = attribution_notice()
        assert "Open Food Facts" in notice
        assert "Open Database License" in notice or "ODbL" in notice
        assert "USDA" in notice


class TestSourceUrl:
    def test_usda_deep_link(self):
        url = source_url_for(FoodSource.usda, "173944", None)
        assert url == "https://fdc.nal.usda.gov/fdc-app.html#/food-details/173944"

    def test_off_deep_link_uses_the_barcode(self):
        url = source_url_for(FoodSource.off, "x", "4006381333931")
        assert url == "https://world.openfoodfacts.org/product/4006381333931"

    def test_returns_none_when_there_is_nothing_to_link(self):
        """A licence name alone does not let a user verify a number.

        None is honest; a fabricated link is not.
        """
        assert source_url_for(FoodSource.curated, "abc", None) is None
        assert source_url_for(FoodSource.off, "x", None) is None
        assert source_url_for(FoodSource.usda, None, None) is None


class TestDisplayNames:
    """What a source is CALLED in front of a user.

    Split from `attribution_for` because a list row has space for a name and
    nothing else, while a detail view has room for the whole sentence. The
    failure this guards is the one that already happened once: `nutritionix`
    was added to the API and never to the client's copy of this table, so
    metered rows rendered "SOURCE UNKNOWN" and dropped a credit owed by
    contract.
    """

    @pytest.mark.parametrize("source", list(FoodSource))
    def test_every_source_has_a_display_name(self, source):
        assert source in DISPLAY_NAMES, f"{source} has no display name"
        assert DISPLAY_NAMES[source].strip()

    def test_names_are_the_ones_a_user_would_recognise(self):
        assert display_name_for(FoodSource.off) == "Open Food Facts"
        assert display_name_for(FoodSource.usda) == "USDA FoodData Central"
        assert display_name_for(FoodSource.nutritionix) == "Nutritionix"

    def test_our_own_estimate_says_so(self):
        """`ai_estimated` is not an unknown source. We know exactly whose it is."""
        assert display_name_for(FoodSource.ai) == "Trace estimate"
        assert "unknown" not in display_name_for(FoodSource.ai).lower()

    def test_an_unmapped_source_is_not_prettified_into_a_name(self):
        """A made-up name reads as authoritative. "We do not know" is true."""
        assert display_name_for("some_feed_added_next_year") == "Source not recorded"


class TestAttributionLine:
    """The sentence rendered on the food-detail sheet."""

    def test_open_food_facts_names_the_licence(self):
        line = attribution_line(FoodSource.off)
        assert "Open Food Facts" in line
        assert "Open Database License (ODbL)" in line

    def test_usda_is_public_domain_and_never_odbl(self):
        line = attribution_line(FoodSource.usda)
        assert "USDA FoodData Central" in line
        assert "public domain" in line
        assert "ODbL" not in line
        assert "Open Food Facts" not in line

    def test_nutritionix_is_credited_as_licensed(self):
        line = attribution_line(FoodSource.nutritionix)
        assert "Nutritionix" in line
        assert "under licence" in line

    @pytest.mark.parametrize(
        "source", [FoodSource.curated, FoodSource.user, FoodSource.ai]
    )
    def test_our_own_rows_get_no_credit_line_at_all(self, source):
        """None, not an empty string.

        The UI branches on it: None means render nothing, "" would render an
        empty notice with a divider above it.
        """
        assert attribution_line(source) is None

    def test_the_rows_stored_licence_wins_over_the_source_default(self):
        """A row whose licence column says 'unknown' must SAY so.

        Inheriting ODbL from the source table would be the app asserting a
        licence the row does not actually record.
        """
        line = attribution_line(FoodSource.off, Licence.unknown)
        assert "Open Food Facts" in line
        assert "licence not recorded" in line
        assert "ODbL" not in line

    def test_a_named_publisher_is_credited_even_under_an_unknown_licence(self):
        """IFCT: named publisher, licence nobody has confirmed.

        The two fail-closed directions in this module point opposite ways.
        For EXPORT, unsure means no -- distributing without the right is the
        harm. For CREDIT, unsure means yes -- omitting a credit is the harm
        and showing one costs nothing.
        """
        line = attribution_line(FoodSource.ifct)
        assert "Indian Food Composition Tables" in line
        assert "licence not recorded" in line
        assert not is_exportable(licence_for(FoodSource.ifct))

    @pytest.mark.parametrize("source", list(FoodSource))
    def test_no_line_ever_claims_compliance(self, source):
        """Nothing in this app may assert that showing a credit discharges
        an obligation. That is a question for a lawyer, not for a format
        string. See services/api/review/LICENSING_REVIEW.md."""
        line = attribution_line(source) or ""
        low = line.lower()
        for banned in ("compliant", "compliance", "permitted", "authorised",
                       "authorized", "we own", "all rights"):
            assert banned not in low, f"{source}: {line!r}"

    @pytest.mark.parametrize("source", list(FoodSource))
    def test_a_line_never_credits_the_wrong_party(self, source):
        """The specific error this whole module exists to prevent."""
        line = attribution_line(source) or ""
        if source is not FoodSource.off:
            assert "Open Food Facts" not in line
        if source is not FoodSource.usda:
            assert "USDA" not in line
