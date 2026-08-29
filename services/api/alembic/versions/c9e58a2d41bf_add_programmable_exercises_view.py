"""Make "programmable" a thing the database enforces, not a rule to remember

Revision ID: c9e58a2d41bf
Revises: b8d47f1c39ae
Create Date: 2026-08-27

WHY
`b8d47f1c39ae` made `default_rep_min` and `default_rep_max` nullable, because
a movement can be CLASSIFIED long before anyone decides how to prescribe it,
and forcing NOT NULL would have meant inventing a rep range for 154 movements
to satisfy a constraint.

The cost was that `exercise_attributes` no longer guarantees what it used to.
Before, an INNER JOIN was proof a row was programmable. After, it is only
proof the row is classified, and the difference was carried by a comment
saying "generation must also check the rep columns are non-null". That kind
of rule holds for three months and then does not.

So the guarantee is restored as an object rather than an instruction.
Generation selects from `programmable_exercises` and cannot see a row with a
missing rep range, whatever it forgets.

    A view, not a partial index or a trigger, because the failure being
    prevented is "somebody wrote the join by hand and left a predicate out".
    Only something that owns the predicate itself fixes that.

`ck_exattr_rep_range_paired` closes the other half: a half-populated range
(min set, max null) is worse than none, because it looks like data. The two
columns are one fact and are now null or non-null together.

SAFETY
Creating a view touches no rows and no existing column. The CHECK is
validated against 154 rows that all hold NULL in both columns, so it passes
trivially today; it exists for the rows written later.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c9e58a2d41bf"
down_revision: Union[str, Sequence[str], None] = "b8d47f1c39ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VIEW = """
CREATE VIEW programmable_exercises AS
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
    op.execute(VIEW)

    # One fact, two columns. Null or non-null together, never half.
    op.create_check_constraint(
        "ck_exattr_rep_range_paired",
        "exercise_attributes",
        "(default_rep_min IS NULL) = (default_rep_max IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_exattr_rep_range_paired", "exercise_attributes", type_="check"
    )
    op.execute("DROP VIEW IF EXISTS programmable_exercises")
