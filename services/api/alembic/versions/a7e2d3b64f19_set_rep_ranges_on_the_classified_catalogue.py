"""Set rep ranges on the classified catalogue

Revision ID: a7e2d3b64f19
Revises: f3c7a90e15d2
Create Date: 2026-08-28

WHY THIS IS THE LAST THING BLOCKING GENERATION
----------------------------------------------
`default_rep_min` and `default_rep_max` were NULL on all 154 classified
movements. `programmable_exercises` requires them non-null, so the view was
empty and generation returned 422 for every request. This fills them.

A REP RANGE IS A PRESCRIPTION, NOT A MEASUREMENT
------------------------------------------------
Every value here is JUDGEMENT, and `docs/11-constants-and-evidence.md`
records it as such. There is no study establishing the correct rep range for
a cable lateral raise. The literature supports a broad claim -- hypertrophy
is similar across a wide loading range when sets are taken near failure --
and that claim underdetermines any specific range. We choose, and we say we
chose.

THE BASE RULE: DERIVED CLASS, WITH is_isolation TESTED FIRST
------------------------------------------------------------
    isolation                       -> 10-15   (68 rows)
    machine/smith equipment         ->  8-12   (15 rows)
    everything else                 ->  6-10   (71 rows)

Note the ORDER. `exercise_classify.py` tests equipment first, which sends
eleven machine-based isolations -- leg extension, lying leg curl, the calf
raises, machine lateral raise -- down the "machine" branch and hands a leg
extension a machine chest press's prescription. Testing `is_isolation` first
puts them where they belong. That precedence fix is the reason this
migration does not simply reuse `CLASS_DEFAULTS`.

FIVE OVERRIDES, AND WHY
-----------------------
1. CORE (6 rows) -> 10-15.
   The derived rule has no branch for core, because core is neither
   isolation nor a modality. Five of the seven core rows derive to
   "compound" and would be prescribed for SIX REPS -- a cable crunch for
   six reps is not a prescription anyone would write. Core is accessory
   work and is ranged like isolation. This is the same "the binary does not
   cover core" gap that `f3c7a90e15d2` found in is_compound/is_isolation.

2. PLANK -> LEFT NULL, DELIBERATELY.
   A plank is an isometric hold measured in SECONDS. There is no honest rep
   range for it, and inventing one would be exactly the fabricated number
   this project refuses elsewhere. The schema has no way to express "held
   for time", so the row stays unprescribable until it does. Cost: the core
   slot drops from 7 candidates to 6, which still fills.

3. OLYMPIC LIFTS (3 rows) -> 3-5.
   Power Clean, Power Snatch, Hang Clean. These are speed-dependent; rep
   quality collapses under fatigue in a way that a 6-10 prescription would
   actively cause. SEPARATELY FLAGGED: these arguably should not be in a
   beginner's candidate pool at all. That is a difficulty-gate problem, not
   a rep-range one, and no difficulty column exists.

4. FLOOR-PULL DEADLIFTS (4 rows) -> 5-8.
   Conventional, Sumo, Trap Bar, Deficit. The technical crux is holding a
   loaded position, and it is the first thing to go as reps accumulate.
   This is a programming argument about technique, not a medical one.
   Romanian and dumbbell variants keep 6-10: less spinal loading, and they
   are hinge accessories rather than floor pulls. The specialty variants
   (Jefferson, Dimel, Rack Pull) also keep the default -- Dimel deadlifts
   are conventionally a HIGH-rep speed movement, so blanket-capping the
   whole "deadlift" name family would have been wrong.

5. CALVES (4 rows) -> 12-20.
   The loaded range of motion is a few centimetres, and at low reps the
   limiting factor is ankle tolerance and balance rather than the muscle.

REVERSIBILITY
-------------
`downgrade()` sets both columns back to NULL on all 154 rows, which is
their true prior state. Nothing is lost.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7e2d3b64f19"
down_revision: Union[str, None] = "f3c7a90e15d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLYMPIC = ("Power Clean", "Power Snatch", "Hang Clean")
FLOOR_PULLS = (
    "Conventional Deadlift",
    "Sumo Deadlift",
    "Trap Bar Deadlift",
    "Deficit Deadlift",
)
CALVES = (
    "Standing Calf Raise",
    "Seated Calf Raise",
    "Leg Press Calf Raise",
    "Tibialis Raise",
)
TIME_BASED = ("Plank",)


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Base rule. `is_isolation` is tested BEFORE equipment, on purpose.
    conn.execute(
        sa.text(
            """
            UPDATE exercise_attributes a
               SET default_rep_min = CASE
                       WHEN a.is_isolation THEN 10
                       WHEN e.equipment IN ('machine','smith') THEN 8
                       ELSE 6 END,
                   default_rep_max = CASE
                       WHEN a.is_isolation THEN 15
                       WHEN e.equipment IN ('machine','smith') THEN 12
                       ELSE 10 END,
                   updated_at = now()
              FROM exercises e
             WHERE e.id = a.exercise_id
            """
        )
    )

    # 2. Core is neither isolation nor a modality; the base rule has no
    #    branch for it and would prescribe a cable crunch for six reps.
    conn.execute(
        sa.text(
            "UPDATE exercise_attributes SET default_rep_min = 10,"
            " default_rep_max = 15, updated_at = now()"
            " WHERE movement_pattern = 'core'"
        )
    )

    # 3-5. Named overrides.
    for names, lo, hi in (
        (OLYMPIC, 3, 5),
        (FLOOR_PULLS, 5, 8),
        (CALVES, 12, 20),
    ):
        conn.execute(
            sa.text(
                "UPDATE exercise_attributes SET default_rep_min = :lo,"
                " default_rep_max = :hi, updated_at = now()"
                " WHERE exercise_id IN"
                " (SELECT id FROM exercises WHERE name = ANY(:names))"
            ),
            {"lo": lo, "hi": hi, "names": list(names)},
        )

    # 6. Isometric holds get NO range. A plank is measured in seconds, and
    #    a fabricated rep range is worse than an unprescribable row.
    conn.execute(
        sa.text(
            "UPDATE exercise_attributes SET default_rep_min = NULL,"
            " default_rep_max = NULL, updated_at = now()"
            " WHERE exercise_id IN"
            " (SELECT id FROM exercises WHERE name = ANY(:names))"
        ),
        {"names": list(TIME_BASED)},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE exercise_attributes SET default_rep_min = NULL,"
            " default_rep_max = NULL, updated_at = now()"
        )
    )
