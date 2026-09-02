"""The spec for barcode normalisation.

Pure -- no database. The premise: `food_items.barcode` holds 565,839 strings
written by four different sources in four different encodings, plus a quantity
of crowd-sourced text that is not a barcode at all. Normalisation has to make
the first group collide correctly and the second group not collide at all.
"""

from __future__ import annotations

import pytest

from app.services.gtin import (
    STATUS_BAD_CHECK_DIGIT,
    STATUS_BAD_LENGTH,
    STATUS_NOT_NUMERIC,
    STATUS_OK,
    STATUS_RESTRICTED,
    check_digit,
    classify,
    expand_upce,
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
    @pytest.mark.parametrize(
        "raw,label",
        [
            ("0200000000004", "02 in-store, variable measure"),
            ("0400000000008", "04 in-store"),
            ("2000000000008", "20 restricted distribution"),
            ("2900000000001", "29 restricted distribution, top of range"),
            ("9800000000007", "98 coupon"),
            ("9900000000004", "99 coupon"),
            ("0490711802107", "a real number-system-4 own-label code"),
        ],
    )
    def test_in_store_codes_are_not_indexable(self, raw, label):
        """Restricted-circulation codes are unique only inside one retailer.

        Two chains issue the same number for different products, so INDEXING
        on them fabricates cross-retailer collisions out of nothing.

        EVERY VECTOR HERE CARRIES A CORRECT CHECK DIGIT, and that is the point
        of the rewrite. The version of this test that shipped used
        '0400000000006', whose check digit is wrong -- so `normalize_gtin`
        refused it two steps before the restricted rule was ever consulted.
        The test was green and the rule underneath it did not work: every
        number-system-4 code passed, and 1,079 of them are in the live
        catalogue.
        """
        assert check_digit(raw[:-1]) == int(raw[-1]), (
            f"{label}: fixture has a bad check digit, so this test would pass "
            "without exercising the restricted rule at all"
        )
        assert normalize_gtin(raw) is None

    def test_the_prefix_is_positional_not_whatever_survives_stripping_zeros(self):
        """A GS1 prefix lives at a fixed offset in the 13-digit form.

        The old implementation did `gtin.lstrip('0')` and tested the
        remainder, which is wrong in both directions:

          '00400000000008' -> strips to '400000000008', starts '40', so the
                              '04' rule never fired.
          '00000200000000' -> strips to '200000000', starts '20', so an
                              ordinary UPC-A was refused as restricted.
        """
        # Restricted, and must stay restricted once padded to 14.
        assert is_restricted("00200000000000")   # 0200000000000 padded
        assert is_restricted("00400000000008")   # 0400000000008 padded
        # NOT restricted: its GS1 prefix is '00'. The digits '2' and '0' appear
        # further in, which is not the same thing as a prefix.
        assert not is_restricted("00000200000000")

    def test_ordinary_prefixes_pass(self):
        assert not is_restricted("00012345678905")   # prefix 00, UPC-A
        assert not is_restricted("04006381333931")   # prefix 40, Germany
        assert not is_restricted("08906136651951")   # prefix 89, India
        assert not is_restricted("09780306406157")   # prefix 97, ISBN

    def test_a_restricted_code_still_normalises_for_a_local_lookup(self):
        """`classify` and `normalize_gtin` disagree here ON PURPOSE.

        `normalize_gtin` answers "may this be indexed" -- no, because the
        number is retailer-scoped. `classify` answers "what am I holding" --
        a well-formed GTIN that only means something inside one chain. The
        endpoint uses the second to look in OUR catalogue, where 1,079 real
        own-label products live, while never sending it to an external source.
        """
        status, g = classify("0490711802107")
        assert status == STATUS_RESTRICTED
        assert g == "00490711802107"
        assert normalize_gtin("0490711802107") is None


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


# ---------------------------------------------------------------- classify


def _vectors() -> list[dict]:
    """The shared contract table, also consumed by the mobile test.

    One table, two implementations. A drift between the device's validator and
    the server's would mean the phone accepts what the server refuses, which
    presents to a user as a mystery error rather than as a failing test.
    """
    import json
    from pathlib import Path

    path = Path(__file__).parent / "fixtures" / "barcode_vectors.json"
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


class TestClassifyContract:
    @pytest.mark.parametrize("case", _vectors(), ids=lambda c: c["why"][:48])
    def test_matches_the_shared_vector_table(self, case):
        status, g = classify(case["raw"], case["symbology"])
        assert status == case["status"]
        assert g == case["gtin14"]

    def test_the_table_covers_every_status(self):
        """A vector table missing a status is a test suite with a blind spot."""
        seen = {c["status"] for c in _vectors()}
        assert seen == {
            STATUS_OK,
            STATUS_NOT_NUMERIC,
            STATUS_BAD_LENGTH,
            STATUS_BAD_CHECK_DIGIT,
            STATUS_RESTRICTED,
        }

    @pytest.mark.parametrize(
        "case",
        [c for c in _vectors() if c["symbology"] is None],
        ids=lambda c: c["why"][:48],
    )
    def test_classify_and_normalize_agree_when_there_is_no_symbology(self, case):
        """`classify(...) == OK` must mean exactly `normalize_gtin(...) is not None`.

        Two functions answering the same question differently is how a scan
        resolves to a product the backfill decided not to index.

        RESTRICTED IS THE ONE DELIBERATE ASYMMETRY, and it is not a
        disagreement about validity: `normalize_gtin` returns None because the
        code must not be INDEXED, while `classify` still hands back the key so
        a LOCAL lookup can answer for the 1,079 own-label rows we already
        hold. Both refuse to treat it as a global identifier.
        """
        status, g = classify(case["raw"], None)
        normalised = normalize_gtin(case["raw"])
        if status == STATUS_OK:
            assert normalised == g
        else:
            assert normalised is None

    def test_they_diverge_on_upce_because_only_one_of_them_is_told(self):
        """`normalize_gtin` has no symbology argument, and must not grow one.

        It runs over catalogue strings during backfill, where nothing recorded
        which symbol was scanned. `classify` runs at the camera, where the
        scanner reports it. Same digits, different information available,
        legitimately different answers -- and the alternative is `classify`
        guessing, which measured worse than a coin toss.
        """
        raw = "24252614"
        # As an EAN-8 (all the backfill can know) this is valid.
        assert normalize_gtin(raw) == "00000024252614"
        # The scanner said UPC-E, and it does not expand: a damaged read.
        assert classify(raw, "upc_e") == (STATUS_BAD_CHECK_DIGIT, None)
        # With no symbology, classify falls back to the EAN-8 reading and the
        # two agree again.
        assert classify(raw, None) == (STATUS_OK, "00000024252614")


class TestUpcE:
    """UPC-E and EAN-8 share a length and mean different things."""

    @pytest.mark.parametrize(
        "compressed,expanded",
        [
            ("04252614", "042100005264"),
            ("01234565", "012345000065"),
            ("12345670", "123456000070"),
        ],
    )
    def test_expands_to_upc_a(self, compressed, expanded):
        assert expand_upce(compressed) == expanded
        assert has_valid_check_digit(expanded)

    def test_the_check_digit_belongs_to_the_expanded_form(self):
        """A UPC-E's check digit is defined on its UPC-A, not on its 8 digits.

        Validating the compressed form as if it were an EAN-8 is why UPC-E
        scans used to be rejected as corrupt.
        """
        assert expand_upce("04252614") is not None
        # ...and the same eight digits fail an EAN-8 check.
        assert not has_valid_check_digit("04252614")

    @pytest.mark.parametrize("system", ["2", "3", "7", "9"])
    def test_only_number_systems_0_and_1_have_a_upce_form(self, system):
        assert expand_upce(system + "4252614"[1:]) is None

    def test_symbology_decides_and_the_digits_do_not(self):
        """The measured reason `classify` takes a symbology argument.

        Over 200,000 randomly generated valid EAN-8 codes beginning 0 or 1,
        58% ALSO expand as a valid UPC-E. Guessing from the digits is worse
        than a coin toss, and the two readings name different products.
        """
        assert classify("04252614", "upc_e") == (STATUS_OK, "00042100005264")
        # Same string, scanner said EAN-8: not expanded, and it is not a
        # valid EAN-8 either.
        assert classify("04252614", "ean8")[0] == STATUS_BAD_CHECK_DIGIT

    def test_unknown_symbology_declines_to_expand(self):
        """The safe direction is a MISS, not a wrong product.

        Expanding an EAN-8 that was never a UPC-E fabricates a valid-looking
        GTIN for a different product, and the user believes it. Declining
        merely sends them to search by name.
        """
        assert classify("04252614", None)[0] == STATUS_BAD_CHECK_DIGIT

    def test_a_upce_the_scanner_named_but_that_will_not_expand_is_a_bad_read(self):
        assert classify("24252614", "upc_e") == (STATUS_BAD_CHECK_DIGIT, None)


class TestClassifyRefusals:
    """Each refusal names a DIFFERENT recovery, which is the point of them."""

    @pytest.mark.parametrize("raw", ["", "abc", "n/a", None, "🍫"])
    def test_not_numeric(self, raw):
        assert classify(raw)[0] == STATUS_NOT_NUMERIC

    @pytest.mark.parametrize("raw", ["12345", "0123456789", "012345678901234", "1"])
    def test_invalid_length(self, raw):
        assert classify(raw)[0] == STATUS_BAD_LENGTH

    def test_six_digits_is_not_a_barcode(self):
        """The endpoint used to accept 6-to-14 digits and look them up.

        There is no 6-digit GTIN. Every one of those was a truncated read that
        still cost two external HTTP round trips.
        """
        assert classify("123456")[0] == STATUS_BAD_LENGTH

    def test_bad_check_digit(self):
        assert classify("012345678906")[0] == STATUS_BAD_CHECK_DIGIT

    def test_restricted_is_not_retryable_in_spirit(self):
        """A restricted code is well-formed and will never resolve globally.

        The endpoint turns this into `retryable: false`, because telling the
        user to scan it again is how they rescan a deli sticker forever.
        """
        status, g = classify("0200000000004")
        assert status == STATUS_RESTRICTED
        assert g == "00200000000004"

    def test_never_raises_on_arbitrary_input(self):
        for junk in ["\x00" * 10, "9" * 400, "١٢٣٤٥٦٧٨", "1e5", "-1234567890128", 12345]:
            classify(junk)  # type: ignore[arg-type]
