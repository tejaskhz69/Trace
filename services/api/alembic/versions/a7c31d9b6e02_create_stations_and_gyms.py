"""Create gyms and stations; add station columns to set_logs.

Revision ID: a7c31d9b6e02
Revises: f6a9c2e47d85
Create Date: 2026-08-26

WHAT THIS DOES TO EXISTING DATA: nothing.

`set_logs.station_id` and `set_logs.station_profile` are added NULLABLE with no
default and **no backfill**. Every set already in the table keeps working
exactly as it did, and reads as "machine not recorded" -- which is the truth.
We do not know which machine those sets were performed on, and guessing would
invent a fact about somebody's training history in order to make a chart look
tidier.

NULL is therefore a permanent, legitimate value here, not a migration
staging state. A barbell squat has no station either.

WHAT IS NOT IN THIS MIGRATION
No load-conversion column, on any table. There is no `effective_load_ratio`,
no normalisation factor and no equivalence mapping between stations, because
no honest one exists -- plate-loaded leverage runs roughly 2:1 to 5:1, is
never published by manufacturers, and varies through the range of motion.
Progress is compared within a station and never across.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7c31d9b6e02"
down_revision: Union[str, Sequence[str], None] = "f6a9c2e47d85"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- gyms ------------------------------------------------------------
    # Deliberately thin: a grouping key for stations, not a venue directory.
    op.create_table(
        "gyms",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("created_by_user_id", sa.String(), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_gym_creator",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_gyms_name", "gyms", ["name"])
    op.create_index("ix_gym_city", "gyms", ["city"])
    op.create_index("ix_gyms_created_by_user_id", "gyms", ["created_by_user_id"])

    # --- stations --------------------------------------------------------
    op.create_table(
        "stations",
        sa.Column("id", sa.String(), primary_key=True),
        # Free text, never a controlled brand vocabulary. Most machines in
        # Indian gyms are unbranded or locally fabricated; a dropdown of
        # premium US brands would exclude them entirely.
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("exercise_id", sa.String(), nullable=False),
        # Nullable: a home-gym lifter has no gym, and there is no gym-setup
        # step before somebody's first set.
        sa.Column("gym_id", sa.String(), nullable=True),
        sa.Column("created_by_user_id", sa.String(), nullable=False),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("loading", sa.String(), nullable=True),
        sa.Column(
            "has_adjustable_profile",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "profile_settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # An ORDERED LIST of {start, end, step}, never a single increment.
        # Real stacks are non-uniform -- 5 kg steps from 15-25, 10 from 25-55,
        # 15 from 55-190 on one machine -- and a lone increment column tells
        # people to load weights the machine does not have.
        sa.Column(
            "stack_ranges",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("unit", sa.String(), nullable=False, server_default="kg"),
        sa.Column("micro_adjust_kg", sa.Float(), nullable=True),
        sa.Column("carriage_weight_kg", sa.Float(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("log_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name="fk_station_exercise",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["gym_id"], ["gyms.id"], name="fk_station_gym", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_station_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "loading IN ('plate','pin','dial','cable','bodyweight','free_weight')",
            name="ck_station_loading",
        ),
        sa.CheckConstraint("unit IN ('kg','lb')", name="ck_station_unit"),
    )
    op.create_index("ix_stations_name", "stations", ["name"])
    op.create_index("ix_stations_exercise_id", "stations", ["exercise_id"])
    op.create_index("ix_stations_gym_id", "stations", ["gym_id"])
    op.create_index("ix_station_gym_exercise", "stations", ["gym_id", "exercise_id"])
    op.create_index("ix_station_owner", "stations", ["created_by_user_id"])

    # --- set_logs --------------------------------------------------------
    # Nullable, no default, no backfill. See the module docstring.
    op.add_column("set_logs", sa.Column("station_id", sa.String(), nullable=True))
    op.add_column(
        "set_logs", sa.Column("station_profile", sa.String(), nullable=True)
    )
    op.create_foreign_key(
        "fk_set_station",
        "set_logs",
        "stations",
        ["station_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # The shape `strength/progress` actually queries.
    op.create_index(
        "ix_set_user_ex_station_time",
        "set_logs",
        ["user_id", "exercise_id", "station_id", "performed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_set_user_ex_station_time", table_name="set_logs")
    op.drop_constraint("fk_set_station", "set_logs", type_="foreignkey")
    op.drop_column("set_logs", "station_profile")
    op.drop_column("set_logs", "station_id")

    op.drop_index("ix_station_owner", table_name="stations")
    op.drop_index("ix_station_gym_exercise", table_name="stations")
    op.drop_index("ix_stations_gym_id", table_name="stations")
    op.drop_index("ix_stations_exercise_id", table_name="stations")
    op.drop_index("ix_stations_name", table_name="stations")
    op.drop_table("stations")

    op.drop_index("ix_gyms_created_by_user_id", table_name="gyms")
    op.drop_index("ix_gym_city", table_name="gyms")
    op.drop_index("ix_gyms_name", table_name="gyms")
    op.drop_table("gyms")
