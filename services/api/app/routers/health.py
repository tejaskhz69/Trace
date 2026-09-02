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

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import (
    ActivityDay as ActivityDayModel,
)
from ..models import (
    CoachBriefingRecord,
    ExternalWorkout,
    HealthSource,
    HealthSyncState,
    MealLog,
    User,
    WeightEntry,
    WorkoutSession,
)
from ..models import (
    SleepNight as SleepNightModel,
)
from ..services import activity as act
from ..services import coach as coach_svc
from ..services import sports as sports_svc
from ..services import streak as streak_svc
from .adjudication import weekly_verdict
from .auth import current_user

router = APIRouter(prefix="/api/health", tags=["health"])

MAX_BATCH = 400


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ActivityDayIn(BaseModel):
    day: date
    steps: int | None = Field(default=None, ge=0, le=200_000)
    active_energy_kcal: float | None = Field(default=None, ge=0, le=15_000)
    resting_energy_kcal: float | None = Field(default=None, ge=0, le=5_000)
    exercise_minutes: float | None = Field(default=None, ge=0, le=1_440)
    stand_hours: float | None = Field(default=None, ge=0, le=24)
    distance_km: float | None = Field(default=None, ge=0, le=500)
    flights_climbed: int | None = Field(default=None, ge=0, le=2_000)
    resting_heart_rate: float | None = Field(default=None, ge=25, le=150)
    hrv_ms: float | None = Field(default=None, ge=1, le=400)
    vo2_max: float | None = Field(default=None, ge=10, le=100)


class SleepNightIn(BaseModel):
    night_of: date
    asleep_hours: float = Field(ge=0, le=24)
    in_bed_hours: float | None = Field(default=None, ge=0, le=24)
    deep_hours: float | None = Field(default=None, ge=0, le=12)
    rem_hours: float | None = Field(default=None, ge=0, le=12)
    core_hours: float | None = Field(default=None, ge=0, le=16)
    awakenings: int | None = Field(default=None, ge=0, le=100)


class ExternalWorkoutIn(BaseModel):
    external_id: str
    activity_type: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_minutes: float = Field(ge=0, le=2_880)
    active_energy_kcal: float | None = Field(default=None, ge=0, le=15_000)
    distance_km: float | None = Field(default=None, ge=0, le=500)
    mean_heart_rate: float | None = Field(default=None, ge=25, le=250)
    max_heart_rate: float | None = Field(default=None, ge=25, le=250)


class HealthSyncRequest(BaseModel):
    source: HealthSource = HealthSource.healthkit
    activity: list[ActivityDayIn] = []
    sleep: list[SleepNightIn] = []
    workouts: list[ExternalWorkoutIn] = []


class HealthSyncResponse(BaseModel):
    activity_days_written: int
    sleep_nights_written: int
    workouts_written: int
    synced_through: date | None
    message: str


class InsightOut(BaseModel):
    key: str
    urgency: int
    lever: str
    headline: str
    detail: str
    action: str | None
    evidence: dict[str, Any]
    confidence: float


class ActivityTodayOut(BaseModel):
    steps: int | None
    active_energy_kcal: float | None
    exercise_minutes: float | None
    sessions_today: int
    steps_vs_baseline: int | None  # % vs the user's own 28-day baseline
    synced_at: str | None


class BriefingOut(BaseModel):
    for_date: date
    primary: InsightOut | None
    secondary: list[InsightOut]
    prompts: list[str]
    data_completeness: float
    neat: dict[str, Any] | None = None
    sleep: dict[str, Any] | None = None
    energy_reconciliation: dict[str, Any] | None = None
    # Consumed by the home screen's "Activity today" block.
    activity_today: ActivityTodayOut | None = None
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

    now = datetime.now(UTC)
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
                MealLog.logged_at >= datetime.combine(since_14, datetime.min.time(), tzinfo=UTC),
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
                >= datetime.combine(today - timedelta(days=7), datetime.min.time(), tzinfo=UTC),
            )
        )
    ) or 0
    sessions_14 = (
        await session.scalar(
            sa_select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == user.id,
                WorkoutSession.started_at
                >= datetime.combine(since_14, datetime.min.time(), tzinfo=UTC),
            )
        )
    ) or 0
    sessions_56 = (
        await session.scalar(
            sa_select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == user.id,
                WorkoutSession.started_at
                >= datetime.combine(today - timedelta(days=56), datetime.min.time(), tzinfo=UTC),
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
            >= datetime.now(UTC) - timedelta(hours=6),
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
                >= datetime.combine(today, datetime.min.time(), tzinfo=UTC),
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
        )
        from ..services.adjudication import (
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


# ===========================================================================
# SPORT AND ACTIVITY LOGGING
#
# The Activities tab used to be nine chips that set a local variable and did
# nothing -- tapping one had no effect anywhere, which is exactly how it was
# reported. These three endpoints are what make it a real screen: the
# catalogue to render, a way to save a session, and a way to read them back
# alongside whatever Strava and the watch sent.
#
# EVERY ONE OF THEM RETURNS BURN AS CONTEXT. Nothing here adjusts a calorie
# target, and `where_this_goes` says so on the wire so the client cannot
# quietly decide otherwise. See services/activity.py for the argument and
# tests/test_sports.py::TestNeverFeedsTheCalorieTarget for the guard.
# ===========================================================================


class SportOut(BaseModel):
    key: str
    name: str
    group: str
    met: float
    #: True when the MET is interpolated rather than taken from the
    #: Compendium. Surfaced so the UI can mark the number as a rougher guess.
    estimated: bool
    tracks_distance: bool


class SportsResponse(BaseModel):
    sports: list[SportOut]
    #: The user's current body mass, so the client can preview a burn as the
    #: duration dial moves without a round trip per tap. Null when we have
    #: none on file -- the client then widens the band and says why, rather
    #: than quietly substituting an average and looking equally confident.
    weight_kg: float | None


@router.get("/sports", response_model=SportsResponse)
async def list_sports(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> SportsResponse:
    """The sport catalogue, plus the one number needed to price a session."""
    return SportsResponse(
        sports=[
            SportOut(
                key=s.key,
                name=s.name,
                group=s.group,
                met=s.met,
                estimated=s.estimated,
                tracks_distance=s.tracks_distance,
            )
            for s in sports_svc.SPORTS
        ],
        weight_kg=await _latest_weight_kg(session, user),
    )


class ActivityLogRequest(BaseModel):
    sport: str
    duration_minutes: float
    intensity: str = "moderate"
    started_at: datetime | None = None
    distance_km: float | None = Field(default=None, ge=0, le=1000)
    mean_heart_rate: float | None = Field(default=None, ge=30, le=240)
    #: Let the user overrule us. A chest strap beats a MET table, and
    #: refusing their measured number in favour of our population average
    #: would be the wrong kind of confident.
    active_energy_kcal: float | None = Field(default=None, ge=0, le=10000)


class BurnOut(BaseModel):
    low: int
    point: int
    high: int
    band: int
    met_used: float
    assumed_weight: bool
    met_estimated: bool
    measured: bool = False


class ActivityOut(BaseModel):
    id: str
    sport: str
    name: str
    started_at: datetime
    duration_minutes: float
    distance_km: float | None
    mean_heart_rate: float | None
    source: str
    burn: BurnOut | None


class ActivityLogResponse(BaseModel):
    activity: ActivityOut
    where_this_goes: list[tuple[str, str]]
    target_explainer: str


async def _latest_weight_kg(session: AsyncSession, user: User) -> float | None:
    """Body mass for the MET formula, most recent first.

    Falls back to the profile weight, then to nothing at all -- and "nothing"
    is handled by widening the band rather than by inventing a number.
    """
    row = await session.scalar(
        select(WeightEntry)
        .where(WeightEntry.user_id == user.id)
        .order_by(WeightEntry.measured_on.desc())  # type: ignore[union-attr]
        .limit(1)
    )
    if row is not None and row.weight_kg:
        return float(row.weight_kg)
    return float(user.weight_kg) if getattr(user, "weight_kg", None) else None


def _burn_for(
    sport_key: str,
    duration_minutes: float,
    weight_kg: float | None,
    intensity: str,
    measured_kcal: float | None,
) -> BurnOut | None:
    try:
        est = sports_svc.estimate_burn(
            sport_key, duration_minutes, weight_kg, intensity
        )
    except sports_svc.SportError:
        return None

    if measured_kcal is not None:
        # A MEASURED NUMBER WINS, and it wins with a narrow band rather than
        # our wide one -- the same rule the ride screen applies when a power
        # meter disagrees with Strava's model. The band is not zero because a
        # wearable is not a calorimeter.
        point = round(measured_kcal)
        margin = max(1, round(point * 0.08))
        return BurnOut(
            low=point - margin,
            point=point,
            high=point + margin,
            band=margin,
            met_used=est.met_used,
            assumed_weight=False,
            met_estimated=False,
            measured=True,
        )

    return BurnOut(
        low=est.low,
        point=est.point,
        high=est.high,
        band=est.band,
        met_used=est.met_used,
        assumed_weight=est.assumed_weight,
        met_estimated=est.met_estimated,
    )


@router.post("/activities", response_model=ActivityLogResponse, status_code=201)
async def log_activity(
    payload: ActivityLogRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> ActivityLogResponse:
    """Log a session the user did and told us about."""
    sport = sports_svc.BY_KEY.get(payload.sport) or sports_svc.find(payload.sport)
    if sport is None:
        raise HTTPException(status_code=422, detail=f"Unknown sport: {payload.sport}")

    weight = await _latest_weight_kg(session, user)
    try:
        sports_svc.estimate_burn(
            sport.key, payload.duration_minutes, weight, payload.intensity
        )
    except sports_svc.SportError as exc:
        # Refuse rather than bank a nonsense session. A stuck timer that
        # writes 6,000 kcal of "activity" poisons the training load for weeks.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    started = payload.started_at or datetime.now(UTC)
    row = ExternalWorkout(
        user_id=user.id,
        # Manual entries still need a unique external_id: the table's
        # uniqueness constraint is what makes device sync idempotent, and a
        # NULL here would collide the moment someone logs two sessions.
        external_id=f"manual:{user.id}:{started.isoformat()}:{sport.key}",
        activity_type=sport.key,
        started_at=started,
        ended_at=started + timedelta(minutes=payload.duration_minutes),
        duration_minutes=payload.duration_minutes,
        active_energy_kcal=payload.active_energy_kcal,
        distance_km=payload.distance_km,
        mean_heart_rate=payload.mean_heart_rate,
        source=HealthSource.manual,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return ActivityLogResponse(
        activity=ActivityOut(
            id=row.id,
            sport=sport.key,
            name=sport.name,
            started_at=row.started_at,
            duration_minutes=row.duration_minutes,
            distance_km=row.distance_km,
            mean_heart_rate=row.mean_heart_rate,
            source=row.source.value,
            burn=_burn_for(
                sport.key,
                payload.duration_minutes,
                weight,
                payload.intensity,
                payload.active_energy_kcal,
            ),
        ),
        where_this_goes=list(sports_svc.WHERE_THIS_GOES),
        target_explainer=sports_svc.TARGET_EXPLAINER,
    )


@router.get("/activities", response_model=list[ActivityOut])
async def list_activities(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    days: int = Query(default=14, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ActivityOut]:
    """Recent sessions, manual and imported, newest first.

    One list rather than two. The artifact separates "what did you do" from
    "arrived on their own" visually, but they are the same kind of thing and
    splitting them in the API would mean the client had to merge and re-sort
    two feeds to render one timeline.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        await session.execute(
            select(ExternalWorkout)
            .where(
                ExternalWorkout.user_id == user.id,
                ExternalWorkout.started_at >= since,
            )
            .order_by(ExternalWorkout.started_at.desc())  # type: ignore[union-attr]
            .limit(limit)
        )
    ).scalars().all()

    weight = await _latest_weight_kg(session, user)
    out: list[ActivityOut] = []
    for r in rows:
        sport = sports_svc.BY_KEY.get(r.activity_type) or sports_svc.find(
            r.activity_type
        )
        out.append(
            ActivityOut(
                id=r.id,
                sport=r.activity_type,
                name=sport.name if sport else r.activity_type.replace("_", " ").title(),
                started_at=r.started_at,
                duration_minutes=r.duration_minutes,
                distance_km=r.distance_km,
                mean_heart_rate=r.mean_heart_rate,
                source=r.source.value if hasattr(r.source, "value") else str(r.source),
                burn=(
                    _burn_for(
                        sport.key,
                        r.duration_minutes,
                        weight,
                        "moderate",
                        r.active_energy_kcal,
                    )
                    if sport
                    else None
                ),
            )
        )
    return out


@router.delete("/activities/{activity_id}", status_code=204)
async def delete_activity(
    activity_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> None:
    """Remove a session. Mistyped durations are the common case."""
    row = await session.get(ExternalWorkout, activity_id)
    # The ownership check is folded into the 404 on purpose: a distinct 403
    # would confirm that someone else's activity id exists.
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Activity not found.")
    await session.delete(row)
    await session.commit()


# ===========================================================================
# CONSISTENCY, AND WHETHER THE PHASE IS WORKING
#
# ONE ENDPOINT RETURNS BOTH, and that is a design decision rather than a
# convenience. A streak shown on its own is a slot machine: forty days of
# diligent logging on a bulk that has added nothing but fat is not an
# achievement, and an app that congratulates you for it is lying pleasantly.
#
# Returning them together means the client cannot render the flattering half
# without the honest half -- it would have to deliberately discard a field it
# already has.
# ===========================================================================


class ConsistencyOut(BaseModel):
    current_streak: int
    longest_streak: int
    days_logged: int
    window_days: int
    consistency_pct: float
    logged_today: bool
    data_confidence: float
    milestone: str | None
    next_milestone: str | None
    days_to_next: int | None
    headline: str


class PhaseOut(BaseModel):
    verdict: str
    goal: str
    weeks_elapsed: float
    start_weight_kg: float | None
    current_weight_kg: float | None
    total_change_kg: float | None
    rate_kg_per_week: float | None
    target_rate_kg_per_week: float | None
    headline: str
    detail: str
    notes: list[str]


class ProgressOut(BaseModel):
    consistency: ConsistencyOut
    phase: PhaseOut


@router.get("/consistency", response_model=ProgressOut)
async def consistency_and_phase(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    window_days: int = Query(default=30, ge=7, le=365),
) -> ProgressOut:
    """How consistently they've logged, and whether the phase is working."""
    today = date.today()

    # ---- what counts as "used the app" --------------------------------
    # A logged MEAL, specifically. Opening the app is not participation, and
    # a streak that counts app opens would reward the wrong behaviour and
    # give the TDEE engine nothing extra to work with.
    since = today - timedelta(days=max(window_days, 400))
    rows = (
        await session.execute(
            sa_select(func.date(MealLog.logged_at)).where(
                MealLog.user_id == user.id,
                func.date(MealLog.logged_at) >= since,
            ).distinct()
        )
    ).scalars().all()
    logged_days = {r if isinstance(r, date) else date.fromisoformat(str(r)) for r in rows}

    con = streak_svc.consistency(logged_days, today, window_days=window_days)

    # ---- the phase ----------------------------------------------------
    weights = (
        await session.execute(
            select(WeightEntry)
            .where(WeightEntry.user_id == user.id)
            .order_by(WeightEntry.measured_on)  # type: ignore[arg-type]
        )
    ).scalars().all()

    start_kg: float | None = None
    current_kg: float | None = None
    started_on = None
    if weights:
        # SMOOTHED at both ends, never a single morning. One salty dinner at
        # either end of the window would otherwise swing the computed rate by
        # more than the entire effect being measured.
        head = weights[: min(3, len(weights))]
        tail = weights[-min(7, len(weights)) :]
        start_kg = sum(w.weight_kg for w in head) / len(head)
        current_kg = sum(w.weight_kg for w in tail) / len(tail)
        started_on = weights[0].measured_on

    target_rate = _target_rate_for(user)
    ph = streak_svc.phase_progress(
        goal=user.goal_type.value if hasattr(user.goal_type, "value") else str(user.goal_type),
        start_weight_kg=start_kg,
        current_weight_kg=current_kg,
        started_on=started_on,
        today=today,
        target_rate_kg_per_week=target_rate,
    )

    return ProgressOut(
        consistency=ConsistencyOut(**con.__dict__),
        phase=PhaseOut(
            verdict=ph.verdict.value,
            goal=ph.goal,
            weeks_elapsed=ph.weeks_elapsed,
            start_weight_kg=round(ph.start_weight_kg, 2) if ph.start_weight_kg else None,
            current_weight_kg=(
                round(ph.current_weight_kg, 2) if ph.current_weight_kg else None
            ),
            total_change_kg=ph.total_change_kg,
            rate_kg_per_week=ph.rate_kg_per_week,
            target_rate_kg_per_week=ph.target_rate_kg_per_week,
            headline=ph.headline,
            detail=ph.detail,
            notes=ph.notes,
        ),
    )


def _target_rate_for(user: User) -> float | None:
    """The weekly rate this user's goal implies, in kg.

    Conservative on purpose. A faster bulk is mostly fat and a faster cut
    costs muscle, so the defaults sit where the literature puts the best
    ratio of tissue gained to tissue regretted -- not where someone impatient
    would put them.
    """
    goal = user.goal_type.value if hasattr(user.goal_type, "value") else str(user.goal_type)
    if goal == "gain":
        return 0.25
    if goal == "lose":
        # Scaled to body mass: 0.7%/week is the usual ceiling before lifts
        # start dropping, and 0.7% of 60 kg is a very different number from
        # 0.7% of 110 kg.
        mass = user.starting_weight_kg or 75.0
        return -round(mass * 0.006, 2)
    return 0.0
