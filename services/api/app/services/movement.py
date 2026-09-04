"""Movement classification: the eight patterns, and what has none.

WHY THE PATTERN IS NULLABLE
An eight-pattern taxonomy comes from strength coaching, where it describes
compound lifts: does this session cover a squat, a hinge, a horizontal push,
a vertical pull. Roughly a third of the catalogue is isolation work, and a
lateral raise is not a vertical push. Forcing it into one would put a false
value into a field generation trusts, and generation would then believe it
had covered a pattern it had not.

So `movement_pattern` is NULL for isolation work, and that NULL is an answer:
"this movement does not satisfy a pattern". `is_isolation` is what carries
those rows -- they are selected by target muscle, not by pattern.

    A NULL PATTERN IS NOT A COVERAGE GAP. Generation must never try to fill
    it. Pattern coverage is a question about compounds only; counting a
    curl's missing pattern as a hole to plug is how a session ends up with
    three more isolation exercises nobody asked for.

WHY BOTH VOCABULARIES ARE KEPT
`movement_detail` keeps the nineteen-value vocabulary the catalogue was
curated with. It distinguishes `knee-ext` from `knee-flex`, and `lateral`
from `elbow-flex`, in a way the eight cannot -- and that distinction is what
muscle-targeted selection and later analysis need. Collapsing it to satisfy
an enum would be discarding real information to gain tidiness.

    The EIGHT is what programming reads. The NINETEEN is what selection and
    analysis read.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "MOVEMENT_DETAILS",
    "MOVEMENT_PATTERNS",
    "PATTERN_FOR_DETAIL",
    "RESISTANCE_PROFILES",
    "is_isolation_detail",
    "pattern_for",
]

#: The eight. What a session-coverage question is asked in.
MOVEMENT_PATTERNS: Final[tuple[str, ...]] = (
    "squat",
    "hinge",
    "lunge",
    "h-push",
    "v-push",
    "h-pull",
    "v-pull",
    "core",
    "carry",
)

#: The nineteen the catalogue was curated with.
MOVEMENT_DETAILS: Final[tuple[str, ...]] = (
    "squat",
    "lunge",
    "hinge",
    "h-press",
    "v-press",
    "h-pull",
    "v-pull",
    "lateral",
    "elbow-flex",
    "elbow-ext",
    "knee-ext",
    "knee-flex",
    "calf",
    "abduction",
    "shrug",
    "trunk-flex",
    "anti-ext",
    "anti-rot",
    "pull",
    "carry",
)

#: Where in the range of motion the movement is hardest.
RESISTANCE_PROFILES: Final[tuple[str, ...]] = ("lengthened", "mid", "shortened")

#: detail -> pattern, or None where the movement genuinely satisfies none.
#:
#: `pull` (the Olympic derivatives -- clean, snatch) maps to `hinge` because a
#: power clean is hip-dominant and hinge-derived. The explosive quality is
#: real but it is not a pattern; if it needs to be programmed on, it belongs
#: on its own attribute rather than distorting this one.
PATTERN_FOR_DETAIL: Final[dict[str, str | None]] = {
    "squat": "squat",
    "hinge": "hinge",
    "lunge": "lunge",
    "h-press": "h-push",
    "v-press": "v-push",
    "h-pull": "h-pull",
    "v-pull": "v-pull",
    "trunk-flex": "core",
    "anti-ext": "core",
    "anti-rot": "core",
    "pull": "hinge",
    # A loaded carry is its own pattern -- push, pull, hinge, squat,
    # carry is the classic five. It was dropped when the eight were
    # written and that was an oversight, not a decision: two generator
    # templates ask for it by name, and mapping it to `core` would have
    # made those days prescribe a crunch where a farmer's walk belongs.
    "carry": "carry",
    # No honest pattern. Selected by target muscle instead.
    "elbow-flex": None,
    "elbow-ext": None,
    "lateral": None,
    "calf": None,
    "knee-ext": None,
    "knee-flex": None,
    "shrug": None,
    "abduction": None,
}


def pattern_for(detail: str) -> str | None:
    """The programming pattern for a curated detail, or None if it has none.

    Raises on an unknown detail rather than returning None: "I do not
    recognise this" and "this movement has no pattern" are different facts,
    and collapsing them would let a typo silently become an isolation row.
    """
    if detail not in PATTERN_FOR_DETAIL:
        raise KeyError(
            f"{detail!r} is not one of the {len(MOVEMENT_DETAILS)} curated "
            f"movement details"
        )
    return PATTERN_FOR_DETAIL[detail]


def is_isolation_detail(detail: str) -> bool:
    """Isolation is exactly the set with no pattern.

    Derived rather than stored twice -- the two would drift, and then a row
    could claim to be a compound with no pattern, or an isolation with one.
    """
    return pattern_for(detail) is None
