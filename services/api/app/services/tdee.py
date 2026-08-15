"""Adaptive TDEE / calorie-target engine.

This is the MacroFactor-style loop: stop trusting a static formula, and instead
reconstruct the user's real expenditure from the energy balance they actually
demonstrated, blending toward observation as evidence accumulates.

Pure functions, no I/O -- so it is trivially unit-testable, which matters
because a bug here silently gives people wrong calorie targets for weeks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

KCAL_PER_KG_TISSUE = 7700.0  # ~7,700 kcal per kg of mostly-fat tissue
TREND_ALPHA = 0.1            # EWMA smoothing; ~20-day half-life
MAX_WEEKLY_TARGET_CHANGE = 150.0
# Fiber scales with how much you eat, not with body weight. 14 g per 1,000
# kcal is the Dietary Guidelines / IOM figure.
FIBER_G_PER_1000_KCAL = 14.0
TDEE_CLAMP_PCT = 0.25
MIN_LOGGED_DAYS = 5
MIN_WEIGH_INS = 10
WASHOUT_DAYS = 10            # first 10 days are water/glycogen noise


# ---------------------------------------------------------------------------
# Trend weight
# ---------------------------------------------------------------------------


def trend_weight_series(
    entries: list[tuple[date, float]],
    alpha: float = TREND_ALPHA,
) -> list[tuple[date, float | None, float]]:
    """Return [(date, raw_or_None, trend)] over a gap-filled daily calendar.

    Missing days carry the previous trend forward rather than interpolating a
    fake measurement. Showing the raw dots faintly and the trend line boldly is
    what stops users panicking about a 1.5 kg overnight "gain" that is entirely
    salt and glycogen.
    """
    if not entries:
        return []

    entries = sorted(entries, key=lambda e: e[0])
    by_day = {d: w for d, w in entries}

    start, end = entries[0][0], entries[-1][0]
    out: list[tuple[date, float | None, float]] = []
    trend = entries[0][1]

    day = start
    while day <= end:
        raw = by_day.get(day)
        if raw is not None:
            trend = trend + alpha * (raw - trend)
        out.append((day, raw, round(trend, 3)))
        day += timedelta(days=1)

    return out


def mifflin_st_jeor(
    weight_kg: float, height_cm: float, age_years: float, sex: str | None
) -> float:
    """Resting metabolic rate. The prior we start from before we have data."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age_years
    if (sex or "").lower() == "female":
        return base - 161
    return base + 5


# ---------------------------------------------------------------------------
# Expenditure estimation
# ---------------------------------------------------------------------------


@dataclass
class ExpenditureResult:
    tdee_prior: float
    tdee_observed: float | None
    tdee_blended: float
    confidence: float
    days_of_data: int
    logged_days: int
    weigh_ins: int
    notes: list[str] = field(default_factory=list)


def estimate_expenditure(
    *,
    intake_by_day: dict[date, float],
    trend_series: list[tuple[date, float | None, float]],
    tdee_prior: float,
    window_days: int = 21,
) -> ExpenditureResult:
    """Reconstruct TDEE from observed energy balance, blended with the prior.

        TDEE_observed = mean_intake - (delta_trend_kg * 7700) / days

    A user losing 0.3 kg/week while eating 2,400 kcal/day is burning roughly
    2,400 + (0.3 * 7700 / 7) = ~2,730 kcal/day, regardless of what any equation
    predicts about them.
    """
    notes: list[str] = []

    if len(trend_series) < 2:
        return ExpenditureResult(
            tdee_prior, None, tdee_prior, 0.0, 0, 0, 0, ["no_weight_data"]
        )

    # Drop the washout period -- early water shifts wreck the estimate.
    usable = trend_series[WASHOUT_DAYS:] if len(trend_series) > WASHOUT_DAYS else []
    if not usable:
        notes.append("washout_period")
        return ExpenditureResult(
            tdee_prior, None, tdee_prior, 0.0, len(trend_series), 0, 0, notes
        )

    window = usable[-window_days:]
    days = len(window)
    if days < 7:
        notes.append("window_too_short")
        return ExpenditureResult(
            tdee_prior, None, tdee_prior, 0.0, days, 0, 0, notes
        )

    window_dates = {d for d, _, _ in window}
    logged = {d: kcal for d, kcal in intake_by_day.items() if d in window_dates}
    weigh_ins = sum(1 for _, raw, _ in window if raw is not None)

    if len(logged) < MIN_LOGGED_DAYS or weigh_ins < MIN_WEIGH_INS:
        notes.append("insufficient_logging")
        return ExpenditureResult(
            tdee_prior, None, tdee_prior, 0.0, days, len(logged), weigh_ins, notes
        )

    mean_intake = sum(logged.values()) / len(logged)
    delta_trend = window[-1][2] - window[0][2]
    tdee_observed = mean_intake - (delta_trend * KCAL_PER_KG_TISSUE) / days

    # Clamp: a wildly out-of-range observation means under-logging, not a
    # broken metabolism. Say so instead of silently slashing the target.
    lo, hi = tdee_prior * (1 - TDEE_CLAMP_PCT), tdee_prior * (1 + TDEE_CLAMP_PCT)
    if tdee_observed < lo:
        notes.append("observed_below_plausible_range__likely_underlogging")
        tdee_observed = lo
    elif tdee_observed > hi:
        notes.append("observed_above_plausible_range__check_weigh_in_consistency")
        tdee_observed = hi

    # Confidence grows with data, capped so the prior never fully disappears.
    adherence = len(logged) / days
    w = min(0.85, (days / 28.0) * adherence)
    tdee_blended = w * tdee_observed + (1 - w) * tdee_prior

    return ExpenditureResult(
        tdee_prior=round(tdee_prior, 1),
        tdee_observed=round(tdee_observed, 1),
        tdee_blended=round(tdee_blended, 1),
        confidence=round(w, 3),
        days_of_data=days,
        logged_days=len(logged),
        weigh_ins=weigh_ins,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Target setting
# ---------------------------------------------------------------------------


@dataclass
class TargetRecommendation:
    calorie_target: float
    protein_target_g: float
    fat_target_g: float
    carb_target_g: float
    fiber_target_g: float
    delta_from_previous: float
    rationale: str
    math: dict


def recommend_targets(
    *,
    tdee: float,
    weight_kg: float,
    goal_type: str,
    previous_target: float | None,
    bmr: float,
    goal_rate_pct_per_week: float | None = None,
) -> TargetRecommendation:
    """Turn an expenditure estimate into calorie + macro targets.

    Protein floors are non-negotiable in the algorithm: the whole strength
    verdict is meaningless if the user is under-eating protein, because then
    "lifts went flat" tells you nothing about their calorie level.
    """
    if goal_rate_pct_per_week is None:
        goal_rate_pct_per_week = {
            "lose": -0.7,
            "gain": 0.35,
            "recomp": 0.0,
            "maintain": 0.0,
        }.get(goal_type, 0.0)

    weekly_kg = weight_kg * (goal_rate_pct_per_week / 100.0)
    daily_delta = (weekly_kg * KCAL_PER_KG_TISSUE) / 7.0
    raw_target = tdee + daily_delta

    # Never prescribe below BMR * 1.1 -- below that, adherence collapses and
    # lean mass goes with it.
    floor = bmr * 1.1
    if raw_target < floor:
        raw_target = floor
        rationale_floor = " (raised to your minimum safe intake)"
    else:
        rationale_floor = ""

    # Smooth: never lurch the plan by more than 150 kcal in a week.
    if previous_target is not None:
        change = raw_target - previous_target
        if abs(change) > MAX_WEEKLY_TARGET_CHANGE:
            raw_target = previous_target + (
                MAX_WEEKLY_TARGET_CHANGE if change > 0 else -MAX_WEEKLY_TARGET_CHANGE
            )

    target = round(raw_target / 10) * 10  # round to a friendly number

    protein_g = round(weight_kg * (2.0 if goal_type == "lose" else 1.6))
    fat_g = round(max(weight_kg * 0.6, target * 0.20 / 9))
    carb_g = round(max(0.0, (target - protein_g * 4 - fat_g * 9) / 4))
    fiber_g = round(target / 1000.0 * FIBER_G_PER_1000_KCAL)

    delta = target - previous_target if previous_target is not None else 0.0

    return TargetRecommendation(
        calorie_target=target,
        protein_target_g=protein_g,
        fat_target_g=fat_g,
        carb_target_g=carb_g,
        fiber_target_g=fiber_g,
        delta_from_previous=delta,
        rationale=(
            f"Your expenditure is running at ~{tdee:.0f} kcal/day. "
            f"To move at {goal_rate_pct_per_week:+.2f}% body weight per week "
            f"you need {target:.0f} kcal/day{rationale_floor}."
        ),
        math={
            "tdee_estimate": tdee,
            "goal_rate_pct_per_week": goal_rate_pct_per_week,
            "goal_rate_kg_per_week": round(weekly_kg, 3),
            "daily_energy_delta": round(daily_delta, 1),
            "bmr_floor": round(floor, 1),
            "previous_target": previous_target,
            "capped_at_150_kcal_change": previous_target is not None
            and abs(raw_target - previous_target) >= MAX_WEEKLY_TARGET_CHANGE,
            "final_target": target,
            "fiber_g_per_1000_kcal": FIBER_G_PER_1000_KCAL,
        },
    )
