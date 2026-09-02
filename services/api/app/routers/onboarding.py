"""New-user questionnaire -> starting plan.

Thin, like every router here: all the arithmetic lives in
`services/onboarding.py` as pure functions, so it can be tested exhaustively
without a database. This layer only persists the answers and hands back what
the service computed.

TWO ENDPOINTS, DELIBERATELY:

  POST /api/onboarding/preview   computes a plan and saves NOTHING
  POST /api/onboarding           computes, saves the profile, returns the plan

The preview exists so the last step of the wizard can show a user their week
before they commit to it. Recomputing on submit rather than trusting a
client-supplied plan means the numbers can never be tampered with in transit.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import BodyComposition, User
from ..schemas import OnboardingPlanResponse, OnboardingRequest
from ..services.onboarding import build_plan
from .auth import current_user

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

# Used only when a user declines to give a birth date. Mifflin-St Jeor needs an
# age, and refusing to produce any plan over a missing optional field would be
# worse than being slightly wrong -- but the plan says so in its notes rather
# than quietly pretending this was measured.
ASSUMED_AGE_YEARS = 30.0


def _age_from(dob: date | None, explicit: float | None) -> tuple[float, bool]:
    """Return (age, was_assumed)."""
    if explicit is not None:
        return explicit, False
    if dob is not None:
        today = date.today()
        years = (today - dob).days / 365.25
        if 10 <= years <= 100:
            return years, False
    return ASSUMED_AGE_YEARS, True


def _to_response(plan, extra_notes: list[str]) -> OnboardingPlanResponse:
    return OnboardingPlanResponse(
        bmr=plan.bmr,
        activity_multiplier=plan.activity_multiplier,
        tdee_prior=plan.tdee_prior,
        calorie_target=plan.calorie_target,
        protein_target_g=plan.protein_target_g,
        carb_target_g=plan.carb_target_g,
        fat_target_g=plan.fat_target_g,
        fiber_target_g=plan.fiber_target_g,
        goal_rate_pct_per_week=plan.goal_rate_pct_per_week,
        week={
            "days": [d.__dict__ for d in plan.week.days],
            "weekly_calories": plan.week.weekly_calories,
            "daily_average": plan.week.daily_average,
            "training_days": plan.week.training_days,
            "rationale": plan.week.rationale,
            "math": plan.week.math,
        },
        adaptation_factor=plan.history.adaptation_factor,
        pct_below_peak=plan.history.pct_below_peak,
        notes=plan.notes + extra_notes,
    )


def _compute(payload: OnboardingRequest) -> tuple[object, list[str]]:
    age, assumed = _age_from(payload.date_of_birth, payload.age_years)

    plan = build_plan(
        sex=payload.sex,
        age_years=age,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        highest_weight_kg=payload.highest_weight_kg,
        daily_steps=payload.daily_steps,
        cardio_sessions_per_week=payload.cardio_sessions_per_week,
        lifting_sessions_per_week=payload.lifting_sessions_per_week,
        lifting_experience_months=payload.lifting_experience_months,
        goal_type=payload.goal_type.value,
        training_day_indices=payload.training_day_indices,
    )

    extra: list[str] = []
    if assumed:
        extra.append(
            f"No date of birth given, so we assumed {ASSUMED_AGE_YEARS:.0f}. "
            f"Add it in Settings for a sharper starting estimate."
        )
    return plan, extra


@router.post("/preview", response_model=OnboardingPlanResponse)
async def preview_plan(payload: OnboardingRequest) -> OnboardingPlanResponse:
    """Compute a plan without saving anything, or requiring an account.

    Unauthenticated on purpose: the wizard runs before a user has necessarily
    finished signing up, and there is nothing to leak -- the request contains
    only what the caller already typed, and the response is arithmetic over it.
    """
    plan, extra = _compute(payload)
    return _to_response(plan, extra)


@router.post("", response_model=OnboardingPlanResponse)
async def submit_onboarding(
    payload: OnboardingRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> OnboardingPlanResponse:
    """Save the questionnaire and seed week one's targets."""
    plan, extra = _compute(payload)

    user.sex = payload.sex or user.sex
    user.date_of_birth = payload.date_of_birth or user.date_of_birth
    user.height_cm = payload.height_cm
    user.starting_weight_kg = payload.weight_kg
    user.goal_weight_kg = payload.goal_weight_kg
    user.highest_weight_kg = payload.highest_weight_kg
    user.lifting_experience_months = payload.lifting_experience_months
    user.lifting_sessions_per_week = payload.lifting_sessions_per_week
    user.cardio_sessions_per_week = payload.cardio_sessions_per_week
    user.daily_steps = payload.daily_steps
    user.goal_type = payload.goal_type
    user.activity_multiplier = plan.activity_multiplier
    user.onboarded_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    session.add(user)

    # Seed week one so the Today screen has a target immediately instead of
    # showing "no goal set" until the first adjudication runs three weeks out.
    # `confidence=0.0` is the honest value: nothing here is observed yet, and
    # the UI keys off it to label these numbers as estimates.
    #
    # Re-running the wizard must not violate uq_bodycomp_week, so this looks
    # up the real row rather than relying on session.get() -- BodyComposition
    # is keyed on a surrogate `id`, and (user_id, week_start) is only a unique
    # constraint, so a primary-key fetch would silently miss every time.
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    existing = await session.scalar(
        select(BodyComposition).where(
            BodyComposition.user_id == user.id,
            BodyComposition.week_start == week_start,
        )
    )
    if existing is not None:
        existing.tdee_prior = plan.tdee_prior
        existing.tdee_blended = plan.tdee_prior
        existing.calorie_target = plan.calorie_target
        existing.protein_target_g = plan.protein_target_g
        existing.fat_target_g = plan.fat_target_g
        existing.carb_target_g = plan.carb_target_g
        existing.fiber_target_g = plan.fiber_target_g
        session.add(existing)
    else:
        session.add(
            BodyComposition(
                user_id=user.id,
                week_start=week_start,
                trend_weight_kg=payload.weight_kg,
                tdee_observed=None,
                tdee_prior=plan.tdee_prior,
                tdee_blended=plan.tdee_prior,
                confidence=0.0,
                calorie_target=plan.calorie_target,
                protein_target_g=plan.protein_target_g,
                fat_target_g=plan.fat_target_g,
                carb_target_g=plan.carb_target_g,
                fiber_target_g=plan.fiber_target_g,
            )
        )

    await session.commit()
    return _to_response(plan, extra)


@router.get("/status")
async def onboarding_status(
    user: Annotated[User, Depends(current_user)],
) -> dict:
    """Whether this user still needs the wizard.

    The client calls this straight after login to decide between the tabs and
    the questionnaire, so it stays deliberately tiny.
    """
    return {
        "onboarded": user.onboarded_at is not None,
        "onboarded_at": user.onboarded_at.isoformat() if user.onboarded_at else None,
    }
