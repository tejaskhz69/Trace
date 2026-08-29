"""Record who classified each movement, so a re-run cannot overwrite a review

Revision ID: d5f18c04e7a3
Revises: a7e2d3b64f19
Create Date: 2026-08-28

THE PROBLEM THIS SOLVES
-----------------------
Running the rule engine over the catalogue today would revert 23 rows that
a human reviewed and corrected in `f3c7a90e15d2` -- every fly, the pec
decks, the face pull, the sissy squat -- back to being compound-slot
eligible. Nothing in the schema said those rows had been looked at, so
nothing could stop it.

THE TIERING, WHICH IS THE SAME ONE THE EVAL SET USES
----------------------------------------------------
    label > weighed > recipe > menu > estimate      (nutrition truth)
    human-reviewed > engine-derived                 (classification)

An engine deriving a pattern is a guess with a rule behind it. A human
reviewing a row is a higher tier of evidence. A LOWER TIER MUST NEVER
SILENTLY OVERWRITE A HIGHER ONE. That is the whole architecture of the eval
set and it applies here unchanged.

WHY PROVENANCE AND NOT A BOOLEAN
--------------------------------
`is_reviewed = true` answers "may I overwrite this". `classified_by` plus
`reviewed_at` also answers "how much of this catalogue does anyone actually
stand behind", which is the more useful number and the one that belongs
next to the coverage figure in /healthz/db. `classified_movements: 154`
says nothing about whether those 154 are trustworthy.

WHICH ROWS ARE MARKED HUMAN, AND WHY THESE
------------------------------------------
The 31 rows a human examined one at a time while resolving the
is_compound/is_isolation disagreement:

  23  Group A -- corrected to isolation with a NULL pattern
   7  Group C -- core work, examined and deliberately LEFT ALONE
   1  JM Press -- examined and deliberately left alone

Group C and the JM Press matter as much as Group A. A review that concluded
"this row is already right" is still a review, and it is exactly the
conclusion an engine re-run would destroy without knowing it had.

Everything else is 'engine'. That is not a criticism of those rows; it is
the honest statement that a rule produced them and no person has checked.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5f18c04e7a3"
down_revision: Union[str, None] = "a7e2d3b64f19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: Group A -- single-joint movements corrected off a compound pattern.
_GROUP_A = (
    "Pec Deck", "Dumbbell Fly", "Incline Dumbbell Fly", "Cable Chest Fly",
    "High-to-Low Cable Fly", "Low-to-High Cable Fly", "Seated Cable Pec Fly",
    "Cable Press-Around", "Svend Press", "Reverse Cable Crossover",
    "Rear Delt Fly", "Reverse Pec Deck", "Face Pull", "Kelso Shrug",
    "Straight-Arm Pulldown", "Dumbbell Pullover", "Machine Pullover",
    "Cable Lat Prayer", "Cable Kickback", "Nordic Curl", "Back Extension",
    "Reverse Hyperextension", "Sissy Squat",
)
#: Group C -- core work, reviewed and correctly left unchanged.
_GROUP_C = (
    "Plank", "Pallof Press", "Hanging Leg Raise", "Ab Wheel Rollout",
    "Cable Crunch", "Machine Crunch", "Rotary Torso",
)
#: Reviewed, ambiguous, deliberately held. Multi-joint but prescribed as an
#: accessory; revisit if a difficulty column ever lands.
_HELD = ("JM Press",)

REVIEWED = _GROUP_A + _GROUP_C + _HELD


def upgrade() -> None:
    op.add_column(
        "exercise_attributes",
        sa.Column(
            "classified_by", sa.Text(), nullable=False,
            server_default="engine",
        ),
    )
    op.add_column(
        "exercise_attributes",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_exattr_classified_by",
        "exercise_attributes",
        "classified_by IN ('engine','human')",
    )
    # A human review has a date; an engine derivation does not.
    op.create_check_constraint(
        "ck_exattr_reviewed_at_matches_provenance",
        "exercise_attributes",
        "(classified_by = 'human') = (reviewed_at IS NOT NULL)",
    )

    op.get_bind().execute(
        sa.text(
            "UPDATE exercise_attributes SET classified_by = 'human',"
            " reviewed_at = now() WHERE exercise_id IN"
            " (SELECT id FROM exercises WHERE name = ANY(:names))"
        ),
        {"names": list(REVIEWED)},
    )

    op.create_index(
        "ix_exattr_classified_by", "exercise_attributes", ["classified_by"]
    )


def downgrade() -> None:
    op.drop_index("ix_exattr_classified_by", table_name="exercise_attributes")
    op.drop_constraint(
        "ck_exattr_reviewed_at_matches_provenance",
        "exercise_attributes", type_="check",
    )
    op.drop_constraint(
        "ck_exattr_classified_by", "exercise_attributes", type_="check"
    )
    op.drop_column("exercise_attributes", "reviewed_at")
    op.drop_column("exercise_attributes", "classified_by")
