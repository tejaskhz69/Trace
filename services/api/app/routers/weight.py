"""Weight logging, trend, and the measured-maintenance readout."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import MealLog, User, WeightEntry
from ..schemas import WeightLogRequest, WeightTrendPoint
from ..services.tdee import (
    estimate_expenditure,
    maintenance_history,
    maintenance_readout,
    mifflin_st_jeor,
    trend_weight_series,
)
from .auth import current_user

router = APIRouter(prefix="/api/weight", tags=["weight"])


@router.post("/log", status_code=201)
async def log_weight(
    payload: WeightLogRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    """One weigh-in per day. A second entry for the same day replaces it."""
    on = payload.measured_on or date.today()
    stmt = (
        pg_insert(WeightEntry)
        .values(user_id=user.id, weight_kg=payload.weight_kg, measured_on=on)
        .on_conflict_do_update(
            constraint="uq_weight_user_day", set_={"weight_kg": payload.weight_kg}
        )
        .returning(WeightEntry.id)
    )
    result = await session.execute(stmt)
    await session.commit()
    return {"id": result.scalar_one(), "measured_on": on.isoformat()}


@router.get("/trend", response_model=list[WeightTrendPoint])
async def weight_trend(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    days: int = Query(default=90, ge=7, le=730),
) -> list[WeightTrendPoint]:
    """Raw weigh-ins plus the smoothed trend line.

    Always render the trend prominently and the raw dots faintly. A user who
    sees a 1.5 kg overnight "gain" (salt, glycogen, time of day) and no trend
    line to contextualise it is a user who churns that week.
    """
    since = date.today() - timedelta(days=days)
    rows = (
        await session.execute(
            select(WeightEntry)
            .where(WeightEntry.user_id == user.id, WeightEntry.measured_on >= since)
            .order_by(WeightEntry.measured_on)  # type: ignore[arg-type]
        )
    ).scalars().all()

    series = trend_weight_series([(r.measured_on, r.weight_kg) for r in rows])
    return [
        WeightTrendPoint(date=d, raw_kg=raw, trend_kg=trend) for d, raw, trend in series
    ]


@router.get("/maintenance")
async def maintenance(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    days: int = Query(default=180, ge=30, le=730),
) -> dict:
    """The maintenance card: what we MEASURED your expenditure to be.

    THE POINT OF THIS ENDPOINT IS THE DISAGREEMENT. If our number always
    matched what a calculator predicts, this app would be an expensive
    calculator. When it comes back 200 kcal away from Mifflin-St Jeor, that
    gap is the product, and `vs_calculator` exists so the UI can show it.

    It always ships a band and a source line alongside the number. A bare
    figure invites more confidence than any expenditure estimate has earned,
    and the honest failure mode -- "still the calculator's guess, here is what
    would unlock a real measurement" -- is far better than a confident wrong
    number.
    """
    since = date.today() - timedelta(days=days)

    weights = (
        await session.execute(
            select(WeightEntry)
            .where(WeightEntry.user_id == user.id, WeightEntry.measured_on >= since)
            .order_by(WeightEntry.measured_on)  # type: ignore[arg-type]
        )
    ).scalars().all()

    # Intake per day, summed in the database rather than pulling every meal
    # row across the wire -- a year of logging is tens of thousands of rows.
    intake_rows = (
        await session.execute(
            select(
                func.date(MealLog.logged_at).label("day"),
                func.sum(MealLog.calories),
            )
            .where(MealLog.user_id == user.id, func.date(MealLog.logged_at) >= since)
            .group_by(func.date(MealLog.logged_at))  # type: ignore[arg-type]
        )
    ).all()
    intake_by_day: dict[date, float] = {
        (d if isinstance(d, date) else date.fromisoformat(str(d))): float(v or 0)
        for d, v in intake_rows
    }

    trend = trend_weight_series([(w.measured_on, w.weight_kg) for w in weights])

    # The prior. Falls back to the user's stored multiplier when we lack the
    # inputs for Mifflin -- which is the honest thing to do rather than
    # refusing to render the screen at all for a new account.
    latest_kg = trend[-1][2] if trend else (user.starting_weight_kg or 75.0)
    if user.date_of_birth and user.height_cm:
        today = date.today()
        age = (today - user.date_of_birth).days / 365.25
        bmr = mifflin_st_jeor(latest_kg, user.height_cm, age, user.sex)
    else:
        bmr = 10 * latest_kg + 625.0  # rough RMR when height/age are missing
    prior = bmr * user.activity_multiplier

    result = estimate_expenditure(
        intake_by_day=intake_by_day, trend_series=trend, tdee_prior=prior
    )

    # "What am I eating lately" is the last 14 days of days that were actually
    # logged. Averaging over calendar days instead would divide by days the
    # user never opened the app and report a fictitious deficit.
    recent_cut = date.today() - timedelta(days=14)
    recent = [v for d, v in intake_by_day.items() if d >= recent_cut and v > 0]
    eating = sum(recent) / len(recent) if recent else None

    readout = maintenance_readout(
        result,
        recent_intake_kcal=eating,
        total_weigh_ins=len(weights),
        total_logged_days=len([v for v in intake_by_day.values() if v > 0]),
    )

    return {
        "maintenance_kcal": readout.maintenance_kcal,
        "band_low": readout.band_low,
        "band_high": readout.band_high,
        "dialed_pct": readout.dialed_pct,
        "is_data_driven": readout.is_data_driven,
        "prior_kcal": readout.prior_kcal,
        "observed_kcal": readout.observed_kcal,
        "vs_calculator": readout.vs_calculator,
        "weigh_ins": readout.weigh_ins,
        "logged_days": readout.logged_days,
        "eating_kcal": readout.eating_kcal,
        "eating_delta": readout.eating_delta,
        "expected_rate_kg_per_week": readout.expected_rate_kg_per_week,
        "source_line": readout.source_line,
        "notes": result.notes,
        "history": maintenance_history(
            intake_by_day=intake_by_day,
            trend_series=trend,
            tdee_prior=prior,
        ),
    }
