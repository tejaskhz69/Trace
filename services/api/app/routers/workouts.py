"""Workout session and set logging -- the second data stream.

Logging speed is the whole game here. Hevy wins on one behaviour: it
auto-fills your previous performance so a set is two taps mid-workout. The
`GET /sessions/last-performance` endpoint below exists purely to make that
possible on the client.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import case, func, or_
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import Exercise, Gym, SetLog, Station, User, WorkoutSession
from ..schemas import (
    PlateauAssessmentPublic,
    PlateauPerformance,
    SetLogRequest,
    StationCreate,
    StationPublic,
    StrengthPoint,
    StrengthSeries,
    VoiceCommitRequest,
    WorkoutSessionRequest,
)
from ..services import strength
from ..services.adjudication import MIN_SESSIONS
from ..services.plateau import (
    Exposure as PlateauExposure,
)
from ..services.plateau import (
    Series as PlateauSeries,
)
from ..services.plateau import (
    SeriesKey as PlateauSeriesKey,
)
from ..services.plateau import (
    assess_plateau,
)
from ..services.strength import ewma_over_weeks
from ..services.workout_voice import transcribe_workout
from .auth import current_user

# How far back a "current best" reaches. Long enough that a deload week does
# not reset your record, short enough that a personal best from last winter is
# not the bar you are held to today.
REFERENCE_WINDOW_DAYS = 42

router = APIRouter(prefix="/api/workouts", tags=["workouts"])


def _alias_match(needle: str):
    r"""`EXISTS (SELECT 1 FROM jsonb_array_elements_text(aliases) WHERE ... ILIKE)`.

    Written as a correlated EXISTS rather than the shorter
    `aliases.cast(Text).ilike(...)`, because casting the whole array to text
    matches ACROSS element boundaries -- a search would hit the `", "` between
    two unrelated aliases and return a movement nobody asked for. Matching
    each element separately is the honest test, and it is what makes brand
    search trustworthy enough to be the primary way people find a machine.

    Aliases get the same token-prefix treatment as names, and for the same
    reason: without it "row" still reached Narrow Stance Squats through the
    alias "narrow stance squat", having been filtered out of the name side.
    That row is why the name-side fix alone was not enough -- it was the one
    removal of eleven that a name-only audit could not see.
    """
    return sa_text(
        "EXISTS (SELECT 1 FROM jsonb_array_elements_text(exercises.aliases)"
        " AS alias WHERE alias ~* ('\\m' || :alias_prefix))"
    ).bindparams(alias_prefix=re.escape(needle.strip("%")))


def _exact_alias_match(needle: str):
    """The movement that OWNS this term, as opposed to merely containing it."""
    return sa_text(
        "EXISTS (SELECT 1 FROM jsonb_array_elements_text(exercises.aliases) AS alias"
        " WHERE lower(alias) = lower(:exact_needle))"
    ).bindparams(exact_needle=needle)


def _name_match(needle: str):
    r"""Match the name at a TOKEN PREFIX -- Postgres `\m`, not `\y`.

    The query must start a word; it need not end one. That single rule is
    correct at every length, which is why there is no short-query special
    case here any more.

    WHY NOT A WORD BOUNDARY ON BOTH SIDES. `\yrow\y` does not match "Rows",
    and the catalogue is full of plurals. Measured over all 897 rows:

        query      \y..\y   \m     lost by the two-sided rule
        row          55      61    Seated Cable Rows, Elevated Cable Rows
        fly          13      26    Dumbbell Flyes, Bodyweight Flyes
        curl         77      88    Concentration Curls, Finger Curls
        dip           6      10    Bench Dips, Ring Dips
        pulldown     18      20    Underhand Cable Pulldowns

    `fly` loses HALF its results. Note `pulldown` too: a long query is
    damaged as well, so there is no length at which the two-sided rule
    becomes the right one.

    Token-prefix still excludes the coincidences that started this --
    "th(row)" and "na(rrow)" have the query starting mid-token, so `\m`
    rejects them exactly as the old rule did.

    """
    # The needle reaches a regex, so metacharacters have to be escaped: a
    # user typing "c++" must search for "c++", not raise a regex error.
    return sa_text(
        r"exercises.name ~* ('\m' || :name_prefix)"
    ).bindparams(name_prefix=re.escape(needle))


@router.get("/exercises", response_model=list[dict])
async def list_exercises(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    q: str | None = Query(default=None),
) -> list[dict]:
    """Search a movement by name OR by alias.

    THE ALIAS HALF IS LOAD-BEARING, NOT A CONVENIENCE.
    It is the entire mechanism by which "prime row" and "hammer strength row"
    reach Chest-Supported Row. Without it the only way to find your machine is
    to give it its own catalogue row, which splits one trend into five and
    makes `adjudication.MIN_SESSIONS = 8` unreachable for anybody who trains a
    lift once a week. Search finds the machine; the trend stays continuous.
    """
    stmt = select(Exercise)
    if q:
        needle = q.strip()
        like = f"%{needle}%"
        stmt = stmt.where(
            or_(
                _name_match(needle),
                _alias_match(like),
            )
        ).order_by(
            # Best match first. AN EXACT ALIAS SITS SECOND, ABOVE EVERY
            # PARTIAL NAME MATCH. Without that tier "lateral raise" returned
            # "Lateral Raise - With Bands" first and the movement that
            # actually owns the alias, Dumbbell Lateral Raise, came sixth.
            # Aliases are how a nameplate or brand term reaches a movement at
            # all; ranking them below every substring hit defeats the thing
            # they exist for.
            case(
                (func.lower(Exercise.name) == needle.lower(), 0),
                (_exact_alias_match(needle), 1),
                (Exercise.name.ilike(f"{needle}%"), 2),  # type: ignore[union-attr]
                (Exercise.name.ilike(like), 3),  # type: ignore[union-attr]
                else_=4,
            ),
            Exercise.name,
        )
    else:
        stmt = stmt.order_by(Exercise.name)

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


@router.get("/catalogue")
async def exercise_catalogue(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    q: str | None = Query(default=None, max_length=80),
    limit_per_group: int = Query(default=50, le=200),
) -> dict:
    """The Trainer tab's exercise list: grouped by muscle, with the user's
    own working weight and trend against last week.

    ONE QUERY FOR THE WHOLE LIST, not one per row. A naive implementation
    fetches 736 exercises then asks the database for each one's history, which
    is 737 round trips -- and at ~130 ms each against a database in another
    region that is a minute and a half of loading. The two aggregates below
    are computed set-wise and joined in memory.

    `working_weight` is the heaviest non-warmup set in the last 30 days, not
    an all-time best: the list is answering "what am I lifting on this right
    now", and a PR from eight months ago is the wrong answer to that.
    """
    now = datetime.now(UTC)
    recent_cut = now - timedelta(days=30)
    this_week_cut = now - timedelta(days=7)
    last_week_cut = now - timedelta(days=14)

    stmt = select(Exercise)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        # Match the muscle group too, so "chest" finds the chest exercises
        # rather than only the ones with "chest" in their name.
        stmt = stmt.where(
            Exercise.name.ilike(needle) | Exercise.muscle_group.ilike(needle)  # type: ignore[union-attr]
        )
    exercises = (await session.execute(stmt)).scalars().all()

    # Heaviest working set per exercise in the last 30 days.
    working = dict(
        (
            await session.execute(
                select(SetLog.exercise_id, func.max(SetLog.weight_kg))
                .where(
                    SetLog.user_id == user.id,
                    SetLog.performed_at >= recent_cut,
                    SetLog.is_warmup == False,  # noqa: E712
                )
                .group_by(SetLog.exercise_id)  # type: ignore[arg-type]
            )
        ).all()
    )

    # Best e1RM this week and the week before, for the trend arrow. e1RM
    # rather than raw weight, so adding a rep counts as progress -- which is
    # what actually happens between sessions.
    async def best_e1rm(since, until) -> dict[str, float]:
        rows = (
            await session.execute(
                select(SetLog.exercise_id, func.max(SetLog.e1rm))
                .where(
                    SetLog.user_id == user.id,
                    SetLog.performed_at >= since,
                    SetLog.performed_at < until,
                    SetLog.is_warmup == False,  # noqa: E712
                )
                .group_by(SetLog.exercise_id)  # type: ignore[arg-type]
            )
        ).all()
        return {k: v for k, v in rows if v is not None}

    this_week = await best_e1rm(this_week_cut, now)
    last_week = await best_e1rm(last_week_cut, this_week_cut)

    groups: dict[str, list[dict]] = {}
    for e in exercises:
        now_v, prev_v = this_week.get(e.id), last_week.get(e.id)
        # Only claim a delta when BOTH weeks have data. "0.0%" against a week
        # you didn't train is a fabricated comparison, and the client renders
        # a null as a dash instead.
        delta = (
            round((now_v - prev_v) / prev_v * 100, 1)
            if now_v is not None and prev_v not in (None, 0)
            else None
        )
        groups.setdefault(e.muscle_group, []).append(
            {
                "id": e.id,
                "name": e.name,
                "muscle_group": e.muscle_group,
                "secondary_muscles": e.secondary_muscles or [],
                "equipment": e.equipment,
                "is_compound": e.is_compound,
                "working_weight_kg": working.get(e.id),
                "delta_pct": delta,
            }
        )

    # Exercises the user actually lifts float to the top of their group; the
    # rest fall back to alphabetical so the list is predictable.
    out = []
    for name in sorted(groups):
        items = sorted(
            groups[name],
            key=lambda x: (x["working_weight_kg"] is None, x["name"].lower()),
        )
        out.append(
            {
                "muscle_group": name,
                "count": len(items),
                "exercises": items[:limit_per_group],
            }
        )
    # Groups the user has trained come first.
    out.sort(key=lambda g: (not any(e["working_weight_kg"] for e in g["exercises"]),))
    return {"groups": out, "total": len(exercises)}


@router.post("/sessions", status_code=201)
async def start_session(
    payload: WorkoutSessionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    ws = WorkoutSession(
        user_id=user.id,
        routine_name=payload.routine_name,
        started_at=payload.started_at or datetime.now(UTC),
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

    # RIR is the honest input; RPE is the same scale inverted. Accept either,
    # prefer RIR, and store both so nothing the user actually typed is lost.
    rir = payload.rir
    if rir is None and payload.rpe is not None:
        rir = max(0.0, 10.0 - payload.rpe)
    rpe = payload.rpe if payload.rpe is not None else strength.rpe_from_rir(rir)

    reference = (
        None
        if payload.is_warmup
        else await _reference_e1rm(session, user.id, payload.exercise_id)
    )
    ex = await session.get(Exercise, payload.exercise_id)

    # A station id we cannot honour is a 422, never a silent NULL. Dropping it
    # quietly would move the set into the "not recorded" series without
    # telling anybody, which is exactly the kind of invisible trend split this
    # whole model exists to prevent.
    station = await _resolve_station(session, user.id, payload)

    entry = SetLog(
        session_id=session_id,
        user_id=user.id,
        exercise_id=payload.exercise_id,
        set_index=index,
        weight_kg=payload.weight_kg,
        reps=payload.reps,
        rpe=rpe,
        rir=rir,
        is_warmup=payload.is_warmup,
        station_id=station.id if station else None,
        station_profile=payload.station_profile,
        # RIR-adjusted, not plain Epley. A set stopped three reps short is
        # evidence of a heavier set, and ignoring that under-rates almost
        # every set a sensible lifter performs.
        e1rm=strength.e1rm(payload.weight_kg, payload.reps, rir),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    # The verdict travels back with the write, so the client renders it
    # without a second round trip while the lifter is still standing there.
    a = strength.assess_set(
        weight_kg=payload.weight_kg,
        reps=payload.reps,
        rir=rir,
        reference_e1rm=reference,
        equipment=ex.equipment if ex else None,
    )
    return {
        "id": entry.id,
        "set_index": entry.set_index,
        "e1rm": entry.e1rm,
        "rir": rir,
        "rpe": rpe,
        "verdict": a.verdict.value,
        "headline": a.headline,
        "detail": a.detail,
        "load_pct": a.load_pct,
        "reference_e1rm": a.reference_e1rm,
        "route": {
            "reps_needed": a.route.reps_needed,
            "weight_needed_kg": a.route.weight_needed_kg,
        },
    }


async def _reference_e1rm(
    session: AsyncSession, user_id: str, exercise_id: str
) -> float | None:
    """The best estimate we already had for this lift.

    Warm-ups are excluded. A warm-up single at 60% is not a claim about your
    max, and letting one set the reference would make it bounce around and
    turn every real working set into a fake personal record.
    """
    since = datetime.now(UTC) - timedelta(days=REFERENCE_WINDOW_DAYS)
    return await session.scalar(
        select(func.max(SetLog.e1rm)).where(
            SetLog.user_id == user_id,
            SetLog.exercise_id == exercise_id,
            SetLog.performed_at >= since,
            SetLog.is_warmup == False,  # noqa: E712
        )
    )


@router.get("/sessions/{session_id}/next-set")
async def next_set(
    session_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    exercise_id: str = Query(...),
) -> dict:
    """Everything the live set screen needs, in one request.

    The lifter is standing at the bar between sets. Two round trips is one too
    many, so the prescription, the reference max, what they have already done
    in this session and the rest timer all come back together.
    """
    ws = await session.get(WorkoutSession, session_id)
    if ws is None or ws.user_id != user.id:
        raise HTTPException(status_code=404, detail="Workout session not found.")

    ex = await session.get(Exercise, exercise_id)
    if ex is None:
        raise HTTPException(status_code=404, detail="Exercise not found.")

    reference = await _reference_e1rm(session, user.id, exercise_id)

    done = (
        await session.execute(
            select(SetLog)
            .where(
                SetLog.session_id == session_id,
                SetLog.exercise_id == exercise_id,
            )
            .order_by(SetLog.set_index)  # type: ignore[arg-type]
        )
    ).scalars().all()

    # Prefer the last set in THIS session; fall back to the last one anywhere.
    last = next((s for s in reversed(done) if not s.is_warmup), None)
    if last is None:
        last = (
            await session.execute(
                select(SetLog)
                .where(
                    SetLog.user_id == user.id,
                    SetLog.exercise_id == exercise_id,
                    SetLog.is_warmup == False,  # noqa: E712
                )
                .order_by(SetLog.performed_at.desc())  # type: ignore[union-attr]
                .limit(1)
            )
        ).scalars().first()

    p = strength.prescribe_next_set(
        last_weight_kg=last.weight_kg if last else None,
        last_reps=last.reps if last else None,
        last_rir=last.rir if last else None,
        reference_e1rm=reference,
        is_compound=ex.is_compound,
        equipment=ex.equipment,
    )

    return {
        "exercise": {
            "id": ex.id,
            "name": ex.name,
            "muscle_group": ex.muscle_group,
            "equipment": ex.equipment,
            "is_compound": ex.is_compound,
        },
        "reference_e1rm": round(reference, 1) if reference else None,
        "weight_step_kg": strength.weight_step(ex.equipment),
        "prescription": {
            "weight_kg": p.weight_kg,
            "reps": p.reps,
            "target_rir": p.target_rir,
            "rest_s": p.rest_s,
            "note": p.note,
        },
        "sets_done": [
            {
                "set_index": s.set_index,
                "weight_kg": s.weight_kg,
                "reps": s.reps,
                "rir": s.rir,
                "e1rm": s.e1rm,
                "is_warmup": s.is_warmup,
                "verdict": (
                    None
                    if s.is_warmup
                    else strength.assess_set(
                        weight_kg=s.weight_kg,
                        reps=s.reps,
                        rir=s.rir,
                        reference_e1rm=reference,
                    ).verdict.value
                ),
            }
            for s in done
        ],
    }


@router.post("/sessions/{session_id}/finish")
async def finish_session(
    session_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    """Close the session and hand back the summary in the same response."""
    ws = await session.get(WorkoutSession, session_id)
    if ws is None or ws.user_id != user.id:
        raise HTTPException(status_code=404, detail="Workout session not found.")
    if ws.ended_at is None:
        ws.ended_at = datetime.now(UTC)
        session.add(ws)
        await session.commit()
    return await session_summary(session_id, session, user)


@router.get("/sessions/{session_id}/summary")
async def session_summary(
    session_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    """The SESSION COMPLETE card: what that hour in the gym actually proved."""
    ws = await session.get(WorkoutSession, session_id)
    if ws is None or ws.user_id != user.id:
        raise HTTPException(status_code=404, detail="Workout session not found.")

    rows = (
        await session.execute(
            select(SetLog, Exercise.name, Exercise.muscle_group)
            .join(Exercise, Exercise.id == SetLog.exercise_id)  # type: ignore[arg-type]
            .where(SetLog.session_id == session_id)
            .order_by(SetLog.performed_at)  # type: ignore[arg-type]
        )
    ).all()

    logged = [
        strength.LoggedSet(
            exercise_id=s.exercise_id,
            exercise_name=name,
            weight_kg=s.weight_kg,
            reps=s.reps,
            rir=s.rir,
            is_warmup=s.is_warmup,
            e1rm=s.e1rm,
        )
        for s, name, _ in rows
    ]

    # Muscle split, by share of the session's volume rather than by set count.
    # Sets treat a 20 kg lateral raise and a 140 kg squat as equal work, which
    # is how a leg day ends up reading as "40% shoulders".
    split_load: dict[str, float] = {}
    for s, _, muscle in rows:
        split_load[muscle] = split_load.get(muscle, 0.0) + s.weight_kg * s.reps
    split_total = sum(split_load.values())
    muscle_split = [
        {"muscle": m, "volume_kg": round(v, 1),
         "pct": round(v / split_total * 100, 1) if split_total else 0.0}
        for m, v in sorted(split_load.items(), key=lambda kv: -kv[1])
    ]

    # The reference each lift is judged against must EXCLUDE this session --
    # otherwise every set is compared against itself and nothing is ever a
    # personal record. One query for all of them, not one per exercise.
    since = ws.started_at - timedelta(days=REFERENCE_WINDOW_DAYS)
    prev_rows = (
        await session.execute(
            select(SetLog.exercise_id, func.max(SetLog.e1rm))
            .where(
                SetLog.user_id == user.id,
                SetLog.session_id != session_id,
                SetLog.performed_at >= since,
                SetLog.performed_at < ws.started_at,
                SetLog.is_warmup == False,  # noqa: E712
            )
            .group_by(SetLog.exercise_id)  # type: ignore[arg-type]
        )
    ).all()
    previous = {k: v for k, v in prev_rows if v is not None}

    ended = ws.ended_at or datetime.now(UTC)
    duration = max(0, int((ended - ws.started_at).total_seconds() // 60))

    s = strength.summarise_session(
        logged, previous_bests=previous, duration_min=duration or None
    )

    return {
        "session_id": session_id,
        "routine_name": ws.routine_name,
        "started_at": ws.started_at.isoformat(),
        "ended_at": ws.ended_at.isoformat() if ws.ended_at else None,
        "duration_min": s.duration_min,
        "total_sets": s.total_sets,
        "total_reps": sum(r.reps for r, _, _ in rows),
        "volume_kg": s.volume_kg,
        "avg_rpe": s.avg_rpe,
        "muscle_split": muscle_split,
        "purple_sets": s.purple_sets,
        "lifts_moved_up": s.lifts_moved_up,
        "headline": s.headline,
        "exercises": [
            {
                "exercise_id": e.exercise_id,
                "name": e.exercise_name,
                "sets": e.sets,
                "top_weight_kg": e.top_weight_kg,
                "volume_kg": e.volume_kg,
                "best_e1rm": e.best_e1rm,
                "previous_e1rm": e.previous_e1rm,
                "delta_pct": e.delta_pct,
                "trend": e.trend.value,
                "set_verdicts": e.set_verdicts,
            }
            for e in s.exercises
        ],
    }


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


# ---------------------------------------------------------------------------
# Stations -- which machine, not which movement
# ---------------------------------------------------------------------------


async def _resolve_station(
    session: AsyncSession, user_id: str, payload: SetLogRequest
) -> Station | None:
    """Validate an optional station reference and bump its use count.

    Returns None when no station was supplied, which is the common case and a
    perfectly good answer: barbell lifts have no station, and nobody is ever
    blocked from logging because they cannot name the machine.
    """
    if payload.station_id is None:
        return None

    station = await session.get(Station, payload.station_id)
    if station is None or station.exercise_id != payload.exercise_id:
        raise HTTPException(status_code=422, detail="Unknown station for this exercise.")
    if not station.is_public and station.created_by_user_id != user_id:
        # Indistinguishable from "does not exist", on purpose.
        raise HTTPException(status_code=422, detail="Unknown station for this exercise.")

    if payload.station_profile and station.profile_settings:
        if payload.station_profile not in station.profile_settings:
            raise HTTPException(
                status_code=422,
                detail="That setting is not one this machine has.",
            )

    # Ordering key for the picker: the machine people actually use floats up.
    station.log_count += 1
    session.add(station)
    return station


def _station_public(station: Station, user_id: str) -> StationPublic:
    return StationPublic(
        id=station.id,
        exercise_id=station.exercise_id,
        name=station.name,
        gym_id=station.gym_id,
        brand=station.brand,
        model=station.model,
        loading=station.loading,
        has_adjustable_profile=station.has_adjustable_profile,
        profile_settings=station.profile_settings or [],
        stack_ranges=station.stack_ranges or [],
        unit=station.unit,
        micro_adjust_kg=station.micro_adjust_kg,
        carriage_weight_kg=station.carriage_weight_kg,
        is_public=station.is_public,
        verified=station.verified,
        log_count=station.log_count,
        is_mine=station.created_by_user_id == user_id,
    )


@router.get("/stations", response_model=list[StationPublic])
async def list_stations(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    exercise_id: str = Query(...),
    gym_id: str | None = Query(default=None),
) -> list[StationPublic]:
    """Which machines exist for this movement, here.

    PUBLIC STATIONS FROM OTHER MEMBERS ARE INCLUDED, and that is the point.
    Once one person at a gym names the PRIME Extreme Row, everybody who joins
    later finds it already there. We are never going to maintain a worldwide
    hardware database; the members of each gym know their own equipment and we
    do not.
    """
    visible = or_(Station.is_public == True, Station.created_by_user_id == user.id)  # noqa: E712
    stmt = select(Station).where(Station.exercise_id == exercise_id, visible)
    if gym_id is not None:
        # A lifter with no gym still sees the stations they named themselves.
        stmt = stmt.where(
            or_(
                Station.gym_id == gym_id,
                (Station.gym_id.is_(None)) & (Station.created_by_user_id == user.id),
            )
        )
    stmt = stmt.order_by(Station.log_count.desc(), Station.name).limit(100)  # type: ignore[union-attr]

    rows = (await session.execute(stmt)).scalars().all()
    return [_station_public(r, user.id) for r in rows]


@router.post("/stations", response_model=StationPublic, status_code=201)
async def create_station(
    payload: StationCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> StationPublic:
    """Name a machine. Free text, one required field.

    Stations are created lazily, from logging -- the first time you log a
    movement the app asks "which machine?" and this is what answers it. There
    is no gym setup step, and there never will be: an inventory screen before
    somebody's first set is how you lose them before the first set.

    Free text rather than a brand list because most machines in Indian gyms
    are unbranded or locally fabricated, and a dropdown of premium US brands
    would exclude them completely.
    """
    exercise = await session.get(Exercise, payload.exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Exercise not found.")

    if payload.gym_id is not None and await session.get(Gym, payload.gym_id) is None:
        raise HTTPException(status_code=404, detail="Gym not found.")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="A station needs a name.")

    station = Station(
        exercise_id=payload.exercise_id,
        name=name,
        gym_id=payload.gym_id,
        created_by_user_id=user.id,
        brand=payload.brand,
        model=payload.model,
        loading=payload.loading,
        has_adjustable_profile=payload.has_adjustable_profile,
        profile_settings=list(payload.profile_settings),
        stack_ranges=[r.model_dump() for r in payload.stack_ranges],
        unit=payload.unit,
        micro_adjust_kg=payload.micro_adjust_kg,
        carriage_weight_kg=payload.carriage_weight_kg,
        is_public=payload.is_public,
        search_text=" ".join(
            p.lower() for p in (name, payload.brand, payload.model) if p
        ),
    )
    session.add(station)
    await session.commit()
    await session.refresh(station)
    return _station_public(station, user.id)


@router.get("/strength/overview")
async def strength_overview(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    weeks: int = Query(default=10, ge=4, le=52),
    top: int = Query(default=3, ge=1, le=6),
) -> dict:
    """The Progress tab's strength chart: the user's main lifts on one axis.

    `strength/progress` answers "how is THIS exercise going" and takes an
    exercise_id. This answers "how is my training going" and picks the lifts
    itself -- ranked by how many weeks they actually appear in, then by load,
    so a heavy one-off doesn't outrank the squat you do every week.
    """
    since = datetime.now(UTC) - timedelta(weeks=weeks)
    rows = (
        await session.execute(
            select(SetLog, Exercise.name)
            .join(Exercise, Exercise.id == SetLog.exercise_id)  # type: ignore[arg-type]
            .where(
                SetLog.user_id == user.id,
                SetLog.performed_at >= since,
                SetLog.is_warmup == False,  # noqa: E712
            )
            .order_by(SetLog.performed_at)  # type: ignore[arg-type]
        )
    ).all()

    # exercise_id -> {name, week -> best e1rm}
    by_ex: dict[str, dict] = {}
    for s, name in rows:
        if s.e1rm is None:
            continue
        d = s.performed_at.date()
        week = d - timedelta(days=d.weekday())
        entry = by_ex.setdefault(s.exercise_id, {"name": name, "weeks": {}})
        entry["weeks"][week] = max(entry["weeks"].get(week, 0.0), s.e1rm)

    ranked = sorted(
        by_ex.values(),
        key=lambda e: (len(e["weeks"]), max(e["weeks"].values(), default=0.0)),
        reverse=True,
    )[:top]

    series = []
    for e in ranked:
        pts = [
            {"week_start": w.isoformat(), "e1rm": round(v, 1)}
            for w, v in sorted(e["weeks"].items())
        ]
        # Change is measured across the points we actually have. A lift with a
        # single week gets None rather than 0 -- "no change" and "no comparison"
        # are different claims and the client renders them differently.
        change = (
            round(pts[-1]["e1rm"] - pts[0]["e1rm"], 1) if len(pts) >= 2 else None
        )
        series.append({"name": e["name"], "points": pts, "change_kg": change})

    rising = [s for s in series if s["change_kg"] is not None and s["change_kg"] > 0]
    if not series:
        headline = None
    elif len(rising) == len([s for s in series if s["change_kg"] is not None]):
        headline = "All rising"
    elif rising:
        headline = f"{len(rising)} of {len(series)} rising"
    else:
        headline = "Holding"

    return {"weeks": weeks, "series": series, "headline": headline}


@router.get("/strength/progress", response_model=list[StrengthSeries])
async def strength_progress(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    exercise_id: str = Query(...),
    days: int = Query(default=180, ge=14, le=1095),
) -> list[StrengthSeries]:
    """Weekly best e1RM, smoothed -- ONE SERIES PER (station, profile).

    WHY THIS IS NOT ONE LINE PER EXERCISE
    Moving from the Hammer row to the PRIME row can change the number on the
    plates by twenty kilos without the lifter getting one gram stronger or
    weaker. Leverage differs, and by an amount nobody publishes. Pooled into a
    single trend that reads as a jump or a collapse, and the strength verdict
    -- the thing this app exists to get right -- is then wrong.

    So a change of machine starts a new series instead of corrupting the old
    one. Cam setting does the same: same machine, same load, setting 1 versus
    setting 3 is genuinely a different exercise.

    Sets with no station form their own series, named rather than blank. That
    is not a fallback bucket to be tidied away later -- "I did not record the
    machine" is a real and permanent answer, and it is what every set logged
    before stations existed will always say.

    There is deliberately NO conversion between series. Compare within one;
    never across.
    """
    since = datetime.now(UTC) - timedelta(days=days)
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

    # (station_id, station_profile) -> week -> sets
    grouped: dict[tuple[str | None, str | None], dict[date, list[SetLog]]] = {}
    for r in rows:
        key = (r.station_id, r.station_profile)
        d = r.performed_at.date()
        week = d - timedelta(days=d.weekday())
        grouped.setdefault(key, {}).setdefault(week, []).append(r)

    names = await _station_names(session, {k[0] for k in grouped if k[0]})

    series: list[StrengthSeries] = []
    for (station_id, profile), weekly in grouped.items():
        # Weeks with no training are ABSENT from `weekly`, not present with a
        # null, so an undated smoother would run straight across a layoff and
        # score the first session back against pre-layoff form. The dated
        # smoother sees the interval and starts a new baseline instead.
        dated: list[tuple[date, float]] = []
        for week in sorted(weekly):
            best = max((s.e1rm for s in weekly[week] if s.e1rm), default=None)
            if best is not None:
                dated.append((week, best))

        smoothed = ewma_over_weeks(dated)
        points: list[StrengthPoint] = [
            StrengthPoint(
                week_start=week,
                best_e1rm=round(best, 1),
                e1rm_ewma=round(smooth, 1),
                volume_load=round(
                    sum(s.weight_kg * s.reps for s in weekly[week]), 1
                ),
            )
            for (week, best), smooth in zip(dated, smoothed)
        ]
        if not points:
            continue
        label = names.get(station_id, "Not recorded") if station_id else "Not recorded"
        if profile:
            label = f"{label} · setting {profile}"
        series.append(
            StrengthSeries(
                station_id=station_id,
                station_profile=profile,
                station_name=label,
                points=points,
            )
        )

    # Longest history first: the series someone has actually been training is
    # the one they came to look at.
    series.sort(key=lambda s: (-len(s.points), s.station_name))
    return series


@router.get("/plateau", response_model=PlateauAssessmentPublic)
async def exercise_plateau(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    exercise_id: str = Query(...),
    days: int = Query(default=180, ge=14, le=1095),
) -> PlateauAssessmentPublic:
    """Has this lift stopped moving, and if not, what is actually going on?

    READ-ONLY, AND THAT IS THE FEATURE. This endpoint writes nothing, changes
    no programme, and creates no plateau record. Every recommendation it
    returns is phrased as options and carries `requires_confirmation`; the
    spec is explicit that adjustments are recommended and never applied.

    THE SEGMENTATION IS THE SAME ONE `/strength/progress` USES. Sets are
    grouped by `(station_id, station_profile)` exactly as they are there, so
    "you moved from the Hammer row to the PRIME row" is a lookup rather than
    a question put to the user. There is no conversion between series, here
    or anywhere.

    SUPPRESSED WHILE ADJUDICATION CANNOT SPEAK. One screen saying "not
    enough data to tell you anything" while another names a plateau is a
    product that contradicts itself, so the detector stays quiet until the
    strength engine could reach a verdict.

    What is passed below is a PROXY for that, not the verdict itself:
    `MIN_SESSIONS` distinct sessions on this exercise, which is the
    adjudication precondition this endpoint can evaluate cheaply. The real
    verdict also needs weigh-ins and logging-day coverage, and it is
    strictly harder to satisfy -- so this errs toward silence, which is the
    safe direction. Swap in the true verdict when the adjudication read is
    available on this path.

    WHAT IS NOT WIRED YET, AND WHY THE STATUS LIST LOOKS SHORTER THAN IT IS
    `incomplete_execution`, `deload_period`, `confounded` and `safety_stop`
    are implemented and tested in `services/plateau.py`, but nothing in the
    database feeds them today: a performed `WorkoutSession` carries no link
    to the `PlannedSession` that prescribed it, no deload flag, and no pain
    flag, and `readiness_checkins` is captured but deliberately unread in
    release one. They light up when steps 3-6 land. Passing zeroes or
    `False` here would be a lie dressed as data, so the exposures below say
    "unknown" and the detector treats unknown as unknown.
    """
    since = datetime.now(UTC) - timedelta(days=days)
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

    exercise = await session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Unknown exercise")

    names = await _station_names(
        session, {r.station_id for r in rows if r.station_id}
    )

    # (station, profile) -> session -> the sets of this exercise in it. One
    # exposure per training session, not per week: three sessions in a week
    # are three chances to progress, and rolling them into one point would
    # hide exactly the pattern this is looking for.
    grouped: dict[
        tuple[str | None, str | None], dict[str, list[SetLog]]
    ] = {}
    for r in rows:
        grouped.setdefault((r.station_id, r.station_profile), {}).setdefault(
            r.session_id, []
        ).append(r)

    series: list[PlateauSeries] = []
    for (station_id, profile), sessions in grouped.items():
        label = names.get(station_id, "Not recorded") if station_id else "Not recorded"
        exposures: list[PlateauExposure] = []
        for sets in sessions.values():
            top = max(
                sets,
                key=lambda s: (
                    s.e1rm if s.e1rm is not None else s.weight_kg * s.reps,
                    s.weight_kg,
                ),
            )
            exposures.append(
                PlateauExposure(
                    performed_on=top.performed_at.date(),
                    top_set_weight_kg=top.weight_kg,
                    top_set_reps=top.reps,
                    top_set_e1rm=top.e1rm,
                    top_set_rir=top.rir,
                    volume_load=round(
                        sum(s.weight_kg * s.reps for s in sets), 1
                    ),
                    # See the docstring: these have no source yet, and
                    # "unknown" is the honest value.
                    sets_prescribed=0,
                    sets_completed=len(sets),
                    readiness=None,
                )
            )
        if exposures:
            series.append(
                PlateauSeries(
                    key=PlateauSeriesKey(
                        exercise_id=exercise_id,
                        exercise_name=exercise.name,
                        station_id=station_id,
                        station_profile=profile,
                        station_name=label,
                    ),
                    exposures=tuple(exposures),
                )
            )

    # See the docstring: a conservative stand-in for the adjudication
    # verdict, deliberately erring toward saying nothing.
    # TODO: replace with `adjudication.adjudicate(...).verdict is
    # Verdict.insufficient_data` once the weight-trend and weigh-in inputs it
    # needs are available on this path (they arrive with step 3's readiness
    # and programme context). Until then this proxy is strictly easier to
    # satisfy than the real verdict, so it can only make us quieter.
    distinct_sessions = len({r.session_id for r in rows})
    assessment = assess_plateau(
        series,
        today=datetime.now(UTC).date(),
        adjudication_insufficient=distinct_sessions < MIN_SESSIONS,
        window_days=days,
    )

    return PlateauAssessmentPublic(
        status=assessment.status.value,
        exercise_id=exercise_id,
        exercise_name=exercise.name,
        station_id=assessment.series.station_id,
        station_profile=assessment.series.station_profile,
        station_name=assessment.series.station_name,
        reason=assessment.reason,
        recommendation=assessment.recommendation,
        confidence=assessment.confidence,
        evidence_sessions=list(assessment.evidence),
        baseline=_plateau_perf(assessment.baseline),
        current=_plateau_perf(assessment.current),
        stalled_metric=assessment.stalled_metric,
        improving_metrics=list(assessment.improving_metrics),
        requires_confirmation=assessment.requires_confirmation,
    )


def _plateau_perf(snap) -> PlateauPerformance | None:
    if snap is None:
        return None
    return PlateauPerformance(
        performed_on=snap.performed_on,
        top_set_weight_kg=snap.top_set_weight_kg,
        top_set_reps=snap.top_set_reps,
        top_set_e1rm=snap.top_set_e1rm,
        top_set_rir=snap.top_set_rir,
        volume_load=snap.volume_load,
    )


async def _station_names(session: AsyncSession, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = (
        await session.execute(select(Station).where(Station.id.in_(ids)))  # type: ignore[union-attr]
    ).scalars().all()
    return {r.id: r.name for r in rows}


# ---------------------------------------------------------------------------
# Voice logging
# ---------------------------------------------------------------------------

# Roughly four minutes of compressed speech. The whole-session flow means
# someone can narrate a full workout -- eight exercises, thirty sets -- in one
# recording, so the single-set budget was far too tight. Still bounded, so a
# recorder left running in a pocket cannot post a 40 MB file.
MAX_AUDIO_BYTES = 12 * 1024 * 1024

ALLOWED_AUDIO = {
    "audio/m4a", "audio/mp4", "audio/x-m4a", "audio/aac",
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
    "audio/webm", "audio/ogg", "audio/3gpp", "audio/amr",
}


@router.post("/voice")
async def voice_log(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    audio: UploadFile = File(...),
    unit: str = Form(default="kg"),
) -> dict:
    """Speak a set, get a PROPOSAL back. This endpoint never writes a set.

    "three sets of bench press at sixty kilos, ten to fifteen reps"

    WHY NOTHING IS SAVED HERE
    A misheard "sixty" as "sixteen" entering the training history silently
    corrupts the e1RM, and the strength trend is half of what this product
    claims to know. So the response is something to confirm, and the existing
    `POST /sessions/{id}/sets` is still the only way a set is written. The
    round trip costs one tap and buys the entire feature its trustworthiness.

    THE MODEL DOES NOT PICK THE EXERCISE. It returns the phrase as spoken;
    `workout_voice.match_exercise` maps that onto the catalogue here, so the
    mapping is deterministic, testable, and cannot drift when the model
    changes underneath us.
    """
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio upload.")
    if len(raw) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio is {len(raw) // 1024} KB; the limit is "
                   f"{MAX_AUDIO_BYTES // 1024} KB. Record a shorter clip.",
        )

    mime = (audio.content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_AUDIO:
        # Don't reject outright -- phone recorders report a zoo of MIME types
        # and refusing a valid clip over a header is a worse failure than
        # letting the model tell us it cannot read it. Fall back to m4a, which
        # is what Expo's recorder produces on both platforms.
        mime = "audio/m4a"

    catalogue = [
        (e.id, e.name)
        for e in (await session.execute(select(Exercise.id, Exercise.name))).all()
    ]
    if not catalogue:
        raise HTTPException(
            status_code=503,
            detail="The exercise catalogue is empty. Seed it before voice logging.",
        )

    try:
        result = await transcribe_workout(
            raw,
            mime_type=mime,
            catalogue=catalogue,
            default_unit="lb" if unit.lower() == "lb" else "kg",
        )
    except RuntimeError as exc:  # no API key configured
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "transcript": result.transcript,
        "model": result.model_used,
        "latency_ms": result.latency_ms,
        "duration_min": result.duration_min,
        "total_sets": result.total_sets,
        "needs_attention": result.needs_attention,
        "entries": [
            {
                "exercise_phrase": e.exercise_phrase,
                "exercise_id": e.exercise_id,
                "exercise_name": e.exercise_name,
                "match_score": e.match_score,
                "alternatives": e.alternatives,
                "weight_was_converted": e.weight_was_converted,
                "unit_assumed": e.unit_assumed,
                "confidence": e.confidence,
                "warnings": e.warnings,
                "sets": [
                    {
                        "reps": st.reps,
                        "weight_kg": st.weight_kg,
                        "rir": st.rir,
                        "is_warmup": st.is_warmup,
                        "reps_low": st.reps_low,
                        "reps_high": st.reps_high,
                    }
                    for st in e.sets
                ],
            }
            for e in result.entries
        ],
    }


@router.post("/voice/commit", status_code=201)
async def commit_voice_workout(
    payload: VoiceCommitRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    """Write a whole reviewed session in one call.

    THIS IS THE POINT OF THE FEATURE. Logging a workout set by set is thirty
    interactions; narrating it and confirming once is two. The user speaks,
    checks what was heard on one screen, and taps save -- and every set lands
    with its e1RM computed, in the order performed, inside a single session.

    STILL EXACTLY ONE CONFIRM, AND THAT IS DELIBERATE.
    The tedium worth removing is the per-exercise typing, not the human
    glance. A misheard "sixty" as "sixteen" would enter the training history,
    move the estimated max, and corrupt the strength verdict -- which is half
    of what this product claims to know. One screen, one tap, everything
    saved; zero taps is a different and much worse product.

    ATOMIC. One transaction for the session and every set in it. A partial
    commit would leave a session holding half a workout, which is worse than
    no session at all -- the volume chart and the per-lift trend would both
    quietly report numbers that never happened.
    """
    if not payload.entries:
        raise HTTPException(status_code=400, detail="No sets to save.")

    ids = {e.exercise_id for e in payload.entries}
    known = set(
        (
            await session.execute(select(Exercise.id).where(Exercise.id.in_(ids)))  # type: ignore[union-attr]
        )
        .scalars()
        .all()
    )
    missing = ids - known
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"{len(missing)} exercise(s) could not be found. Re-pick them.",
        )

    equipment = {
        r[0]: r[1]
        for r in (
            await session.execute(
                select(Exercise.id, Exercise.equipment).where(Exercise.id.in_(ids))  # type: ignore[union-attr]
            )
        ).all()
    }

    started = payload.started_at or datetime.now(UTC)
    ws = WorkoutSession(
        user_id=user.id,
        routine_name=payload.routine_name or "Voice log",
        started_at=started,
        # Narration happens AFTER the workout, so the session is closed on
        # arrival. Leaving it open would make it the "resume workout" banner
        # and let tomorrow's sets fall into yesterday's session.
        ended_at=started + timedelta(minutes=payload.duration_min)
        if payload.duration_min
        else datetime.now(UTC),
        notes=payload.transcript,
    )
    session.add(ws)
    await session.flush()  # need ws.id before the set rows, same transaction

    written = 0
    for entry in payload.entries:
        for index, st in enumerate(entry.sets):
            rir = st.rir
            session.add(
                SetLog(
                    session_id=ws.id,
                    user_id=user.id,
                    exercise_id=entry.exercise_id,
                    set_index=index,
                    weight_kg=st.weight_kg or 0.0,
                    reps=st.reps,
                    rir=rir,
                    rpe=strength.rpe_from_rir(rir),
                    is_warmup=st.is_warmup,
                    e1rm=strength.e1rm(st.weight_kg or 0.0, st.reps, rir),
                    performed_at=started,
                )
            )
            written += 1

    await session.commit()

    # Hand back the summary so the client can go straight to the session card
    # instead of saving, navigating, and fetching again.
    summary = await session_summary(ws.id, session, user)
    return {"session_id": ws.id, "sets_written": written, "summary": summary}
