"""create workout programming tables

Revision ID: f6a9c2e47d85
Revises: e4f7b0d25c63
Create Date: 2026-08-23

THIS MIGRATION IS PURELY ADDITIVE. It creates nine tables and alters nothing.

That is a deliberate design property, not a happy accident. `exercise_attributes`
exists as a side table specifically so `exercises` needs no ALTER, and
`training_profiles` exists specifically so `users` needs no ALTER. The result:
no pre-existing row is read, written, locked for rewrite, or touched in any
way, and the downgrade is exactly reversible because there is nothing to
restore.

NOT ONE STATEMENT HERE REFERENCES A NUTRITION TABLE.
No `food_items`, no `food_aliases`, no `meal_logs`, and none of the protected
columns (`gtin14`, `name_normalized`, `barcode`, `name`, `names_i18n`,
`search_text`, `source_licence`, `verification_tier`). There is also no DML of
any kind -- no INSERT, no UPDATE, no DELETE. All nine tables are created empty.

INDEXES ARE BUILT INLINE AND NON-CONCURRENTLY, DELIBERATELY.
Every table here is empty at the instant its indexes are built, so each build
is instant and the lock is on a table no query has ever read. This is the same
reasoning c2d5f8b03a41 recorded for `food_aliases`. CREATE INDEX CONCURRENTLY
would be cargo-cult here: slower, unable to run inside this transaction, and
guarding against contention that cannot exist. Contrast e4f7b0d25c63, where
the same operation across 578,773 `food_items` rows genuinely did need it.

WHY `ai_generations` IS CREATED BEFORE `planned_sessions`
`planned_sessions.generation_id` references it. That is the only non-obvious
ordering constraint in the upgrade.

`exercise_attributes` IS NOT SEEDED HERE.
The 874 existing exercises get no attribute rows from this migration. Seeding
is a data task with its own review of the classifications, and mixing it into
a schema migration would make this file unreviewable and its downgrade lossy.
Generation treats an unattributed exercise as ineligible for prescription, so
an empty table is a safe state rather than a broken one.

See WORKOUT_SCHEMA_DESIGN.md for the full design, the ER diagram, and the
decisions still open.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# Autogenerate emits `sqlmodel.sql.sqltypes.AutoString()` for every str column
# but its own template only imports sqlalchemy, so the name is never bound.
import sqlmodel  # noqa: F401 -- may be unused; see comment above
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f6a9c2e47d85"
down_revision: Union[str, Sequence[str], None] = "e4f7b0d25c63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: Every table this revision creates, in dependency order. The downgrade walks
#: this list backwards, which is what keeps the two halves from drifting apart.
TABLES: tuple[str, ...] = (
    "exercise_attributes",
    "exercise_substitutions",
    "training_profiles",
    "training_programmes",
    "programme_days",
    "ai_generations",
    "readiness_checkins",
    "planned_sessions",
    "prescribed_exercises",
)


def _jsonb_empty_list() -> sa.TextClause:
    """DEFAULT '[]'::jsonb -- spelled out rather than left to coercion."""
    return sa.text("'[]'::jsonb")


def upgrade() -> None:
    """Upgrade schema."""

    # -- 1. exercise_attributes ------------------------------------------
    # Programming metadata the catalogue lacks. PK is also the FK: one row per
    # exercise, enforced by the primary key rather than a separate constraint.
    op.create_table(
        "exercise_attributes",
        sa.Column("exercise_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("movement_pattern", sa.Text(), nullable=False),
        sa.Column("exercise_class", sa.Text(), nullable=False),
        sa.Column(
            "is_unilateral", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("default_rep_min", sa.SmallInteger(), nullable=False),
        sa.Column("default_rep_max", sa.SmallInteger(), nullable=False),
        sa.Column(
            "default_rest_seconds",
            sa.SmallInteger(),
            nullable=False,
            server_default="120",
        ),
        sa.Column(
            "fatigue_cost", sa.SmallInteger(), nullable=False, server_default="3"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("exercise_id"),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name="fk_exattr_exercise",
            ondelete="CASCADE",
        ),
        # Text + CHECK rather than PG enums: extending the vocabulary later is
        # DROP/ADD CONSTRAINT inside an ordinary transaction, instead of the
        # ALTER TYPE dance that cannot run in one. Same call as ck_alias_type.
        sa.CheckConstraint(
            "movement_pattern IN ('squat','hinge','push_horizontal',"
            "'push_vertical','pull_horizontal','pull_vertical','carry',"
            "'isolation')",
            name="ck_exattr_movement_pattern",
        ),
        sa.CheckConstraint(
            "exercise_class IN ('compound','machine','isolation')",
            name="ck_exattr_exercise_class",
        ),
        sa.CheckConstraint("default_rep_min >= 1", name="ck_exattr_rep_min"),
        sa.CheckConstraint(
            "default_rep_min <= default_rep_max", name="ck_exattr_rep_order"
        ),
        sa.CheckConstraint("default_rep_max <= 50", name="ck_exattr_rep_max"),
        sa.CheckConstraint(
            "default_rest_seconds BETWEEN 15 AND 600", name="ck_exattr_rest"
        ),
        sa.CheckConstraint("fatigue_cost BETWEEN 1 AND 5", name="ck_exattr_fatigue"),
    )
    op.create_index("ix_exattr_pattern", "exercise_attributes", ["movement_pattern"])
    op.create_index("ix_exattr_class", "exercise_attributes", ["exercise_class"])

    # -- 2. exercise_substitutions ---------------------------------------
    # A directed, ranked graph. Direction is not assumed symmetric; if both
    # directions hold, both rows exist.
    op.create_table(
        "exercise_substitutions",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "from_exercise_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column(
            "to_exercise_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["from_exercise_id"],
            ["exercises.id"],
            name="fk_exsub_from",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_exercise_id"],
            ["exercises.id"],
            name="fk_exsub_to",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "from_exercise_id", "to_exercise_id", name="uq_exsub_pair"
        ),
        sa.CheckConstraint(
            "from_exercise_id <> to_exercise_id", name="ck_exsub_not_self"
        ),
        sa.CheckConstraint("rank BETWEEN 1 AND 10", name="ck_exsub_rank"),
        sa.CheckConstraint(
            "reason IN ('equipment','branded','limitation','preference')",
            name="ck_exsub_reason",
        ),
    )
    op.create_index(
        "ix_exsub_from", "exercise_substitutions", ["from_exercise_id", "rank"]
    )

    # -- 3. training_profiles --------------------------------------------
    # One per user, enforced by the database rather than by application code.
    op.create_table(
        "training_profiles",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "days_per_week", sa.SmallInteger(), nullable=False, server_default="3"
        ),
        sa.Column(
            "available_days",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_jsonb_empty_list(),
        ),
        sa.Column(
            "preferred_minutes",
            sa.SmallInteger(),
            nullable=False,
            server_default="60",
        ),
        sa.Column(
            "equipment",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_jsonb_empty_list(),
        ),
        sa.Column(
            "disliked_exercise_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_jsonb_empty_list(),
        ),
        # Health-sensitive free text. Never logged, never in an error message.
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column(
            "ai_enabled", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_training_profile_user",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", name="uq_training_profile_user"),
        sa.CheckConstraint("days_per_week BETWEEN 1 AND 7", name="ck_profile_days"),
        sa.CheckConstraint(
            "preferred_minutes BETWEEN 15 AND 180", name="ck_profile_minutes"
        ),
    )

    # -- 4. training_programmes ------------------------------------------
    op.create_table(
        "training_programmes",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("split_type", sa.Text(), nullable=False),
        sa.Column("days_per_week", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "generated_by", sa.Text(), nullable=False, server_default="template"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_programme_user", ondelete="CASCADE"
        ),
        sa.CheckConstraint("days_per_week BETWEEN 1 AND 7", name="ck_programme_days"),
        sa.CheckConstraint(
            "status IN ('active','paused','archived')", name="ck_programme_status"
        ),
        sa.CheckConstraint(
            "generated_by IN ('template','ai','user')",
            name="ck_programme_generated_by",
        ),
        # status and archived_at must agree. A status that disagrees with its
        # own timestamp is the kind of thing nobody notices for a year.
        sa.CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)",
            name="ck_programme_archived_at",
        ),
    )
    op.create_index(
        "ix_programme_user_status", "training_programmes", ["user_id", "status"]
    )
    # THE PARTIAL UNIQUE INDEX. "One active programme per user" is the
    # invariant most likely to be broken by a retry or a double-tap, and an
    # application-level check loses that race every time. Postgres does not.
    # Archived and paused rows are exempt, which is what makes archival work.
    op.create_index(
        "uq_active_programme_per_user",
        "training_programmes",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # -- 5. programme_days -----------------------------------------------
    op.create_table(
        "programme_days",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("programme_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("day_index", sa.SmallInteger(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column(
            "focus",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_jsonb_empty_list(),
        ),
        sa.Column("target_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["programme_id"],
            ["training_programmes.id"],
            name="fk_programme_day_programme",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("programme_id", "day_index", name="uq_programme_day"),
        sa.CheckConstraint("day_index BETWEEN 0 AND 6", name="ck_programme_day_index"),
        sa.CheckConstraint(
            "target_minutes IS NULL OR target_minutes BETWEEN 15 AND 180",
            name="ck_programme_day_minutes",
        ),
    )

    # -- 6. ai_generations -----------------------------------------------
    # Audit structure only -- nothing writes to it yet. It ships early so that
    # AI generation cannot later land without its audit trail.
    #
    # prompt_digest, NOT the prompt: a prompt would carry the user's
    # limitations, pain notes and training history, and a digest answers the
    # only question this table needs to answer.
    op.create_table(
        "ai_generations",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_digest", sa.Text(), nullable=False),
        # Nullable precisely because storing raw responses is an open decision.
        sa.Column(
            "raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("validation_status", sa.Text(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_aigen_user", ondelete="CASCADE"
        ),
        sa.CheckConstraint("kind IN ('programme','session')", name="ck_aigen_kind"),
        sa.CheckConstraint(
            "validation_status IN ('accepted','rejected')",
            name="ck_aigen_validation_status",
        ),
        sa.CheckConstraint(
            "(validation_status = 'rejected') = (rejection_reason IS NOT NULL)",
            name="ck_aigen_rejection_reason",
        ),
    )
    op.create_index(
        "ix_aigen_user_time",
        "ai_generations",
        ["user_id", sa.text("created_at DESC")],
    )

    # -- 7. readiness_checkins -------------------------------------------
    # HEALTH-SENSITIVE. Every score is nullable so a partially answered
    # questionnaire stays distinguishable from a low score -- defaulting an
    # unanswered soreness question to any number would fabricate a reading.
    op.create_table(
        "readiness_checkins",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("available_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("energy", sa.SmallInteger(), nullable=True),
        sa.Column("sleep_quality", sa.SmallInteger(), nullable=True),
        sa.Column("soreness", sa.SmallInteger(), nullable=True),
        sa.Column("stress", sa.SmallInteger(), nullable=True),
        sa.Column(
            "pain_flag", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("pain_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_readiness_user", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "for_date", name="uq_readiness_user_date"),
        sa.CheckConstraint(
            "energy IS NULL OR energy BETWEEN 1 AND 5", name="ck_readiness_energy"
        ),
        sa.CheckConstraint(
            "sleep_quality IS NULL OR sleep_quality BETWEEN 1 AND 5",
            name="ck_readiness_sleep",
        ),
        sa.CheckConstraint(
            "soreness IS NULL OR soreness BETWEEN 1 AND 5",
            name="ck_readiness_soreness",
        ),
        sa.CheckConstraint(
            "stress IS NULL OR stress BETWEEN 1 AND 5", name="ck_readiness_stress"
        ),
        sa.CheckConstraint(
            "available_minutes IS NULL OR available_minutes BETWEEN 5 AND 300",
            name="ck_readiness_minutes",
        ),
    )
    op.create_index(
        "ix_readiness_user_date",
        "readiness_checkins",
        ["user_id", sa.text("for_date DESC")],
    )

    # -- 8. planned_sessions ---------------------------------------------
    # The join between intention and reality. session_id runs plan ->
    # performance and is nullable, which is what lets a spontaneous workout
    # need no plan at all.
    op.create_table(
        "planned_sessions",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        # Denormalised from programme_day -> programme -> user. A considered
        # exception: it is the ownership filter on the hottest query here, and
        # a one-off session has no programme to derive it from.
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "programme_day_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="planned"),
        sa.Column("readiness_status", sa.Text(), nullable=True),
        sa.Column("estimated_minutes", sa.SmallInteger(), nullable=True),
        sa.Column(
            "generated_by", sa.Text(), nullable=False, server_default="template"
        ),
        sa.Column("generation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "notes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_jsonb_empty_list(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_planned_user", ondelete="CASCADE"
        ),
        # SET NULL, not CASCADE. If a programme is rebuilt, the record that a
        # user trained on a given day must survive -- it becomes a one-off.
        sa.ForeignKeyConstraint(
            ["programme_day_id"],
            ["programme_days.id"],
            name="fk_planned_programme_day",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["workout_sessions.id"],
            name="fk_planned_session_ref",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["ai_generations.id"],
            name="fk_planned_generation",
            ondelete="SET NULL",
        ),
        # CAVEAT: Postgres treats NULLs as DISTINCT, so this constrains
        # nothing for one-off sessions (programme_day_id IS NULL) -- the same
        # trap c2d5f8b03a41 documented for food_aliases.lang. Intended here (a
        # user may legitimately plan two ad-hoc sessions in a day), and
        # spelled out so nobody mistakes it for protection it does not give.
        sa.UniqueConstraint(
            "user_id", "scheduled_for", "programme_day_id", name="uq_planned_day"
        ),
        sa.CheckConstraint(
            "status IN ('planned','active','completed','skipped')",
            name="ck_planned_status",
        ),
        sa.CheckConstraint(
            "generated_by IN ('template','ai','user')",
            name="ck_planned_generated_by",
        ),
        sa.CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes BETWEEN 5 AND 300",
            name="ck_planned_minutes",
        ),
        sa.CheckConstraint(
            "generated_by = 'ai' OR generation_id IS NULL",
            name="ck_planned_generation_ref",
        ),
    )
    op.create_index(
        "ix_planned_user_date",
        "planned_sessions",
        ["user_id", sa.text("scheduled_for DESC")],
    )
    op.create_index("ix_planned_session", "planned_sessions", ["session_id"])

    # -- 9. prescribed_exercises -----------------------------------------
    # The CHECK constraints here are the backstop on AI output: validation
    # happens in the service so the error is legible, and is enforced here so
    # a validation bug is a failed insert rather than bad advice on screen.
    op.create_table(
        "prescribed_exercises",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "planned_session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("exercise_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("order_index", sa.SmallInteger(), nullable=False),
        sa.Column("sets", sa.SmallInteger(), nullable=False),
        sa.Column("rep_min", sa.SmallInteger(), nullable=False),
        sa.Column("rep_max", sa.SmallInteger(), nullable=False),
        sa.Column(
            "target_rir", sa.SmallInteger(), nullable=False, server_default="2"
        ),
        sa.Column(
            "rest_seconds", sa.SmallInteger(), nullable=False, server_default="120"
        ),
        sa.Column("suggested_weight_kg", sa.Float(), nullable=True),
        sa.Column(
            "progression_rule",
            sa.Text(),
            nullable=False,
            server_default="double_progression",
        ),
        sa.Column(
            "substitution_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_jsonb_empty_list(),
        ),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default="prescribed"
        ),
        sa.Column(
            "replaced_with_exercise_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["planned_session_id"],
            ["planned_sessions.id"],
            name="fk_prescribed_planned_session",
            ondelete="CASCADE",
        ),
        # RESTRICT, AND IT IS THE ONLY FK HERE THAT IS. Cascading would let a
        # catalogue cleanup silently erase training history; SET NULL would
        # leave a prescription that prescribes nothing. RESTRICT makes the
        # deletion fail loudly and forces a human decision.
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name="fk_prescribed_exercise",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_with_exercise_id"],
            ["exercises.id"],
            name="fk_prescribed_replacement",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "planned_session_id", "order_index", name="uq_prescribed_order"
        ),
        sa.CheckConstraint("sets BETWEEN 1 AND 12", name="ck_prescribed_sets"),
        sa.CheckConstraint("rep_min >= 1", name="ck_prescribed_rep_min"),
        sa.CheckConstraint("rep_min <= rep_max", name="ck_prescribed_rep_order"),
        sa.CheckConstraint("rep_max <= 50", name="ck_prescribed_rep_max"),
        sa.CheckConstraint("target_rir BETWEEN 0 AND 6", name="ck_prescribed_rir"),
        sa.CheckConstraint(
            "rest_seconds BETWEEN 15 AND 600", name="ck_prescribed_rest"
        ),
        sa.CheckConstraint("order_index >= 0", name="ck_prescribed_order_index"),
        sa.CheckConstraint(
            "suggested_weight_kg IS NULL OR "
            "(suggested_weight_kg > 0 AND suggested_weight_kg <= 1000)",
            name="ck_prescribed_weight",
        ),
        sa.CheckConstraint(
            "status IN ('prescribed','replaced','skipped','done')",
            name="ck_prescribed_status",
        ),
        sa.CheckConstraint(
            "(status = 'replaced') = (replaced_with_exercise_id IS NOT NULL)",
            name="ck_prescribed_replacement",
        ),
    )
    op.create_index(
        "ix_prescribed_session",
        "prescribed_exercises",
        ["planned_session_id", "order_index"],
    )


def downgrade() -> None:
    """Downgrade schema.

    Exact reverse of the upgrade: children before parents, so no FK is ever
    left dangling mid-drop. Indexes and constraints are owned by their tables
    and go with them, so there is nothing to drop separately.

    LOSSLESS WITH RESPECT TO EVERYTHING THAT EXISTED AT e4f7b0d25c63 -- the
    upgrade altered nothing, so reversing it removes only what it added.

    NOT lossless with respect to programming data created after the upgrade:
    this destroys every training profile, programme, planned session,
    prescription, readiness check-in and generation record. In development
    that is free; in production it needs a fresh dump first, because the
    pre-migration backup will not contain any of it.
    """
    for table in reversed(TABLES):
        op.drop_table(table)
