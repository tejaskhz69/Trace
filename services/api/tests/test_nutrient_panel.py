"""The 26-nutrient panel. The last class is the one that matters most."""

import pytest

from app.services import nutrient_panel as np
from app.services.nutrient_panel import Kind

FULL = {n.key: 1.0 for n in np.NUTRIENTS}


def cov(value: float = 1.0) -> dict[str, float]:
    return {n.key: value for n in np.NUTRIENTS}


class TestCatalogue:
    def test_tracks_twenty_six(self):
        assert len(np.NUTRIENTS) == 26

    def test_keys_are_unique(self):
        keys = [n.key for n in np.NUTRIENTS]
        assert len(keys) == len(set(keys))

    def test_groups_in_reading_order(self):
        assert np.groups() == ["Macronutrients", "Minerals", "Vitamins"]

    def test_ceilings_are_the_ones_you_stay_under(self):
        ceilings = {n.key for n in np.NUTRIENTS if n.kind is Kind.ceiling}
        assert ceilings == {
            "sodium_mg", "sugar_g", "saturated_fat_g", "trans_fat_g",
            "cholesterol_mg",
        }

    def test_potassium_is_a_floor_not_a_ceiling(self):
        # Colouring a low potassium bar like a high sodium bar teaches the
        # wrong reading of half the panel.
        assert np.BY_KEY["potassium_mg"].kind is Kind.floor


class TestTargets:
    def test_iron_target_is_sex_specific(self):
        iron = np.BY_KEY["iron_mg"]
        assert np.target_for(iron, "female", None) > np.target_for(iron, "male", None) * 2

    def test_unknown_sex_falls_back_to_male(self):
        iron = np.BY_KEY["iron_mg"]
        assert np.target_for(iron, None, None) == iron.target_m

    def test_energy_linked_targets_scale(self):
        carbs = np.BY_KEY["carbs_g"]
        big = np.target_for(carbs, None, 3000)
        small = np.target_for(carbs, None, 1500)
        assert big > small
        assert big / small == pytest.approx(2.0, rel=0.01)

    def test_fixed_targets_do_not_scale(self):
        b12 = np.BY_KEY["vitamin_b12_ug"]
        assert np.target_for(b12, None, 3000) == np.target_for(b12, None, 1500)


class TestPanel:
    def test_every_nutrient_gets_a_row(self):
        p = np.build_panel({}, {})
        assert len(p.rows) == 26
        assert p.tracked == 26

    def test_a_met_floor_reads_ok(self):
        p = np.build_panel({"protein_g": 60}, {"protein_g": 1.0}, sex="male")
        row = next(r for r in p.rows if r.key == "protein_g")
        assert row.status == "ok"

    def test_a_missed_floor_reads_short(self):
        p = np.build_panel({"protein_g": 20}, {"protein_g": 1.0}, sex="male")
        assert next(r for r in p.rows if r.key == "protein_g").status == "short"

    def test_a_blown_ceiling_reads_over(self):
        p = np.build_panel({"sodium_mg": 3600}, {"sodium_mg": 1.0})
        assert next(r for r in p.rows if r.key == "sodium_mg").status == "over"

    def test_a_ceiling_well_under_is_ok_not_short(self):
        # Being far under a limit is success, not a deficiency.
        p = np.build_panel({"sodium_mg": 500}, {"sodium_mg": 1.0})
        assert next(r for r in p.rows if r.key == "sodium_mg").status == "ok"

    def test_notable_ranks_the_worst_first(self):
        p = np.build_panel(
            {"sodium_mg": 4600, "iron_mg": 7.6, "protein_g": 56},
            {"sodium_mg": 1.0, "iron_mg": 1.0, "protein_g": 1.0},
            sex="male",
        )
        assert p.notable[0] == "sodium_mg"

    def test_notable_is_capped_so_it_stays_a_shortlist(self):
        p = np.build_panel({n.key: 0.1 for n in np.NUTRIENTS}, cov())
        assert len(p.notable) <= 5

    def test_headline_says_so_when_everything_is_fine(self):
        totals = {
            n.key: (np.target_for(n, None, None) * (0.5 if n.kind is Kind.ceiling else 1.0))
            for n in np.NUTRIENTS
        }
        p = np.build_panel(totals, cov())
        assert "in range" in p.headline


class TestUnknownStaysUnknown:
    """Non-negotiable #3, applied to a nutrition table.

    Public food data is patchy. Reporting "Vitamin D: 4% of target" from a
    database that has no vitamin D would invite someone to supplement against
    an artefact of our ingestion, not a fact about their diet.
    """

    def test_thin_coverage_refuses_a_percentage(self):
        p = np.build_panel({"vitamin_d_ug": 0.6}, {"vitamin_d_ug": 0.05})
        row = next(r for r in p.rows if r.key == "vitamin_d_ug")
        assert row.status == "unknown"
        assert row.pct is None

    def test_a_missing_nutrient_is_unknown_not_zero(self):
        p = np.build_panel({}, {})
        row = next(r for r in p.rows if r.key == "vitamin_k_ug")
        assert row.status == "unknown"
        assert row.pct is None

    def test_never_reports_short_from_an_empty_database(self):
        p = np.build_panel({}, {})
        assert all(r.status == "unknown" for r in p.rows)
        assert p.notable == []
        assert p.known == 0

    def test_good_coverage_does_report(self):
        p = np.build_panel({"vitamin_d_ug": 0.6}, {"vitamin_d_ug": 0.95})
        row = next(r for r in p.rows if r.key == "vitamin_d_ug")
        assert row.status == "short"
        assert row.pct is not None

    def test_coverage_is_reported_so_the_ui_can_explain_itself(self):
        p = np.build_panel({"iron_mg": 8}, {"iron_mg": 0.42})
        assert next(r for r in p.rows if r.key == "iron_mg").covered == 0.42

    def test_the_headline_admits_it_knows_nothing(self):
        assert "Not enough" in np.build_panel({}, {}).headline


class TestSodiumPotassium:
    def test_refuses_without_both(self):
        ratio, note = np.sodium_potassium_ratio(3000, None)
        assert ratio is None
        assert "not enough data" in note.lower()

    def test_balanced_is_praised(self):
        ratio, note = np.sodium_potassium_ratio(3000, 3000)
        assert ratio == 1.0
        assert "want it" in note.lower()

    def test_sodium_heavy_is_flagged_with_the_easier_fix(self):
        ratio, note = np.sodium_potassium_ratio(3290, 1400)
        assert ratio > 2
        # Raising potassium is easier than cutting salt, and the copy says so.
        assert "potassium" in note.lower()


class TestNotes:
    def test_the_usual_suspects_have_an_explanation(self):
        for key in ("sodium_mg", "potassium_mg", "iron_mg", "vitamin_b12_ug"):
            assert key in np.NOTES
            assert len(np.NOTES[key]) > 40

    def test_notes_reference_real_nutrients(self):
        assert all(k in np.BY_KEY for k in np.NOTES)
