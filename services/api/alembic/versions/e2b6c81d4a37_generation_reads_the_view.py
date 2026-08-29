"""Add exercise_class to programmable_exercises, so generation can read it

Revision ID: e2b6c81d4a37
Revises: d1a4f8c72b60
Create Date: 2026-08-28

WHY
`c9e58a2d41bf` created `programmable_exercises` so that "programmable" was a
thing the database enforced rather than a rule someone had to remember. The
view was created. Generation was never repointed at it.

The consequence was total, and live. `_load_options` kept its raw INNER JOIN
on `exercise_attributes`, which after `b8d47f1c39ae` proves only that a
movement is CLASSIFIED. All 154 classified movements have a NULL rep range,
`prescribed_exercises.rep_min` is NOT NULL, and so every attempt to generate
a programme inserted NULL into a NOT NULL column: a 500 for every user, on
every request, for the entire feature. The test suite stayed green because
its fixture supplies rep ranges that production does not have.

This migration only widens the view. The repointing happens in
`routers/programming.py`, and the reason it needs this at all is that
`exercise_class` was not in the original SELECT -- it is NULL on all 154 rows
today and the generator already falls back to defaults, but leaving it out
would have silently changed set counts and ordering for any row that ever
gets one.

CREATE OR REPLACE VIEW permits appending columns, not reordering or retyping
them, so `exercise_class` goes last.

SAFETY
Replacing a view rewrites no rows and touches no constraint. The old
definition and the new one differ by one appended column, so every existing
reader keeps working.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e2b6c81d4a37"
down_revision: Union[str, Sequence[str], None] = "d1a4f8c72b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VIEW_WITH_CLASS = """
CREATE OR REPLACE VIEW programmable_exercises AS
SELECT
    e.id                    AS exercise_id,
    e.name,
    e.muscle_group,
    e.secondary_muscles,
    e.equipment,
    e.is_compound,
    a.movement_pattern,
    a.movement_detail,
    a.resistance_profile,
    a.is_isolation,
    a.is_unilateral,
    a.default_rep_min,
    a.default_rep_max,
    a.default_rest_seconds,
    a.fatigue_cost,
    a.exercise_class
FROM exercises e
JOIN exercise_attributes a ON a.exercise_id = e.id
WHERE a.default_rep_min IS NOT NULL
  AND a.default_rep_max IS NOT NULL
"""

VIEW_WITHOUT_CLASS = """
CREATE OR REPLACE VIEW programmable_exercises AS
SELECT
    e.id                    AS exercise_id,
    e.name,
    e.muscle_group,
    e.secondary_muscles,
    e.equipment,
    e.is_compound,
    a.movement_pattern,
    a.movement_detail,
    a.resistance_profile,
    a.is_isolation,
    a.is_unilateral,
    a.default_rep_min,
    a.default_rep_max,
    a.default_rest_seconds,
    a.fatigue_cost
FROM exercises e
JOIN exercise_attributes a ON a.exercise_id = e.id
WHERE a.default_rep_min IS NOT NULL
  AND a.default_rep_max IS NOT NULL
"""


def upgrade() -> None:
    op.execute(VIEW_WITH_CLASS)


def downgrade() -> None:
    # Dropping a column needs a full DROP: CREATE OR REPLACE cannot remove one.
    op.execute("DROP VIEW IF EXISTS programmable_exercises")
    op.execute(VIEW_WITHOUT_CLASS)
