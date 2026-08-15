"""SQLModel ORM models for Trace.

Design notes
------------
* Nutrition is always stored **per 100 g** on FoodItem, and denormalised
  absolute values are stored on MealLog. This means a later correction to a
  food's nutrition never silently rewrites a user's logged history.
* `serving_sizes` is JSON rather than a table because it is always read as a
  whole and never queried across rows.
* `search_text` is a denormalised lowercase blob (name + aliases + brand +
  translations) with a GIN trigram index -- this is what makes typo-tolerant
  search fast without pulling in Elasticsearch.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# asyncpg returns/expects timezone-aware datetimes; the SQLModel default maps
# datetime -> TIMESTAMP WITHOUT TIME ZONE, which asyncpg refuses ("can't
# subtract offset-naive and offset-aware datetimes"). Every datetime column
# uses this explicit type. Date columns are unaffected -- a calendar day has
# no timezone.
TZDateTime = DateTime(timezone=True)


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GoalType(str, enum.Enum):
    lose = "lose"
    maintain = "maintain"
    gain = "gain"
    recomp = "recomp"


class MealType(str, enum.Enum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"
    snack = "snack"


class ProgramType(str, enum.Enum):
    collaborative = "collaborative"
    coached = "coached"
    manual = "manual"


class Verdict(str, enum.Enum):
    lean_gain = "lean_gain"
    fat_gain = "fat_gain"
    recomposition = "recomposition"
    clean_cut = "clean_cut"
    muscle_loss_risk = "muscle_loss_risk"
    insufficient_data = "insufficient_data"


class FoodSource(str, enum.Enum):
    off = "openfoodfacts"
    usda = "usda_fdc"
    ifct = "ifct"
    curated = "curated"
    user = "user"
    ai = "ai_estimated"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str

    display_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None  # 'male' | 'female' | 'other'
    height_cm: Optional[float] = None
    starting_weight_kg: Optional[float] = None
    goal_weight_kg: Optional[float] = None
    goal_type: GoalType = Field(default=GoalType.maintain)
    program_type: ProgramType = Field(default=ProgramType.collaborative)
    activity_multiplier: float = 1.45
    lifting_experience_months: int = 0

    is_pro: bool = False
    timezone: str = "UTC"

    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class RefreshToken(SQLModel, table=True):
    """Refresh tokens are persisted so they can be revoked.

    We store only a SHA-256 hash -- a database leak must not hand an attacker
    working session tokens.
    """

    __tablename__ = "refresh_tokens"

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(index=True, unique=True)
    expires_at: datetime = Field(sa_type=TZDateTime)
    revoked_at: Optional[datetime] = Field(default=None, sa_type=TZDateTime)
    device_label: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# Food
# ---------------------------------------------------------------------------


class FoodItem(SQLModel, table=True):
    __tablename__ = "food_items"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_food_source"),
        Index("ix_food_barcode", "barcode"),
        Index(
            "ix_food_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    source: FoodSource = Field(default=FoodSource.curated)
    source_id: Optional[str] = None

    name: str
    brand: Optional[str] = None
    barcode: Optional[str] = None

    # Translations / colloquial names, e.g. {"hi": "रोटी", "aliases": ["chapati", "phulka"]}
    names_i18n: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))

    # Everything per 100 g (or per 100 ml for liquids).
    calories: float
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0
    sugar_g: float = 0.0
    sodium_mg: float = 0.0
    saturated_fat_g: float = 0.0
    micronutrients: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB)
    )

    is_liquid: bool = False
    # [{"name": "1 katori", "grams": 150, "is_default": true}, ...]
    serving_sizes: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONB)
    )

    cuisine: Optional[str] = None       # 'indian_north', 'italian', ...
    category: Optional[str] = None      # 'dal', 'bread', 'snack', ...
    countries: list[str] = Field(default_factory=list, sa_column=Column(JSONB))

    # Confidence in the *nutrition data itself* (not the AI estimate).
    data_quality: float = 0.5           # 0..1; verified sources score higher
    is_verified: bool = False
    created_by_user_id: Optional[str] = Field(default=None, foreign_key="users.id")
    moderation_status: str = "approved"  # approved | pending | rejected

    search_text: str = Field(default="", sa_column=Column(Text))
    log_count: int = 0                   # popularity -> search ranking

    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class MealLog(SQLModel, table=True):
    __tablename__ = "meal_logs"
    __table_args__ = (Index("ix_meal_user_time", "user_id", "logged_at"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    food_item_id: Optional[str] = Field(default=None, foreign_key="food_items.id")

    # Snapshot at log time -- never recomputed from FoodItem.
    display_name: str
    grams: float
    serving_label: Optional[str] = None
    calories: float
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0

    meal_type: MealType = Field(default=MealType.snack)
    logged_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    photo_url: Optional[str] = None
    recognition_id: Optional[str] = Field(default=None, foreign_key="recognitions.id")
    # Uncertainty carried through from an AI estimate, so the weekly report can
    # say "your intake was 2,640 kcal ± 180" instead of pretending to precision.
    kcal_low: Optional[float] = None
    kcal_high: Optional[float] = None

    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class Recognition(SQLModel, table=True):
    """One photo-scan request and its result."""

    __tablename__ = "recognitions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    image_hash: str = Field(index=True)      # perceptual hash -> deterministic rescans
    image_url: Optional[str] = None
    model_used: str
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    overall_confidence: float = 0.0
    raw_output: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class RecognitionFeedback(SQLModel, table=True):
    """The proprietary dataset. Every user correction lands here.

    This is the single most valuable table in the product -- it is the only
    asset a competitor cannot buy, scrape, or replicate.
    """

    __tablename__ = "recognition_feedback"

    id: str = Field(default_factory=_uuid, primary_key=True)
    recognition_id: str = Field(foreign_key="recognitions.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    ai_output: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    user_correction: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB)
    )
    correction_type: str = "edit"  # edit | reject | confirm
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# Body + training
# ---------------------------------------------------------------------------


class WeightEntry(SQLModel, table=True):
    __tablename__ = "weight_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "measured_on", name="uq_weight_user_day"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    weight_kg: float
    measured_on: date
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class Exercise(SQLModel, table=True):
    __tablename__ = "exercises"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True)
    muscle_group: str
    secondary_muscles: list[str] = Field(
        default_factory=list, sa_column=Column(JSONB)
    )
    equipment: str = "barbell"
    is_compound: bool = False
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSONB))


class WorkoutSession(SQLModel, table=True):
    __tablename__ = "workout_sessions"
    __table_args__ = (Index("ix_session_user_time", "user_id", "started_at"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    started_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    ended_at: Optional[datetime] = Field(default=None, sa_type=TZDateTime)
    routine_name: Optional[str] = None
    notes: Optional[str] = None


class SetLog(SQLModel, table=True):
    __tablename__ = "set_logs"
    __table_args__ = (Index("ix_set_session", "session_id"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(foreign_key="workout_sessions.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    exercise_id: str = Field(foreign_key="exercises.id", index=True)
    set_index: int = 0
    weight_kg: float
    reps: int
    rpe: Optional[float] = None
    is_warmup: bool = False
    e1rm: Optional[float] = None  # computed on write
    performed_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class StrengthSnapshot(SQLModel, table=True):
    """Weekly rollup per exercise -- keeps the adjudication query cheap."""

    __tablename__ = "strength_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "week_start", "exercise_id", name="uq_strength_week"
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    exercise_id: str = Field(foreign_key="exercises.id")
    week_start: date
    best_e1rm: float
    e1rm_ewma: float
    volume_load: float
    session_count: int


class BodyComposition(SQLModel, table=True):
    __tablename__ = "body_composition"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_bodycomp_week"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    week_start: date
    trend_weight_kg: float
    tdee_observed: Optional[float] = None
    tdee_prior: float
    tdee_blended: float
    confidence: float = 0.0
    calorie_target: float
    protein_target_g: float
    # Nullable: rows written before these were persisted have no value, and
    # the client renders a macro with no target as "no goal set" rather than
    # inventing one.
    fat_target_g: Optional[float] = None
    carb_target_g: Optional[float] = None
    fiber_target_g: Optional[float] = None


class Adjudication(SQLModel, table=True):
    """The weekly verdict -- the product's headline feature."""

    __tablename__ = "adjudications"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_adjudication_week"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    week_start: date

    verdict: Verdict = Field(default=Verdict.insufficient_data)
    strength_index_delta_pct: Optional[float] = None
    weight_delta_pct_per_week: Optional[float] = None
    protein_g_per_kg: Optional[float] = None
    logging_adherence: Optional[float] = None

    previous_target: Optional[float] = None
    recommended_target: Optional[float] = None
    recommended_protein_g: Optional[float] = None

    headline: str = ""
    explanation: str = ""
    math_breakdown: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB)
    )
    guardrails_triggered: list[str] = Field(
        default_factory=list, sa_column=Column(JSONB)
    )

    user_accepted: Optional[bool] = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# Health integration (Apple Health / Health Connect)
# ---------------------------------------------------------------------------


class HealthSource(str, enum.Enum):
    healthkit = "healthkit"
    health_connect = "health_connect"
    manual = "manual"


class ActivityDay(SQLModel, table=True):
    """One day of aggregate activity, synced from the phone.

    NOTE: active_energy_kcal is stored for EXPLANATION and reconciliation only.
    It is never added to the user's calorie target -- see services/activity.py
    for why that would double-count.
    """

    __tablename__ = "activity_days"
    __table_args__ = (
        UniqueConstraint("user_id", "day", name="uq_activity_user_day"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    day: date = Field(index=True)

    steps: Optional[int] = None
    active_energy_kcal: Optional[float] = None
    resting_energy_kcal: Optional[float] = None
    exercise_minutes: Optional[float] = None
    stand_hours: Optional[float] = None
    distance_km: Optional[float] = None
    flights_climbed: Optional[int] = None

    # Cardio / recovery signals where available
    resting_heart_rate: Optional[float] = None
    hrv_ms: Optional[float] = None
    vo2_max: Optional[float] = None

    source: HealthSource = Field(default=HealthSource.healthkit)
    synced_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class SleepNight(SQLModel, table=True):
    __tablename__ = "sleep_nights"
    __table_args__ = (
        UniqueConstraint("user_id", "night_of", name="uq_sleep_user_night"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    night_of: date = Field(index=True)

    asleep_hours: float
    in_bed_hours: Optional[float] = None
    deep_hours: Optional[float] = None
    rem_hours: Optional[float] = None
    core_hours: Optional[float] = None
    awakenings: Optional[int] = None
    efficiency: Optional[float] = None

    source: HealthSource = Field(default=HealthSource.healthkit)
    synced_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class ExternalWorkout(SQLModel, table=True):
    """A workout recorded outside Trace -- a run, a ride, a class.

    Distinct from WorkoutSession, which is resistance training WE logged and
    which feeds the strength engine. External workouts feed activity context
    only; they have no e1RM.
    """

    __tablename__ = "external_workouts"
    __table_args__ = (
        UniqueConstraint("user_id", "external_id", name="uq_external_workout"),
        Index("ix_external_user_time", "user_id", "started_at"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    external_id: str  # HealthKit/Health Connect UUID -- makes sync idempotent

    activity_type: str  # 'running', 'cycling', 'hiit', ...
    started_at: datetime = Field(sa_type=TZDateTime)
    ended_at: Optional[datetime] = Field(default=None, sa_type=TZDateTime)
    duration_minutes: float = 0.0
    active_energy_kcal: Optional[float] = None
    distance_km: Optional[float] = None
    mean_heart_rate: Optional[float] = None
    max_heart_rate: Optional[float] = None

    source: HealthSource = Field(default=HealthSource.healthkit)
    synced_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class HealthSyncState(SQLModel, table=True):
    """Per-user, per-metric sync cursor, so we only pull deltas."""

    __tablename__ = "health_sync_state"
    __table_args__ = (
        UniqueConstraint("user_id", "metric", name="uq_sync_user_metric"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    metric: str  # 'steps', 'sleep', 'workouts', ...
    last_synced_through: Optional[date] = None
    anchor: Optional[str] = None  # HealthKit anchored-query token
    permission_granted: bool = False
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class CoachBriefingRecord(SQLModel, table=True):
    """A generated daily briefing, so we can measure what advice we gave."""

    __tablename__ = "coach_briefings"
    __table_args__ = (
        UniqueConstraint("user_id", "for_date", name="uq_briefing_user_day"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    for_date: date

    primary_key_: Optional[str] = Field(default=None, alias="primary_insight_key")
    primary_lever: Optional[str] = None
    headline: str = ""
    body: str = ""
    narrated: bool = False
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    data_completeness: float = 0.0

    user_dismissed: Optional[bool] = None
    user_acted: Optional[bool] = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
