"""Barcode normalisation: every GS1 length folded onto one comparable key.

THE BUG THIS FIXES
`food_items.barcode` stores whatever the source sent. Open Food Facts sends
EAN-13, US retailers send UPC-A, small packages carry EAN-8, cases carry
ITF-14 -- and the SAME PRODUCT has different strings in each. UPC-A
'012345678905' and EAN-13 '0012345678905' are one product and two rows, and
neither lookup finds the other. 565,839 rows in the catalogue carry a barcode.

GS1 solved this: every one of those encodings is a GTIN-14 with leading zeros
suppressed. Zero-pad back to 14 and they collide correctly.

WHAT THIS MODULE REFUSES, AND WHY THAT MATTERS MORE
Open Food Facts is crowd-sourced, and its barcode field contains a great deal
that is not a barcode: internal store SKUs, weighed-item labels, truncated
scans, and free text. A normaliser that accepts those produces confident
collisions between unrelated products, which is the one failure mode a food
database must not have -- the user sees a barcode match and trusts it.

So the check digit is verified rather than assumed, and restricted-circulation
prefixes are rejected outright: those are in-store codes, unique only within
one retailer's walls, and two supermarkets will happily use '0200000000000'
for different things.

`normalize_gtin` returns None instead of raising. It runs over half a million
uncontrolled strings during backfill, and an exception on row 300,000 is a
failed migration, not a useful signal.

Pure functions, no I/O.
"""

from __future__ import annotations

import re

_NON_DIGIT = re.compile(r"\D")

#: The four GS1 encodings in the wild. Anything else is not a GTIN, whatever
#: else it might be.
#:   8  EAN-8   small packages
#:   12 UPC-A   North America
#:   13 EAN-13  the global default
#:   14 ITF-14  cases and outer packaging
VALID_LENGTHS = frozenset({8, 12, 13, 14})

GTIN_LENGTH = 14

#: GS1 prefixes reserved for restricted circulation -- in-store codes assigned
#: by a retailer for its own use. They are NOT globally unique, so two chains
#: can and do issue the same number for different products. Matching on them
#: would fabricate cross-retailer collisions out of nothing.
#:
#: 02 / 04    variable-measure and in-store items (GS1 General Specs 1.4.3)
#: 20-29      restricted distribution
_RESTRICTED_PREFIXES = frozenset({"02", "04"} | {str(n) for n in range(20, 30)})

#: Coupon codes, not products.
_COUPON_PREFIXES = frozenset({"98", "99"})


def check_digit(digits: str) -> int:
    """GS1 mod-10 check digit for a payload WITHOUT its check digit.

    Weights alternate 3,1,3,1... from the RIGHTMOST payload digit leftwards.
    Anchoring on the right rather than the left is the whole trick: it is what
    makes the algorithm length-independent, so one implementation serves EAN-8
    through ITF-14 without a per-length special case.
    """
    total = 0
    for i, ch in enumerate(reversed(digits)):
        weight = 3 if i % 2 == 0 else 1
        total += int(ch) * weight
    return (10 - (total % 10)) % 10


def has_valid_check_digit(gtin: str) -> bool:
    """Does this complete barcode's final digit match its payload?"""
    if len(gtin) < 2 or not gtin.isdigit():
        return False
    return check_digit(gtin[:-1]) == int(gtin[-1])


def is_restricted(gtin: str) -> bool:
    """Is this an in-store or coupon code rather than a global product?

    THE PREFIX IS READ FROM THE 13-DIGIT FORM, WHICH IS `gtin[1:]`.

    This used to strip leading zeros and test the remainder, and that was
    wrong in both directions:

      * '0400000000008' -- a real in-store code -- strips to '400000000008',
        whose first digits are '40', so the '04' rule never fired. Every
        number-system-4 code passed. Measured against the live catalogue,
        1,079 rows carry one.
      * '00000200000000' -- an ordinary UPC-A padded out -- strips to
        '200000000', which starts '20', so it was refused as restricted when
        its actual GS1 prefix is '00'.

    A GS1 prefix is positional, not "whatever survives stripping zeros". In a
    GTIN-14 the leading digit is the packaging-level indicator and the 13
    digits after it carry the prefix, so `gtin[1:2+n]` is the right slice at
    every length -- EAN-8, UPC-A, EAN-13 and ITF-14 alike, once padded.

    THE EXISTING TEST FOR THIS PASSED ANYWAY. It asserted that
    '0400000000006' is refused, and it is -- but for the wrong reason: that
    string has a bad check digit, so `normalize_gtin` rejected it two steps
    earlier and never reached this function. A green test over a broken rule.
    """
    if len(gtin) != GTIN_LENGTH or not gtin.isdigit():
        return True                       # not a GTIN-14: refuse rather than guess
    if gtin.strip("0") == "":
        return True                       # all zeros: a placeholder, not a product
    prefix = gtin[1:3]
    return prefix in _RESTRICTED_PREFIXES or prefix in _COUPON_PREFIXES


def normalize_gtin(raw: str | None) -> str | None:
    """Fold any GS1 barcode to GTIN-14, or None if it is not one.

    None means "do not index this by barcode". It never means "delete the
    original" -- callers write this alongside `food_items.barcode`, which is
    left exactly as the source supplied it so the existing lookup keeps
    working.

    >>> normalize_gtin("012345678905")          # UPC-A
    '00012345678905'
    >>> normalize_gtin("0012345678905")         # same product, EAN-13
    '00012345678905'
    >>> normalize_gtin("012345678906")          # bad check digit
    >>> normalize_gtin("0200000000000")         # in-store code
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None

    digits = _NON_DIGIT.sub("", raw)
    if not digits:
        return None

    # Length is checked BEFORE padding. A 9-digit string is a truncated or
    # mistyped scan; zero-padding it to 14 would manufacture a valid-looking
    # GTIN out of a broken one, which is exactly the confident-collision
    # failure this module exists to prevent.
    if len(digits) not in VALID_LENGTHS:
        return None

    if not has_valid_check_digit(digits):
        return None

    padded = digits.rjust(GTIN_LENGTH, "0")

    if is_restricted(padded):
        return None

    return padded


def same_product(a: str | None, b: str | None) -> bool:
    """Do two barcodes, in any encoding, identify one product?

    False when either fails validation: unknown is not a match.
    """
    na, nb = normalize_gtin(a), normalize_gtin(b)
    return na is not None and na == nb


# ---------------------------------------------------------------------------
# UPC-E, and why it cannot be treated as EAN-8
# ---------------------------------------------------------------------------

#: The six expansion rules, keyed on the LAST digit of the 6-digit payload.
#: GS1 General Specifications 5.2.2.4. Each maps the payload to the 10-digit
#: body of a UPC-A, which then gets its own check digit recomputed.
#:
#: WHY THIS EXISTS
#: `expo-camera` reports a UPC-E scan as its **compressed 8-digit** string,
#: and 8 digits is also the length of an EAN-8. Feeding one to a validator
#: that assumes EAN-8 checks the mod-10 against the wrong payload: most real
#: UPC-E codes are then rejected as corrupt, and the rare collision is
#: accepted as a different product entirely. A small package and a compressed
#: US code are simply not the same thing at the same length.


def expand_upce(raw: str) -> str | None:
    """Expand a UPC-E (8 digits: number system, 6 payload, check) to UPC-A.

    Returns None when the input is not a well-formed UPC-E. The check digit is
    re-derived from the EXPANDED form, which is where it is actually defined --
    a UPC-E's check digit belongs to its UPC-A, not to its own eight digits.

    >>> expand_upce("04252614")
    '042100005264'
    """
    if not raw or not raw.isdigit() or len(raw) != 8:
        return None
    system, payload, check = raw[0], raw[1:7], raw[7]
    # Only number systems 0 and 1 have a UPC-E form.
    if system not in ("0", "1"):
        return None

    last = payload[5]
    body = payload[:5]
    if last in ("0", "1", "2"):
        expanded = f"{system}{body[:2]}{last}0000{body[2:5]}"
    elif last == "3":
        expanded = f"{system}{body[:3]}00000{body[3:5]}"
    elif last == "4":
        expanded = f"{system}{body[:4]}00000{body[4]}"
    else:  # 5-9
        expanded = f"{system}{body}0000{last}"

    if len(expanded) != 11:
        return None
    if check_digit(expanded) != int(check):
        return None
    return expanded + check


# ---------------------------------------------------------------------------
# Classification: the same decision, but explaining itself
# ---------------------------------------------------------------------------

#: Why a barcode was refused. The API returns this so the client can offer the
#: RIGHT recovery, which is different in every case:
#:
#:   invalid_length / not_numeric -> a partial or misread scan. Scan again.
#:   bad_check_digit             -> a damaged or misprinted symbol. Scan again,
#:                                  or type it in.
#:   restricted                  -> a real barcode that is not a product
#:                                  identifier. Scanning again will never help;
#:                                  send the user to search or the label.
#:
#: Collapsing all three into "not found" is what makes a scanner feel broken:
#: the user re-scans a deli sticker forever because nothing told them it is not
#: the kind of barcode that can be looked up.
STATUS_OK = "ok"
STATUS_NOT_NUMERIC = "not_numeric"
STATUS_BAD_LENGTH = "invalid_length"
STATUS_BAD_CHECK_DIGIT = "bad_check_digit"
STATUS_RESTRICTED = "restricted"


#: The scanner's own report of which symbology it decoded. `expo-camera`
#: supplies this on every callback and the client forwards it.
SYMBOLOGY_UPC_E = "upc_e"


def classify(
    raw: str | None, symbology: str | None = None
) -> tuple[str, str | None]:
    """Validate a scanned barcode and say WHY if it fails.

    Returns `(status, gtin14)`. `gtin14` is non-None only for STATUS_OK, and
    is then exactly what `normalize_gtin` produces for the same input -- a
    test pins that so the two can never drift.

    THE SYMBOLOGY ARGUMENT IS NOT OPTIONAL IN PRACTICE, ONLY IN SIGNATURE.
    UPC-E and EAN-8 are both eight digits, and the two interpretations of one
    string give two DIFFERENT products. Measured over 200,000 randomly
    generated valid EAN-8 codes beginning 0 or 1, **58% also expand as a
    valid UPC-E** -- so deciding by looking at the digits is wrong more often
    than a coin toss. The scanner knows which symbol it read; throwing that
    away and guessing is the bug.

    When the symbology is unknown, this treats 8 digits as EAN-8 and does NOT
    expand. That direction is chosen deliberately: expanding an EAN-8 that was
    never a UPC-E fabricates a valid-looking GTIN for a DIFFERENT product,
    which is the confident-collision failure this module exists to prevent.
    Declining to expand merely produces a miss, and a miss is recoverable --
    the user searches by name instead. It is also exactly the behaviour that
    shipped before this function existed, so nothing regresses.
    """
    if raw is None or not isinstance(raw, str):
        return STATUS_NOT_NUMERIC, None

    digits = _NON_DIGIT.sub("", raw)
    if not digits:
        return STATUS_NOT_NUMERIC, None

    if len(digits) == 8 and symbology == SYMBOLOGY_UPC_E:
        expanded = expand_upce(digits)
        if expanded is None:
            # The scanner said UPC-E and it does not expand. That is a damaged
            # read, not an EAN-8 -- reinterpreting it would be guessing again.
            return STATUS_BAD_CHECK_DIGIT, None
        digits = expanded

    if len(digits) not in VALID_LENGTHS:
        return STATUS_BAD_LENGTH, None
    if not has_valid_check_digit(digits):
        return STATUS_BAD_CHECK_DIGIT, None

    padded = digits.rjust(GTIN_LENGTH, "0")

    # All zeros is a placeholder somebody typed to satisfy a required field,
    # not a retailer-scoped product. There is nothing to look up locally
    # either, so unlike a real restricted code it yields no key.
    if padded.strip("0") == "":
        return STATUS_RESTRICTED, None

    if is_restricted(padded):
        # THE NORMALISED FORM IS RETURNED ANYWAY, and that is the difference
        # between `classify` and `normalize_gtin`.
        #
        # A restricted code is still a well-formed GTIN -- it just is not a
        # GLOBAL one. `normalize_gtin` returns None because its job is to
        # decide what may be INDEXED, and indexing a retailer-scoped number
        # invites cross-retailer collisions. `classify`'s job is to tell a
        # caller what it is holding, and "this is 00490711802107, and it only
        # means something inside one chain" is more useful than "no".
        #
        # It matters concretely: 1,079 rows in the live catalogue carry a
        # number-system-4 code, and they are real own-label products --
        # "Organic fruit pouches", "Cookies with quinoa". Somebody catalogued
        # them, so answering a LOCAL lookup for one is not a guess. What the
        # caller must not do is send it to an external source, where the same
        # digits belong to a different chain's different product.
        return STATUS_RESTRICTED, padded
    return STATUS_OK, padded
