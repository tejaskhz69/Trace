"""The nutrition-v2 screens: uncertainty, the weekly budget, protein, fuel.

Thin, like every router here. All four services underneath are pure functions
with their own exhaustive tests; this file's whole job is fetching rows and
handing them over.

ONE ENDPOINT PER SCREEN, not one per fact. Each of these screens needs several
related numbers at once, and splitting them would mean the client firing four
requests and stitching the results — which is how a screen ends up rendering
half a state.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import (
    BodyComposition,
    FoodItem,
    MealLog,
    SetLog,
    User,
    WorkoutSession,
)
from ..services import (
    fuel_link,
    nutrient_panel,
    protein_coach,
    uncertainty,
    week_budget,
)
from ..services.fuel_link import Session as FuelSession
from ..services.protein_coach import MealProtein
from ..services.uncertainty import LoggedItem
from .auth import current_user

router = APIRouter(prefix="/api/insights", tags=["insights"])


async def _calorie_target(session: AsyncSession, user: User) -> float | None:
    row = await session.scalar(
        select(BodyComposition)
        .where(BodyComposition.user_id == user.id)
        .order_by(BodyComposition.week_start.desc())  # type: ignore[union-attr]
    )
    return row.calorie_target if row else None


async def _meals_on(
    session: AsyncSession, user: User, on: date
) -> list[MealLog]:
    start = datetime.combine(on, time.min, tzinfo=timezone.utc)
    end = datetime.combine(on, time.max, tzinfo=timezone.utc)
    return list(
        (
            await session.execute(
                select(MealLog)
                .where(
                    MealLog.user_id == user.id,
                    MealLog.logged_at >= start,
                    MealLog.logged_at <= end,
                )
                .order_by(MealLog.logged_at)  # type: ignore[arg-type]
            )
        ).scalars().all()
    )


# ===========================================================================
# 1 · HOW WELL DO WE KNOW TODAY?
# ===========================================================================


class SliceOut(BaseModel):
    source: str
    label: str
    kcal: float
    share: float
    uncertainty_share: float


class ItemOut(BaseModel):
    name: str
    kcal: float
    band: float
    source: str
    source_label: str


class UncertaintyOut(BaseModel):
    total_kcal: float
    band: float
    low: float
    high: float
    confidence: str
    band_pct: float
    mix: list[SliceOut]
    items: list[ItemOut]
    worst_item: Optional[str]
    worst_item_band: Optional[float]
    headline: str
    advice: Optional[str]
    calorie_target: Optional[float]


@router.get("/uncertainty", response_model=UncertaintyOut)
async def today_uncertainty(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    on: date = Query(default_factory=date.today, alias="date"),
) -> UncertaintyOut:
    """The day total as an honest range, and where the width comes from."""
    rows = await _meals_on(session, user, on)

    # One query for every food row referenced, rather than one per meal. A
    # barcode is what separates "label" from "search" and we need it for each.
    ids = {r.food_item_id for r in rows if r.food_item_id}
    barcoded: set[str] = set()
    if ids:
        barcoded = {
            fid
            for fid in (
                await session.execute(
                    sa_select(FoodItem.id).where(
                        FoodItem.id.in_(list(ids)),  # type: ignore[union-attr]
                        FoodItem.barcode.is_not(None),  # type: ignore[union-attr]
                    )
                )
            ).scalars().all()
        }

    items = [
        LoggedItem(
            name=r.display_name or "Meal",
            kcal=float(r.calories or 0.0),
            source=uncertainty.classify_source(
                recognition_id=r.recognition_id,
                food_item_id=r.food_item_id,
                has_barcode=bool(r.food_item_id and r.food_item_id in barcoded),
            ),
            kcal_low=r.kcal_low,
            kcal_high=r.kcal_high,
        )
        for r in rows
    ]

    result = uncertainty.day_uncertainty(items)

    return UncertaintyOut(
        total_kcal=result.total_kcal,
        band=result.band,
        low=result.low,
        high=result.high,
        confidence=result.confidence,
        band_pct=result.band_pct,
        mix=[SliceOut(**s.__dict__) for s in result.mix],
        items=[
            ItemOut(
                name=i.name,
                kcal=round(i.kcal, 1),
                band=round(i.half_width(), 1),
                source=i.source.value,
                source_label=uncertainty.SOURCE_LABEL.get(
                    i.source.value, i.source.value
                ),
            )
            for i in items
        ],
        worst_item=result.worst_item,
        worst_item_band=result.worst_item_band,
        headline=result.headline,
        advice=result.advice,
        calorie_target=await _calorie_target(session, user),
    )


# ===========================================================================
# 2 · THE WEEKLY BUDGET
# ===========================================================================


class DayOut(BaseModel):
    day: date
    baseline_kcal: float
    planned_kcal: float
    logged_kcal: Optional[float]
    shift: float
    delta: Optional[float]
    flagged: bool
    is_past: bool
    is_today: bool


class WeekOut(BaseModel):
    start: date
    end: date
    daily_target: float
    week_target: float
    spent: float
    remaining: float
    days_left: int
    per_day_remaining: Optional[float]
    status: str
    days: list[DayOut]
    headline: str
    detail: str
    notes: list[str]
    carries_forward: float


@router.get("/week", response_model=WeekOut)
async def weekly_budget(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    flagged: str = Query(default="", description="ISO dates, comma separated"),
) -> WeekOut:
    """The week as a budget, with any flagged days already paid for."""
    today = date.today()
    target = await _calorie_target(session, user) or 2000.0

    start, end = week_budget.week_bounds(today)
    rows = (
        await session.execute(
            sa_select(
                func.date(MealLog.logged_at),
                func.sum(MealLog.calories),
            )
            .where(
                MealLog.user_id == user.id,
                func.date(MealLog.logged_at) >= start,
                func.date(MealLog.logged_at) <= end,
            )
            .group_by(func.date(MealLog.logged_at))
        )
    ).all()

    logged = {
        (d if isinstance(d, date) else date.fromisoformat(str(d))): float(k or 0)
        for d, k in rows
    }

    flagged_days: set[date] = set()
    for token in flagged.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            flagged_days.add(date.fromisoformat(token))
        except ValueError:
            # A malformed date is the client's problem, not a 500. Ignore it
            # and plan the week without that flag.
            continue

    w = week_budget.build_week(today, target, logged, flagged_days)

    return WeekOut(
        start=w.start,
        end=w.end,
        daily_target=w.daily_target,
        week_target=w.week_target,
        spent=w.spent,
        remaining=w.remaining,
        days_left=w.days_left,
        per_day_remaining=w.per_day_remaining,
        status=w.status,
        days=[
            DayOut(
                day=d.day,
                baseline_kcal=d.baseline_kcal,
                planned_kcal=d.planned_kcal,
                logged_kcal=d.logged_kcal,
                shift=d.shift,
                delta=d.delta,
                flagged=d.flagged,
                is_past=d.is_past,
                is_today=d.is_today,
            )
            for d in w.days
        ],
        headline=w.headline,
        detail=w.detail,
        notes=w.notes,
        # Always 0.0. Sent on the wire so the client can state the promise
        # rather than assert it from memory.
        carries_forward=week_budget.settle(w),
    )


# ===========================================================================
# 3 · PROTEIN
# ===========================================================================


class MealProteinOut(BaseModel):
    name: str
    hour: float
    protein_g: float


class FoodOut(BaseModel):
    key: str
    name: str
    portion: str
    protein_g: float
    kcal: float
    rupees: float
    g_per_10_rupees: float
    veg: bool
    price_confidence: str


class ProteinOut(BaseModel):
    total_g: float
    target_g: Optional[float]
    short_by_g: float
    shape: str
    thinnest_meal: Optional[str]
    real_doses: int
    meals: list[MealProteinOut]
    headline: str
    detail: str
    fix_foods: list[FoodOut]
    fix_protein_g: float
    fix_rupees: float
    fix_note: str
    ranked: list[FoodOut]
    prices_as_of: str
    prices_region: str
    prices_stale_months: int


def _food_out(f: protein_coach.ProteinFood) -> FoodOut:
    return FoodOut(
        key=f.key,
        name=f.name,
        portion=f.portion,
        protein_g=f.protein_g,
        kcal=f.kcal,
        rupees=f.rupees,
        g_per_10_rupees=f.g_per_10_rupees,
        veg=f.veg,
        price_confidence=f.price_confidence,
    )


@router.get("/protein", response_model=ProteinOut)
async def protein_today(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    on: date = Query(default_factory=date.today, alias="date"),
    veg_only: bool = Query(default=False),
) -> ProteinOut:
    """When the protein landed, how short it is, and the cheapest fix."""
    rows = await _meals_on(session, user, on)
    meals = [
        MealProtein(
            name=r.display_name or (r.meal_type or "Meal").title(),
            hour=r.logged_at.hour + r.logged_at.minute / 60,
            protein_g=float(r.protein_g or 0.0),
        )
        for r in rows
        if (r.protein_g or 0) > 0
    ]

    comp = await session.scalar(
        select(BodyComposition)
        .where(BodyComposition.user_id == user.id)
        .order_by(BodyComposition.week_start.desc())  # type: ignore[union-attr]
    )
    target = comp.protein_target_g if comp else None
    weight = user.starting_weight_kg

    timing = protein_coach.analyse_timing(meals, target, weight)
    short = max(0.0, (target or 0) - timing.total_g)
    fix = protein_coach.close_the_gap(short, veg_only=veg_only)

    return ProteinOut(
        total_g=timing.total_g,
        target_g=timing.target_g,
        short_by_g=round(short, 1),
        shape=timing.shape,
        thinnest_meal=timing.thinnest_meal,
        real_doses=timing.real_doses,
        meals=[MealProteinOut(**m.__dict__) for m in timing.meals],
        headline=timing.headline,
        detail=timing.detail,
        fix_foods=[_food_out(f) for f in fix.foods],
        fix_protein_g=fix.protein_g,
        fix_rupees=fix.rupees,
        fix_note=fix.note,
        ranked=[_food_out(f) for f in protein_coach.rank_by_cost(veg_only=veg_only)],
        prices_as_of=protein_coach.PRICES_AS_OF,
        prices_region=protein_coach.PRICES_REGION,
        prices_stale_months=protein_coach.price_staleness_months(),
    )


# ===========================================================================
# 4 · FUEL vs TRAINING
# ===========================================================================


class ShiftOut(BaseModel):
    carbs_delta_g: float
    fat_delta_g: float
    kcal_delta: float
    headline: str
    detail: str


class FuelOut(BaseModel):
    verdict: str
    pairs: int
    rho: Optional[float]
    high_carb_volume: Optional[float]
    low_carb_volume: Optional[float]
    uplift_pct: Optional[float]
    carb_threshold_g: Optional[float]
    headline: str
    detail: str
    notes: list[str]
    suggestion: Optional[ShiftOut]


@router.get("/fuel", response_model=FuelOut)
async def fuel_vs_training(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    days: int = Query(default=90, ge=21, le=365),
    training_tomorrow: bool = Query(default=False),
) -> FuelOut:
    """Whether yesterday's carbs show up in today's session volume."""
    since = date.today() - timedelta(days=days)

    carb_rows = (
        await session.execute(
            sa_select(func.date(MealLog.logged_at), func.sum(MealLog.carbs_g))
            .where(
                MealLog.user_id == user.id,
                func.date(MealLog.logged_at) >= since,
            )
            .group_by(func.date(MealLog.logged_at))
        )
    ).all()
    carbs = {
        (d if isinstance(d, date) else date.fromisoformat(str(d))): float(c or 0)
        for d, c in carb_rows
    }

    # Volume is sum(weight x reps) per session, warm-ups excluded -- they are
    # tonnage that says nothing about how the session went.
    vol_rows = (
        await session.execute(
            sa_select(
                func.date(WorkoutSession.started_at),
                WorkoutSession.routine_name,
                func.sum(SetLog.weight_kg * SetLog.reps),
            )
            .join(SetLog, SetLog.session_id == WorkoutSession.id)  # type: ignore[arg-type]
            .where(
                WorkoutSession.user_id == user.id,
                func.date(WorkoutSession.started_at) >= since,
                SetLog.is_warmup.is_(False),  # type: ignore[union-attr]
            )
            .group_by(
                func.date(WorkoutSession.started_at), WorkoutSession.routine_name
            )
        )
    ).all()

    sessions = [
        FuelSession(
            day=(d if isinstance(d, date) else date.fromisoformat(str(d))),
            volume_kg=float(v or 0),
            focus=(name or "").lower() or None,
        )
        for d, name, v in vol_rows
    ]

    link = fuel_link.analyse(carbs, sessions)
    shift = fuel_link.suggest_shift(link, training_tomorrow)

    return FuelOut(
        verdict=link.verdict.value,
        pairs=link.pairs,
        rho=link.rho,
        high_carb_volume=link.high_carb_volume,
        low_carb_volume=link.low_carb_volume,
        uplift_pct=link.uplift_pct,
        carb_threshold_g=link.carb_threshold_g,
        headline=link.headline,
        detail=link.detail,
        notes=link.notes,
        suggestion=ShiftOut(**shift.__dict__) if shift else None,
    )


# ===========================================================================
# 5 · THE FULL NUTRIENT PANEL
# ===========================================================================


class NutrientRowOut(BaseModel):
    key: str
    name: str
    unit: str
    group: str
    kind: str
    amount: Optional[float]
    target: float
    pct: Optional[float]
    status: str
    covered: float


class PanelOut(BaseModel):
    rows: list[NutrientRowOut]
    notable: list[str]
    tracked: int
    known: int
    headline: str
    notes: dict[str, str]
    sodium_potassium_ratio: Optional[float]
    sodium_potassium_note: str


@router.get("/nutrients", response_model=PanelOut)
async def nutrient_panel_today(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    on: date = Query(default_factory=date.today, alias="date"),
) -> PanelOut:
    """Every nutrient we can see, and an explicit gap where we cannot.

    COVERAGE IS COMPUTED PER NUTRIENT, weighted by calories. A day where one
    500 kcal meal carries iron and a 1,500 kcal meal does not is 25% covered
    for iron -- and 25% is not enough to tell somebody they are deficient.
    """
    rows = await _meals_on(session, user, on)
    if not rows:
        panel = nutrient_panel.build_panel({}, {})
        return PanelOut(
            rows=[NutrientRowOut(**r.__dict__) for r in panel.rows],
            notable=panel.notable,
            tracked=panel.tracked,
            known=panel.known,
            headline=panel.headline,
            notes={},
            sodium_potassium_ratio=None,
            sodium_potassium_note="Nothing logged yet today.",
        )

    ids = {r.food_item_id for r in rows if r.food_item_id}
    foods: dict[str, FoodItem] = {}
    if ids:
        found = (
            await session.execute(
                select(FoodItem).where(FoodItem.id.in_(list(ids)))  # type: ignore[union-attr]
            )
        ).scalars().all()
        foods = {f.id: f for f in found}

    totals: dict[str, float] = {}
    covered_kcal: dict[str, float] = {}
    day_kcal = sum(float(r.calories or 0.0) for r in rows) or 1.0

    #: Columns the diary row carries itself, so they need no food join.
    DIRECT = {
        "protein_g": "protein_g",
        "carbs_g": "carbs_g",
        "fat_g": "fat_g",
        "fiber_g": "fiber_g",
        "sugar_g": "sugars_g",
        "sodium_mg": "sodium_mg",
        "potassium_mg": "potassium_mg",
    }

    for meal in rows:
        kcal = float(meal.calories or 0.0)
        food = foods.get(meal.food_item_id) if meal.food_item_id else None
        # The diary stores absolute amounts for the portion eaten; the food row
        # stores per-100 g, so micronutrients scale by the grams logged.
        factor = (float(meal.grams or 0.0) / 100.0) if meal.grams else 0.0

        for key, attr in DIRECT.items():
            val = getattr(meal, attr, None)
            if val is not None:
                totals[key] = totals.get(key, 0.0) + float(val)
                covered_kcal[key] = covered_kcal.get(key, 0.0) + kcal

        if food is None or factor <= 0:
            continue

        if food.saturated_fat_g is not None:
            totals["saturated_fat_g"] = (
                totals.get("saturated_fat_g", 0.0) + food.saturated_fat_g * factor
            )
            covered_kcal["saturated_fat_g"] = (
                covered_kcal.get("saturated_fat_g", 0.0) + kcal
            )

        micro = food.micronutrients or {}
        for key, raw in micro.items():
            if key not in nutrient_panel.BY_KEY or raw is None:
                continue
            try:
                totals[key] = totals.get(key, 0.0) + float(raw) * factor
            except (TypeError, ValueError):
                continue
            covered_kcal[key] = covered_kcal.get(key, 0.0) + kcal

    coverage = {k: v / day_kcal for k, v in covered_kcal.items()}

    comp = await session.scalar(
        select(BodyComposition)
        .where(BodyComposition.user_id == user.id)
        .order_by(BodyComposition.week_start.desc())  # type: ignore[union-attr]
    )

    panel = nutrient_panel.build_panel(
        totals,
        coverage,
        sex=user.sex.value if hasattr(user.sex, "value") else user.sex,
        calorie_target=comp.calorie_target if comp else None,
    )

    ratio, ratio_note = nutrient_panel.sodium_potassium_ratio(
        totals.get("sodium_mg"), totals.get("potassium_mg")
    )

    return PanelOut(
        rows=[NutrientRowOut(**r.__dict__) for r in panel.rows],
        notable=panel.notable,
        tracked=panel.tracked,
        known=panel.known,
        headline=panel.headline,
        # Only the notes for rows actually worth surfacing. Shipping all of
        # them would make the client decide what matters, which is the
        # server's job here.
        notes={k: nutrient_panel.NOTES[k] for k in panel.notable if k in nutrient_panel.NOTES},
        sodium_potassium_ratio=ratio,
        sodium_potassium_note=ratio_note,
    )
