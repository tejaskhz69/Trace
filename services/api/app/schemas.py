"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from .models import FoodSource, GoalType, MealType, RecipeVisibility, Verdict


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    display_name: Optional[str] = None
    sex: Optional[str] = None
    height_cm: Optional[float] = Field(default=None, gt=50, lt=280)
    weight_kg: Optional[float] = Field(default=None, gt=20, lt=400)
    goal_weight_kg: Optional[float] = Field(default=None, gt=20, lt=400)
    goal_type: GoalType = GoalType.maintain
    lifting_experience_months: Optional[int] = Field(default=0, ge=0, le=1200)
    device_label: Optional[str] = None

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if v.strip() != v:
            raise ValueError("Password must not start or end with whitespace.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_label: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class UserPublic(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    sex: Optional[str] = None
    height_cm: Optional[float] = None
    goal_type: GoalType
    is_pro: bool
    lifting_experience_months: int
    created_at: datetime
    # The client's routing gate reads this: null means the questionnaire has
    # not been completed, so the app sends them to onboarding instead of the
    # tabs. It lives on the user rather than in local storage so a reinstall
    # or a second device doesn't re-ask questions they already answered.
    onboarded_at: Optional[datetime] = None


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


# ---------------------------------------------------------------------------
# Food
# ---------------------------------------------------------------------------


class ServingSize(BaseModel):
    name: str
    grams: float
    is_default: bool = False


class FoodItemPublic(BaseModel):
    id: str
    name: str
    brand: Optional[str] = None
    barcode: Optional[str] = None
    source: FoodSource
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    sugar_g: float
    is_liquid: bool
    serving_sizes: list[dict[str, Any]] = []
    cuisine: Optional[str] = None
    data_quality: float
    is_verified: bool

    # --- additive, all optional: existing clients keep working -------------
    #: Licence of THIS row's nutrition data. Per-row, never global: the
    #: catalogue mixes ODbL (Open Food Facts), public-domain (USDA) and
    #: user-curated data, and labelling them alike would be wrong.
    source_licence: Optional[str] = None
    #: 1..7, lower is better evidence. See services/licensing.py.
    verification_tier: Optional[int] = None
    #: Deterministic upstream URL where one exists, else None. Never invented.
    source_url: Optional[str] = None
    #: How this row was reached: 'direct' or 'alias'. Provenance for the
    #: result, not a ranking input.
    matched_via: Optional[str] = None
    #: The alias text that matched, when matched_via == 'alias'. Without this
    #: the UI cannot say WHY a search for 'avalakki' returned Poha.
    matched_alias: Optional[str] = None


class FoodSearchResponse(BaseModel):
    query: str
    results: list[FoodItemPublic]
    took_ms: int
    source: str  # "local" | "local+remote"


class BarcodeResolveResponse(BaseModel):
    found: bool
    barcode: str
    item: Optional[FoodItemPublic] = None
    resolved_from: Optional[str] = None  # local | openfoodfacts | usda
    message: Optional[str] = None


class CustomFoodRequest(BaseModel):
    name: str
    brand: Optional[str] = None
    barcode: Optional[str] = None
    calories: float = Field(ge=0, le=900)  # per 100 g; 900 = pure fat ceiling
    protein_g: float = Field(default=0, ge=0, le=100)
    carbs_g: float = Field(default=0, ge=0, le=100)
    fat_g: float = Field(default=0, ge=0, le=100)
    fiber_g: float = Field(default=0, ge=0, le=100)
    is_liquid: bool = False
    serving_sizes: list[ServingSize] = []


# ---------------------------------------------------------------------------
# Meals
# ---------------------------------------------------------------------------


class MealLogRequest(BaseModel):
    food_item_id: Optional[str] = None
    display_name: Optional[str] = None
    grams: float = Field(gt=0, le=5000)
    serving_label: Optional[str] = None
    meal_type: MealType = MealType.snack
    logged_at: Optional[datetime] = None
    recognition_id: Optional[str] = None
    # Only used when logging a free-form / AI item with no food_item_id
    calories: Optional[float] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None


class MealLogPublic(BaseModel):
    id: str
    display_name: str
    grams: float
    serving_label: Optional[str]
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    meal_type: MealType
    logged_at: datetime
    kcal_low: Optional[float] = None
    kcal_high: Optional[float] = None


class DailySummary(BaseModel):
    date: date
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    calorie_target: Optional[float] = None
    protein_target_g: Optional[float] = None
    carb_target_g: Optional[float] = None
    fat_target_g: Optional[float] = None
    fiber_target_g: Optional[float] = None

    # --- The Home screen's "worth watching" ledger --------------------------
    # None means "not known for today's foods", which is NOT the same as zero.
    # A day whose foods carry no sodium data must render as unknown rather than
    # as a reassuring empty bar.
    sodium_mg: Optional[float] = None
    potassium_mg: Optional[float] = None
    sugars_g: Optional[float] = None
    sodium_limit_mg: float = 2300.0
    potassium_target_mg: float = 3400.0
    sugars_limit_g: float = 50.0

    meals: list[MealLogPublic] = []


# ---------------------------------------------------------------------------
# Recognition
# ---------------------------------------------------------------------------


class ClarifyingQuestion(BaseModel):
    text: str
    options: list[str]
    kcal_deltas: list[float]


class RecognizedItem(BaseModel):
    name: str
    name_local: Optional[str] = None
    portion_unit: str
    portion_count: float
    grams_est: float
    grams_range: list[float]
    kcal_point: float
    kcal_low: float
    kcal_high: float
    protein_g: float
    carbs_g: float
    fat_g: float
    confidence: float
    matched_food_item_id: Optional[str] = None
    clarifying_question: Optional[ClarifyingQuestion] = None


class RecognitionResponse(BaseModel):
    recognition_id: str
    items: list[RecognizedItem]
    hidden_ingredients: list[str] = []
    overall_confidence: float
    model_used: str
    latency_ms: int
    cached: bool = False


class RecognitionCorrection(BaseModel):
    correction_type: str = "edit"
    corrected_items: list[dict[str, Any]] = []
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Weight / training / adjudication
# ---------------------------------------------------------------------------


class WeightLogRequest(BaseModel):
    weight_kg: float = Field(gt=20, lt=400)
    measured_on: Optional[date] = None


class WeightTrendPoint(BaseModel):
    date: date
    raw_kg: Optional[float]
    trend_kg: float


class SetLogRequest(BaseModel):
    exercise_id: str
    weight_kg: float = Field(ge=0, le=700)
    reps: int = Field(ge=1, le=100)
    # WHICH MACHINE. Both optional and both staying optional -- a barbell
    # squat has no station, and a lifter who cannot say what they used must
    # still be able to log the set.
    station_id: Optional[str] = None
    station_profile: Optional[str] = Field(default=None, max_length=32)
    # Ask for RIR, not RPE. "How many more could you have done" is a question
    # a beginner can answer honestly; "rate this 1-10" is jargon. RPE is
    # derived for display. Either may be sent; RIR wins if both are.
    rir: Optional[float] = Field(default=None, ge=0, le=10)
    rpe: Optional[float] = Field(default=None, ge=1, le=10)
    is_warmup: bool = False


class VoiceSetInput(BaseModel):
    """One set from a reviewed voice proposal."""

    reps: int = Field(ge=1, le=100)
    weight_kg: float = Field(default=0.0, ge=0, le=700)
    rir: Optional[float] = Field(default=None, ge=0, le=10)
    is_warmup: bool = False


class VoiceEntryInput(BaseModel):
    exercise_id: str
    sets: list[VoiceSetInput] = Field(min_length=1, max_length=20)


class VoiceCommitRequest(BaseModel):
    """A whole dictated workout, after the user has looked at it.

    The proposal from POST /voice is NOT what gets written -- this is. The
    client sends back what the user actually confirmed, so any correction
    they made on the review screen is what lands in the database, and a
    replayed proposal cannot resurrect a value they fixed.
    """

    entries: list[VoiceEntryInput] = Field(min_length=1, max_length=40)
    routine_name: Optional[str] = Field(default=None, max_length=80)
    duration_min: Optional[int] = Field(default=None, ge=1, le=600)
    started_at: Optional[datetime] = None
    # Kept as the session note. When a number is ever disputed, the words that
    # produced it are the only way to work out what happened.
    transcript: Optional[str] = Field(default=None, max_length=8000)


class PhoneStartRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=24)
    country_code: Optional[str] = Field(default=None, max_length=5)


class PhoneVerifyRequest(BaseModel):
    """Verifying a code both signs in and signs up.

    A verified phone number IS the account, so asking a user whether they are
    new is asking them to remember something they should not have to.
    """

    phone: str = Field(min_length=6, max_length=24)
    code: str = Field(min_length=4, max_length=8)
    country_code: Optional[str] = Field(default=None, max_length=5)
    display_name: Optional[str] = Field(default=None, max_length=120)
    device_label: Optional[str] = Field(default=None, max_length=80)


class SocialSignInRequest(BaseModel):
    """A Google/Apple identity token, to be exchanged for a Trace session.

    `display_name` is here rather than read from the token on purpose: Apple
    sends the user's full name EXACTLY ONCE, in the credential object on the
    very first authorization, and never inside the token. If the client does
    not forward it at that moment it is gone permanently.
    """

    provider: str = Field(pattern="^(google|apple)$")
    id_token: str = Field(min_length=20, max_length=8192)
    display_name: Optional[str] = Field(default=None, max_length=120)
    device_label: Optional[str] = Field(default=None, max_length=80)


class WorkoutSessionRequest(BaseModel):
    routine_name: Optional[str] = None
    started_at: Optional[datetime] = None
    notes: Optional[str] = None


class StrengthPoint(BaseModel):
    week_start: date
    best_e1rm: float
    e1rm_ewma: float
    volume_load: float


class StrengthSeries(BaseModel):
    """One continuous trend: this movement, on this machine, at this setting.

    Progress is only comparable WITHIN a series. Two series on the same
    exercise are two different pieces of equipment, and the difference between
    their loads says nothing about the lifter -- see the note on Station.
    """

    station_id: Optional[str] = None
    station_profile: Optional[str] = None
    #: "Not recorded" when the sets carry no station. Named, not blank, so the
    #: chart legend never has an anonymous line on it.
    station_name: str
    points: list[StrengthPoint]


class PlateauPerformance(BaseModel):
    """One end of the comparison window."""

    performed_on: date
    top_set_weight_kg: float
    top_set_reps: int
    top_set_e1rm: Optional[float] = None
    top_set_rir: Optional[float] = None
    volume_load: float


class PlateauAssessmentPublic(BaseModel):
    """A read-only opinion about one lift on one piece of equipment.

    Carries its own evidence. `evidence_sessions` is every session that was
    counted, so the screen can show which ones -- an assessment the user
    cannot audit is one they have to take on faith, and this one is an
    inference from a handful of sessions.

    `requires_confirmation` is true whenever acting on the recommendation
    would change training. Nothing here is ever applied automatically.
    """

    status: str
    exercise_id: str
    exercise_name: str
    station_id: Optional[str] = None
    station_profile: Optional[str] = None
    station_name: str = "Not recorded"
    reason: str
    recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_sessions: list[date] = Field(default_factory=list)
    baseline: Optional[PlateauPerformance] = None
    current: Optional[PlateauPerformance] = None
    stalled_metric: Optional[str] = None
    improving_metrics: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False


class StackRange(BaseModel):
    """One uniform run of a weight stack. Stacks are lists of these."""

    start: float = Field(ge=0, le=1000)
    end: float = Field(ge=0, le=1000)
    step: float = Field(gt=0, le=100)


class StationCreate(BaseModel):
    """Name is the only thing we insist on.

    Everything else is optional because the alternative is a configuration
    screen standing between somebody and their first set. A station named
    "the blue row machine" and nothing else is a completely valid record.
    """

    exercise_id: str
    name: str = Field(min_length=1, max_length=120)
    gym_id: Optional[str] = None
    brand: Optional[str] = Field(default=None, max_length=80)
    model: Optional[str] = Field(default=None, max_length=80)
    loading: Optional[Literal["plate", "pin", "dial", "cable", "bodyweight", "free_weight"]] = None
    has_adjustable_profile: bool = False
    profile_settings: list[str] = Field(default_factory=list, max_length=12)
    stack_ranges: list[StackRange] = Field(default_factory=list, max_length=12)
    unit: Literal["kg", "lb"] = "kg"
    micro_adjust_kg: Optional[float] = Field(default=None, ge=0, le=50)
    carriage_weight_kg: Optional[float] = Field(default=None, ge=0, le=200)
    is_public: bool = True


class StationPublic(BaseModel):
    id: str
    exercise_id: str
    name: str
    gym_id: Optional[str]
    brand: Optional[str]
    model: Optional[str]
    loading: Optional[str]
    has_adjustable_profile: bool
    profile_settings: list[str]
    stack_ranges: list[dict]
    unit: str
    micro_adjust_kg: Optional[float]
    carriage_weight_kg: Optional[float]
    is_public: bool
    verified: bool
    log_count: int
    is_mine: bool


class AdjudicationPublic(BaseModel):
    id: str
    week_start: date
    verdict: Verdict
    headline: str
    explanation: str
    strength_index_delta_pct: Optional[float]
    weight_delta_pct_per_week: Optional[float]
    protein_g_per_kg: Optional[float]
    logging_adherence: Optional[float]
    previous_target: Optional[float]
    recommended_target: Optional[float]
    recommended_protein_g: Optional[float]
    math_breakdown: dict[str, Any]
    guardrails_triggered: list[str]
    user_accepted: Optional[bool]


# ---------------------------------------------------------------------------
# AI Trainer chat (pre-login quick question, see app/services/chat.py)
# ---------------------------------------------------------------------------


class ChatAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ChatAskResponse(BaseModel):
    answer: str


# ---------------------------------------------------------------------------
# Onboarding (see app/services/onboarding.py)
# ---------------------------------------------------------------------------


class OnboardingRequest(BaseModel):
    """The new-user questionnaire.

    Bounds are validation, not opinion: they exist to stop a typo (178 kg
    instead of 78 kg) from generating a 5,000 kcal plan. Anything genuinely
    outside them is a data-entry error, not an unusual user.
    """

    sex: Optional[str] = None
    date_of_birth: Optional[date] = None
    age_years: Optional[float] = Field(default=None, ge=13, le=100)
    height_cm: float = Field(gt=100, lt=250)
    weight_kg: float = Field(gt=25, lt=350)

    # The "have you ever weighed 200 lbs?" question. Optional, and None means
    # "didn't say" rather than "no" -- the service treats those differently.
    highest_weight_kg: Optional[float] = Field(default=None, gt=25, lt=400)

    lifting_experience_months: int = Field(ge=0, le=720)
    lifting_sessions_per_week: int = Field(ge=0, le=14)
    cardio_sessions_per_week: int = Field(ge=0, le=21)
    daily_steps: int = Field(ge=0, le=60_000)

    goal_type: GoalType
    goal_weight_kg: Optional[float] = Field(default=None, gt=25, lt=350)
    training_day_indices: Optional[list[int]] = None

    @field_validator("training_day_indices")
    @classmethod
    def _valid_days(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        if v is not None and any(d < 0 or d > 6 for d in v):
            raise ValueError("training_day_indices must be 0 (Mon) to 6 (Sun)")
        return v


class PlannedDaySchema(BaseModel):
    day: str
    index: int
    day_type: str
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int


class WeekPlanSchema(BaseModel):
    days: list[PlannedDaySchema]
    weekly_calories: int
    daily_average: int
    training_days: int
    rationale: str
    math: dict[str, Any]


class OnboardingPlanResponse(BaseModel):
    bmr: float
    activity_multiplier: float
    tdee_prior: float
    calorie_target: int
    protein_target_g: int
    carb_target_g: int
    fat_target_g: int
    fiber_target_g: int
    goal_rate_pct_per_week: float
    week: WeekPlanSchema
    adaptation_factor: float
    pct_below_peak: float
    notes: list[str]


# ---------------------------------------------------------------------------
# Recipes
# ---------------------------------------------------------------------------


class RecipeIngredientInput(BaseModel):
    """One line the user added to a recipe.

    `food_item_id` is optional: a hand-entered line is allowed, and the macros
    are then taken from this payload. When an id IS given the server re-reads
    the panel from the catalogue and ignores any macros sent here, so a client
    cannot invent nutrition for a real food.
    """

    food_item_id: Optional[str] = None
    display_name: str = Field(min_length=1, max_length=120)
    grams: float = Field(gt=0, le=20_000)
    quantity_label: Optional[str] = Field(default=None, max_length=60)
    note: Optional[str] = Field(default=None, max_length=200)

    # Used only when food_item_id is None. Same per-100 g ceilings as
    # CustomFoodRequest -- 900 kcal is pure fat and nothing exceeds it.
    calories: float = Field(default=0, ge=0, le=900)
    protein_g: float = Field(default=0, ge=0, le=100)
    carbs_g: float = Field(default=0, ge=0, le=100)
    fat_g: float = Field(default=0, ge=0, le=100)
    fiber_g: float = Field(default=0, ge=0, le=100)
    sugar_g: float = Field(default=0, ge=0, le=100)
    sodium_mg: float = Field(default=0, ge=0, le=40_000)
    saturated_fat_g: float = Field(default=0, ge=0, le=100)


class RecipeIngredientPublic(BaseModel):
    id: str
    food_item_id: Optional[str] = None
    display_name: str
    grams: float
    quantity_label: Optional[str] = None
    note: Optional[str] = None
    sort_order: int
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float


class RecipeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    cuisine: Optional[str] = Field(default=None, max_length=60)
    photo_url: Optional[str] = None
    servings: float = Field(default=1, ge=0.25, le=100)
    #: What the FINISHED dish weighed. Omit it and the recipe logs by serving
    #: only -- see services/recipes.py for why we will not derive this from
    #: the raw ingredient sum.
    cooked_weight_g: Optional[float] = Field(default=None, gt=0, le=50_000)
    prep_minutes: Optional[int] = Field(default=None, ge=0, le=2880)
    cook_minutes: Optional[int] = Field(default=None, ge=0, le=2880)
    steps: list[str] = []
    tags: list[str] = []
    visibility: RecipeVisibility = RecipeVisibility.private
    ingredients: list[RecipeIngredientInput] = []


class NutritionPanel(BaseModel):
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    sugar_g: float = 0
    sodium_mg: float = 0
    saturated_fat_g: float = 0


class RecipePublic(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    cuisine: Optional[str] = None
    photo_url: Optional[str] = None
    visibility: RecipeVisibility
    published_at: Optional[datetime] = None

    servings: float
    cooked_weight_g: Optional[float] = None
    #: True when nobody weighed the finished dish. The client MUST NOT offer
    #: gram-based logging in that case -- the server refuses it anyway.
    yield_estimated: bool
    serving_grams: Optional[float] = None

    prep_minutes: Optional[int] = None
    cook_minutes: Optional[int] = None
    steps: list[str] = []
    tags: list[str] = []

    total: NutritionPanel
    per_serving: NutritionPanel
    #: None when the finished weight is unknown. Rendering a per-100 g panel
    #: from the raw ingredient sum would understate every simmered dish.
    per_100g: Optional[NutritionPanel] = None
    ingredient_grams: float
    sourced_fraction: float
    warnings: list[str] = []

    ingredients: list[RecipeIngredientPublic] = []

    #: True when the caller owns this recipe. Drives edit/publish affordances.
    is_owner: bool = False
    is_saved: bool = False
    author_name: Optional[str] = None
    forked_from_id: Optional[str] = None
    save_count: int = 0
    log_count: int = 0
    created_at: datetime
    updated_at: datetime


class RecipeSummary(BaseModel):
    """The list-view row. Deliberately smaller than RecipePublic -- a library
    of 200 recipes should not ship 200 ingredient lists."""

    id: str
    name: str
    cuisine: Optional[str] = None
    photo_url: Optional[str] = None
    visibility: RecipeVisibility
    servings: float
    calories_per_serving: float
    protein_per_serving_g: float
    ingredient_count: int
    yield_estimated: bool
    author_name: Optional[str] = None
    is_owner: bool = False
    is_saved: bool = False
    save_count: int = 0
    log_count: int = 0
    updated_at: datetime


class RecipeListResponse(BaseModel):
    recipes: list[RecipeSummary]
    total: int


class PublishCheckResponse(BaseModel):
    """Why a recipe can or cannot be published.

    Returned on the dry-run endpoint AND in the 422 body of a refused publish,
    so the client renders one component either way.
    """

    ok: bool
    blockers: list[str] = []
    cautions: list[str] = []


class RecipeVisibilityRequest(BaseModel):
    visibility: RecipeVisibility
    #: Publishing with known cautions requires the user to have seen them.
    #: The client sends this after showing the list; the server does not
    #: enforce it, it only records intent.
    acknowledged_cautions: bool = False


class RecipeLogRequest(BaseModel):
    """Log a recipe as a meal.

    Exactly one of servings/grams is honoured, servings winning, because
    servings is exact and grams is derived from a weight that may never have
    been measured.
    """

    servings: Optional[float] = Field(default=None, gt=0, le=100)
    grams: Optional[float] = Field(default=None, gt=0, le=20_000)
    meal_type: MealType = MealType.snack
    logged_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Workout programming
#
# Bounds here mirror the CHECK constraints in models.py rather than replacing
# them. Validating in both places is deliberate: Pydantic gives the caller a
# legible 422 naming the field, and the database makes a bug in this layer a
# failed insert instead of bad advice on someone's screen.
# ---------------------------------------------------------------------------


class TrainingProfileRequest(BaseModel):
    """Create the caller's training profile. One per user."""

    days_per_week: int = Field(default=3, ge=1, le=7)
    available_days: list[str] = Field(default_factory=list)
    preferred_minutes: int = Field(default=60, ge=15, le=180)
    equipment: list[str] = Field(default_factory=list)
    disliked_exercise_ids: list[str] = Field(default_factory=list)
    #: Free text. HEALTH-SENSITIVE -- never logged, never echoed into an
    #: error message. See WORKOUT_SCHEMA_DESIGN.md 10.8.
    limitations: Optional[str] = Field(default=None, max_length=2000)
    #: Opt-in for AI-generated programming. Separate from users.program_type,
    #: and the stricter of the two: false disables AI generation whatever
    #: program_type says. Unused in the deterministic MVP.
    ai_enabled: bool = True


class TrainingProfilePatch(BaseModel):
    """Partial update. Only fields actually sent are applied.

    Every field is optional and there is no sentinel default, so
    `model_dump(exclude_unset=True)` distinguishes "not sent" from "sent as
    null" -- which matters for `limitations`, where clearing the field is a
    real thing a user may want to do.
    """

    days_per_week: Optional[int] = Field(default=None, ge=1, le=7)
    available_days: Optional[list[str]] = None
    preferred_minutes: Optional[int] = Field(default=None, ge=15, le=180)
    equipment: Optional[list[str]] = None
    disliked_exercise_ids: Optional[list[str]] = None
    limitations: Optional[str] = Field(default=None, max_length=2000)
    ai_enabled: Optional[bool] = None


class TrainingProfilePublic(BaseModel):
    id: str
    days_per_week: int
    available_days: list[str]
    preferred_minutes: int
    equipment: list[str]
    disliked_exercise_ids: list[str]
    limitations: Optional[str]
    ai_enabled: bool
    created_at: datetime
    updated_at: datetime


class ProgrammeRequest(BaseModel):
    """Generate a programme. Omitted fields fall back to the profile."""

    days_per_week: Optional[int] = Field(default=None, ge=1, le=7)


class ProgrammeDayPublic(BaseModel):
    id: str
    day_index: int
    label: str
    focus: list[str]
    target_minutes: Optional[int]


class ProgrammePublic(BaseModel):
    id: str
    name: str
    split_type: str
    days_per_week: int
    status: str
    generated_by: str
    started_at: datetime
    archived_at: Optional[datetime]
    days: list[ProgrammeDayPublic]


class PlannedSessionRequest(BaseModel):
    """Materialise one dated session from a programme day.

    `programme_day_id` omitted means "whichever day comes next in the
    rotation", which is what the client actually wants on the home screen.
    """

    scheduled_for: Optional[date] = None
    programme_day_id: Optional[str] = None


class ExerciseEducationPublic(BaseModel):
    """Why this exercise is here and how to perform it.

    COACHING LANGUAGE ONLY. Nothing in `form_cue` diagnoses, mentions injury,
    or implies medical advice, and it must stay that way.
    """

    primary_muscle: str
    secondary_muscles: list[str]
    movement_pattern: str
    form_cue: str


class PrescribedExercisePublic(BaseModel):
    id: str
    exercise_id: str
    exercise_name: str
    equipment: str
    order_index: int
    sets: int
    rep_min: int
    rep_max: int
    target_rir: int
    rest_seconds: int
    #: NULL until there is logged history to base it on. The client renders
    #: that as an em dash -- never as a number, and never as a guess.
    suggested_weight_kg: Optional[float]
    progression_rule: str
    status: str
    replaced_with_exercise_id: Optional[str]
    substitution_ids: list[str]
    education: Optional[ExerciseEducationPublic] = None


class PrescribedExercisePatch(BaseModel):
    """Skip a prescribed exercise, or swap it for another.

    `status` is the only required field, and the two legal transitions are
    deliberately narrow: a client may decline an exercise or substitute one,
    and may not invent an arbitrary state.
    """

    status: str = Field(pattern="^(skipped|replaced|prescribed)$")
    replaced_with_exercise_id: Optional[str] = None


class PlannedSessionPublic(BaseModel):
    id: str
    programme_day_id: Optional[str]
    programme_day_label: Optional[str]
    session_id: Optional[str]
    scheduled_for: date
    status: str
    estimated_minutes: Optional[int]
    generated_by: str
    notes: list[str]
    exercises: list[PrescribedExercisePublic]


class PlannedSessionStartPublic(BaseModel):
    """The handoff to the existing set-logging flow.

    `session_id` is a real WorkoutSession the untouched
    `POST /api/workouts/sessions/{id}/sets` endpoint already accepts, which is
    the whole point: programming hands over and stops.
    """

    planned_session_id: str
    session_id: str
    created: bool
