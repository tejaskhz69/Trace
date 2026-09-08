"""Calibrate the validator before measuring anything with it.

WHY THIS FILE EXISTS
--------------------
The D'lecta Mozzarella panel -- whose Atwater arithmetic reconciles to 0.2% --
scored `quarantine` with quality 0.0. Not because the panel was bad, but
because it was transcribed with the printed panel's wording (`energy_kcal`,
`carbohydrates_g`, `total_fat_g`) instead of the column names the validator
reads (`calories`, `carbs_g`, `fat_g`).

A validator that reports "unreadable" as "impossible" cannot be used to
measure a defect rate, because the number it produces is part importer bug
and part food problem, with no way to separate them. Every downstream figure
inherits that ambiguity -- including the August "1 in 3 Indian products are
defective" claim.

So this file characterises the instrument first. It is the software equivalent
of weighing a known 140 g pack before trusting the scale.

TWO WAYS TO FAIL, AND THEY ARE NOT SYMMETRIC
--------------------------------------------
A validator that never flags anything is useless. A validator that flags good
data is worse than useless -- it destroys trust in the queue and trains people
to click through warnings. USDA rows are the control: public domain, curated,
the least likely source of defects in the whole catalogue. **If a USDA row
fails, the validator is wrong, not USDA.**
"""
from __future__ import annotations

import pytest

from app.services import nutrition_validator as nv

# ---------------------------------------------------------------------------
# KNOWN GOOD -- every one of these must ACCEPT
# ---------------------------------------------------------------------------

#: D'lecta Mozzarella Shreds, transcribed from the physical pack 2026-09-05.
#: 24.5x4 + 0.5x4 + 20.5x9 = 284.5 vs 284 declared -- 0.2%.
#: Macro mass 45.5 g/100 g, the rest water and ash, right for ~50% moisture.
DLECTA_MOZZARELLA = {
    "calories": 284.0,
    "protein_g": 24.5,
    "carbs_g": 0.5,
    "fat_g": 20.5,
    "sugar_g": 0.5,
    "saturated_fat_g": 12.9,
    "sodium_mg": 640.0,
    "fiber_g": 0.0,
}

#: Hand-built stand-ins with the shape of real USDA rows. These are NOT drawn
#: from the live catalogue -- see the module-level skip below for the ten real
#: rows, which need a database connection.
USDA_SHAPED = {
    "raw chicken breast": {
        "calories": 120.0, "protein_g": 22.5, "carbs_g": 0.0, "fat_g": 2.6,
        "fiber_g": 0.0, "sugar_g": 0.0, "sodium_mg": 45.0,
        "saturated_fat_g": 0.7,
    },
    "white rice, cooked": {
        "calories": 130.0, "protein_g": 2.7, "carbs_g": 28.2, "fat_g": 0.3,
        "fiber_g": 0.4, "sugar_g": 0.1, "sodium_mg": 1.0,
        "saturated_fat_g": 0.1,
    },
    "whole milk": {
        "calories": 61.0, "protein_g": 3.2, "carbs_g": 4.8, "fat_g": 3.3,
        "fiber_g": 0.0, "sugar_g": 5.1, "sodium_mg": 43.0,
        "saturated_fat_g": 1.9,
    },
    "olive oil": {
        "calories": 884.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 100.0,
        "fiber_g": 0.0, "sugar_g": 0.0, "sodium_mg": 2.0,
        "saturated_fat_g": 13.8,
    },
    "lentils, boiled": {
        "calories": 116.0, "protein_g": 9.0, "carbs_g": 20.1, "fat_g": 0.4,
        "fiber_g": 7.9, "sugar_g": 1.8, "sodium_mg": 2.0,
        "saturated_fat_g": 0.1,
    },
}

#: Our own curated Indian rows.
CURATED_INDIAN = {
    "dal tadka": {
        "calories": 128.0, "protein_g": 7.0, "carbs_g": 15.0, "fat_g": 4.5,
        "fiber_g": 3.0, "sugar_g": 1.0, "sodium_mg": 320.0,
        "saturated_fat_g": 1.2,
    },
    "idli": {
        "calories": 105.0, "protein_g": 3.0, "carbs_g": 21.0, "fat_g": 0.5,
        "fiber_g": 1.0, "sugar_g": 0.3, "sodium_mg": 180.0,
        "saturated_fat_g": 0.1,
    },
}

# ---------------------------------------------------------------------------
# KNOWN BAD -- every one of these must FLAG (quarantine, or corrections)
# ---------------------------------------------------------------------------

#: MTR Rava Idli Mix, 8901042954516. Declares 1.5 g protein/100 g. The
#: ingredient list is semolina and gram flour, which cannot fall below ~11 g.
MTR_RAVA_IDLI = {
    "calories": 348.0, "protein_g": 1.5, "carbs_g": 78.0, "fat_g": 3.0,
    "fiber_g": 2.0, "sugar_g": 4.0, "sodium_mg": 890.0,
    "saturated_fat_g": 1.5,
}
MTR_RAVA_IDLI_INGREDIENTS = [("semolina", 70.0), ("gram flour", 20.0)]

#: Gits Sambar Mix: 5,480 mg sodium/100 g. Physically possible only if the
#: product is more than half salt.
GITS_SAMBAR_SODIUM = {
    "calories": 320.0, "protein_g": 12.0, "carbs_g": 50.0, "fat_g": 8.0,
    "fiber_g": 8.0, "sugar_g": 3.0, "sodium_mg": 5480.0,
    "saturated_fat_g": 3.0,
}

#: Eastern Rice Rava: 46.7 g fibre/100 g. Wheat bran, the highest-fibre food
#: in normal commerce, is ~43 g.
EASTERN_RICE_RAVA_FIBRE = {
    "calories": 360.0, "protein_g": 8.0, "carbs_g": 76.0, "fat_g": 1.0,
    "fiber_g": 46.7, "sugar_g": 1.0, "sodium_mg": 12.0,
    "saturated_fat_g": 0.3,
}

#: Bambino: sodium recorded in grams where the column is milligrams, so the
#: value reads ~1000x low. The panel looks innocuous; the unit is the bug.
BAMBINO_SODIUM_UNIT = {
    "calories": 350.0, "protein_g": 11.0, "carbs_g": 72.0, "fat_g": 1.5,
    "fiber_g": 3.0, "sugar_g": 2.0, "sodium_mg": 0.9,
    "saturated_fat_g": 0.4,
}

#: Aachi Rice Idli: 133 kcal/100 g filed under a DRY MIX barcode. A dry mix
#: is 300-430 kcal; 133 is an as-prepared figure in a dry-mix row.
AACHI_AS_PREPARED = {
    "calories": 133.0, "protein_g": 3.5, "carbs_g": 27.0, "fat_g": 0.5,
    "fiber_g": 1.2, "sugar_g": 0.5, "sodium_mg": 210.0,
    "saturated_fat_g": 0.1,
}

# ---------------------------------------------------------------------------
# The known-good set
# ---------------------------------------------------------------------------


class TestKnownGoodMustPass:
    """False positives are the expensive failure. These must all accept."""

    def test_dlecta_mozzarella_accepts(self):
        r = nv.validate(DLECTA_MOZZARELLA)
        assert r.verdict is nv.Verdict.accept, nv.explain(r)

    @pytest.mark.parametrize("name", sorted(USDA_SHAPED))
    def test_usda_shaped_rows_accept(self, name):
        """USDA is the control. A failure here indicts the validator."""
        r = nv.validate(USDA_SHAPED[name])
        assert r.verdict is nv.Verdict.accept, f"{name}: {nv.explain(r)}"

    @pytest.mark.parametrize("name", sorted(CURATED_INDIAN))
    def test_curated_indian_rows_accept(self, name):
        r = nv.validate(CURATED_INDIAN[name])
        assert r.verdict is nv.Verdict.accept, f"{name}: {nv.explain(r)}"


# ---------------------------------------------------------------------------
# The known-bad set
# ---------------------------------------------------------------------------

#: Each entry is the full set of kwargs a real row would supply. Passing a
#: bare panel understates what the validator has to work with -- every row in
#: `food_items` carries a name, and most carry a category.
KNOWN_BAD = {
    "MTR Rava Idli protein floor": dict(
        nutriments=MTR_RAVA_IDLI,
        ingredients=MTR_RAVA_IDLI_INGREDIENTS,
        name="MTR Rava Idli Mix",
        category="dry_mix",
    ),
    "Gits Sambar sodium": dict(
        nutriments=GITS_SAMBAR_SODIUM,
        name="Gits Sambar Mix",
        category="dry_mix",
    ),
    "Eastern Rice Rava fibre": dict(
        nutriments=EASTERN_RICE_RAVA_FIBRE,
        name="Eastern Rice Rava",
        category="flour",
    ),
    "Bambino sodium unit error": dict(
        nutriments=BAMBINO_SODIUM_UNIT,
        name="Bambino Vermicelli Upma Mix",
        category="dry_mix",
    ),
    "Aachi as-prepared in a dry-mix row": dict(
        nutriments=AACHI_AS_PREPARED,
        name="Aachi Rice Idli Mix",
        category="dry_mix",
    ),
}


class TestKnownBadMustFlag:
    """A validator that never fires is not strict, it is asleep."""

    @pytest.mark.parametrize("name", sorted(KNOWN_BAD))
    def test_flags(self, name):
        kwargs = dict(KNOWN_BAD[name])
        panel = kwargs.pop("nutriments")
        r = nv.validate(panel, **kwargs)
        assert r.verdict is not nv.Verdict.accept, (
            f"{name} passed clean, which it should not:\n{nv.explain(r)}"
        )
        assert r.verdict is not nv.Verdict.unreadable, (
            f"{name} came back unreadable -- the fixture has a field-name bug, "
            f"not the validator:\n{nv.explain(r)}"
        )


# ---------------------------------------------------------------------------
# Salt evidence
#
# The check that broke the known-good set. It is not disabled -- it is made to
# require evidence, and these pin both halves of that.
# ---------------------------------------------------------------------------


class TestSaltEvidence:
    """`is_salted` must be earned. None means the check stays quiet."""

    def test_a_bare_panel_yields_no_verdict_on_salt(self):
        """No name, no category, no ingredients -- so no opinion.

        This is the whole fix. A panel carrying nothing but numbers cannot
        support the claim "this product contains salt", and the check that
        used to assume it condemned every whole food in the catalogue.
        """
        assert nv.infer_is_salted() is None

    def test_an_ingredient_list_naming_salt_is_the_strongest_signal(self):
        assert nv.infer_is_salted(
            ingredients_text="semolina, edible common salt, turmeric"
        ) is True

    def test_indian_language_salt_terms_are_recognised(self):
        assert nv.infer_is_salted(ingredients_text="besan, namak, haldi") is True
        assert nv.infer_is_salted(ingredients_text="arisi, uppu, milagai") is True

    def test_unsalted_is_not_read_as_salted(self):
        """"unsalted" contains "salt". The negation must be tested first."""
        assert nv.infer_is_salted(ingredients_text="cream, unsalted butter") is False

    def test_an_ingredient_list_without_salt_is_evidence_of_absence(self):
        assert nv.infer_is_salted(ingredients_text="milk, live cultures") is False

    def test_a_sweet_overrides_a_salted_category(self):
        """Gulab jamun mix and rava idli mix are both dry_mix."""
        assert nv.infer_is_salted(
            name="MTR Gulab Jamun Mix", category="dry_mix"
        ) is False

    def test_a_pure_spice_overrides_a_salted_category(self):
        """Garam masala runs ~50 mg sodium. That is the correct answer."""
        assert nv.infer_is_salted(
            name="Everest Garam Masala", category="masala"
        ) is False

    def test_category_is_the_last_resort_and_only_for_certain_ones(self):
        assert nv.infer_is_salted(category="dry_mix") is True
        # `meat` carries raw beef and cured ham alike, so it may not answer.
        assert nv.infer_is_salted(category="meat") is None
        # Nor may `bakery`, which carries both bread and cake.
        assert nv.infer_is_salted(category="bakery") is None

    def test_the_check_still_fires_when_salt_is_attested(self):
        """Aachi Idli Podi: 2.3 mg sodium on a product whose #2 is salt."""
        podi = {
            "calories": 480.0, "protein_g": 18.0, "carbs_g": 40.0,
            "fat_g": 28.0, "fiber_g": 12.0, "sugar_g": 2.0,
            "sodium_mg": 2.3, "saturated_fat_g": 4.0,
        }
        r = nv.validate(
            podi,
            name="Aachi Idli Podi",
            ingredients_text="bengal gram, salt, red chilli, urad dal",
        )
        codes = {i.code for i in r.issues}
        assert "sodium_near_zero_on_salted_product" in codes, nv.explain(r)

    def test_an_explicit_caller_is_still_believed(self):
        """The parameter survives. A caller who knows can overrule."""
        rice = dict(USDA_SHAPED["white rice, cooked"])
        assert nv.validate(rice, is_salted=False).verdict is nv.Verdict.accept
        forced = nv.validate(rice, is_salted=True)
        assert "sodium_near_zero_on_salted_product" in {
            i.code for i in forced.issues
        }


# ---------------------------------------------------------------------------
# Energy the 4/4/9 sum cannot model
#
# 41% of the quarantines this validator produced on the cached FDC release
# were beer. The sum describes protein, available carbohydrate and fat; it has
# nothing to say about ethanol, polyols, organic acids, or the 2-to-4 kcal/g
# range fibre actually occupies. A check that cannot model a food must say so
# rather than convict it.
# ---------------------------------------------------------------------------

#: Real rows, transcribed from the cached FDC release (SR Legacy / Survey).
REAL_UNMODELLABLE = {
    "beer": {
        "panel": {"calories": 43.0, "protein_g": 0.46, "carbs_g": 3.55,
                  "fat_g": 0.0, "fiber_g": 0.0, "sugar_g": 0.0,
                  "sodium_mg": 4.0, "saturated_fat_g": 0.0},
        "name": "Alcoholic beverage, beer, regular, all",
        "category": "drink",
        "why": "ethanol is 7 kcal/g and appears in no macro column",
    },
    "sake": {
        "panel": {"calories": 134.0, "protein_g": 0.5, "carbs_g": 5.0,
                  "fat_g": 0.0, "fiber_g": 0.0, "sugar_g": 0.0,
                  "sodium_mg": 2.0, "saturated_fat_g": 0.0},
        "name": "Alcoholic beverage, rice (sake)",
        "category": "drink",
        "why": "macros imply 22 kcal against 134 declared -- all of it alcohol",
    },
    "lemon": {
        "panel": {"calories": 29.0, "protein_g": 1.1, "carbs_g": 9.32,
                  "fat_g": 0.3, "fiber_g": 2.8, "sugar_g": 2.5,
                  "sodium_mg": 2.0, "saturated_fat_g": 0.04},
        "name": "Lemons, raw, without peel",
        "category": "fruit",
        "why": "citric acid yields ~2.5 kcal/g, not 4",
    },
    "oat bran": {
        "panel": {"calories": 246.0, "protein_g": 17.3, "carbs_g": 66.22,
                  "fat_g": 7.03, "fiber_g": 15.4, "sugar_g": 1.45,
                  "sodium_mg": 4.0, "saturated_fat_g": 1.33},
        "name": "Oat bran, raw",
        "category": "grain",
        "why": "fibre's yield depends on fermentability",
    },
}

#: Leafy vegetables. These were failing before the band replaced the point
#: estimate -- USDA derives their energy with specific Atwater factors.
REAL_LEAFY = {
    "spinach": {
        "panel": {"calories": 23.0, "protein_g": 2.86, "carbs_g": 3.63,
                  "fat_g": 0.39, "fiber_g": 2.2, "sugar_g": 0.42,
                  "sodium_mg": 79.0, "saturated_fat_g": 0.06},
        "name": "Spinach, raw", "category": "vegetable",
    },
    "broccoli": {
        "panel": {"calories": 32.0, "protein_g": 2.57, "carbs_g": 6.29,
                  "fat_g": 0.34, "fiber_g": 2.4, "sugar_g": 1.4,
                  "sodium_mg": 36.0, "saturated_fat_g": 0.04},
        "name": "Broccoli, raw", "category": "vegetable",
    },
}


class TestEnergyWeCannotModel:
    """`energy_unexplained` asserts nothing about the food. That is the point."""

    @pytest.mark.parametrize("key", sorted(REAL_UNMODELLABLE))
    def test_unmodellable_energy_is_never_a_defect(self, key):
        row = REAL_UNMODELLABLE[key]
        r = nv.validate(row["panel"], name=row["name"],
                        category=row["category"],
                        carb_convention=nv.CARB_TOTAL)
        assert r.verdict is not nv.Verdict.quarantine, (
            f"{row['name']} was called defective, but {row['why']}:\n"
            f"{nv.explain(r)}"
        )
        assert r.is_servable, f"{key} must still be servable"

    @pytest.mark.parametrize("key", sorted(REAL_UNMODELLABLE))
    def test_the_reason_is_named_not_swallowed(self, key):
        """Silence would be as bad as a false conviction."""
        row = REAL_UNMODELLABLE[key]
        r = nv.validate(row["panel"], name=row["name"],
                        category=row["category"],
                        carb_convention=nv.CARB_TOTAL)
        if r.verdict is nv.Verdict.accept:
            return  # reconciled inside the band; nothing to explain
        assert "energy_unexplained" in {i.code for i in r.issues}, nv.explain(r)

    @pytest.mark.parametrize("key", sorted(REAL_LEAFY))
    def test_leafy_vegetables_accept(self, key):
        row = REAL_LEAFY[key]
        r = nv.validate(row["panel"], name=row["name"],
                        category=row["category"],
                        carb_convention=nv.CARB_TOTAL)
        assert r.verdict is nv.Verdict.accept, nv.explain(r)

    def test_an_unexplained_gap_is_still_a_defect(self):
        """The check must not have been defanged.

        Same shape of failure as sake -- macros nowhere near the declared
        energy -- but on a food with nothing to explain it.
        """
        r = nv.validate(
            {"calories": 400.0, "protein_g": 2.0, "carbs_g": 5.0,
             "fat_g": 1.0, "fiber_g": 0.0, "sugar_g": 1.0,
             "sodium_mg": 10.0, "saturated_fat_g": 0.2},
            name="Plain wheat cracker", category="bakery",
        )
        assert r.verdict is nv.Verdict.quarantine, nv.explain(r)
        assert "atwater_mismatch_severe" in {i.code for i in r.issues}

    def test_unverifiable_does_not_compound_into_a_quarantine(self):
        """Two checks we could not run are not evidence of two problems."""
        row = REAL_UNMODELLABLE["sake"]
        r = nv.validate(row["panel"], name=row["name"],
                        category=row["category"])
        assert r.verdict is nv.Verdict.unverifiable
        assert not r.errors
        assert r.quality_score > 0.0


class TestCarbConvention:
    """The two sources disagree, and the column does not record which."""

    def test_usda_carbs_include_fibre(self):
        """Verified on the cached release: 0 of 7,931 rows had fibre > carbs."""
        oat_bran = REAL_UNMODELLABLE["oat bran"]["panel"]
        lo, hi = nv.expected_energy_band(oat_bran, nv.CARB_TOTAL)
        # Fibre sits INSIDE carbs, so it is re-priced, never added on top.
        assert lo < hi
        flat = (oat_bran["protein_g"] * 4 + oat_bran["carbs_g"] * 4
                + oat_bran["fat_g"] * 9)
        assert hi == pytest.approx(flat), "upper edge is the flat 4/4/9 sum"

    def test_an_unknown_convention_widens_the_band_rather_than_guessing(self):
        panel = REAL_UNMODELLABLE["oat bran"]["panel"]
        t_lo, t_hi = nv.expected_energy_band(panel, nv.CARB_TOTAL)
        u_lo, u_hi = nv.expected_energy_band(panel, nv.CARB_UNKNOWN)
        assert u_lo <= t_lo and u_hi >= t_hi
        assert u_hi > t_hi, "the unknown band must span the EU reading too"

    def test_a_row_without_fibre_has_no_band_at_all(self):
        """Nothing to be uncertain about, so do not manufacture slack."""
        lo, hi = nv.expected_energy_band(
            {"calories": 884.0, "protein_g": 0.0, "carbs_g": 0.0,
             "fat_g": 100.0, "fiber_g": 0.0},
            nv.CARB_UNKNOWN,
        )
        assert lo == hi == 900.0


# ---------------------------------------------------------------------------
# The validator annotates. It does not rewrite.
# ---------------------------------------------------------------------------

#: Real rows, from the cached FDC release. Every one of these clears 5,000 mg
#: sodium per 100 g honestly.
GENUINELY_SALTY = {
    "jellyfish": (
        "Jellyfish, dried, salted", "seafood",
        {"calories": 36.0, "protein_g": 5.5, "carbs_g": 0.0, "fat_g": 1.4,
         "fiber_g": 0.0, "sugar_g": 0.0, "sodium_mg": 9690.0,
         "saturated_fat_g": 0.3},
    ),
    "bouillon": (
        "Soup, beef broth, cubed, dry", "soup",
        {"calories": 170.0, "protein_g": 16.7, "carbs_g": 16.7, "fat_g": 4.0,
         "fiber_g": 0.0, "sugar_g": 0.0, "sodium_mg": 24000.0,
         "saturated_fat_g": 2.0},
    ),
    "soy sauce": (
        "Soy sauce made from soy and wheat (shoyu)", "soup",
        {"calories": 53.0, "protein_g": 8.14, "carbs_g": 4.93, "fat_g": 0.57,
         "fiber_g": 0.8, "sugar_g": 0.4, "sodium_mg": 5493.0,
         "saturated_fat_g": 0.08},
    ),
    "fish sauce": (
        "Fish sauce, ready-to-serve", "soup",
        {"calories": 35.0, "protein_g": 5.06, "carbs_g": 3.64, "fat_g": 0.01,
         "fiber_g": 0.0, "sugar_g": 3.6, "sodium_mg": 7851.0,
         "saturated_fat_g": 0.0},
    ),
}


class TestTheValidatorNeverRewritesAValue:
    """A validator that alters data is worse than one that flags it.

    The damage is invisible downstream and the original is gone. These pin the
    property rather than trusting that no check happens to do it today.
    """

    @pytest.mark.parametrize("key", sorted(GENUINELY_SALTY))
    def test_the_input_panel_is_never_mutated(self, key):
        _, _, panel = GENUINELY_SALTY[key]
        name, category, _ = GENUINELY_SALTY[key]
        before = dict(panel)
        nv.validate(dict(panel), name=name, category=category)
        nv.validate(panel, name=name, category=category)
        assert panel == before, "validate() edited the dict it was handed"

    def test_a_result_carries_no_channel_for_applying_values(self):
        """`corrections` was declared and never written. It is gone.

        A dead field with that name is an invitation to start applying
        suggestions automatically later, which is the failure this class
        exists to prevent.
        """
        r = nv.validate(DLECTA_MOZZARELLA)
        assert not hasattr(r, "corrections")

    def test_a_suggested_value_is_advisory_and_clearly_marked(self):
        """A real unit error may still SUGGEST the corrected figure."""
        r = nv.validate(
            {"calories": 350.0, "protein_g": 11.0, "carbs_g": 72.0,
             "fat_g": 1.5, "fiber_g": 3.0, "sugar_g": 2.0,
             "sodium_mg": 16290.0, "saturated_fat_g": 0.4},
            name="Bambino Vermicelli Upma Mix", category="dry_mix",
        )
        issue = next(i for i in r.issues if i.code == "sodium_unit_error")
        assert issue.observed == 16290.0, "the original must be reported"
        assert issue.expected == 16.29
        assert "left exactly as it was found" in issue.message


class TestSaltyFoodIsNotAUnitError:
    """8,000 mg/100 g is not impossible. It is Tuesday, for some foods."""

    @pytest.mark.parametrize("key", sorted(GENUINELY_SALTY))
    def test_genuinely_salty_food_survives(self, key):
        name, category, panel = GENUINELY_SALTY[key]
        r = nv.validate(panel, name=name, category=category)
        assert r.verdict is not nv.Verdict.quarantine, nv.explain(r)
        assert r.is_servable
        assert "sodium_unit_error" not in {i.code for i in r.issues}

    @pytest.mark.parametrize("key", sorted(GENUINELY_SALTY))
    def test_and_keeps_its_own_sodium_figure(self, key):
        name, category, panel = GENUINELY_SALTY[key]
        original = panel["sodium_mg"]
        nv.validate(panel, name=name, category=category)
        assert panel["sodium_mg"] == original

    def test_a_real_unit_error_still_flags(self):
        """Bambino: sodium recorded in grams where milligrams belong.

        Nothing about a vermicelli upma mix explains 16,290 mg, so the
        unit-error reading is the only one left.
        """
        r = nv.validate(
            {"calories": 350.0, "protein_g": 11.0, "carbs_g": 72.0,
             "fat_g": 1.5, "fiber_g": 3.0, "sugar_g": 2.0,
             "sodium_mg": 16290.0, "saturated_fat_g": 0.4},
            name="Bambino Vermicelli Upma Mix", category="dry_mix",
        )
        assert r.verdict is nv.Verdict.quarantine
        assert "sodium_unit_error" in {i.code for i in r.issues}

    def test_a_biscuit_is_not_excused_by_the_marker_list(self):
        """The escape hatch must not be reachable by ordinary food."""
        assert not nv.sodium_extremity_is_explained(
            "Britannia Marie Gold biscuit", "bakery"
        )
        assert not nv.sodium_extremity_is_explained("Milk, whole", "dairy")
        assert not nv.sodium_extremity_is_explained(
            "Cookies, chocolate chip", "bakery"
        )


class TestMarkersMatchWholeWords:
    """`sour` once matched 548 rows of Sweet And Sour Pork.

    A false marker EXCUSES a defect, so an over-broad term does not merely add
    noise -- it silently stops the check working. Same bug as `cure` matching
    `obscured`, and the same fix.
    """

    @pytest.mark.parametrize("name,category", [
        ("Kale, frozen, cooked, boiled, drained, without salt", "vegetable"),
        ("Fish, drum, freshwater, raw", "seafood"),
        ("Emu, inside drum, raw", "meat"),
        ("Sweet And Sour Pork, Chinese restaurant", "restaurant"),
        ("MORI-NU, Tofu, silken, lite firm", "legume"),
        ("Pears, canned, extra light syrup pack", "fruit"),
    ])
    def test_ordinary_food_carries_no_marker(self, name, category):
        assert nv.unmodelled_energy_marker(name, category) is None

    @pytest.mark.parametrize("name,category,want", [
        ("Alcoholic beverage, beer, regular, all", "drink", "alcohol"),
        ("Wine, table, red", "drink", "alcohol"),
        ("Alcoholic beverage, rice (sake)", "drink", "alcohol"),
        ("Lemons, raw, without peel", "fruit", "organic_acid"),
        ("Vinegar, red wine", "drink", "organic_acid"),
        ("Oat bran, raw", "grain", "unusual_fibre"),
        ("Gelatin desserts, dry mix, reduced calorie, with aspartame",
         "sweet", "polyol"),
    ])
    def test_the_real_cases_still_match(self, name, category, want):
        marker = nv.unmodelled_energy_marker(name, category)
        assert marker is not None and marker[0] == want


class TestZeroCaloriesIsAValue:
    """A filled-in table that reads zero is a measurement, not a gap.

    `food_sources._off_to_resolved` already decided this, deliberately letting
    kcal == 0 through and naming Kirkland Purified Water in the comment. The
    validator then quarantined every one of them and the importer dropped
    them, so the fix was undone two steps downstream of itself.
    """

    ZERO = {
        "calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0,
        "fiber_g": 0.0, "sugar_g": 0.0, "sodium_mg": 2.0,
        "saturated_fat_g": 0.0,
    }

    @pytest.mark.parametrize("name", [
        "Kirkland Purified Water",
        "Coffee, brewed, black",
        "Diet Coke",
        "Sparkling water, unsweetened",
        "Tea, brewed, plain",
    ])
    def test_a_real_zero_is_accepted(self, name):
        r = nv.validate(dict(self.ZERO), name=name, category="drink")
        assert r.verdict is nv.Verdict.accept, nv.explain(r)
        assert r.is_servable

    def test_pure_salt_is_accepted_too(self):
        """0 kcal and 38,758 mg sodium are both correct."""
        panel = dict(self.ZERO, sodium_mg=38758.0)
        r = nv.validate(panel, name="Salt, table", category="spice")
        assert r.verdict is not nv.Verdict.quarantine, nv.explain(r)

    def test_zero_energy_with_real_macros_is_still_a_contradiction(self):
        """The check is relaxed, not removed."""
        panel = dict(self.ZERO, protein_g=8.0, carbs_g=20.0, fat_g=3.0)
        r = nv.validate(panel, name="Mystery bar", category="snack")
        assert r.verdict is nv.Verdict.quarantine
        assert "energy_missing_but_macros_present" in {
            i.code for i in r.issues
        }

    def test_a_record_with_no_calories_key_is_still_unreadable(self):
        """Absent and zero remain different facts."""
        panel = {k: v for k, v in self.ZERO.items() if k != "calories"}
        r = nv.validate(panel, name="Kirkland Purified Water")
        assert r.verdict is nv.Verdict.unreadable


# ---------------------------------------------------------------------------
# The schema pre-check itself
# ---------------------------------------------------------------------------


class TestSchemaPrecheck:
    """The bug that started all this."""

    def test_label_wording_is_unreadable_not_quarantine(self):
        """The exact failure: a clean panel under panel wording.

        This is the whole point. Same numbers, same food, same arithmetic --
        only the key names differ. It must not come back as a claim about the
        nutrition.
        """
        label_style = {
            "energy_kcal": 284.0, "protein_g": 24.5, "carbohydrates_g": 0.5,
            "total_fat_g": 20.5, "total_sugar_g": 0.5,
            "saturated_fat_g": 12.9, "sodium_mg": 640.0,
        }
        r = nv.validate(label_style)
        assert r.verdict is nv.Verdict.unreadable
        assert r.verdict is not nv.Verdict.quarantine
        assert not r.is_servable

    def test_the_aliases_are_named_so_the_bug_is_findable(self):
        r = nv.validate({"energy_kcal": 284.0, "protein_g": 24.5})
        assert r.schema is not None
        assert r.schema.aliased.get("energy_kcal") == "calories"
        assert "calories" in r.schema.missing

    def test_an_empty_record_is_unreadable(self):
        r = nv.validate({})
        assert r.verdict is nv.Verdict.unreadable

    def test_a_readable_panel_reports_no_schema_problem(self):
        r = nv.validate(DLECTA_MOZZARELLA)
        assert r.schema is not None
        assert r.schema.ok
        assert not r.schema.missing
        assert not r.schema.aliased

    def test_unknown_extra_fields_do_not_block_reading(self):
        """Extra keys are noted, not fatal. Only missing REQUIRED blocks."""
        panel = dict(DLECTA_MOZZARELLA, cholesterol_mg=64.62, trans_fat_g=0.73)
        r = nv.validate(panel)
        assert r.verdict is nv.Verdict.accept
        assert "cholesterol_mg" in r.schema.unknown
        assert "trans_fat_g" in r.schema.unknown
