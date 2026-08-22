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

    # Rounding to the nearest 10 can land BELOW the floor we just enforced --
    # a 1,383 kcal BMR gives a floor of 1,522, which rounds to 1,520. Two
    # kilocalories is nutritionally meaningless, but a safety floor that the
    # very next line can round through is not a safety floor, and the next
    # person to read this would reasonably assume it holds. Round up instead.
    if target < floor:
        target += 10

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


# ---------------------------------------------------------------------------
# The maintenance readout -- what the user actually sees
# ---------------------------------------------------------------------------
#
# The blended number above is the honest answer, but a bare "2,514" invites
# more trust than any expenditure estimate deserves. So the readout always
# carries three things a single number cannot:
#
#   the BAND    how wide the uncertainty still is
#   the SOURCE  how many weigh-ins and logged days produced it
#   the DELTA   how far it sits from what a formula would have guessed
#
# The third one is the whole pitch. If our number always agreed with
# Mifflin-St Jeor we would be an expensive calculator; when it disagrees by
# 200 kcal, that gap IS the product, and the user should see it.

# A prediction equation carries roughly this much error on an individual --
# Mifflin-St Jeor's published SEE is about 10%, and it is worse at the tails.
BAND_MAX_PCT = 0.18

# ...and this is the floor. Even with a year of perfect data, true daily
# expenditure moves with NEAT, thermic effect and water. Claiming +/-1% would
# be a lie told in a confident voice.
BAND_MIN_PCT = 0.04


@dataclass
class MaintenanceReadout:
    maintenance_kcal: float
    band_low: float
    band_high: float
    band_pct: float
    dialed_pct: int              # 0-100, how tight the band has become
    is_data_driven: bool
    prior_kcal: float
    observed_kcal: float | None
    vs_calculator: float | None  # measured - calculator, signed
    weigh_ins: int
    logged_days: int
    eating_kcal: float | None
    eating_delta: float | None
    expected_rate_kg_per_week: float | None
    source_line: str


def maintenance_readout(
    result: ExpenditureResult,
    *,
    recent_intake_kcal: float | None = None,
    total_weigh_ins: int | None = None,
    total_logged_days: int | None = None,
) -> MaintenanceReadout:
    """Turn an ExpenditureResult into the numbers the maintenance card shows.

    `total_weigh_ins` / `total_logged_days` describe the user's whole history,
    not just the estimation window -- the card is answering "how much have I
    given you to work with", and "106 weigh-ins" is a fairer answer to that
    than "21 days of window".

    `expected_rate_kg_per_week` is a projection from an energy balance, not a
    promise. It is only produced when we have an intake to project from.
    """
    kcal = result.tdee_blended
    band_pct = BAND_MIN_PCT + (BAND_MAX_PCT - BAND_MIN_PCT) * (1 - result.confidence)
    half = kcal * band_pct

    # `dialed` is derived from the band rather than stored beside it, so the
    # bar and the range on screen can never disagree with each other.
    dialed = (BAND_MAX_PCT - band_pct) / (BAND_MAX_PCT - BAND_MIN_PCT)

    data_driven = result.tdee_observed is not None and result.confidence > 0
    vs_calc = (
        round(kcal - result.tdee_prior, 0) if data_driven else None
    )

    weigh_ins = total_weigh_ins if total_weigh_ins is not None else result.weigh_ins
    logged = total_logged_days if total_logged_days is not None else result.logged_days

    eating_delta = None
    rate = None
    if recent_intake_kcal is not None:
        eating_delta = round(recent_intake_kcal - kcal, 0)
        rate = round(eating_delta * 7 / KCAL_PER_KG_TISSUE, 2)

    if data_driven:
        source = (
            f"Calculator guessed {result.tdee_prior:,.0f} · "
            f"I measured {kcal:,.0f} from {weigh_ins} weigh-ins "
            f"+ {logged} logged days"
        )
    else:
        # Say WHY it is still a guess. "Not enough data" with no path forward
        # is the least useful sentence an app can show.
        need = []
        if weigh_ins < MIN_WEIGH_INS:
            need.append(f"{MIN_WEIGH_INS - weigh_ins} more weigh-ins")
        if logged < MIN_LOGGED_DAYS:
            need.append(f"{MIN_LOGGED_DAYS - logged} more logged days")
        tail = " · ".join(need) if need else "a few more days of data"
        source = f"Still the calculator's guess — {tail} and I can measure it"

    return MaintenanceReadout(
        maintenance_kcal=round(kcal, 0),
        band_low=round(kcal - half, 0),
        band_high=round(kcal + half, 0),
        band_pct=round(band_pct, 4),
        dialed_pct=int(round(max(0.0, min(1.0, dialed)) * 100)),
        is_data_driven=data_driven,
        prior_kcal=round(result.tdee_prior, 0),
        observed_kcal=(
            round(result.tdee_observed, 0)
            if result.tdee_observed is not None
            else None
        ),
        vs_calculator=vs_calc,
        weigh_ins=weigh_ins,
        logged_days=logged,
        eating_kcal=round(recent_intake_kcal, 0) if recent_intake_kcal else None,
        eating_delta=eating_delta,
        expected_rate_kg_per_week=rate,
        source_line=source,
    )


def maintenance_history(
    *,
    intake_by_day: dict[date, float],
    trend_series: list[tuple[date, float | None, float]],
    tdee_prior: float,
    window_days: int = 21,
    max_points: int = 90,
) -> list[dict]:
    """The band chart: what our estimate WAS on each past day.

    This is a re-run of the estimator against progressively less data, not a
    smoothing of the current number -- so the chart genuinely shows the band
    narrowing as evidence arrived, which is the story the card is telling. A
    fabricated taper would be a much prettier lie.

    Capped at `max_points` by strided sampling; the shape is what matters and
    a 400-day chart on a phone is 400 invisible pixels of work.
    """
    if len(trend_series) < 2:
        return []

    # Only days where an estimate is even possible.
    start = max(2, WASHOUT_DAYS + 7)
    days = list(range(start, len(trend_series) + 1))
    if not days:
        return []
    # Ceiling division, not floor: floor overshoots the cap (383 days at
    # max_points=60 gives stride 6, which yields 64 points, not 60).
    stride = max(1, -(-len(days) // max_points))
    days = days[::stride]
    if days[-1] != len(trend_series):
        days.append(len(trend_series))

    out: list[dict] = []
    for n in days:
        head = trend_series[:n]
        as_of = head[-1][0]
        r = estimate_expenditure(
            intake_by_day={d: v for d, v in intake_by_day.items() if d <= as_of},
            trend_series=head,
            tdee_prior=tdee_prior,
            window_days=window_days,
        )
        band_pct = BAND_MIN_PCT + (BAND_MAX_PCT - BAND_MIN_PCT) * (1 - r.confidence)
        half = r.tdee_blended * band_pct
        out.append(
            {
                "date": as_of.isoformat(),
                "kcal": round(r.tdee_blended, 0),
                "low": round(r.tdee_blended - half, 0),
                "high": round(r.tdee_blended + half, 0),
            }
        )
    return out
