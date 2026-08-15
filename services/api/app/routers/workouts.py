"""Workout session and set logging -- the second data stream.

Logging speed is the whole game here. Hevy wins on one behaviour: it
auto-fills your previous performance so a set is two taps mid-workout. The
`GET /sessions/last-performance` endpoint below exists purely to make that
possible on the client.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import Exercise, SetLog, User, WorkoutSession
from ..schemas import SetLogRequest, StrengthPoint, WorkoutSessionRequest
from ..services.adjudication import epley_e1rm, ewma
from .auth import current_user

router = APIRouter(prefix="/api/workouts", tags=["workouts"])


@router.get("/exercises", response_model=list[dict])
async def list_exercises(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    q: str | None = Query(default=None),
) -> list[dict]:
    stmt = select(Exercise)
    if q:
        stmt = stmt.where(Exercise.name.ilike(f"%{q.strip()}%"))  # type: ignore[union-attr]
    rows = (await session.execute(stmt.limit(100))).scalars().all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "muscle_group": e.muscle_group,
            "equipment": e.equipment,
            "is_compound": e.is_compound,
        }
        for e in rows
    ]


@router.post("/sessions", status_code=201)
async def start_session(
    payload: WorkoutSessionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    ws = WorkoutSession(
        user_id=user.id,
        routine_name=payload.routine_name,
        started_at=payload.started_at or datetime.now(timezone.utc),
        notes=payload.notes,
    )
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return {"id": ws.id, "started_at": ws.started_at.isoformat()}


@router.post("/sessions/{session_id}/sets", status_code=201)
async def log_set(
    session_id: str,
    payload: SetLogRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    ws = await session.get(WorkoutSession, session_id)
    if ws is None or ws.user_id != user.id:
        raise HTTPException(status_code=404, detail="Workout session not found.")

    index = (
        await session.scalar(
            select(func.count(SetLog.id)).where(
                SetLog.session_id == session_id,
                SetLog.exercise_id == payload.exercise_id,
            )
        )
    ) or 0

    entry = SetLog(
        session_id=session_id,
        user_id=user.id,
        exercise_id=payload.exercise_id,
        set_index=index,
        weight_kg=payload.weight_kg,
        reps=payload.reps,
        rpe=payload.rpe,
        is_warmup=payload.is_warmup,
        e1rm=epley_e1rm(payload.weight_kg, payload.reps),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return {"id": entry.id, "set_index": entry.set_index, "e1rm": entry.e1rm}


@router.get("/sessions/last-performance")
async def last_performance(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    exercise_id: str = Query(...),
) -> dict:
    """The previous session's sets for this exercise, for client auto-fill.

    This single endpoint is what turns a mid-workout set entry from "type 4
    numbers" into "tap +, tap done". It is the highest-leverage 20 lines in
    the workout module.
    """
    last_session_id = await session.scalar(
        select(SetLog.session_id)
        .where(SetLog.user_id == user.id, SetLog.exercise_id == exercise_id)
        .order_by(SetLog.performed_at.desc())  # type: ignore[union-attr]
        .limit(1)
    )
    if not last_session_id:
        return {"sets": [], "best_e1rm": None}

    rows = (
        await session.execute(
            select(SetLog)
            .where(
                SetLog.session_id == last_session_id,
                SetLog.exercise_id == exercise_id,
                SetLog.is_warmup == False,  # noqa: E712
            )
            .order_by(SetLog.set_index)  # type: ignore[arg-type]
        )
    ).scalars().all()

    return {
        "sets": [
            {"weight_kg": r.weight_kg, "reps": r.reps, "rpe": r.rpe} for r in rows
        ],
        "best_e1rm": max((r.e1rm for r in rows if r.e1rm), default=None),
    }


@router.get("/strength/progress", response_model=list[StrengthPoint])
async def strength_progress(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    exercise_id: str = Query(...),
    days: int = Query(default=180, ge=14, le=1095),
) -> list[StrengthPoint]:
    """Weekly best e1RM, smoothed. The chart behind the strength verdict."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await session.execute(
            select(SetLog)
            .where(
                SetLog.user_id == user.id,
                SetLog.exercise_id == exercise_id,
                SetLog.performed_at >= since,
                SetLog.is_warmup == False,  # noqa: E712
            )
            .order_by(SetLog.performed_at)  # type: ignore[arg-type]
        )
    ).scalars().all()

    weekly: dict[date, list[SetLog]] = {}
    for r in rows:
        d = r.performed_at.date()
        week = d - timedelta(days=d.weekday())
        weekly.setdefault(week, []).append(r)

    out: list[StrengthPoint] = []
    running: list[float] = []
    for week in sorted(weekly):
        sets = weekly[week]
        best = max((s.e1rm for s in sets if s.e1rm), default=None)
        if best is None:
            continue
        running.append(best)
        out.append(
            StrengthPoint(
                week_start=week,
                best_e1rm=round(best, 1),
                e1rm_ewma=round(ewma(running) or best, 1),
                volume_load=round(sum(s.weight_kg * s.reps for s in sets), 1),
            )
        )
    return out
