"""Spec for nutrition-label transcription.

The rule this file exists to enforce: a label reader must REFUSE rather than
invent. A hallucinated "12 g protein" looks exactly like a real reading, and
the user has no way to tell the difference — which makes it worse than a blank
field they would have filled in themselves.
"""

from __future__ import annotations

import pytest

from app.services.label_ocr import (
    KJ_PER_KCAL,
    SALT_G_TO_SODIUM_MG,
    assess,
    to_per_100g,
)


def _label(**over):
    base = {
        "legible": True,
        "basis": "100g",
        "calories": 380.0,
        "protein_g": 20.0,
        "carbs_g": 40.0,
        "fat_g": 14.0,
        "confidence": 0.9,
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Refusing to invent
# ---------------------------------------------------------------------------


def test_a_missing_field_stays_missing():
    """None means 'not printed'. Filling it with a typical value would be a
    fabrication the user cannot detect."""
    panel, _ = to_per_100g(_label(fiber_g=None))
    assert panel["fiber_g"] is None


def test_an_unreadable_label_is_flagged_not_silently_accepted():
    r = assess(_label(legible=False, confidence=0.2))
    assert r.legible is False
    assert any("too unclear" in w for w in r.warnings)


def test_negative_values_are_rejected_as_misread_characters():
    panel, _ = to_per_100g(_label(protein_g=-20.0))
    assert panel["protein_g"] is None


def test_non_numeric_garbage_does_not_crash_the_read():
    panel, _ = to_per_100g(_label(carbs_g="forty"))
    assert panel["carbs_g"] is None


# ---------------------------------------------------------------------------
# The per-serving trap
# ---------------------------------------------------------------------------


def test_a_per_serving_label_is_scaled_to_per_100g():
    """The classic silent error: reading a US per-serving column and storing
    it as per 100 g scales every number at once, invisibly."""
    panel, warnings = to_per_100g(
        _label(basis="serving", serving_size_g=50.0, calories=190.0, protein_g=10.0)
    )
    assert panel["calories"] == pytest.approx(380.0)
    assert panel["protein_g"] == pytest.approx(20.0)
    assert any("scaled to per 100 g" in w for w in warnings)


def test_a_per_100g_label_is_left_alone():
    panel, _ = to_per_100g(_label(basis="100g", serving_size_g=50.0))
    assert panel["calories"] == pytest.approx(380.0)


def test_per_serving_without_a_serving_size_refuses_to_convert():
    """Scaling by an unknown factor, or pretending the numbers are per 100 g,
    are both worse than saying we could not do it."""
    panel, warnings = to_per_100g(_label(basis="serving", serving_size_g=None))
    assert panel["calories"] == pytest.approx(380.0)  # unconverted, as read
    assert any("could not be put on a per-100 g basis" in w for w in warnings)


def test_an_absurd_serving_size_is_treated_as_a_misread_decimal():
    panel, warnings = to_per_100g(_label(basis="serving", serving_size_g=0.02))
    assert any("no usable serving size" in w for w in warnings)
    assert panel["calories"] == pytest.approx(380.0)


def test_an_unknown_basis_is_surfaced_rather_than_assumed():
    _, warnings = to_per_100g(_label(basis="unknown"))
    assert any("per 100 g or per serving" in w for w in warnings)


# ---------------------------------------------------------------------------
# Units the label may or may not print
# ---------------------------------------------------------------------------


def test_kilojoules_are_converted_when_kcal_is_absent():
    panel, warnings = to_per_100g(
        _label(calories=None, energy_kj=1590.0)
    )
    assert panel["calories"] == pytest.approx(1590.0 / KJ_PER_KCAL, abs=0.1)
    assert any("kilojoules" in w for w in warnings)


def test_kcal_wins_when_both_are_printed():
    panel, _ = to_per_100g(_label(calories=380.0, energy_kj=9999.0))
    assert panel["calories"] == pytest.approx(380.0)


def test_salt_is_converted_to_sodium_not_treated_as_it():
    """EU labels print salt, US labels print sodium. Treating them as the same
    number over-states sodium by two and a half times."""
    panel, warnings = to_per_100g(_label(salt_g=1.0, sodium_mg=None))
    assert panel["sodium_mg"] == pytest.approx(SALT_G_TO_SODIUM_MG, abs=1)
    assert panel["sodium_mg"] < 1000  # NOT 1000 mg, which the naive read gives
    assert any("salt" in w for w in warnings)


def test_printed_sodium_is_preferred_over_derived_salt():
    panel, _ = to_per_100g(_label(sodium_mg=250.0, salt_g=1.0))
    assert panel["sodium_mg"] == pytest.approx(250.0)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_a_coherent_label_passes_and_keeps_a_high_quality_score():
    r = assess(_label())
    assert r.verdict != "quarantine"
    assert r.quality > 0.5


def test_a_panel_whose_macros_cannot_explain_its_calories_is_rejected():
    """20 kcal cannot contain 30 g of fat. The label was misread or misprinted,
    and offering it would put a wrong number in someone's diary for months."""
    r = assess(_label(calories=20.0, protein_g=30.0, carbs_g=30.0, fat_g=30.0))
    assert r.verdict == "quarantine"
    assert any("do not add up" in w for w in r.warnings)


def test_the_reading_carries_the_product_name_when_it_was_visible():
    r = assess(_label(product_name="  Kirkland Protein Bar  ", brand="Kirkland"))
    assert r.product_name == "Kirkland Protein Bar"
    assert r.brand == "Kirkland"


def test_an_absent_product_name_is_none_not_an_empty_string():
    r = assess(_label())
    assert r.product_name is None
