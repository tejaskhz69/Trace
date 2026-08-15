"""Weight logging and trend."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import User, WeightEntry
from ..schemas import WeightLogRequest, WeightTrendPoint
from ..services.tdee import trend_weight_series
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
