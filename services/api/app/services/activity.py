"""Activity, sleep, and NEAT analysis from Apple Health / Health Connect.

THE ONE RULE THAT MATTERS
-------------------------
**Never add exercise calories to the user's target.**

This is the single most common — and most damaging — mistake in fitness apps.
MyFitnessPal does it, and it is why people "eat back" 700 phantom calories and
stall.

The reason is structural, not a matter of taste. Our TDEE engine estimates
expenditure from observed energy balance:

    TDEE_observed = mean_intake - (delta_trend_weight_kg * 7700) / days

That figure ALREADY CONTAINS every calorie the user burned in the gym, on
their walk, and fidgeting at their desk — because all of it showed up in the
weight change. Adding HealthKit's `activeEnergyBurned` on top counts the same
energy twice. A user who burns 500 kcal in a session and eats it back is now
running a 500 kcal surplus against a target that already assumed the session.

Worse, consumer wearables overestimate active energy substantially — error
rates of 25-90% are well documented for non-steady-state activity. So you'd be
double-counting a number that is itself inflated.

SO WHY PULL HEALTH DATA AT ALL?
-------------------------------
Because it is the best *explainer* and *leading indicator* you can get, and
nobody uses it that way:

1. **NEAT drift** — the killer feature. When someone cuts, their non-exercise
   activity unconsciously falls: they take the lift, they fidget less, they
   walk slower. Adaptive TDEE detects the *result* (expenditure fell) three
   weeks later. Step count shows the *cause* immediately, and it is fixable
   without touching food. "Your burn is down 180 kcal/day and your steps fell
   from 9,400 to 6,100. Walk more before we cut your calories further."

2. **Faster convergence** — activity is a covariate. A user whose steps and
   training volume are stable gives a cleaner expenditure signal, so we can
   trust the observed estimate sooner. A user whose activity swings wildly
   needs a longer window. This cuts the cold-start lag materially.

3. **Readiness** — sleep debt and HRV predict a bad session before it happens.
   A strength drop after two nights of 5 hours is not a nutrition signal, and
   the adjudication engine must not treat it as one.

Pure functions. No I/O. Fully tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

# Steps -> kcal is body-mass dependent. ~0.04 kcal per step per kg is the
# common approximation for level walking at a moderate pace.
KCAL_PER_STEP_PER_KG = 0.0005
BASELINE_WINDOW_DAYS = 28
RECENT_WINDOW_DAYS = 7

# A NEAT change worth telling someone about. Below this it's noise.
NEAT_DRIFT_STEP_THRESHOLD = 1200
NEAT_DRIFT_PCT_THRESHOLD = 0.15

# Sleep
SLEEP_TARGET_HOURS = 7.5
SLEEP_DEBT_CONCERN_HOURS = 3.0   # cumulative over the recent window


class ActivityTrend(str, Enum):
    rising = "rising"
    stable = "stable"
    falling = "falling"
    insufficient_data = "insufficient_data"


@dataclass
class ActivityDay:
    day: date
    steps: int | None = None
    active_energy_kcal: float | None = None
    resting_energy_kcal: float | None = None
    exercise_minutes: float | None = None
    distance_km: float | None = None
    stand_hours: float | None = None
    source: str = "healthkit"


@dataclass
class SleepNight:
    night_of: date
    asleep_hours: float
    in_bed_hours: float | None = None
    deep_hours: float | None = None
    rem_hours: float | None = None
    awakenings: int | None = None
    efficiency: float | None = None  # asleep / in_bed


# ---------------------------------------------------------------------------
# NEAT drift
# ---------------------------------------------------------------------------


@dataclass
class NeatDrift:
    trend: ActivityTrend
    baseline_steps: float | None
    recent_steps: float | None
    delta_steps: float | None
    delta_pct: float | None
    estimated_kcal_delta: float | None
    days_of_data: int
    is_significant: bool
    message: str | None = None


def analyse_neat(
    days: list[ActivityDay],
    body_weight_kg: float,
    *,
    baseline_window: int = BASELINE_WINDOW_DAYS,
    recent_window: int = RECENT_WINDOW_DAYS,
) -> NeatDrift:
    """Compare recent daily steps against the user's own baseline.

    The comparison is against the SAME user's history, never a population
    norm. "10,000 steps" is a marketing number from a 1960s pedometer
    campaign; what matters is whether this person is moving less than they
    used to.
    """
    with_steps = [d for d in days if d.steps is not None]
    if len(with_steps) < 14:
        return NeatDrift(
            trend=ActivityTrend.insufficient_data,
            baseline_steps=None,
            recent_steps=None,
            delta_steps=None,
            delta_pct=None,
            estimated_kcal_delta=None,
            days_of_data=len(with_steps),
            is_significant=False,
            message="Not enough step data yet — I need about two weeks.",
        )

    ordered = sorted(with_steps, key=lambda d: d.day)
    recent = ordered[-recent_window:]
    # Baseline excludes the recent window so we're comparing distinct periods.
    baseline_pool = ordered[-(baseline_window + recent_window) : -recent_window]
    if len(baseline_pool) < 7:
        baseline_pool = ordered[:-recent_window] or ordered[:1]

    baseline = sum(d.steps for d in baseline_pool) / len(baseline_pool)  # type: ignore[misc]
    current = sum(d.steps for d in recent) / len(recent)  # type: ignore[misc]

    delta = current - baseline
    delta_pct = delta / baseline if baseline > 0 else 0.0
    kcal_delta = delta * KCAL_PER_STEP_PER_KG * body_weight_kg

    significant = (
        abs(delta) >= NEAT_DRIFT_STEP_THRESHOLD
        and abs(delta_pct) >= NEAT_DRIFT_PCT_THRESHOLD
    )

    if not significant:
        trend = ActivityTrend.stable
        message = None
    elif delta < 0:
        trend = ActivityTrend.falling
        message = (
            f"Your daily steps have dropped from about {baseline:,.0f} to "
            f"{current:,.0f} — roughly {abs(kcal_delta):.0f} kcal/day less "
            f"movement. This is the most common reason progress stalls on a "
            f"cut, and it's usually unconscious."
        )
    else:
        trend = ActivityTrend.rising
        message = (
            f"Your steps are up from about {baseline:,.0f} to {current:,.0f} "
            f"— roughly {kcal_delta:.0f} kcal/day more movement."
        )

    return NeatDrift(
        trend=trend,
        baseline_steps=round(baseline),
        recent_steps=round(current),
        delta_steps=round(delta),
        delta_pct=round(delta_pct, 3),
        estimated_kcal_delta=round(kcal_delta),
        days_of_data=len(with_steps),
        is_significant=significant,
        message=message,
    )


# ---------------------------------------------------------------------------
# Activity stability -> confidence in the TDEE estimate
# ---------------------------------------------------------------------------


def activity_stability(days: list[ActivityDay], window: int = 21) -> float:
    """0..1 — how consistent this user's activity has been.

    Used as a MULTIPLIER on the adaptive-TDEE confidence weight. Someone whose
    steps and training are steady gives a clean energy-balance signal, so we
    can trust the observed estimate sooner. Someone who did a 20km hike one
    weekend and nothing the next needs a longer window before we act.

    This is the legitimate way to use activity data in the TDEE loop: it
    changes how much we TRUST the estimate, never the estimate itself.
    """
    with_steps = [d.steps for d in days[-window:] if d.steps is not None]
    if len(with_steps) < 7:
        return 0.5  # neutral

    mean = sum(with_steps) / len(with_steps)
    if mean <= 0:
        return 0.5

    variance = sum((s - mean) ** 2 for s in with_steps) / len(with_steps)
    cv = (variance**0.5) / mean  # coefficient of variation

    # CV of 0.15 or below is very stable; 0.6+ is chaotic.
    if cv <= 0.15:
        return 1.0
    if cv >= 0.60:
        return 0.5
    return round(1.0 - ((cv - 0.15) / 0.45) * 0.5, 3)


# ---------------------------------------------------------------------------
# Sleep -> readiness
# ---------------------------------------------------------------------------


@dataclass
class SleepSummary:
    nights: int
    mean_hours: float | None
    debt_hours: float | None       # cumulative shortfall vs target
    worst_night_hours: float | None
    mean_efficiency: float | None
    is_concerning: bool
    message: str | None = None


def analyse_sleep(
    nights: list[SleepNight], window: int = RECENT_WINDOW_DAYS
) -> SleepSummary:
    recent = sorted(nights, key=lambda n: n.night_of)[-window:]
    if len(recent) < 3:
        return SleepSummary(
            nights=len(recent),
            mean_hours=None,
            debt_hours=None,
            worst_night_hours=None,
            mean_efficiency=None,
            is_concerning=False,
            message=None,
        )

    mean = sum(n.asleep_hours for n in recent) / len(recent)
    debt = sum(max(0.0, SLEEP_TARGET_HOURS - n.asleep_hours) for n in recent)
    worst = min(n.asleep_hours for n in recent)

    effs = [n.efficiency for n in recent if n.efficiency is not None]
    mean_eff = sum(effs) / len(effs) if effs else None

    concerning = debt >= SLEEP_DEBT_CONCERN_HOURS or mean < 6.0

    message = None
    if concerning:
        message = (
            f"You've averaged {mean:.1f} h of sleep over {len(recent)} nights "
            f"— about {debt:.1f} h of accumulated debt. Expect lower strength "
            f"and worse appetite control until that recovers. This is not a "
            f"nutrition problem, so don't change your calories over it."
        )

    return SleepSummary(
        nights=len(recent),
        mean_hours=round(mean, 2),
        debt_hours=round(debt, 1),
        worst_night_hours=round(worst, 1),
        mean_efficiency=round(mean_eff, 3) if mean_eff else None,
        is_concerning=concerning,
        message=message,
    )


# ---------------------------------------------------------------------------
# Sanity-checking wearable energy data
# ---------------------------------------------------------------------------


@dataclass
class EnergyReconciliation:
    wearable_tdee: float | None       # resting + active, per the device
    observed_tdee: float | None       # from our energy-balance model
    ratio: float | None
    verdict: str
    message: str | None = None


def reconcile_energy(
    days: list[ActivityDay], observed_tdee: float | None
) -> EnergyReconciliation:
    """Compare what the watch claims against what the scale proves.

    We never USE the wearable number for targets. But comparing them is a
    useful honesty check we can show the user — and it explains, concretely,
    why we ignore the watch's calorie figure.
    """
    usable = [
        d
        for d in days[-14:]
        if d.active_energy_kcal is not None and d.resting_energy_kcal is not None
    ]
    if len(usable) < 7 or observed_tdee is None:
        return EnergyReconciliation(None, observed_tdee, None, "insufficient_data")

    wearable = sum(
        (d.active_energy_kcal or 0) + (d.resting_energy_kcal or 0) for d in usable
    ) / len(usable)
    ratio = wearable / observed_tdee if observed_tdee > 0 else None

    if ratio is None:
        return EnergyReconciliation(wearable, observed_tdee, None, "insufficient_data")

    if ratio > 1.15:
        verdict = "wearable_overestimates"
        message = (
            f"Your watch says you burn about {wearable:.0f} kcal/day. Your "
            f"actual weight change says {observed_tdee:.0f}. Wearables "
            f"routinely overestimate by 20-40%, which is exactly why I use "
            f"your scale rather than your watch to set targets."
        )
    elif ratio < 0.85:
        verdict = "wearable_underestimates"
        message = (
            f"Your watch says {wearable:.0f} kcal/day but your weight change "
            f"says {observed_tdee:.0f}. You may not be wearing it for all your "
            f"activity — I'll keep using the scale."
        )
    else:
        verdict = "agrees"
        message = (
            f"Your watch ({wearable:.0f} kcal/day) and your actual weight "
            f"change ({observed_tdee:.0f}) agree closely. Good sign."
        )

    return EnergyReconciliation(
        wearable_tdee=round(wearable),
        observed_tdee=round(observed_tdee),
        ratio=round(ratio, 3),
        verdict=verdict,
        message=message,
    )


# ---------------------------------------------------------------------------
# Weigh-in prompting
# ---------------------------------------------------------------------------


def should_prompt_weigh_in(
    *,
    last_weigh_in: date | None,
    today: date,
    workout_just_finished: bool,
    weigh_ins_last_14_days: int,
) -> tuple[bool, str | None]:
    """Decide whether to ask for a weight right now.

    The user asked for a weigh-in prompt after every workout. Two refinements
    that make it work rather than annoy:

    1. Post-workout weight is a BAD measurement — you've lost 0.5-1.5 kg of
       sweat. Prompting then trains people to log noise. So a workout marks
       the user as "prompt tomorrow morning" rather than "prompt now".
    2. Never prompt twice in a day, and back off if they're already
       consistent — a daily weigher doesn't need reminding.
    """
    if last_weigh_in == today:
        return False, None

    if workout_just_finished:
        return (
            True,
            "Nice session. Weigh in first thing tomorrow — right after a "
            "workout you're down a kilo of sweat, so it wouldn't be a real "
            "reading.",
        )

    if last_weigh_in is None:
        return True, "Log your first weight to start calibrating your targets."

    days_since = (today - last_weigh_in).days

    if weigh_ins_last_14_days >= 10:
        # Already consistent. Only nudge after a real gap.
        return (days_since >= 3, "Been a few days — quick weigh-in?" if days_since >= 3 else None)

    if days_since >= 2:
        return (
            True,
            f"It's been {days_since} days. I need regular weigh-ins to keep "
            f"your targets accurate — the trend line does the smoothing, so "
            f"don't worry about daily bounce.",
        )

    return False, None
