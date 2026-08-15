"""The weekly verdict endpoint -- Trace's headline feature.

Wires the two pure engines (tdee.py + adjudication.py) to real user data.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import (
    Adjudication,
    BodyComposition,
    Exercise,
    MealLog,
    SetLog,
    User,
    Verdict as VerdictModel,
    WeightEntry,
    WorkoutSession,
)
from ..schemas import AdjudicationPublic
from ..services import adjudication as adj
from ..services import tdee as tdee_svc
from .auth import current_user

router = APIRouter(prefix="/api/adjudication", tags=["adjudication"])

WINDOW_DAYS = 21


def _age_years(dob: date | None) -> float:
    if dob is None:
        return 30.0
    return (date.today() - dob).days / 365.25


@router.get("/weekly", response_model=AdjudicationPublic)
async def weekly_verdict(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    recompute: bool = False,
) -> AdjudicationPublic:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    if not recompute:
        existing = await session.scalar(
            select(Adjudication).where(
                Adjudication.user_id == user.id, Adjudication.week_start == week_start
            )
        )
        if existing:
            return AdjudicationPublic.model_validate(existing, from_attributes=True)

    window_start = today - timedelta(days=WINDOW_DAYS)

    # --- Weight ---------------------------------------------------------
    weights = (
        await session.execute(
            select(WeightEntry)
            .where(
                WeightEntry.user_id == user.id,
                WeightEntry.measured_on >= window_start - timedelta(days=30),
            )
            .order_by(WeightEntry.measured_on)  # type: ignore[arg-type]
        )
    ).scalars().all()

    series = tdee_svc.trend_weight_series([(w.measured_on, w.weight_kg) for w in weights])
    in_window = [p for p in series if p[0] >= window_start]

    if len(in_window) < 2:
        raise HTTPException(
            status_code=422,
            detail="Not enough weigh-ins in the last three weeks to run a verdict.",
        )

    trend_start, trend_end = in_window[0][2], in_window[-1][2]
    weigh_in_count = sum(1 for _, raw, _ in in_window if raw is not None)
    current_weight = trend_end

    # --- Nutrition ------------------------------------------------------
    meal_rows = (
        await session.execute(
            select(
                func.date(MealLog.logged_at).label("d"),
                func.sum(MealLog.calories).label("kcal"),
                func.sum(MealLog.protein_g).label("protein"),
            )
            .where(
                MealLog.user_id == user.id,
                MealLog.logged_at
                >= datetime.combine(window_start, time.min, tzinfo=timezone.utc),
            )
            .group_by(func.date(MealLog.logged_at))
        )
    ).all()

    intake_by_day = {r.d: float(r.kcal or 0) for r in meal_rows}
    logged_days = len(intake_by_day)
    mean_protein = (
        sum(float(r.protein or 0) for r in meal_rows) / logged_days
        if logged_days
        else 0.0
    )

    # --- Training -------------------------------------------------------
    session_count = (
        await session.scalar(
            select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == user.id,
                WorkoutSession.started_at
                >= datetime.combine(window_start, time.min, tzinfo=timezone.utc),
            )
        )
    ) or 0

    set_rows = (
        await session.execute(
            select(SetLog, Exercise.name)
            .join(Exercise, Exercise.id == SetLog.exercise_id)  # type: ignore[arg-type]
            .where(
                SetLog.user_id == user.id,
                SetLog.performed_at
                >= datetime.combine(window_start, time.min, tzinfo=timezone.utc),
                SetLog.is_warmup == False,  # noqa: E712
            )
            .order_by(SetLog.performed_at)  # type: ignore[arg-type]
        )
    ).all()

    # Bucket into weeks per exercise.
    per_exercise: dict[str, dict] = {}
    for s, ex_name in set_rows:
        d = s.performed_at.date()
        wk = d - timedelta(days=d.weekday())
        bucket = per_exercise.setdefault(
            s.exercise_id, {"name": ex_name, "weeks": {}, "sessions": set()}
        )
        bucket["sessions"].add(s.session_id)
        if s.e1rm:
            bucket["weeks"][wk] = max(bucket["weeks"].get(wk, 0.0), s.e1rm)

    exercises = [
        adj.ExerciseWeeks(
            exercise_id=eid,
            name=b["name"],
            weekly_best_e1rm=[b["weeks"][w] for w in sorted(b["weeks"])],
            session_count=len(b["sessions"]),
        )
        for eid, b in per_exercise.items()
        if b["weeks"]
    ]

    # Program overlap: which exercises appear in both the first and last week?
    weeks_sorted = sorted({d for b in per_exercise.values() for d in b["weeks"]})
    if len(weeks_sorted) >= 2:
        first, last = weeks_sorted[0], weeks_sorted[-1]
        a = {e for e, b in per_exercise.items() if first in b["weeks"]}
        z = {e for e, b in per_exercise.items() if last in b["weeks"]}
        overlap = len(a & z) / len(a | z) if (a | z) else 1.0
    else:
        overlap = 1.0

    # --- Adjudicate ------------------------------------------------------
    result = adj.adjudicate(
        adj.AdjudicationInput(
            week_start=week_start,
            body_weight_kg=current_weight,
            trend_weight_start=trend_start,
            trend_weight_end=trend_end,
            window_days=WINDOW_DAYS,
            exercises=exercises,
            session_count=session_count,
            weigh_in_count=weigh_in_count,
            logged_food_days=logged_days,
            mean_protein_g=mean_protein,
            goal_type=user.goal_type.value,
            lifting_experience_months=user.lifting_experience_months,
            program_overlap=overlap,
        )
    )

    # --- Blend with the adaptive TDEE target -----------------------------
    prior_comp = await session.scalar(
        select(BodyComposition)
        .where(BodyComposition.user_id == user.id)
        .order_by(BodyComposition.week_start.desc())  # type: ignore[union-attr]
    )
    previous_target = prior_comp.calorie_target if prior_comp else None

    bmr = tdee_svc.mifflin_st_jeor(
        current_weight, user.height_cm or 175.0, _age_years(user.date_of_birth), user.sex
    )
    tdee_prior = bmr * user.activity_multiplier

    expenditure = tdee_svc.estimate_expenditure(
        intake_by_day=intake_by_day,
        trend_series=series,
        tdee_prior=tdee_prior,
    )
    targets = tdee_svc.recommend_targets(
        tdee=expenditure.tdee_blended,
        weight_kg=current_weight,
        goal_type=user.goal_type.value,
        previous_target=previous_target,
        bmr=bmr,
    )

    # The strength verdict overrides the pure weight-based nudge -- that is the
    # entire point of the feature.
    recommended = targets.calorie_target + result.recommended_calorie_delta

    record = Adjudication(
        user_id=user.id,
        week_start=week_start,
        verdict=VerdictModel(result.verdict.value),
        strength_index_delta_pct=result.strength_index_delta_pct,
        weight_delta_pct_per_week=result.weight_delta_pct_per_week,
        protein_g_per_kg=result.protein_g_per_kg,
        logging_adherence=result.logging_adherence,
        previous_target=previous_target,
        recommended_target=recommended,
        recommended_protein_g=result.recommended_protein_g
        or targets.protein_target_g,
        headline=result.headline,
        explanation=result.explanation,
        math_breakdown={
            "strength": result.math,
            "expenditure": {
                "tdee_prior": expenditure.tdee_prior,
                "tdee_observed": expenditure.tdee_observed,
                "tdee_blended": expenditure.tdee_blended,
                "confidence": expenditure.confidence,
                "logged_days": expenditure.logged_days,
                "weigh_ins": expenditure.weigh_ins,
                "notes": expenditure.notes,
            },
            "targets": targets.math,
            "strength_adjustment_kcal": result.recommended_calorie_delta,
        },
        guardrails_triggered=result.guardrails_triggered + expenditure.notes,
    )

    existing = await session.scalar(
        select(Adjudication).where(
            Adjudication.user_id == user.id, Adjudication.week_start == week_start
        )
    )
    if existing:
        await session.delete(existing)
        await session.flush()

    session.add(record)

    session.add(
        BodyComposition(
            user_id=user.id,
            week_start=week_start,
            trend_weight_kg=trend_end,
            tdee_observed=expenditure.tdee_observed,
            tdee_prior=expenditure.tdee_prior,
            tdee_blended=expenditure.tdee_blended,
            confidence=expenditure.confidence,
            calorie_target=recommended,
            protein_target_g=record.recommended_protein_g or targets.protein_target_g,
            fat_target_g=targets.fat_target_g,
            carb_target_g=targets.carb_target_g,
            fiber_target_g=targets.fiber_target_g,
        )
        if not prior_comp or prior_comp.week_start != week_start
        else prior_comp
    )

    await session.commit()
    await session.refresh(record)
    return AdjudicationPublic.model_validate(record, from_attributes=True)


@router.post("/{adjudication_id}/accept")
async def accept(
    adjudication_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    accepted: bool = True,
) -> dict:
    record = await session.get(Adjudication, adjudication_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found.")
    record.user_accepted = accepted
    session.add(record)
    await session.commit()
    return {"status": "ok", "user_accepted": accepted}
