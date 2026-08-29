"""Restore `carry` to the movement vocabulary

Revision ID: d1a4f8c72b60
Revises: c9e58a2d41bf
Create Date: 2026-08-27

WHY
`b8d47f1c39ae` wrote the eight-pattern vocabulary and dropped the loaded
carry. That was an oversight rather than a decision. Push, pull, hinge,
squat and loaded carry are the classic five; a farmer's walk is not a
variant of anything else in the list.

The cost was not theoretical. Two generator templates ask for `carry` by
name -- `_FULL_BODY_C` and `_LOWER` in `services/programming.py` -- and the
CHECK written here refused the value they need, so every one of the 45
programming API tests failed on it. The tempting repair was to map `carry`
onto `core`, which would have made those days quietly prescribe a crunch
where the template meant a loaded carry: a corrupted programme wearing the
costume of a rename.

WHY BOTH VOCABULARIES AND NOT JUST THE PATTERN
`movement_pattern` is DERIVED from `movement_detail` by
`services/movement.pattern_for`, never stored independently. Adding `carry`
to the pattern CHECK alone would leave no detail that maps to it, so no row
could ever legitimately hold the value -- and any row that did would
disagree with its own derivation. One value in each vocabulary keeps
`pattern_for` total and keeps the two columns consistent by construction.

WHAT THIS DOES NOT FIX
The catalogue holds four carries -- Farmer's Carry, Farmer's Walk, Rickshaw
Carry, Yoke Walk -- and NONE of them is in the 154 curated rows, so none has
an `exercise_attributes` row. Generation inner-joins that table, so a
`carry` slot still selects nothing in production. This migration makes the
value expressible; it does not make those four movements programmable. That
is a separate, deliberate curation step.

SAFETY
Widening a CHECK cannot fail against existing rows: every value the old
constraint permitted, the new one permits. No data is read or written.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d1a4f8c72b60"
down_revision: Union[str, Sequence[str], None] = "c9e58a2d41bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PATTERNS_WITH_CARRY = (
    "movement_pattern IS NULL OR movement_pattern IN "
    "('squat','hinge','lunge','h-push','v-push','h-pull','v-pull','core',"
    "'carry')"
)
PATTERNS_WITHOUT_CARRY = (
    "movement_pattern IS NULL OR movement_pattern IN "
    "('squat','hinge','lunge','h-push','v-push','h-pull','v-pull','core')"
)
DETAILS_WITH_CARRY = (
    "movement_detail IN ('squat','lunge','hinge','h-press','v-press',"
    "'h-pull','v-pull','lateral','elbow-flex','elbow-ext','knee-ext',"
    "'knee-flex','calf','abduction','shrug','trunk-flex','anti-ext',"
    "'anti-rot','pull','carry')"
)
DETAILS_WITHOUT_CARRY = (
    "movement_detail IN ('squat','lunge','hinge','h-press','v-press',"
    "'h-pull','v-pull','lateral','elbow-flex','elbow-ext','knee-ext',"
    "'knee-flex','calf','abduction','shrug','trunk-flex','anti-ext',"
    "'anti-rot','pull')"
)


def upgrade() -> None:
    op.drop_constraint("ck_exattr_movement_pattern", "exercise_attributes", type_="check")
    op.create_check_constraint(
        "ck_exattr_movement_pattern", "exercise_attributes", PATTERNS_WITH_CARRY
    )
    op.drop_constraint("ck_exattr_movement_detail", "exercise_attributes", type_="check")
    op.create_check_constraint(
        "ck_exattr_movement_detail", "exercise_attributes", DETAILS_WITH_CARRY
    )


def downgrade() -> None:
    # Refuse rather than silently discard: narrowing a CHECK past live rows
    # would fail anyway, and failing with an explanation is cheaper to read.
    rows = op.get_bind().execute(
        __import__("sqlalchemy").text(
            "SELECT count(*) FROM exercise_attributes "
            "WHERE movement_pattern = 'carry' OR movement_detail = 'carry'"
        )
    ).scalar()
    if rows:
        raise RuntimeError(
            f"{rows} exercise_attributes row(s) are classified as carries. "
            "Reclassify them before downgrading; the old vocabulary has "
            "nowhere to put a loaded carry."
        )
    op.drop_constraint("ck_exattr_movement_detail", "exercise_attributes", type_="check")
    op.create_check_constraint(
        "ck_exattr_movement_detail", "exercise_attributes", DETAILS_WITHOUT_CARRY
    )
    op.drop_constraint("ck_exattr_movement_pattern", "exercise_attributes", type_="check")
    op.create_check_constraint(
        "ck_exattr_movement_pattern", "exercise_attributes", PATTERNS_WITHOUT_CARRY
    )
