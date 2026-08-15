"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from .models import FoodSource, GoalType, MealType, Verdict


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
    rpe: Optional[float] = Field(default=None, ge=1, le=10)
    is_warmup: bool = False


class WorkoutSessionRequest(BaseModel):
    routine_name: Optional[str] = None
    started_at: Optional[datetime] = None
    notes: Optional[str] = None


class StrengthPoint(BaseModel):
    week_start: date
    best_e1rm: float
    e1rm_ewma: float
    volume_load: float


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
