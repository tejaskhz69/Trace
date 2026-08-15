"""Health sync + coach endpoints.

SYNC DESIGN
-----------
The phone is the source of truth for health data and pushes deltas up. We
never pull from Apple — HealthKit has no server API; all reads happen on
device.

Idempotency matters more than you'd think: HealthKit re-reports the same
workout when a user edits it, changes source priority, or restores a backup.
Every upsert here is keyed on a natural key (user+day, or user+external_id) so
a re-sync is free rather than a duplicate.

Batch sizes are capped because a first-ever sync can carry years of data and
a naive client will try to send all of it in one request.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select as sa_select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import (
    ActivityDay as ActivityDayModel,
    CoachBriefingRecord,
    ExternalWorkout,
    HealthSource,
    HealthSyncState,
    MealLog,
    SleepNight as SleepNightModel,
    User,
    WeightEntry,
    WorkoutSession,
)
from ..services import activity as act
from ..services import coach as coach_svc
from .adjudication import weekly_verdict
from .auth import current_user

router = APIRouter(prefix="/api/health", tags=["health"])

MAX_BATCH = 400


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ActivityDayIn(BaseModel):
    day: date
    steps: Optional[int] = Field(default=None, ge=0, le=200_000)
    active_energy_kcal: Optional[float] = Field(default=None, ge=0, le=15_000)
    resting_energy_kcal: Optional[float] = Field(default=None, ge=0, le=5_000)
    exercise_minutes: Optional[float] = Field(default=None, ge=0, le=1_440)
    stand_hours: Optional[float] = Field(default=None, ge=0, le=24)
    distance_km: Optional[float] = Field(default=None, ge=0, le=500)
    flights_climbed: Optional[int] = Field(default=None, ge=0, le=2_000)
    resting_heart_rate: Optional[float] = Field(default=None, ge=25, le=150)
    hrv_ms: Optional[float] = Field(default=None, ge=1, le=400)
    vo2_max: Optional[float] = Field(default=None, ge=10, le=100)


class SleepNightIn(BaseModel):
    night_of: date
    asleep_hours: float = Field(ge=0, le=24)
    in_bed_hours: Optional[float] = Field(default=None, ge=0, le=24)
    deep_hours: Optional[float] = Field(default=None, ge=0, le=12)
    rem_hours: Optional[float] = Field(default=None, ge=0, le=12)
    core_hours: Optional[float] = Field(default=None, ge=0, le=16)
    awakenings: Optional[int] = Field(default=None, ge=0, le=100)


class ExternalWorkoutIn(BaseModel):
    external_id: str
    activity_type: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_minutes: float = Field(ge=0, le=2_880)
    active_energy_kcal: Optional[float] = Field(default=None, ge=0, le=15_000)
    distance_km: Optional[float] = Field(default=None, ge=0, le=500)
    mean_heart_rate: Optional[float] = Field(default=None, ge=25, le=250)
    max_heart_rate: Optional[float] = Field(default=None, ge=25, le=250)


class HealthSyncRequest(BaseModel):
    source: HealthSource = HealthSource.healthkit
    activity: list[ActivityDayIn] = []
    sleep: list[SleepNightIn] = []
    workouts: list[ExternalWorkoutIn] = []


class HealthSyncResponse(BaseModel):
    activity_days_written: int
    sleep_nights_written: int
    workouts_written: int
    synced_through: Optional[date]
    message: str


class InsightOut(BaseModel):
    key: str
    urgency: int
    lever: str
    headline: str
    detail: str
    action: Optional[str]
    evidence: dict[str, Any]
    confidence: float


class ActivityTodayOut(BaseModel):
    steps: Optional[int]
    active_energy_kcal: Optional[float]
    exercise_minutes: Optional[float]
    sessions_today: int
    steps_vs_baseline: Optional[int]  # % vs the user's own 28-day baseline
    synced_at: Optional[str]


class BriefingOut(BaseModel):
    for_date: date
    primary: Optional[InsightOut]
    secondary: list[InsightOut]
    prompts: list[str]
    data_completeness: float
    neat: Optional[dict[str, Any]] = None
    sleep: Optional[dict[str, Any]] = None
    energy_reconciliation: Optional[dict[str, Any]] = None
    # Consumed by the home screen's "Activity today" block.
    activity_today: Optional[ActivityTodayOut] = None
    step_history: list[int] = []


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


@router.post("/sync", response_model=HealthSyncResponse)
async def sync_health(
    payload: HealthSyncRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> HealthSyncResponse:
    if (
        len(payload.activity) > MAX_BATCH
        or len(payload.sleep) > MAX_BATCH
        or len(payload.workouts) > MAX_BATCH
    ):
        raise HTTPException(
            status_code=413,
            detail=f"Send at most {MAX_BATCH} records of each type per request.",
        )

    now = datetime.now(timezone.utc)
    written = {"activity": 0, "sleep": 0, "workouts": 0}

    # --- Activity ---------------------------------------------------------
    if payload.activity:
        rows = [
            {
                "user_id": user.id,
                "day": a.day,
                **a.model_dump(exclude={"day"}),
                "source": payload.source.value,
                "synced_at": now,
            }
            for a in payload.activity
        ]
        stmt = pg_insert(ActivityDayModel).values(rows)
        # COALESCE so a partial re-sync never wipes a field the client
        # didn't include this time.
        stmt = stmt.on_conflict_do_update(
            constraint="uq_activity_user_day",
            set_={
                col: func.coalesce(getattr(stmt.excluded, col), getattr(ActivityDayModel, col))
                for col in (
                    "steps", "active_energy_kcal", "resting_energy_kcal",
                    "exercise_minutes", "stand_hours", "distance_km",
                    "flights_climbed", "resting_heart_rate", "hrv_ms", "vo2_max",
                )
            }
            | {"synced_at": stmt.excluded.synced_at},
        )
        await session.execute(stmt)
        written["activity"] = len(rows)

    # --- Sleep ------------------------------------------------------------
    if payload.sleep:
        rows = []
        for s in payload.sleep:
            d = s.model_dump()
            eff = (
                round(s.asleep_hours / s.in_bed_hours, 3)
                if s.in_bed_hours and s.in_bed_hours > 0
                else None
            )
            rows.append(
                {
                    "user_id": user.id,
                    **d,
                    "efficiency": eff,
                    "source": payload.source.value,
                    "synced_at": now,
                }
            )
        stmt = pg_insert(SleepNightModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_sleep_user_night",
            set_={
                col: getattr(stmt.excluded, col)
                for col in (
                    "asleep_hours", "in_bed_hours", "deep_hours", "rem_hours",
                    "core_hours", "awakenings", "efficiency", "synced_at",
                )
            },
        )
        await session.execute(stmt)
        written["sleep"] = len(rows)

    # --- External workouts ------------------------------------------------
    if payload.workouts:
        rows = [
            {
                "user_id": user.id,
                **w.model_dump(),
                "source": payload.source.value,
                "synced_at": now,
            }
            for w in payload.workouts
        ]
        stmt = pg_insert(ExternalWorkout).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_external_workout",
            set_={
                col: getattr(stmt.excluded, col)
                for col in (
                    "activity_type", "started_at", "ended_at",
                    "duration_minutes", "active_energy_kcal", "distance_km",
                    "mean_heart_rate", "max_heart_rate", "synced_at",
                )
            },
        )
        await session.execute(stmt)
        written["workouts"] = len(rows)

    # --- Cursors ----------------------------------------------------------
    latest = max(
        [a.day for a in payload.activity]
        + [s.night_of for s in payload.sleep]
        + [w.started_at.date() for w in payload.workouts]
        + [date.min],
    )
    if latest > date.min:
        for metric in ("activity", "sleep", "workouts"):
            stmt = pg_insert(HealthSyncState).values(
                user_id=user.id,
                metric=metric,
                last_synced_through=latest,
                permission_granted=True,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_sync_user_metric",
                set_={
                    "last_synced_through": stmt.excluded.last_synced_through,
                    "permission_granted": True,
                    "updated_at": now,
                },
            )
            await session.execute(stmt)

    await session.commit()

    return HealthSyncResponse(
        activity_days_written=written["activity"],
        sleep_nights_written=written["sleep"],
        workouts_written=written["workouts"],
        synced_through=latest if latest > date.min else None,
        message="Synced. Your activity now explains your expenditure — it does "
        "not change your calorie target.",
    )


@router.get("/sync/state")
async def sync_state(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    """What the client needs to know before deciding what to pull."""
    rows = (
        await session.execute(
            select(HealthSyncState).where(HealthSyncState.user_id == user.id)
        )
    ).scalars().all()
    return {
        "metrics": {
            r.metric: {
                "last_synced_through": r.last_synced_through,
                "permission_granted": r.permission_granted,
            }
            for r in rows
        },
        # A cold client should backfill ~90 days: enough for a NEAT baseline
        # and a full adaptive-TDEE window, without a multi-year first sync.
        "recommended_backfill_days": 90,
    }


# ---------------------------------------------------------------------------
# The coach
# ---------------------------------------------------------------------------


async def _load_coach_input(
    session: AsyncSession, user: User, today: date
) -> tuple[coach_svc.CoachInput, dict[str, Any]]:
    since_90 = today - timedelta(days=90)
    since_14 = today - timedelta(days=14)

    # Activity
    activity_rows = (
        await session.execute(
            select(ActivityDayModel)
            .where(
                ActivityDayModel.user_id == user.id,
                ActivityDayModel.day >= since_90,
            )
            .order_by(ActivityDayModel.day)  # type: ignore[arg-type]
        )
    ).scalars().all()
    activity_days = [
        act.ActivityDay(
            day=r.day,
            steps=r.steps,
            active_energy_kcal=r.active_energy_kcal,
            resting_energy_kcal=r.resting_energy_kcal,
            exercise_minutes=r.exercise_minutes,
            distance_km=r.distance_km,
        )
        for r in activity_rows
    ]

    # Sleep
    sleep_rows = (
        await session.execute(
            select(SleepNightModel)
            .where(
                SleepNightModel.user_id == user.id,
                SleepNightModel.night_of >= since_14,
            )
            .order_by(SleepNightModel.night_of)  # type: ignore[arg-type]
        )
    ).scalars().all()
    nights = [
        act.SleepNight(
            night_of=r.night_of,
            asleep_hours=r.asleep_hours,
            in_bed_hours=r.in_bed_hours,
            deep_hours=r.deep_hours,
            rem_hours=r.rem_hours,
            awakenings=r.awakenings,
            efficiency=r.efficiency,
        )
        for r in sleep_rows
    ]

    # Weight (latest, for the NEAT kcal conversion)
    latest_weight = await session.scalar(
        select(WeightEntry)
        .where(WeightEntry.user_id == user.id)
        .order_by(WeightEntry.measured_on.desc())  # type: ignore[union-attr]
    )
    body_weight = (
        latest_weight.weight_kg
        if latest_weight
        else (user.starting_weight_kg or 75.0)
    )

    weigh_ins_14 = (
        await session.scalar(
            sa_select(func.count(WeightEntry.id)).where(
                WeightEntry.user_id == user.id,
                WeightEntry.measured_on >= since_14,
            )
        )
    ) or 0

    # Nutrition
    meal_rows = (
        await session.execute(
            sa_select(
                func.date(MealLog.logged_at).label("d"),
                func.sum(MealLog.calories).label("kcal"),
                func.sum(MealLog.protein_g).label("protein"),
            )
            .where(
                MealLog.user_id == user.id,
                MealLog.logged_at >= datetime.combine(since_14, datetime.min.time(), tzinfo=timezone.utc),
            )
            .group_by(func.date(MealLog.logged_at))
        )
    ).all()
    logged_days = len(meal_rows)
    mean_kcal = (
        sum(float(r.kcal or 0) for r in meal_rows) / logged_days if logged_days else None
    )
    mean_protein = (
        sum(float(r.protein or 0) for r in meal_rows) / logged_days
        if logged_days
        else None
    )

    # Training
    sessions_7 = (
        await session.scalar(
            sa_select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == user.id,
                WorkoutSession.started_at
                >= datetime.combine(today - timedelta(days=7), datetime.min.time(), tzinfo=timezone.utc),
            )
        )
    ) or 0
    sessions_14 = (
        await session.scalar(
            sa_select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == user.id,
                WorkoutSession.started_at
                >= datetime.combine(since_14, datetime.min.time(), tzinfo=timezone.utc),
            )
        )
    ) or 0
    sessions_56 = (
        await session.scalar(
            sa_select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == user.id,
                WorkoutSession.started_at
                >= datetime.combine(today - timedelta(days=56), datetime.min.time(), tzinfo=timezone.utc),
            )
        )
    ) or 0
    baseline_sessions = sessions_56 / 8 if sessions_56 else None

    # Did a workout finish in the last few hours?
    recent_session = await session.scalar(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.started_at
            >= datetime.now(timezone.utc) - timedelta(hours=6),
        )
        .order_by(WorkoutSession.started_at.desc())  # type: ignore[union-attr]
    )

    should_prompt, prompt = act.should_prompt_weigh_in(
        last_weigh_in=latest_weight.measured_on if latest_weight else None,
        today=today,
        workout_just_finished=recent_session is not None,
        weigh_ins_last_14_days=weigh_ins_14,
    )

    neat = act.analyse_neat(activity_days, body_weight)
    sleep_summary = act.analyse_sleep(nights)

    coach_input = coach_svc.CoachInput(
        today=today,
        body_weight_kg=body_weight,
        goal_type=user.goal_type.value,
        neat=neat,
        sleep=sleep_summary,
        logged_days_last_14=logged_days,
        mean_protein_g=mean_protein,
        mean_calories=mean_kcal,
        sessions_last_7=sessions_7,
        sessions_last_14=sessions_14,
        mean_sessions_baseline=baseline_sessions,
        weigh_ins_last_14=weigh_ins_14,
        weigh_in_prompt=prompt if should_prompt else None,
    )

    # Today's row + the last 7 days of steps, for the home screen.
    today_row = next((r for r in activity_rows if r.day == today), None)
    last7 = [r.steps or 0 for r in activity_rows[-7:]]

    sessions_today = (
        await session.scalar(
            sa_select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == user.id,
                WorkoutSession.started_at
                >= datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
            )
        )
    ) or 0

    steps_vs_baseline = None
    if today_row and today_row.steps and neat.baseline_steps:
        steps_vs_baseline = round(
            (today_row.steps - neat.baseline_steps) / neat.baseline_steps * 100
        )

    extras = {
        "neat": neat.__dict__ | {"trend": neat.trend.value},
        "sleep": sleep_summary.__dict__,
        "activity_stability": act.activity_stability(activity_days),
        "activity_days": activity_days,
        "step_history": last7,
        "activity_today": (
            {
                "steps": today_row.steps if today_row else None,
                "active_energy_kcal": today_row.active_energy_kcal if today_row else None,
                "exercise_minutes": today_row.exercise_minutes if today_row else None,
                "sessions_today": sessions_today,
                "steps_vs_baseline": steps_vs_baseline,
                "synced_at": today_row.synced_at.isoformat() if today_row else None,
            }
            if today_row or sessions_today
            else None
        ),
    }
    return coach_input, extras


@router.get("/coach", response_model=BriefingOut)
async def coach_briefing(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    on: date = Query(default_factory=date.today, alias="date"),
) -> BriefingOut:
    """One thing to do today, with the evidence behind it."""
    coach_input, extras = await _load_coach_input(session, user, on)

    # Fold in the strength verdict if one exists for this week.
    try:
        verdict = await weekly_verdict(session=session, user=user, recompute=False)
        from ..services.adjudication import (
            AdjudicationResult,
            Verdict as SvcVerdict,
        )

        coach_input.adjudication = AdjudicationResult(
            verdict=SvcVerdict(verdict.verdict.value),
            headline=verdict.headline,
            explanation=verdict.explanation,
            strength_index_delta_pct=verdict.strength_index_delta_pct,
            weight_delta_pct_per_week=verdict.weight_delta_pct_per_week,
            protein_g_per_kg=verdict.protein_g_per_kg,
            logging_adherence=verdict.logging_adherence,
            recommended_calorie_delta=(
                (verdict.recommended_target or 0) - (verdict.previous_target or 0)
                if verdict.previous_target
                else 0.0
            ),
            recommended_protein_g=verdict.recommended_protein_g,
            guardrails_triggered=verdict.guardrails_triggered,
            math=verdict.math_breakdown,
        )
    except HTTPException:
        pass  # not enough data for a verdict yet — the coach still works

    briefing = coach_svc.build_briefing(coach_input)

    # Reconcile the watch against the scale, purely as an honesty check.
    observed = None
    if coach_input.adjudication:
        exp = (coach_input.adjudication.math or {}).get("expenditure", {})
        observed = exp.get("tdee_observed") if isinstance(exp, dict) else None
    recon = act.reconcile_energy(extras["activity_days"], observed)

    def out(i: coach_svc.Insight) -> InsightOut:
        return InsightOut(
            key=i.key,
            urgency=int(i.urgency),
            lever=i.lever.value,
            headline=i.headline,
            detail=i.detail,
            action=i.action,
            evidence=i.evidence,
            confidence=i.confidence,
        )

    # Persist so we can measure which advice actually gets acted on.
    if briefing.primary:
        stmt = pg_insert(CoachBriefingRecord).values(
            user_id=user.id,
            for_date=on,
            primary_lever=briefing.primary.lever.value,
            headline=briefing.primary.headline,
            body=briefing.primary.detail,
            data_completeness=briefing.data_completeness,
            payload={
                "primary": out(briefing.primary).model_dump(),
                "secondary": [out(s).model_dump() for s in briefing.secondary],
            },
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_briefing_user_day",
            set_={
                "headline": stmt.excluded.headline,
                "body": stmt.excluded.body,
                "payload": stmt.excluded.payload,
                "data_completeness": stmt.excluded.data_completeness,
            },
        )
        await session.execute(stmt)
        await session.commit()

    return BriefingOut(
        for_date=on,
        primary=out(briefing.primary) if briefing.primary else None,
        secondary=[out(s) for s in briefing.secondary],
        prompts=briefing.prompts,
        data_completeness=briefing.data_completeness,
        neat=extras["neat"],
        sleep=extras["sleep"],
        energy_reconciliation=recon.__dict__,
        activity_today=(
            ActivityTodayOut(**extras["activity_today"])
            if extras["activity_today"]
            else None
        ),
        step_history=extras["step_history"],
    )


@router.get("/activity/summary")
async def activity_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    days: int = Query(default=30, ge=7, le=365),
) -> dict[str, Any]:
    since = date.today() - timedelta(days=days)
    rows = (
        await session.execute(
            select(ActivityDayModel)
            .where(ActivityDayModel.user_id == user.id, ActivityDayModel.day >= since)
            .order_by(ActivityDayModel.day)  # type: ignore[arg-type]
        )
    ).scalars().all()

    return {
        "days": [
            {
                "day": r.day.isoformat(),
                "steps": r.steps,
                "active_energy_kcal": r.active_energy_kcal,
                "exercise_minutes": r.exercise_minutes,
            }
            for r in rows
        ],
        "mean_steps": (
            round(sum(r.steps for r in rows if r.steps) / max(1, sum(1 for r in rows if r.steps)))
            if rows
            else None
        ),
        "note": (
            "Active energy is shown for context. It is deliberately NOT added "
            "to your calorie target — your weight trend already accounts for it."
        ),
    }
