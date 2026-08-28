"""Correct 27 movements the catalogue and the classifier disagreed about

Revision ID: f3c7a90e15d2
Revises: e2b6c81d4a37
Create Date: 2026-08-28

WHAT WAS WRONG
--------------
`exercises.is_compound` (the catalogue's own flag) and
`exercise_attributes.is_isolation` (our classification) disagreed on 35 rows:

    SELECT count(*) FROM exercises e
    JOIN exercise_attributes a ON a.exercise_id = e.id
    WHERE e.is_compound = a.is_isolation;    -->  35

34 of those said False/False -- neither compound nor isolation -- and one
(JM Press) said True/True.

THE 35 ARE NOT ONE POPULATION. THEY ARE FOUR.
---------------------------------------------
A blanket fix would have created new defects, so each group is handled
separately and only three of the four are touched here.

GROUP A (23 rows, CORRECTED HERE)
    Genuine single-joint movements carrying a COMPOUND movement_pattern.
    A pec deck was eligible to fill a horizontal-push template slot; a sissy
    squat could fill a squat slot. Set `is_isolation = TRUE` and NULL the
    pattern, which is the representation the design already specifies for
    isolation work.

GROUP B (4 rows, CORRECTED HERE)
    Push-Up, Deficit Push-Up, Bradford Press, Scott Press. Multi-joint, and
    mislabelled the OPPOSITE way -- `is_compound = FALSE` on movements that
    plainly are compounds. Set `is_compound = TRUE`, keep the pattern.

    NOTE: this changes NO generation behaviour. `_fills_slot` reads
    `movement_pattern` and `is_isolation` only; `is_compound` is never
    consulted by the generator. These four were always in their slots and
    stay there. What this fixes is the catalogue's own record, the payload
    the mobile client renders, and four false alarms in the
    `exercise_classify` cross-check that were burying real signal.

GROUP C (7 rows, DELIBERATELY UNTOUCHED)
    Plank, Pallof Press, Hanging Leg Raise, Ab Wheel Rollout, Cable Crunch,
    Machine Crunch, Rotary Torso.

    These are NOT defective. Core work is neither compound nor isolation --
    a Pallof press is anti-rotation, where the movement is the absence of
    movement -- and all seven already carry `movement_pattern = 'core'`,
    which is the correct representation. They appeared in the query only
    because the predicate `is_compound = is_isolation` is over-broad for
    core. The data was right and the query was wrong.

JM PRESS (1 row, DELIBERATELY UNTOUCHED)
    `is_compound = TRUE`, `is_isolation = TRUE`, `movement_pattern = NULL`.

    It already reads as isolation-only to the generator, because that is
    decided by `is_isolation` and the NULL pattern. Flipping `is_compound`
    would therefore change nothing about what gets prescribed -- and would
    destroy a true signal. A JM press IS multi-joint. `is_compound` is the
    only independent opinion in the schema, and the cross-check firing on
    this row is CORRECT BEHAVIOUR, not noise.

    Multi-joint, prescribed as an accessory. Revisit if a difficulty column
    lands, at which point it can honestly become a compound that a beginner
    is not offered.

REVERSIBILITY
-------------
`downgrade()` restores every prior value literally, including each Group A
row's original pattern. Nothing here is destructive.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3c7a90e15d2"
down_revision: Union[str, None] = "e2b6c81d4a37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: (name, the movement_pattern it carried before this migration).
#: Single-joint movements that were filling compound template slots.
GROUP_A: tuple[tuple[str, str], ...] = (
    ("Pec Deck", "h-push"),
    ("Dumbbell Fly", "h-push"),
    ("Incline Dumbbell Fly", "h-push"),
    ("Cable Chest Fly", "h-push"),
    ("High-to-Low Cable Fly", "h-push"),
    ("Low-to-High Cable Fly", "h-push"),
    ("Seated Cable Pec Fly", "h-push"),
    ("Cable Press-Around", "h-push"),
    ("Svend Press", "h-push"),
    ("Reverse Cable Crossover", "h-pull"),
    ("Rear Delt Fly", "h-pull"),
    ("Reverse Pec Deck", "h-pull"),
    ("Face Pull", "h-pull"),
    ("Kelso Shrug", "h-pull"),
    ("Straight-Arm Pulldown", "v-pull"),
    ("Dumbbell Pullover", "v-pull"),
    ("Machine Pullover", "v-pull"),
    ("Cable Lat Prayer", "v-pull"),
    ("Cable Kickback", "hinge"),
    ("Nordic Curl", "hinge"),
    ("Back Extension", "hinge"),
    ("Reverse Hyperextension", "hinge"),
    ("Sissy Squat", "squat"),
)

#: Multi-joint movements the catalogue wrongly flagged as non-compound.
GROUP_B: tuple[str, ...] = (
    "Push-Up",
    "Deficit Push-Up",
    "Bradford Press",
    "Scott Press",
)


def upgrade() -> None:
    conn = op.get_bind()

    for name, _pattern in GROUP_A:
        conn.execute(
            sa.text(
                "UPDATE exercise_attributes SET is_isolation = TRUE,"
                " movement_pattern = NULL, updated_at = now()"
                " WHERE exercise_id IN"
                " (SELECT id FROM exercises WHERE name = :name)"
            ),
            {"name": name},
        )

    for name in GROUP_B:
        conn.execute(
            sa.text(
                "UPDATE exercises SET is_compound = TRUE WHERE name = :name"
            ),
            {"name": name},
        )


def downgrade() -> None:
    conn = op.get_bind()

    for name, pattern in GROUP_A:
        conn.execute(
            sa.text(
                "UPDATE exercise_attributes SET is_isolation = FALSE,"
                " movement_pattern = :pattern, updated_at = now()"
                " WHERE exercise_id IN"
                " (SELECT id FROM exercises WHERE name = :name)"
            ),
            {"name": name, "pattern": pattern},
        )

    for name in GROUP_B:
        conn.execute(
            sa.text(
                "UPDATE exercises SET is_compound = FALSE WHERE name = :name"
            ),
            {"name": name},
        )
