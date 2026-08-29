"""Give movement pattern and resistance profile a real home

Revision ID: b8d47f1c39ae
Revises: a7c31d9b6e02
Create Date: 2026-08-27

WHAT THIS IS FOR
The movement pattern and resistance profile for the 154 curated movements
lived in `exercises.aliases`, so they would be searchable without new
columns. An alias list is the search index, so the consequence was that
searching "mid" returned 58 unrelated movements and "squat" returned the leg
press. The aliases were cleaned; this gives the data somewhere to go.

THE PATTERN VOCABULARY CHANGES, AND SHRINKS TO NULLABLE
Before: eight NOT NULL values built for compound lifts, including a catch-all
`isolation`. After: eight values and NULL.

    squat  hinge  lunge  h-push  v-push  h-pull  v-pull  core

Roughly 45 of the 154 movements get NULL, and that is the point. A lateral
raise is not a vertical push, and an `isolation` pattern value is a category
error -- it answers a question ("which pattern does this satisfy?") that has
no true answer for a curl. NULL says so, and `is_isolation` is what carries
those rows into a session, by target muscle rather than by pattern.

`ck_exattr_isolation_matches_pattern` enforces `(pattern IS NULL) =
is_isolation`, because the two are derived from one fact and would otherwise
drift into a row claiming to be a compound with no pattern -- which
generation would read as a coverage gap and try to fill.

THE NINETEEN ARE KEPT TOO, IN `movement_detail`
They separate knee-ext from knee-flex and lateral from elbow-flex in ways the
eight cannot, and that is what muscle-targeted selection needs. The eight are
what programming reads; the nineteen are what selection and analysis read.

THREE COLUMNS BECOME NULLABLE, ON PURPOSE
`default_rep_min`, `default_rep_max` and `exercise_class` were NOT NULL,
which meant no movement could be CLASSIFIED without also inventing a rep
range for it -- the exact thing this table's docstring refuses to do.
Classification and prescription are different facts arriving at different
times. Generation must now require the rep columns non-null as well as
requiring the row; an inner join alone no longer protects it.

`exercise_class` is superseded by `is_isolation` plus `exercises.equipment`
and is left unpopulated. It is not dropped here because dropping a column is
the one edit that cannot be undone by a downgrade.

SAFETY
`exercise_attributes` holds zero rows, which is why NOT NULL columns can be
added without a default and constraints can be replaced outright. Verified
before writing this. No other table is touched, and nothing is backfilled.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d47f1c39ae"
down_revision: Union[str, Sequence[str], None] = "a7c31d9b6e02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PATTERNS = ("squat", "hinge", "lunge", "h-push", "v-push", "h-pull", "v-pull", "core")
DETAILS = (
    "squat", "lunge", "hinge", "h-press", "v-press", "h-pull", "v-pull",
    "lateral", "elbow-flex", "elbow-ext", "knee-ext", "knee-flex", "calf",
    "abduction", "shrug", "trunk-flex", "anti-ext", "anti-rot", "pull",
)
PROFILES = ("lengthened", "mid", "shortened")


def _in_list(column: str, values: Sequence[str]) -> str:
    joined = ",".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    # A migration that assumes an empty table should say so out loud rather
    # than corrupting a populated one. Cheap refusal beats a clever default.
    rows = op.get_bind().execute(
        sa.text("SELECT count(*) FROM exercise_attributes")
    ).scalar_one()
    if rows:
        raise RuntimeError(
            f"exercise_attributes holds {rows} rows; this migration adds "
            f"NOT NULL columns without defaults and replaces the pattern "
            f"vocabulary. Write a backfill before running it."
        )

    op.add_column(
        "exercise_attributes",
        sa.Column("movement_detail", sa.Text(), nullable=False),
    )
    op.add_column(
        "exercise_attributes",
        sa.Column("resistance_profile", sa.Text(), nullable=False),
    )
    op.add_column(
        "exercise_attributes",
        sa.Column(
            "is_isolation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.alter_column("exercise_attributes", "movement_pattern", nullable=True)
    op.alter_column("exercise_attributes", "exercise_class", nullable=True)
    op.alter_column("exercise_attributes", "default_rep_min", nullable=True)
    op.alter_column("exercise_attributes", "default_rep_max", nullable=True)

    for name in (
        "ck_exattr_movement_pattern",
        "ck_exattr_exercise_class",
        "ck_exattr_rep_min",
        "ck_exattr_rep_order",
        "ck_exattr_rep_max",
    ):
        op.drop_constraint(name, "exercise_attributes", type_="check")

    op.create_check_constraint(
        "ck_exattr_movement_pattern",
        "exercise_attributes",
        f"movement_pattern IS NULL OR {_in_list('movement_pattern', PATTERNS)}",
    )
    op.create_check_constraint(
        "ck_exattr_movement_detail",
        "exercise_attributes",
        _in_list("movement_detail", DETAILS),
    )
    op.create_check_constraint(
        "ck_exattr_resistance_profile",
        "exercise_attributes",
        _in_list("resistance_profile", PROFILES),
    )
    op.create_check_constraint(
        "ck_exattr_isolation_matches_pattern",
        "exercise_attributes",
        "(movement_pattern IS NULL) = is_isolation",
    )
    op.create_check_constraint(
        "ck_exattr_exercise_class",
        "exercise_attributes",
        f"exercise_class IS NULL OR {_in_list('exercise_class', ('compound', 'machine', 'isolation'))}",
    )
    op.create_check_constraint(
        "ck_exattr_rep_min",
        "exercise_attributes",
        "default_rep_min IS NULL OR default_rep_min >= 1",
    )
    op.create_check_constraint(
        "ck_exattr_rep_order",
        "exercise_attributes",
        "default_rep_min IS NULL OR default_rep_max IS NULL "
        "OR default_rep_min <= default_rep_max",
    )
    op.create_check_constraint(
        "ck_exattr_rep_max",
        "exercise_attributes",
        "default_rep_max IS NULL OR default_rep_max <= 50",
    )

    op.create_index(
        "ix_exattr_detail", "exercise_attributes", ["movement_detail"]
    )
    op.create_index(
        "ix_exattr_isolation", "exercise_attributes", ["is_isolation"]
    )


def downgrade() -> None:
    # Same refusal in reverse: the old schema cannot hold a NULL pattern, and
    # silently inventing one for every isolation row is how a downgrade
    # becomes a data-loss event.
    rows = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM exercise_attributes "
            "WHERE movement_pattern IS NULL "
            "OR default_rep_min IS NULL OR default_rep_max IS NULL "
            "OR exercise_class IS NULL"
        )
    ).scalar_one()
    if rows:
        raise RuntimeError(
            f"{rows} rows hold a NULL this schema cannot represent "
            f"(pattern, rep range or class). The old vocabulary had no way "
            f"to say 'this movement has no pattern'. Decide what those rows "
            f"should become before downgrading."
        )

    op.drop_index("ix_exattr_isolation", table_name="exercise_attributes")
    op.drop_index("ix_exattr_detail", table_name="exercise_attributes")

    for name in (
        "ck_exattr_movement_pattern",
        "ck_exattr_movement_detail",
        "ck_exattr_resistance_profile",
        "ck_exattr_isolation_matches_pattern",
        "ck_exattr_exercise_class",
        "ck_exattr_rep_min",
        "ck_exattr_rep_order",
        "ck_exattr_rep_max",
    ):
        op.drop_constraint(name, "exercise_attributes", type_="check")

    op.drop_column("exercise_attributes", "is_isolation")
    op.drop_column("exercise_attributes", "resistance_profile")
    op.drop_column("exercise_attributes", "movement_detail")

    op.alter_column("exercise_attributes", "movement_pattern", nullable=False)
    op.alter_column("exercise_attributes", "exercise_class", nullable=False)
    op.alter_column("exercise_attributes", "default_rep_min", nullable=False)
    op.alter_column("exercise_attributes", "default_rep_max", nullable=False)

    op.create_check_constraint(
        "ck_exattr_movement_pattern",
        "exercise_attributes",
        "movement_pattern IN ('squat','hinge','push_horizontal',"
        "'push_vertical','pull_horizontal','pull_vertical','carry',"
        "'isolation')",
    )
    op.create_check_constraint(
        "ck_exattr_exercise_class",
        "exercise_attributes",
        "exercise_class IN ('compound','machine','isolation')",
    )
    op.create_check_constraint(
        "ck_exattr_rep_min", "exercise_attributes", "default_rep_min >= 1"
    )
    op.create_check_constraint(
        "ck_exattr_rep_order",
        "exercise_attributes",
        "default_rep_min <= default_rep_max",
    )
    op.create_check_constraint(
        "ck_exattr_rep_max", "exercise_attributes", "default_rep_max <= 50"
    )
