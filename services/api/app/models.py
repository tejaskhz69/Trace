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

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel
from sqlmodel.sql.sqltypes import AutoString


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
    """Where a food's nutrition data came from.

    NAME vs VALUE, AND WHY IT MATTERS HERE
    SQLAlchemy's Enum type stores the member NAME in Postgres by default,
    while Pydantic validates against the member VALUE. For most enums in this
    file those are identical and nothing goes wrong. For this one they are
    not: `off` != `openfoodfacts`, `usda` != `usda_fdc`, `ai` != `ai_estimated`.

    That mismatch is invisible until the first non-`curated` row is READ back,
    at which point every search touching it 500s with a Pydantic enum error --
    a bug that is silent on write and fatal on read. `FOOD_SOURCE_COLUMN`
    below pins the column to VALUES so the two agree.
    """

    off = "openfoodfacts"
    usda = "usda_fdc"
    ifct = "ifct"
    curated = "curated"
    user = "user"
    ai = "ai_estimated"
    # Metered commercial sources. Rows from these are cached into this table
    # on first fetch so we pay once per product ever, not once per lookup --
    # see services/paid_sources.py.
    nutritionix = "nutritionix"


def _food_source_column() -> Column:
    """Store FoodSource by value, not by name. See the note above."""
    return Column(
        SAEnum(
            FoodSource,
            name="foodsource",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        server_default=FoodSource.curated.value,
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str

    # E.164, e.g. "+919876543210". Nullable because email accounts predate
    # phone sign-in and password users may never add one -- but UNIQUE where
    # present, because a phone number is the identity key for the OTP flow and
    # two accounts sharing one would make "log in with this number"
    # ambiguous.
    phone: Optional[str] = Field(default=None, index=True, unique=True)
    phone_verified_at: Optional[datetime] = Field(default=None, sa_type=TZDateTime)

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

    # --- Onboarding answers -------------------------------------------------
    # Collected once at signup and used only to seed the priors in
    # services/onboarding.py. The adaptive engine overwrites the numbers they
    # produce within ~3 weeks; these are kept so the plan can be explained
    # ("here is why we started you at 2,450") and re-derived if a user edits
    # an answer they got wrong.
    #
    # All nullable: they are additive columns on a table that already has rows,
    # and there are no migrations in this project -- see scripts/sync_schema.py.
    #
    # highest_weight_kg is the "have you ever weighed 200 lbs?" question. It is
    # NOT vanity data: someone at 70 kg who dieted down from 91 kg burns
    # measurably less than someone who has always been 70 kg, and starting them
    # on the textbook number stalls them from day one. None means "not asked",
    # which is deliberately distinct from "never been heavier".
    highest_weight_kg: Optional[float] = None
    daily_steps: Optional[int] = None
    cardio_sessions_per_week: Optional[int] = None
    lifting_sessions_per_week: Optional[int] = None
    onboarded_at: Optional[datetime] = Field(default=None, sa_type=TZDateTime)

    is_pro: bool = False
    timezone: str = "UTC"

    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class PhoneChallenge(SQLModel, table=True):
    """A one-time code sent by SMS, and the state that makes it safe.

    THE CODE IS HASHED, NEVER STORED IN PLAIN TEXT.
    It is a short-lived credential exactly like a password, and a database
    leak must not hand an attacker a list of live codes for numbers they can
    then sign in as. Same reasoning as RefreshToken above.

    WHY attempts AND sent_count BOTH EXIST
    They defend against two completely different attacks:

      attempts    guessing. A 6-digit code is 1-in-a-million per try, which is
                  strong only if the number of tries is small. Unbounded
                  attempts reduce it to a few thousand requests.
      sent_count  SMS pumping / toll fraud. Every send costs real money, so an
                  unthrottled "resend" is a way to spend our balance for us.
                  This is the attack people forget, and it arrives as a bill.
    """

    __tablename__ = "phone_challenges"
    __table_args__ = (Index("ix_phone_challenge_lookup", "phone", "expires_at"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    phone: str = Field(index=True)
    code_hash: str
    expires_at: datetime = Field(sa_type=TZDateTime)
    attempts: int = 0
    sent_count: int = 1
    consumed_at: Optional[datetime] = Field(default=None, sa_type=TZDateTime)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    # For per-IP throttling; a single number is cheap to rotate, an IP is less
    # so. Nullable because a proxy may not forward one.
    request_ip: Optional[str] = None


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
        # Phase 3a. Both are built CONCURRENTLY by migration e4f7b0d25c63
        # against the live table; declared here so `create_all` builds them
        # for tests and so autogenerate does not report drift.
        Index("ix_food_gtin14", "gtin14"),
        Index("ix_food_name_normalized", "name_normalized"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    source: FoodSource = Field(
        default=FoodSource.curated, sa_column=_food_source_column()
    )
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

    # --- Phase 3a: provenance and normalised lookup keys -------------------
    #
    # EVERY DEFAULT BELOW IS A CONSTANT LITERAL, deliberately. PostgreSQL 11+
    # adds a column with a constant DEFAULT by catalog update alone; a
    # non-constant default such as now() forces a full rewrite of all 578,773
    # rows. That is why `last_verified_at` defaults to NULL rather than to a
    # timestamp.

    #: Fail-closed. 'unknown' is a real value, never NULL: a row whose licence
    #: nobody has established must be excluded from exports, and NULL would
    #: make that a three-way test at every call site instead of one.
    source_licence: str = Field(
        default="unknown",
        sa_column=Column(Text, nullable=False, server_default="unknown"),
    )
    #: Deep link to the upstream record. The plan's rule is "do not hide the
    #: source"; a licence name alone does not let a user verify a number.
    source_url: Optional[str] = None
    #: 1-7, LOWER IS BETTER. See services/licensing.Tier. An ordinal, which
    #: `data_quality` cannot be: that float is smeared over 51 values with
    #: 107,863 rows on 0.51 alone, so it cannot express "a curated dish
    #: outranks a crowd-sourced product".
    verification_tier: int = Field(
        default=6,
        sa_column=Column(SmallInteger, nullable=False, server_default="6"),
    )
    last_verified_at: Optional[datetime] = Field(default=None, sa_type=TZDateTime)
    #: Normalised barcode, GTIN-14. `barcode` above is left EXACTLY as the
    #: source sent it -- this is an additional lookup key, never a
    #: replacement, so the existing /barcode endpoint is unaffected.
    gtin14: Optional[str] = None
    #: normalize(name), for exact-match ranking without a correlated subquery.
    name_normalized: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=""),
    )

    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class FoodAlias(SQLModel, table=True):
    """One name a food is known by, with provenance.

    WHY A TABLE AND NOT MORE JSONB
    `names_i18n` cannot be indexed per alias, cannot record where an alias came
    from, and cannot be moderated. Measured on the live catalogue: of 578,773
    rows, 347 carry any alias at all, 168 of those are empty lists -- including
    Sambar and Masala dosa -- and NOT ONE row anywhere holds a native-script
    name. That is why `पोहे`, `தோசை` and `சாம்பார்` each return zero results.

    `names_i18n` IS NOT REPLACED BY THIS TABLE. It also carries `basis`,
    `makes`, `data_notes`, `validation` and `preparation_key`, and
    routers/preparations.py reads `preparation_key` from it at runtime. This
    table sits alongside it; nothing migrates out of it.

    `food_items.search_text` stays the read cache, rebuilt from these rows --
    the same shape as Recipe caching its composition from RecipeIngredient. The
    search query is therefore unchanged, which is what preserves the measured
    257 ms by construction rather than by hope.
    """

    __tablename__ = "food_aliases"
    __table_args__ = (
        # `lang` IS NOT NULL FOR THIS CONSTRAINT'S SAKE.
        #
        # PostgreSQL treats NULLs as DISTINCT inside a UNIQUE constraint, so a
        # nullable `lang` would let ('poha', 'avalakki', NULL) be inserted an
        # unlimited number of times without ever colliding -- silently
        # disabling this constraint for exactly the rows least likely to carry
        # a language tag, i.e. transliterations. NULLS NOT DISTINCT would also
        # fix it but requires PG 15+; '' works on every version.
        UniqueConstraint(
            "food_item_id", "normalized", "lang", name="uq_alias_food_norm_lang"
        ),
        # Text + CHECK rather than PG enums: extending the vocabulary later is
        # then DROP/ADD CONSTRAINT inside an ordinary transaction, instead of
        # the ALTER TYPE dance that cannot run in one.
        CheckConstraint(
            "alias_type IN ('canonical','regional','transliteration',"
            "'colloquial','misspelling','brand_variant')",
            name="ck_alias_type",
        ),
        CheckConstraint(
            "source IN ('curated','import','ai','user')",
            name="ck_alias_source",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_alias_confidence",
        ),
        Index("ix_alias_normalized", "normalized"),
        Index(
            "ix_alias_normalized_trgm",
            "normalized",
            postgresql_using="gin",
            postgresql_ops={"normalized": "gin_trgm_ops"},
        ),
        Index("ix_alias_food", "food_item_id"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    #: AutoString, not Text, to match food_items.id exactly.
    food_item_id: str = Field(
        sa_column=Column(
            AutoString,
            ForeignKey("food_items.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    #: As displayed: 'पोहे', 'avalakki', "Haldiram's".
    alias: str = Field(sa_column=Column(Text, nullable=False))
    #: services.food_text.normalize(alias). What search actually matches on.
    normalized: str = Field(sa_column=Column(Text, nullable=False))
    #: BCP-47, or '' for unspecified. See the UniqueConstraint note above.
    lang: str = Field(
        default="", sa_column=Column(Text, nullable=False, server_default="")
    )
    #: ISO 15924: latn, deva, taml, telu, knda, beng, gujr, mlym, guru.
    script: str = Field(
        default="latn",
        sa_column=Column(Text, nullable=False, server_default="latn"),
    )
    alias_type: str = Field(sa_column=Column(Text, nullable=False))
    #: An AI-generated alias is searchable but must never raise a food's
    #: verification_tier. Recording provenance here is what keeps that
    #: enforceable rather than aspirational.
    source: str = Field(sa_column=Column(Text, nullable=False))
    confidence: float = Field(
        default=1.0, sa_column=Column(Float, nullable=False, server_default="1.0")
    )
    is_active: bool = Field(
        default=True, sa_column=Column(Boolean, nullable=False, server_default="true")
    )
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
    # Snapshotted like the macros above, for the Home screen's "worth watching"
    # ledger. Nullable rather than 0.0-defaulted because there is a real
    # difference between "this food contains no sodium" and "we don't know" --
    # summing unknowns as zero would under-report a day's sodium and quietly
    # tell a user they are under a limit they have actually blown.
    sodium_mg: Optional[float] = None
    potassium_mg: Optional[float] = None
    sugars_g: Optional[float] = None

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
# Recipes
# ---------------------------------------------------------------------------


class RecipeVisibility(str, enum.Enum):
    """Who can see a recipe.

    Two states, not three. There is no "pending" here on purpose: a moderation
    queue with nobody staffing it means nothing is ever published, which is
    indistinguishable from the feature not existing. Published recipes go live
    immediately and carry a low `data_quality`, rank below curated foods, and
    never feed the AI scan's reference panels.
    """

    private = "private"
    published = "published"


def _recipe_visibility_column() -> Column:
    """Store visibility by VALUE, for the same reason FoodSource does.

    SQLAlchemy's Enum stores the member NAME by default while Pydantic
    validates the VALUE. Here they happen to be identical, so nothing breaks
    today -- but the moment someone adds `unlisted = "link_only"` the mismatch
    becomes a read-time 500 on every recipe in the table. Pinning it to values
    now costs nothing and removes that trap.
    """
    return Column(
        SAEnum(
            RecipeVisibility,
            name="recipevisibility",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        server_default=RecipeVisibility.private.value,
    )


class Recipe(SQLModel, table=True):
    """A user's own dish, composed from catalogue foods.

    NUTRITION IS CACHED, NOT SNAPSHOTTED -- the opposite of MealLog, and
    deliberately so. A MealLog must never change after the fact, because it is
    a record of something that was eaten. A Recipe is a living document its
    author edits; when they fix an ingredient, the panel should follow. The
    cached columns below are recomputed from the ingredient rows on every
    write (see `services/recipes.compose`) and exist only so search and list
    views do not have to fan out to the ingredients of every row.

    So: editing a recipe changes the recipe, and changes nothing about the
    meals already logged from it.
    """

    __tablename__ = "recipes"
    __table_args__ = (
        Index("ix_recipe_owner", "user_id", "updated_at"),
        Index("ix_recipe_public", "visibility", "save_count"),
        Index(
            "ix_recipe_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)

    name: str
    description: Optional[str] = None
    cuisine: Optional[str] = None
    photo_url: Optional[str] = None

    visibility: RecipeVisibility = Field(
        default=RecipeVisibility.private, sa_column=_recipe_visibility_column()
    )
    published_at: Optional[datetime] = Field(default=None, sa_type=TZDateTime)

    #: How many portions the whole recipe makes. The exact logging unit --
    #: calories do not evaporate, so total/servings survives any cooking loss.
    servings: float = 1.0

    #: What the FINISHED dish weighed. None means nobody measured it, which is
    #: the common case and is why `per_100g_*` below are nullable. Deriving a
    #: per-100 g panel from the raw ingredient sum would understate every dish
    #: that lost water on the hob -- see services/recipes.py.
    cooked_weight_g: Optional[float] = None

    prep_minutes: Optional[int] = None
    cook_minutes: Optional[int] = None
    #: Free-text method, one string per step.
    steps: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSONB))

    # --- cached composition, recomputed on every ingredient write ----------
    total_calories: float = 0.0
    total_protein_g: float = 0.0
    total_carbs_g: float = 0.0
    total_fat_g: float = 0.0
    total_fiber_g: float = 0.0
    total_sugar_g: float = 0.0
    total_sodium_mg: float = 0.0
    total_saturated_fat_g: float = 0.0
    ingredient_grams: float = 0.0
    #: NULL when `cooked_weight_g` is NULL. A nullable column rather than a
    #: zero default, because "we do not know this dish's density" and "this
    #: dish has no calories" must never render the same way.
    per_100g_calories: Optional[float] = None
    #: Share of the calories traceable to a catalogue food rather than a
    #: hand-typed line. Drives the confidence marker on the panel.
    sourced_fraction: float = 1.0

    # --- social ------------------------------------------------------------
    #: Set when this recipe was copied from someone else's published one. The
    #: copy is fully independent; this is provenance, not a live link.
    forked_from_id: Optional[str] = Field(default=None, foreign_key="recipes.id")
    save_count: int = 0
    log_count: int = 0

    search_text: str = Field(default="", sa_column=Column(Text))

    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class RecipeIngredient(SQLModel, table=True):
    """One line of a recipe.

    The per-100 g panel is COPIED from the food item rather than joined at
    read time. Two reasons: a recipe must still compute after a food row is
    deleted upstream, and the author's totals should not silently shift
    because Open Food Facts revised a product last Tuesday. `food_item_id` is
    kept alongside for provenance and for the "swap this ingredient" flow.
    """

    __tablename__ = "recipe_ingredients"
    __table_args__ = (Index("ix_ringredient_recipe", "recipe_id", "sort_order"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    recipe_id: str = Field(foreign_key="recipes.id", index=True)
    #: None for a hand-entered line the user estimated themselves.
    food_item_id: Optional[str] = Field(default=None, foreign_key="food_items.id")

    display_name: str
    grams: float
    #: What the user actually typed, e.g. "2 medium onions". Kept verbatim so
    #: the recipe reads like a recipe rather than like a spreadsheet.
    quantity_label: Optional[str] = None
    note: Optional[str] = None
    sort_order: int = 0

    # Per 100 g, copied at add time.
    calories: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0
    sugar_g: float = 0.0
    sodium_mg: float = 0.0
    saturated_fat_g: float = 0.0

    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class RecipeSave(SQLModel, table=True):
    """Someone kept a published recipe in their library WITHOUT copying it.

    Distinct from a fork: a save follows the author's edits, a fork does not.
    Both exist because both are things people mean by "save" -- keeping a
    reference to somebody's recipe, versus taking it and making it yours.
    """

    __tablename__ = "recipe_saves"
    __table_args__ = (
        UniqueConstraint("user_id", "recipe_id", name="uq_recipe_save"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    recipe_id: str = Field(foreign_key="recipes.id", index=True)
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
    # Reps left in the tank. THIS is what turns a logged set into a
    # measurement of strength -- 75 kg x 10 with five left and 75 kg x 10 with
    # nothing left are different facts about the same lifter. Nullable because
    # every set logged before this column existed genuinely has no answer, and
    # defaulting those to 0 would retroactively inflate the whole history.
    rir: Optional[float] = None
    is_warmup: bool = False
    e1rm: Optional[float] = None  # computed on write, RIR-adjusted
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


class RideTrack(SQLModel, table=True):
    """Where a ride actually went.

    A SEPARATE TABLE, not columns on ExternalWorkout, for two reasons. The
    practical one: this repo has no migrations, so `create_all` can add a new
    table but cannot ALTER an existing one. The design one is better anyway --
    a track is a fat JSONB blob read only when someone opens a map, while
    `external_workouts` is scanned for every activity list in the app. Keeping
    the geometry out of that hot row is the right shape regardless.

    POINTS ARE STORED SIMPLIFIED. A two-hour ride at 1 Hz is ~7,000 fixes and
    no phone can render more than a few hundred on a 300 px canvas, so
    `services/routes.simplify` runs before the write. The elevation figures
    below are computed from the FULL track first -- simplifying and then
    counting climb would drop exactly the intermediate points the profile is
    made of.
    """

    __tablename__ = "ride_tracks"
    __table_args__ = (
        UniqueConstraint("workout_id", name="uq_ride_track_workout"),
        Index("ix_ride_user_time", "user_id", "started_at"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    #: The session this track belongs to. One track per workout.
    workout_id: str = Field(foreign_key="external_workouts.id", index=True)

    #: Denormalised from the workout so the map can be drawn without a join.
    sport: str = "cycling"
    started_at: datetime = Field(sa_type=TZDateTime)

    #: [[lat, lon, alt|null], ...], already simplified for drawing.
    points: list[Any] = Field(default_factory=list, sa_column=Column(JSONB))
    point_count: int = 0
    #: How many fixes the device actually gave us, before simplification.
    raw_point_count: int = 0

    #: Summed from the track. The device's own figure stays on
    #: ExternalWorkout.distance_km and wins wherever both exist -- a wheel
    #: sensor measures, a sum of GPS fixes approximates.
    track_distance_km: float = 0.0

    # --- elevation, computed from the full track before simplification ----
    #: NULL, not 0.0, when the device gave no altitude. "This ride was flat"
    #: and "we have no altitude for this ride" must never render alike.
    gain_m: Optional[float] = None
    loss_m: Optional[float] = None
    max_alt_m: Optional[float] = None
    min_alt_m: Optional[float] = None
    altitude_samples: int = 0

    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


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
