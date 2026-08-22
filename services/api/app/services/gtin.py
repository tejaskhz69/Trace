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
_RESTRICTED_PREFIXES = ("02", "04") + tuple(str(n) for n in range(20, 30))

#: Coupon codes, not products.
_COUPON_PREFIXES = ("98", "99")


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

    Tested on the GTIN-14 form's significant digits -- i.e. after the leading
    zeros that padding added -- because '0002000000000' and '02000000000' are
    the same restricted code wearing different lengths.
    """
    significant = gtin.lstrip("0")
    if not significant:
        return True                       # all zeros: a placeholder, not a product
    return significant.startswith(_RESTRICTED_PREFIXES + _COUPON_PREFIXES)


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
