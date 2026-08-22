"""The spec for barcode normalisation.

Pure -- no database. The premise: `food_items.barcode` holds 565,839 strings
written by four different sources in four different encodings, plus a quantity
of crowd-sourced text that is not a barcode at all. Normalisation has to make
the first group collide correctly and the second group not collide at all.
"""

from __future__ import annotations

import pytest

from app.services.gtin import (
    check_digit,
    has_valid_check_digit,
    is_restricted,
    normalize_gtin,
    same_product,
)


class TestCheckDigit:
    @pytest.mark.parametrize(
        "payload,expected",
        [
            ("01234567890", 5),      # UPC-A
            ("001234567890", 5),     # same, EAN-13
            ("400638133393", 1),     # real EAN-13
            ("9780306406157"[:-1], 7),
        ],
    )
    def test_computes(self, payload, expected):
        assert check_digit(payload) == expected

    def test_weights_anchor_on_the_right(self):
        """Right-anchoring is what makes one implementation serve all lengths.

        Left-anchored weights give a different digit for the same product at
        two lengths, which would defeat the entire point of normalising.
        """
        upc = "012345678905"
        ean = "0012345678905"
        assert has_valid_check_digit(upc)
        assert has_valid_check_digit(ean)


class TestNormalizeGtin:
    def test_upc_a_and_ean_13_of_one_product_collide(self):
        """THE BUG. Two encodings, one product, two rows that never matched."""
        assert normalize_gtin("012345678905") == normalize_gtin("0012345678905")

    def test_pads_to_fourteen(self):
        assert normalize_gtin("012345678905") == "00012345678905"
        assert len(normalize_gtin("4006381333931")) == 14

    @pytest.mark.parametrize("raw", ["4006381333931", "  4006381333931  ", "4006381-333931"])
    def test_strips_separators_and_whitespace(self, raw):
        assert normalize_gtin(raw) == "04006381333931"

    def test_rejects_bad_check_digit(self):
        """A mistyped scan must not become a confident match."""
        assert normalize_gtin("012345678906") is None
        assert normalize_gtin("4006381333932") is None

    @pytest.mark.parametrize("raw", ["123456789", "1234567", "123456789012345", "1"])
    def test_rejects_non_gs1_lengths(self, raw):
        """Length is checked BEFORE padding.

        Zero-padding a 9-digit fragment to 14 would manufacture a plausible
        GTIN out of a truncated scan -- the confident-collision failure this
        module exists to prevent.
        """
        assert normalize_gtin(raw) is None

    @pytest.mark.parametrize(
        "junk",
        ["", "   ", None, "abc", "n/a", "none", "null", "-", "\x00", "🍫"],
    )
    def test_rejects_junk(self, junk):
        """Open Food Facts's barcode field contains all of this."""
        assert normalize_gtin(junk) is None

    def test_rejects_non_string(self):
        assert normalize_gtin(12345) is None

    def test_rejects_all_zeros(self):
        assert normalize_gtin("00000000") is None

    def test_never_raises_on_arbitrary_input(self):
        """Runs over 565,839 uncontrolled strings during backfill.

        An exception at row 300,000 is a failed migration, not a signal.
        """
        for junk in ["\x00" * 10, "9" * 400, "١٢٣٤٥٦٧٨", "1e5", "-1234567890128"]:
            normalize_gtin(junk)


class TestRestrictedPrefixes:
    @pytest.mark.parametrize("raw", ["0200000000000", "0400000000006"])
    def test_in_store_codes_are_rejected(self, raw):
        """Restricted-circulation codes are unique only inside one retailer.

        Two chains issue the same number for different products, so matching
        on them fabricates cross-retailer collisions out of nothing.
        """
        assert normalize_gtin(raw) is None

    def test_restriction_is_tested_after_padding(self):
        """'02...' and '0002...' are one restricted code at two lengths."""
        assert is_restricted("00000200000000")
        assert is_restricted("00002000000000")

    def test_ordinary_prefixes_pass(self):
        assert not is_restricted("00012345678905")
        assert not is_restricted("04006381333931")


class TestSameProduct:
    def test_matches_across_encodings(self):
        assert same_product("012345678905", "0012345678905")

    def test_different_products_do_not_match(self):
        assert not same_product("012345678905", "4006381333931")

    def test_unknown_never_matches(self):
        """Two unparseable barcodes are not evidence of anything."""
        assert not same_product("garbage", "garbage")
        assert not same_product(None, None)
        assert not same_product("012345678905", None)
