"""Tests for the nutrition validator and the as-prepared engine.

The validator tests use REAL broken rows found in Open Food Facts and USDA
Branded in Aug 2026. If a future refactor stops catching these, users start
getting silently wrong macros -- so each one is pinned here by barcode.
"""

from __future__ import annotations

import pytest

from app.services import nutrition_validator as nv
from app.services.preparation import (
    OIL_UPTAKE,
    PREPARATIONS,
    Nutrients,
    dilution_factor,
    prepare,
)


# ===========================================================================
# Validator -- real defects
# ===========================================================================


def test_mtr_rava_idli_protein_error_is_caught():
    """OFF 8901042954516 declares 1.5 g protein on an 80% semolina product.

    This is THE canonical case: semolina is ~12 g protein/100 g, so 80%
    semolina alone contributes 9.6 g. The declared value is wrong by ~7x, and
    protein is the exact input the strength adjudication engine reads.
    """
    result = nv.validate(
        {
            "calories": 365, "protein_g": 1.5, "carbs_g": 63, "fat_g": 8,
            "sugar_g": 1.5, "saturated_fat_g": 3, "sodium_mg": 3600,
        },
        category="dry_mix",
        ingredients=[("semolina", 80), ("bengal gram splits", 8)],
    )
    assert result.verdict is nv.Verdict.quarantine
    assert not result.is_servable
    codes = {i.code for i in result.issues}
    assert "protein_contradicts_ingredients" in codes


def test_mtr_rava_idli_passes_once_corrected():
    result = nv.validate(
        {
            "calories": 365, "protein_g": 10.5, "carbs_g": 63, "fat_g": 8,
            "sugar_g": 1.5, "saturated_fat_g": 3, "fiber_g": 2.5,
            "sodium_mg": 1200,
        },
        category="dry_mix",
        ingredients=[("semolina", 80), ("bengal gram splits", 8)],
    )
    assert result.verdict is nv.Verdict.accept
    assert result.quality_score >= 0.5


def test_as_prepared_panel_filed_as_dry_mix_is_caught():
    """Aachi 8904209305541: 133 kcal/100 g filed under a dry-mix barcode.

    A dry idli mix is 330-360 kcal. 133 is steamed idli. Importing it as a mix
    understates a user's intake by ~2.6x.
    """
    panel = {
        "calories": 133, "protein_g": 4, "carbs_g": 28.5, "fat_g": 0.3,
        "sugar_g": 0.04, "saturated_fat_g": 0.08, "sodium_mg": 1000,
    }
    as_mix = nv.validate(panel, category="dry_mix")
    assert as_mix.verdict is nv.Verdict.quarantine
    assert "below_category_band_likely_as_prepared" in {
        i.code for i in as_mix.issues
    }

    # The same numbers are perfectly fine once filed correctly.
    as_prepared = nv.validate(panel, category="prepared")
    assert as_prepared.is_servable


def test_sodium_unit_error_is_caught():
    """Bambino Multigrain Vermicelli lists sodium as '16.29 g' (i.e. mg)."""
    result = nv.validate(
        {
            "calories": 341.7, "protein_g": 13.2, "carbs_g": 71.4,
            "fat_g": 1.1, "sugar_g": 2.2, "saturated_fat_g": 0.15,
            "sodium_mg": 16290,
        },
        category="vermicelli",
    )
    assert result.verdict is nv.Verdict.quarantine
    issue = next(i for i in result.issues if i.code == "sodium_unit_error")
    assert issue.expected == pytest.approx(16.29)


def test_impossible_fibre_is_caught():
    """Eastern Rice Rava (USDA): 46.7 g fibre/100 g."""
    result = nv.validate(
        {
            "calories": 273, "protein_g": 6.7, "carbs_g": 53.3, "fat_g": 6.7,
            "fiber_g": 46.7, "sugar_g": 6.7, "sodium_mg": 0,
        },
        category="flour",
    )
    assert result.verdict is nv.Verdict.quarantine
    assert "fibre_impossible" in {i.code for i in result.issues}


def test_incomplete_panel_is_caught():
    """Sakthi Sambar Powder: only ~25 g of 100 g accounted for."""
    result = nv.validate(
        {
            "calories": 162, "protein_g": 2.16, "carbs_g": 12.98,
            "fat_g": 8.39, "fiber_g": 1.47, "sugar_g": 6.74,
            "saturated_fat_g": 1.60, "sodium_mg": 1180,
        },
        category="masala",
    )
    assert result.verdict is nv.Verdict.quarantine
    assert "mass_balance_incomplete" in {i.code for i in result.issues}


def test_near_zero_sodium_on_salted_product_is_flagged():
    """Aachi Idli Podi: 2.3 mg sodium on an oil-roasted, salted podi."""
    result = nv.validate(
        {
            "calories": 548, "protein_g": 14.9, "carbs_g": 31.5,
            "fat_g": 40.3, "saturated_fat_g": 0.1, "fiber_g": 3.7,
            "sugar_g": 0.8, "sodium_mg": 2.3,
        },
        category="masala",
    )
    codes = {i.code for i in result.issues}
    assert "sodium_near_zero_on_salted_product" in codes
    # 0.1 g saturated on 40.3 g total fat is not possible for any edible oil.
    assert "saturated_fat_implausibly_low" in codes
    assert result.quality_score < 0.6


def test_good_data_passes_clean():
    """Gits Rice Idli (8901155102217) -- two independent sources agree."""
    result = nv.validate(
        {
            "calories": 330, "protein_g": 11, "carbs_g": 67, "fat_g": 0.9,
            "fiber_g": 2, "sugar_g": 0, "saturated_fat_g": 0.2,
            "sodium_mg": 1120,
        },
        category="dry_mix",
        source_quality=0.8,
    )
    assert result.verdict is nv.Verdict.accept
    assert result.quality_score == 0.8


def test_pintola_passes():
    """The product that started all this. 8906136651951."""
    result = nv.validate(
        {
            "calories": 390, "protein_g": 25, "carbs_g": 54.6, "fat_g": 8,
            "fiber_g": 9.6, "sugar_g": 14, "saturated_fat_g": 3,
            "sodium_mg": 180,
        },
        category="dry_mix",
    )
    assert result.is_servable


# ===========================================================================
# Validator -- structural checks
# ===========================================================================


def test_macros_cannot_exceed_100g():
    result = nv.validate(
        {"calories": 700, "protein_g": 40, "carbs_g": 50, "fat_g": 30}
    )
    assert "macro_sum_exceeds_100" in {i.code for i in result.issues}


def test_sugar_cannot_exceed_carbs():
    result = nv.validate(
        {"calories": 400, "protein_g": 5, "carbs_g": 20, "fat_g": 30,
         "sugar_g": 35}
    )
    assert "sugar_exceeds_carbs" in {i.code for i in result.issues}


def test_saturated_cannot_exceed_total_fat():
    result = nv.validate(
        {"calories": 400, "protein_g": 5, "carbs_g": 40, "fat_g": 10,
         "saturated_fat_g": 15}
    )
    assert "saturated_exceeds_total_fat" in {i.code for i in result.issues}


def test_atwater_mismatch_detected():
    # Macros imply ~800 kcal; 300 declared.
    result = nv.validate(
        {"calories": 300, "protein_g": 20, "carbs_g": 20, "fat_g": 70}
    )
    assert "atwater_mismatch_severe" in {i.code for i in result.issues}


def test_many_warnings_compound_into_quarantine():
    result = nv.validate(
        {"calories": 200, "protein_g": 2, "carbs_g": 20, "fat_g": 5,
         "fiber_g": 1, "sodium_mg": 6000},
        category="masala",
    )
    assert result.verdict is nv.Verdict.quarantine


def test_duplicate_panel_detection():
    """Four Eastern SKUs share one identical 354/8/78/1/0.5/0.2 block."""
    panel = {"calories": 354, "protein_g": 8, "carbs_g": 78, "fat_g": 0.5,
             "fiber_g": 0, "sugar_g": 1}
    products = [
        {"id": "idiyappam", "nutriments": panel},
        {"id": "white_puttu", "nutriments": panel},
        {"id": "appam", "nutriments": panel},
        {"id": "roasted_rice", "nutriments": panel},
        {"id": "different", "nutriments": {**panel, "protein_g": 9}},
    ]
    dupes = flagged = nv.flag_duplicate_panels(products, threshold=3)
    assert len(flagged) == 1
    assert len(next(iter(dupes.values()))) == 4


# ===========================================================================
# As-prepared engine
# ===========================================================================


MTR_RAVA_IDLI = Nutrients(365, 10.5, 63, 8, 2.5, 1.5, 1200)
GITS_RICE_IDLI = Nutrients(330, 11, 67, 0.9, 2, 0, 1120)
GITS_DOSA = Nutrients(360, 10, 68, 6, 4, 0, 1000)
GITS_VADA = Nutrients(348, 19, 57, 4.5, 9, 0.5, 1150)


def test_nutrients_arithmetic():
    a = Nutrients(100, 10, 10, 5)
    b = Nutrients(50, 5, 5, 2)
    assert (a + b).kcal == 150
    assert a.scaled(2).protein_g == 20
    assert a.per_100g(200).kcal == 50


def test_rava_idli_matches_manufacturer_yield():
    """Gits states 30 idlis per 500 g pack -> 12 per 200 g, ~50 g each."""
    r = prepare(PREPARATIONS["rava_idli"], MTR_RAVA_IDLI)
    assert r.pieces == 12
    assert 45 <= r.grams_per_piece <= 56
    # Published rava idli is ~161 kcal/100 g.
    assert 150 <= r.per_100g.kcal <= 185


def test_rice_idli_matches_published_piece_weight():
    """Gits: 200 g -> 18 idlis. Published idli is 30-40 g, ~130 kcal/100 g."""
    r = prepare(PREPARATIONS["rice_idli"], GITS_RICE_IDLI)
    assert r.pieces == 18
    assert 32 <= r.grams_per_piece <= 42
    assert 100 <= r.per_100g.kcal <= 140


def test_dosa_matches_published_values():
    """Published plain dosa is ~260 kcal/100 g, ~6.5 g fat/100 g."""
    r = prepare(PREPARATIONS["dosa"], GITS_DOSA)
    assert r.pieces == 8
    assert 240 <= r.per_100g.kcal <= 285


def test_pan_oil_dominates_a_dosa():
    """1 tsp of pan oil is ~45 kcal on a ~110 kcal dosa.

    This is why the oil must be a user-editable field, not baked into one
    number. A restaurant dosa uses 2-3x what a home cook does.
    """
    spec = PREPARATIONS["dosa"]
    dry = prepare(spec, GITS_DOSA, overrides={"oil": 0})
    home = prepare(spec, GITS_DOSA)                      # 44 g over 8 dosas
    restaurant = prepare(spec, GITS_DOSA, overrides={"oil": 120})

    assert dry.per_piece.kcal < home.per_piece.kcal < restaurant.per_piece.kcal
    # The oil roughly doubles a dosa.
    assert home.per_piece.kcal > dry.per_piece.kcal * 1.5
    assert restaurant.per_piece.kcal > dry.per_piece.kcal * 2.0


def test_deep_frying_adds_oil_and_loses_water():
    """Medu vada absorbs ~18% of its FINISHED weight as oil.

    Applying uptake to the raw dough instead would overstate by ~20%.
    """
    r = prepare(PREPARATIONS["medu_vada"], GITS_VADA)
    absorbed = r.breakdown["absorbed frying oil"]
    assert absorbed > 0
    ratio = absorbed / r.prepared_weight_g
    assert ratio == pytest.approx(OIL_UPTAKE["medu_vada"], abs=0.01)
    # Finished fat/100 g must land in the published 15-22% band.
    assert 15 <= r.per_100g.fat_g <= 24


def test_gulab_jamun_syrup_dominates_the_piece():
    """A finished jamun is more absorbed syrup than it is dough."""
    r = prepare(PREPARATIONS["gulab_jamun"], Nutrients(428, 14.3, 57.1, 14.3, 1, 21.4, 784))
    syrup = r.breakdown["absorbed sugar syrup"]
    assert syrup / r.prepared_weight_g > 0.5
    # Published gulab jamun is ~323 kcal/100 g; the model should be in range.
    assert 250 <= r.per_100g.kcal <= 360


def test_dilution_factors_are_all_significant():
    """Every one of these is a real logging error a user would otherwise make."""
    for key, spec in PREPARATIONS.items():
        df = dilution_factor(spec)
        assert df > 1.5, f"{key} dilution {df} unexpectedly low"
        assert df < 6.0, f"{key} dilution {df} unexpectedly high"


def test_upma_has_the_largest_dilution():
    """200 g of mix becomes ~865 g of upma -- a 4x error if logged raw."""
    assert dilution_factor(PREPARATIONS["upma"]) > 4.0


def test_curd_choice_changes_rava_idli_materially():
    spec = PREPARATIONS["rava_idli"]
    full = prepare(spec, MTR_RAVA_IDLI)
    less = prepare(spec, MTR_RAVA_IDLI, overrides={"curd_full_fat": 200})
    assert full.total.kcal > less.total.kcal
    assert full.total.fat_g > less.total.fat_g


def test_scaling_the_batch_scales_the_pieces():
    spec = PREPARATIONS["rice_idli"]
    half = prepare(spec, GITS_RICE_IDLI, dry_mix_g=100)
    full = prepare(spec, GITS_RICE_IDLI, dry_mix_g=200)
    assert half.pieces == 9 and full.pieces == 18
    # Per-100 g composition must be identical regardless of batch size.
    assert half.per_100g.kcal == pytest.approx(full.per_100g.kcal, abs=1.0)
