"""What the vision model is allowed to put in a user's diary.

NO MODEL IS CALLED. Every test here feeds `_sanitize` a payload directly --
that is the whole point of the function being pure. A test that needed a live
model would cost money to run and would test the model rather than our defence
against it.

THE THREE DEFENCES, AND WHY THEY ARE DIFFERENT
    DROP    the item is unusable, and nothing is lost by discarding it.
    DELETE  a field that must not exist at all -- an invented identifier.
    FLAG    the numbers are plausible but do not hold together. Kept, marked
            for review, fields named. Never silently repaired.

The third is the one that matters. "Fixing" a macro so the arithmetic closes
invents a number no human asserted and no source supports, and presents it
with exactly the confidence of a real reading.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.services.nutrition_validator import ATWATER_HARD_LIMIT
from app.services.vision import (
    MACRO_MASS_SLACK,
    MAX_ITEM_GRAMS,
    MAX_ITEM_KCAL,
    _sanitize,
)


def item(**over) -> dict:
    """A coherent item: 240 kcal from 8 P / 20 C / 12 F in 200 g."""
    base = {
        "name": "Dal tadka",
        "kcal_low": 190.0,
        "kcal_point": 240.0,
        "kcal_high": 300.0,
        "grams_est": 200.0,
        "protein_g": 8.0,
        "carbs_g": 20.0,
        "fat_g": 12.0,
        "confidence": 0.7,
    }
    base.update(over)
    return base


def sanitize(*items, **payload) -> dict:
    return _sanitize({"items": list(items), "overall_confidence": 0.8, **payload})


class TestTheHappyCase:
    def test_a_coherent_item_survives_intact(self):
        out = sanitize(item())
        assert len(out["items"]) == 1
        got = out["items"][0]
        assert got["name"] == "Dal tadka"
        assert got["kcal_point"] == 240.0
        assert got["review_required"] is False
        assert got["uncertain_fields"] == []
        assert out["review_required"] is False

    def test_every_item_is_marked_an_estimate(self):
        """Stated explicitly rather than left for the client to infer.

        An estimate that reaches a UI without this flag is one refactor away
        from being rendered as established fact.
        """
        assert sanitize(item())["items"][0]["is_estimated"] is True

    def test_required_fields_are_always_present(self):
        got = sanitize(item())["items"][0]
        for field in (
            "name", "portion_unit", "portion_count", "grams_est", "kcal_point",
            "kcal_low", "kcal_high", "protein_g", "carbs_g", "fat_g",
            "confidence", "is_estimated", "review_required", "uncertain_fields",
        ):
            assert field in got, field


class TestDrop:
    """Unusable items. Nothing of value is lost by discarding them."""

    @pytest.mark.parametrize(
        "bad,why",
        [
            ({"name": ""}, "no name"),
            ({"name": "   "}, "whitespace name"),
            ({"kcal_point": 0}, "zero calories"),
            ({"kcal_point": -50}, "negative calories"),
            ({"kcal_point": MAX_ITEM_KCAL + 1}, "one item, more than a day of food"),
            ({"grams_est": 0}, "no mass"),
            ({"grams_est": -5}, "negative mass"),
            ({"grams_est": MAX_ITEM_GRAMS + 1}, "five kilos of one dish"),
            ({"kcal_point": "many"}, "non-numeric calories"),
            ({"grams_est": None}, "null mass"),
        ],
    )
    def test_unusable_items_are_dropped(self, bad, why):
        assert sanitize(item(**bad))["items"] == [], why

    def test_a_missing_key_drops_only_that_item(self):
        payload = {"items": [item(), {"name": "Rice"}], "overall_confidence": 0.8}
        out = _sanitize(payload)
        assert [i["name"] for i in out["items"]] == ["Dal tadka"]

    def test_an_empty_payload_is_not_an_error(self):
        out = _sanitize({})
        assert out["items"] == []
        assert out["review_required"] is False


class TestDeleteHallucinatedIdentifiers:
    """The most dangerous thing this pipeline could produce.

    A fabricated GTIN looks exactly like a scanned one, would be believed, and
    would attach a real product's identity to a guess about somebody's dinner.
    """

    @pytest.mark.parametrize(
        "key",
        ["barcode", "gtin", "gtin14", "ean", "upc", "sku", "product_id",
         "product_code", "fdc_id", "off_id"],
    )
    def test_no_identifier_key_ever_reaches_the_client(self, key):
        out = sanitize(item(**{key: "8906136651951"}))
        assert key not in out["items"][0]

    def test_even_a_checksum_valid_gtin_is_discarded(self):
        """Validity is not the question. PROVENANCE is.

        `services/gtin.py` cannot tell "read off a packet" from "plausible
        digits a model produced", and there is no verification available here,
        so the only safe action is to drop it.
        """
        out = sanitize(item(barcode="8906136651951"))  # a real, valid EAN-13
        assert "barcode" not in out["items"][0]
        assert "8906136651951" not in str(out)

    def test_the_rest_of_the_item_survives(self):
        """An over-helpful model is not a reason to lose a good estimate."""
        out = sanitize(item(barcode="8906136651951"))
        assert out["items"][0]["name"] == "Dal tadka"
        assert out["items"][0]["kcal_point"] == 240.0

    def test_the_schema_never_asked_for_one(self):
        from app.services.vision import TOOL_SCHEMA

        props = TOOL_SCHEMA["parameters"]["properties"]["items"]["items"]["properties"]
        assert not any(
            k in props for k in ("barcode", "gtin", "upc", "ean", "product_id")
        )


class TestFlagRatherThanRepair:
    def test_macros_that_cannot_account_for_the_calories_are_flagged(self):
        # 90/90/90 implies ~1530 kcal against a stated 240.
        out = sanitize(item(protein_g=90, carbs_g=90, fat_g=90))
        got = out["items"][0]
        assert got["review_required"] is True
        assert "kcal_point" in got["uncertain_fields"]

    def test_the_value_is_left_alone(self):
        """Not repaired. A rewritten macro is a number nobody asserted."""
        out = sanitize(item(protein_g=90, carbs_g=90, fat_g=90))
        got = out["items"][0]
        assert got["kcal_point"] == 240.0
        assert got["protein_g"] == 90.0

    def test_the_tolerance_is_the_catalogue_s_own(self):
        """Deliberately not a second, private threshold.

        `nutrition_validator.ATWATER_HARD_LIMIT` is 35% and loose on purpose:
        fibre yields ~2 kcal/g rather than 4, sugar alcohols less again, and
        labels round every figure independently. Demanding equality would flag
        most real food.
        """
        assert ATWATER_HARD_LIMIT == 0.35
        # 8P/20C/12F = 220 kcal. Against 240 that is 8% drift -- well inside.
        assert sanitize(item())["items"][0]["review_required"] is False

    def test_a_drift_inside_the_tolerance_is_not_flagged(self):
        # 220 derived vs 280 stated = 21% drift, under the 35% hard limit.
        out = sanitize(item(kcal_point=280.0, kcal_high=340.0))
        assert "kcal_point" not in out["items"][0]["uncertain_fields"]

    def test_macro_mass_exceeding_portion_mass_is_flagged(self):
        # 50 + 50 + 50 = 150 g of macros in a 100 g portion.
        out = sanitize(item(grams_est=100, protein_g=50, carbs_g=50, fat_g=50))
        assert "grams_est" in out["items"][0]["uncertain_fields"]

    def test_rounding_slack_stops_a_false_flag(self):
        """`grams_est` is itself an estimate and may round independently."""
        assert MACRO_MASS_SLACK > 1.0
        out = sanitize(item(grams_est=100, protein_g=34, carbs_g=34, fat_g=34))
        assert "grams_est" not in out["items"][0]["uncertain_fields"]

    def test_a_band_that_excludes_its_own_point_is_reordered_and_flagged(self):
        out = sanitize(item(kcal_low=400.0, kcal_point=240.0, kcal_high=100.0))
        got = out["items"][0]
        assert got["kcal_low"] <= got["kcal_point"] <= got["kcal_high"]
        assert "kcal_range" in got["uncertain_fields"]
        assert got["review_required"] is True

    def test_the_response_level_flag_summarises_the_items(self):
        clean = sanitize(item())
        assert clean["review_required"] is False
        dirty = sanitize(item(), item(name="Rice", protein_g=90, carbs_g=90, fat_g=90))
        assert dirty["review_required"] is True


class TestDuplicates:
    def test_one_food_listed_twice_becomes_one_item(self):
        """Two entries would be logged twice and double the day's total."""
        out = sanitize(item(), item(name="Dal tadka"))
        assert len(out["items"]) == 1

    def test_matching_ignores_case_and_spacing(self):
        out = sanitize(item(), item(name="  DAL   TADKA  "))
        assert len(out["items"]) == 1

    def test_the_more_confident_reading_is_kept(self):
        out = sanitize(
            item(confidence=0.4, kcal_point=200.0),
            item(confidence=0.9, kcal_point=260.0),
        )
        assert out["items"][0]["kcal_point"] == 260.0

    def test_a_merge_is_surfaced_rather_than_hidden(self):
        """The user should be able to see why the plate looks shorter than
        the photo."""
        out = sanitize(item(), item(name="Dal tadka", confidence=0.9))
        assert "duplicate_merged" in out["items"][0]["uncertain_fields"]
        assert out["review_required"] is True

    def test_similar_but_distinct_dishes_are_not_merged(self):
        """"Dal" and "Dal tadka" are different foods.

        Conservative on purpose: merging two real dishes loses one of them
        from the user's log entirely.
        """
        out = sanitize(item(name="Dal"), item(name="Dal tadka"))
        assert len(out["items"]) == 2


class TestNoUnsupportedClaims:
    #: Medical language the prompt must never ask for, as regexes.
    #:
    #: WHY THESE ARE NOT PLAIN SUBSTRINGS
    #: They were, and `cure` matched `obscured`. It would equally match
    #: `secure` and `procure`. A substring ban on a four-letter English word
    #: fires on ordinary prose, and the fix people reach for is to reword the
    #: prompt around the test -- which degrades the prompt to protect an
    #: assertion, exactly backwards.
    #:
    #: The prefixes are deliberate and stay prefixes: `diagnos` has to cover
    #: diagnose/diagnosis/diagnostic, and `prevent` has to cover prevention.
    #: `\btreat\b` no longer needs the trailing-space hack it used to carry.
    BANNED_MEDICAL: ClassVar[tuple[str, ...]] = (
        r"\bdiagnos",
        r"\bdisease",
        r"\bcure\b",
        r"\btreat\b",
        r"\bprevent",
    )

    def test_the_prompt_asks_for_no_medical_content(self):
        import re

        from app.services.vision import SYSTEM_PROMPT

        low = SYSTEM_PROMPT.lower()
        for banned in self.BANNED_MEDICAL:
            assert not re.search(banned, low), banned

    def test_the_banned_list_still_catches_the_real_words(self):
        """The boundary change must not have quietly disarmed the check."""
        import re

        for phrase, expect in (
            ("this will cure your deficiency", True),
            ("diagnose a condition", True),
            ("prevents disease", True),
            ("treat the patient", True),
            ("the food is obscured", False),
            ("secure the container", False),
            ("procure the ingredients", False),
            ("treatment", False),
        ):
            hit = any(re.search(b, phrase) for b in self.BANNED_MEDICAL)
            assert hit is expect, phrase

    def test_free_text_fields_are_length_bounded(self):
        out = sanitize(item(name="x" * 500, name_local="y" * 500))
        assert len(out["items"][0]["name"]) <= 120
        assert len(out["items"][0]["name_local"]) <= 120

    def test_hidden_ingredients_are_bounded_in_count_and_length(self):
        out = _sanitize(
            {
                "items": [item()],
                "hidden_ingredients": ["z" * 300] * 50,
                "overall_confidence": 0.8,
            }
        )
        assert len(out["hidden_ingredients"]) <= 10
        assert all(len(h) <= 80 for h in out["hidden_ingredients"])

    def test_confidence_is_clamped_to_a_probability(self):
        assert sanitize(item(confidence=9.5))["items"][0]["confidence"] == 1.0
        assert sanitize(item(confidence=-3))["items"][0]["confidence"] == 0.0
        assert _sanitize({"items": [], "overall_confidence": 42})["overall_confidence"] == 1.0


class TestPrivacy:
    def test_a_dropped_identifier_is_logged_without_its_value(self, caplog):
        """A model regression must be visible without logging anybody's dinner."""
        import logging

        with caplog.at_level(logging.WARNING, logger="app.services.vision"):
            sanitize(item(barcode="8906136651951", name="Chocolate bar"))
        text = caplog.text
        assert "identifier" in text.lower()
        assert "8906136651951" not in text
        assert "Chocolate bar" not in text
