"""The Strength Adjudication Engine -- Trace's headline feature.

Answers the one question no competitor can: *is the weight you gained muscle,
and is the weight you lost fat?*

It reads two independent signals -- trend weight and estimated 1RM -- and
classifies the last 21 days into one of five states. Every guardrail here
exists because the failure mode is worse than the feature: telling someone
"you're gaining fat" when they're actually mid-program-change is how you earn
a 1-star review and lose a user forever.

Pure functions. No I/O. Fully unit-tested in tests/test_adjudication.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

E1RM_REP_CAP = 12          # Epley is noise beyond ~12 reps
E1RM_EWMA_ALPHA = 0.4
MIN_SESSIONS = 8
MIN_WEIGH_INS = 14
MIN_LOGGING_DAYS_PER_WEEK = 5
NOVICE_MONTHS = 2          # first 8 weeks of lifting
NOVICE_DISCOUNT = 0.5
PROGRAM_OVERLAP_THRESHOLD = 0.6


class Verdict(str, Enum):
    lean_gain = "lean_gain"
    fat_gain = "fat_gain"
    recomposition = "recomposition"
    clean_cut = "clean_cut"
    muscle_loss_risk = "muscle_loss_risk"
    insufficient_data = "insufficient_data"


# ---------------------------------------------------------------------------
# Estimated 1RM
# ---------------------------------------------------------------------------


def epley_e1rm(weight_kg: float, reps: int) -> float | None:
    """Epley: 1RM = w * (1 + reps/30). Returns None outside the valid range."""
    if reps < 1 or reps > E1RM_REP_CAP or weight_kg <= 0:
        return None
    if reps == 1:
        return weight_kg
    return weight_kg * (1 + reps / 30.0)


def ewma(values: list[float], alpha: float = E1RM_EWMA_ALPHA) -> float | None:
    """Exponentially weighted mean, most recent last."""
    if not values:
        return None
    acc = values[0]
    for v in values[1:]:
        acc = acc + alpha * (v - acc)
    return acc


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass
class ExerciseWeeks:
    """Per-exercise weekly e1RM history, oldest first."""

    exercise_id: str
    name: str
    weekly_best_e1rm: list[float]
    session_count: int


@dataclass
class AdjudicationInput:
    week_start: date
    body_weight_kg: float
    # Trend weight at the start and end of the 21-day window
    trend_weight_start: float
    trend_weight_end: float
    window_days: int
    exercises: list[ExerciseWeeks]
    session_count: int
    weigh_in_count: int
    logged_food_days: int
    mean_protein_g: float
    goal_type: str
    lifting_experience_months: int
    # Fraction of exercises shared between the first and last week of the
    # window. Low overlap => the user changed programs => e1RM is not comparable.
    program_overlap: float = 1.0
    current_calorie_target: float | None = None


@dataclass
class AdjudicationResult:
    verdict: Verdict
    headline: str
    explanation: str
    strength_index_delta_pct: float | None = None
    weight_delta_pct_per_week: float | None = None
    protein_g_per_kg: float | None = None
    logging_adherence: float | None = None
    recommended_calorie_delta: float = 0.0
    recommended_protein_g: float | None = None
    guardrails_triggered: list[str] = field(default_factory=list)
    math: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The strength index
# ---------------------------------------------------------------------------


def strength_index_delta(exercises: list[ExerciseWeeks]) -> tuple[float | None, dict]:
    """Weighted % change in e1RM across the user's 3 most-trained lifts.

    Weights 0.5 / 0.3 / 0.2 by session frequency -- a PR on the lift you train
    weekly says more than a PR on the one you did twice.
    """
    ranked = sorted(exercises, key=lambda e: e.session_count, reverse=True)[:3]
    ranked = [e for e in ranked if len(e.weekly_best_e1rm) >= 2]
    if not ranked:
        return None, {"reason": "no_exercise_with_two_weeks_of_data"}

    weights = [0.5, 0.3, 0.2][: len(ranked)]
    weights = [w / sum(weights) for w in weights]  # renormalise

    detail = []
    weighted = 0.0
    for w, ex in zip(weights, ranked):
        series = ex.weekly_best_e1rm
        smoothed_end = ewma(series)
        start = series[0]
        if not start or smoothed_end is None:
            continue
        pct = (smoothed_end - start) / start * 100.0
        weighted += w * pct
        detail.append(
            {
                "exercise": ex.name,
                "weight": round(w, 2),
                "e1rm_start": round(start, 1),
                "e1rm_now_smoothed": round(smoothed_end, 1),
                "pct_change": round(pct, 2),
                "sessions": ex.session_count,
            }
        )

    if not detail:
        return None, {"reason": "no_usable_e1rm_series"}

    return round(weighted, 2), {"per_exercise": detail}


# ---------------------------------------------------------------------------
# The adjudicator
# ---------------------------------------------------------------------------


def adjudicate(inp: AdjudicationInput) -> AdjudicationResult:
    guardrails: list[str] = []

    # --- Guardrail 1: enough data at all? -------------------------------
    if inp.session_count < MIN_SESSIONS or inp.weigh_in_count < MIN_WEIGH_INS:
        return AdjudicationResult(
            verdict=Verdict.insufficient_data,
            headline="Not enough data yet",
            explanation=(
                f"I need about {MIN_SESSIONS} workouts and {MIN_WEIGH_INS} weigh-ins "
                f"over three weeks before I can tell muscle from fat. "
                f"You're at {inp.session_count} workouts and {inp.weigh_in_count} "
                f"weigh-ins. Keep logging -- this unlocks on its own."
            ),
            guardrails_triggered=["insufficient_data"],
            math={
                "sessions": inp.session_count,
                "sessions_needed": MIN_SESSIONS,
                "weigh_ins": inp.weigh_in_count,
                "weigh_ins_needed": MIN_WEIGH_INS,
            },
        )

    # --- Guardrail 3: did they change programs? -------------------------
    if inp.program_overlap < PROGRAM_OVERLAP_THRESHOLD:
        guardrails.append("program_changed")

    # --- Signals ---------------------------------------------------------
    weeks = max(inp.window_days / 7.0, 1e-6)
    weight_delta_kg = inp.trend_weight_end - inp.trend_weight_start
    weight_delta_pct_per_week = (
        weight_delta_kg / inp.body_weight_kg * 100.0
    ) / weeks

    s_delta, s_math = strength_index_delta(inp.exercises)

    # --- Guardrail 2: novice gains are neurological, not muscular --------
    novice = inp.lifting_experience_months < NOVICE_MONTHS
    if novice and s_delta is not None:
        s_delta = round(s_delta * NOVICE_DISCOUNT, 2)
        guardrails.append("novice_discount_applied")

    protein_per_kg = round(inp.mean_protein_g / inp.body_weight_kg, 2)
    adherence = round(inp.logged_food_days / inp.window_days, 2)

    base_math = {
        "window_days": inp.window_days,
        "trend_weight_start": round(inp.trend_weight_start, 2),
        "trend_weight_end": round(inp.trend_weight_end, 2),
        "trend_weight_delta_kg": round(weight_delta_kg, 3),
        "weight_delta_pct_per_week": round(weight_delta_pct_per_week, 3),
        "strength_index_delta_pct": s_delta,
        "protein_g_per_kg": protein_per_kg,
        "logging_adherence": adherence,
        "strength_detail": s_math,
    }

    if s_delta is None:
        return AdjudicationResult(
            verdict=Verdict.insufficient_data,
            headline="I can see your weight, but not your strength trend",
            explanation=(
                "You need at least two weeks of the same lifts logged before I "
                "can compare strength. Stick with a consistent set of main "
                "movements and this fills in."
            ),
            weight_delta_pct_per_week=round(weight_delta_pct_per_week, 3),
            logging_adherence=adherence,
            guardrails_triggered=guardrails + ["no_strength_signal"],
            math=base_math,
        )

    if inp.program_overlap < PROGRAM_OVERLAP_THRESHOLD:
        return AdjudicationResult(
            verdict=Verdict.insufficient_data,
            headline="Your program changed, so strength isn't comparable",
            explanation=(
                "Only "
                f"{inp.program_overlap:.0%} of your lifts carried over from the "
                "start of this window. I'll have a clean read once you've run "
                "the new routine for a couple of weeks."
            ),
            strength_index_delta_pct=s_delta,
            weight_delta_pct_per_week=round(weight_delta_pct_per_week, 3),
            protein_g_per_kg=protein_per_kg,
            logging_adherence=adherence,
            guardrails_triggered=guardrails,
            math=base_math,
        )

    # --- Guardrail 4: is the food side even real? ------------------------
    weeks_int = max(round(weeks), 1)
    if inp.logged_food_days / weeks_int < MIN_LOGGING_DAYS_PER_WEEK:
        guardrails.append("low_food_logging__no_calorie_verdict")

    # --- Classification --------------------------------------------------
    w = weight_delta_pct_per_week
    s = s_delta

    if w > 0.15 and s > 0.5:
        verdict = Verdict.lean_gain
        headline = "You're gaining mostly lean mass"
        kcal_delta = 0.0
        explanation = (
            f"Trend weight is up {abs(weight_delta_kg):.2f} kg over "
            f"{inp.window_days} days while your strength index rose {s:+.1f}%. "
            "That's the ratio you want in a bulk. Hold your current intake."
        )
    elif w > 0.35 and abs(s) <= 0.5:
        verdict = Verdict.fat_gain
        headline = "That gain isn't showing up in the bar"
        kcal_delta = -150.0
        explanation = (
            f"You've added {abs(weight_delta_kg):.2f} kg but your strength index "
            f"moved {s:+.1f}% -- essentially flat. You're gaining faster than you "
            "can build. Cut 150 kcal/day"
            + (
                f" and get protein from {protein_per_kg:.1f} to 1.6 g/kg."
                if protein_per_kg < 1.6
                else "."
            )
        )
    elif abs(w) <= 0.15 and s > 1.0:
        verdict = Verdict.recomposition
        headline = "Recomposition -- weight flat, strength climbing"
        kcal_delta = 0.0
        explanation = (
            f"Your weight barely moved ({weight_delta_kg:+.2f} kg) while your "
            f"strength index climbed {s:+.1f}%. You're trading fat for muscle. "
            "This is the rarest and best outcome. Change nothing."
        )
    elif w < -0.15 and s >= -0.5:
        verdict = Verdict.clean_cut
        headline = "Clean cut -- you're keeping your strength"
        kcal_delta = 0.0
        explanation = (
            f"Down {abs(weight_delta_kg):.2f} kg with your strength index at "
            f"{s:+.1f}%. You're losing fat and holding muscle. Stay the course."
        )
    elif w < -0.3 and s < -1.5:
        verdict = Verdict.muscle_loss_risk
        headline = "You're losing strength with the weight"
        kcal_delta = 150.0
        explanation = (
            f"Down {abs(weight_delta_kg):.2f} kg and your strength index dropped "
            f"{s:+.1f}%. That's too fast. Add 150 kcal/day, push protein to "
            "2.0 g/kg, and check that you're not also adding training volume."
        )
    else:
        verdict = Verdict.insufficient_data
        headline = "Your trends are still too close to call"
        kcal_delta = 0.0
        explanation = (
            f"Weight is moving {w:+.2f}%/week and strength {s:+.1f}%. Neither is "
            "decisive yet. Another week of consistent logging will sharpen this."
        )
        guardrails.append("signals_within_noise_band")

    if "low_food_logging__no_calorie_verdict" in guardrails:
        kcal_delta = 0.0
        explanation += (
            f" (I'm not recommending a calorie change -- you only logged food on "
            f"{inp.logged_food_days} of {inp.window_days} days, so the intake "
            "side isn't reliable enough to act on.)"
        )

    protein_target = None
    if verdict == Verdict.fat_gain and protein_per_kg < 1.6:
        protein_target = round(inp.body_weight_kg * 1.6)
    elif verdict == Verdict.muscle_loss_risk:
        protein_target = round(inp.body_weight_kg * 2.0)

    return AdjudicationResult(
        verdict=verdict,
        headline=headline,
        explanation=explanation,
        strength_index_delta_pct=s,
        weight_delta_pct_per_week=round(w, 3),
        protein_g_per_kg=protein_per_kg,
        logging_adherence=adherence,
        recommended_calorie_delta=kcal_delta,
        recommended_protein_g=protein_target,
        guardrails_triggered=guardrails,
        math=base_math,
    )
