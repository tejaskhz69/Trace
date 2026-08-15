"""Unit tests for the two engines that must never be wrong.

A bug in tdee.py silently gives thousands of people the wrong calorie target
for weeks. A bug in adjudication.py tells someone they're gaining fat when
they're building muscle. Both are pure functions specifically so they can be
tested exhaustively without a database.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.adjudication import (
    AdjudicationInput,
    ExerciseWeeks,
    Verdict,
    adjudicate,
    epley_e1rm,
    ewma,
    strength_index_delta,
)
from app.services.tdee import (
    estimate_expenditure,
    mifflin_st_jeor,
    recommend_targets,
    trend_weight_series,
)


# ---------------------------------------------------------------------------
# e1RM
# ---------------------------------------------------------------------------


def test_epley_single_rep_is_the_weight():
    assert epley_e1rm(100, 1) == 100


def test_epley_five_reps():
    # 100 * (1 + 5/30) = 116.67
    assert epley_e1rm(100, 5) == pytest.approx(116.667, abs=0.01)


def test_epley_rejects_out_of_range():
    assert epley_e1rm(100, 0) is None
    assert epley_e1rm(100, 25) is None   # beyond the 12-rep cap
    assert epley_e1rm(0, 5) is None


def test_ewma_weights_recent_values_more():
    assert ewma([100, 100, 100]) == 100
    smoothed = ewma([100, 110], alpha=0.4)
    assert 100 < smoothed < 110
    assert smoothed == pytest.approx(104.0)


# ---------------------------------------------------------------------------
# Trend weight
# ---------------------------------------------------------------------------


def test_trend_smooths_a_single_spike():
    start = date(2026, 1, 1)
    entries = [(start + timedelta(days=i), 80.0) for i in range(10)]
    entries[5] = (start + timedelta(days=5), 82.0)  # salty dinner

    series = trend_weight_series(entries)
    spike_day_trend = series[5][2]

    # Raw jumped 2 kg; the trend must barely move.
    assert spike_day_trend < 80.3, "trend should absorb a single-day spike"
    assert series[5][1] == 82.0, "raw value must still be reported"


def test_trend_carries_forward_missing_days():
    start = date(2026, 1, 1)
    entries = [(start, 80.0), (start + timedelta(days=5), 79.5)]
    series = trend_weight_series(entries)

    assert len(series) == 6, "gap days must be filled"
    assert series[2][1] is None, "missing days have no raw value"
    assert series[2][2] == pytest.approx(80.0), "trend carries forward"


def test_trend_handles_empty_input():
    assert trend_weight_series([]) == []


# ---------------------------------------------------------------------------
# Expenditure
# ---------------------------------------------------------------------------


def _build_series(start: date, days: int, start_kg: float, kg_per_day: float):
    entries = [
        (start + timedelta(days=i), start_kg + kg_per_day * i) for i in range(days)
    ]
    return trend_weight_series(entries)


def test_expenditure_recovers_a_known_deficit():
    """If someone eats 2,400 and loses 0.5 kg/wk, TDEE must come out near 2,950."""
    start = date(2026, 1, 1)
    days = 45
    kg_per_day = -0.5 / 7
    series = _build_series(start, days, 85.0, kg_per_day)
    intake = {start + timedelta(days=i): 2400.0 for i in range(days)}

    result = estimate_expenditure(
        intake_by_day=intake, trend_series=series, tdee_prior=2900.0
    )

    assert result.tdee_observed is not None
    # 2400 + (0.5 * 7700 / 7) = 2950
    assert result.tdee_observed == pytest.approx(2950, rel=0.06)
    assert result.confidence > 0.5


def test_expenditure_refuses_without_enough_logging():
    start = date(2026, 1, 1)
    series = _build_series(start, 40, 85.0, -0.05)
    intake = {start + timedelta(days=i): 2400.0 for i in range(3)}  # only 3 days

    result = estimate_expenditure(
        intake_by_day=intake, trend_series=series, tdee_prior=2900.0
    )

    assert result.tdee_observed is None
    assert result.tdee_blended == 2900.0, "must fall back to the prior"
    assert "insufficient_logging" in result.notes


def test_expenditure_clamps_implausible_observations():
    """The classic under-logging signature must be flagged, not believed.

    An 85 kg adult who logs 1,200 kcal/day and barely loses weight implies a
    TDEE of ~1,350 -- physiologically implausible. The honest read is that they
    are not logging everything, not that their metabolism is broken.
    """
    start = date(2026, 1, 1)
    days = 45
    series = _build_series(start, days, 85.0, -0.02)  # only ~0.14 kg/wk
    intake = {start + timedelta(days=i): 1200.0 for i in range(days)}

    result = estimate_expenditure(
        intake_by_day=intake, trend_series=series, tdee_prior=2900.0
    )

    assert any("underlogging" in n or "below_plausible" in n for n in result.notes)
    # Clamped to prior * 0.75, not driven down to the absurd raw observation.
    assert result.tdee_observed == pytest.approx(2900.0 * 0.75)


def test_expenditure_ignores_the_washout_period():
    start = date(2026, 1, 1)
    series = _build_series(start, 8, 85.0, -0.2)  # only 8 days total
    intake = {start + timedelta(days=i): 2000.0 for i in range(8)}

    result = estimate_expenditure(
        intake_by_day=intake, trend_series=series, tdee_prior=2800.0
    )
    assert result.tdee_observed is None
    assert "washout_period" in result.notes or "window_too_short" in result.notes


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


def test_target_never_drops_below_bmr_floor():
    bmr = 1600.0
    rec = recommend_targets(
        tdee=1700,
        weight_kg=60,
        goal_type="lose",
        previous_target=None,
        bmr=bmr,
        goal_rate_pct_per_week=-1.5,  # aggressive
    )
    assert rec.calorie_target >= bmr * 1.1 - 10


def test_target_change_is_capped_at_150():
    rec = recommend_targets(
        tdee=3200, weight_kg=80, goal_type="maintain", previous_target=2000, bmr=1700
    )
    assert abs(rec.delta_from_previous) <= 150
    assert rec.math["capped_at_150_kcal_change"] is True


def test_protein_floor_is_higher_when_cutting():
    cutting = recommend_targets(
        tdee=2500, weight_kg=80, goal_type="lose", previous_target=None, bmr=1700
    )
    gaining = recommend_targets(
        tdee=2500, weight_kg=80, goal_type="gain", previous_target=None, bmr=1700
    )
    assert cutting.protein_target_g == 160  # 2.0 g/kg
    assert gaining.protein_target_g == 128  # 1.6 g/kg


def test_fiber_target_scales_with_calories_not_body_weight():
    """14 g per 1,000 kcal (Dietary Guidelines / IOM). Two people at the same
    body weight but different calorie targets get different fiber targets --
    that's the point of scaling on intake rather than mass."""
    small = recommend_targets(
        tdee=1800, weight_kg=80, goal_type="lose", previous_target=None, bmr=1500
    )
    large = recommend_targets(
        tdee=3200, weight_kg=80, goal_type="gain", previous_target=None, bmr=1500
    )
    assert small.fiber_target_g == round(small.calorie_target / 1000 * 14)
    assert large.fiber_target_g == round(large.calorie_target / 1000 * 14)
    assert large.fiber_target_g > small.fiber_target_g


def test_mifflin_matches_published_values():
    # 80 kg, 180 cm, 30 y, male -> 10*80 + 6.25*180 - 5*30 + 5 = 1780
    assert mifflin_st_jeor(80, 180, 30, "male") == pytest.approx(1780)
    assert mifflin_st_jeor(80, 180, 30, "female") == pytest.approx(1614)


# ---------------------------------------------------------------------------
# Strength index
# ---------------------------------------------------------------------------


def test_strength_index_weights_most_trained_lift_highest():
    exercises = [
        ExerciseWeeks("a", "Squat", [100.0, 110.0], session_count=12),   # +10%
        ExerciseWeeks("b", "Bench", [100.0, 100.0], session_count=3),    # 0%
    ]
    delta, math = strength_index_delta(exercises)
    assert delta is not None
    # Squat carries 0.5/(0.5+0.3) = 62.5% of the weight, so the blend leans up.
    assert delta > 2.0
    assert len(math["per_exercise"]) == 2


def test_strength_index_needs_two_weeks():
    exercises = [ExerciseWeeks("a", "Squat", [100.0], session_count=5)]
    delta, math = strength_index_delta(exercises)
    assert delta is None
    assert "reason" in math


# ---------------------------------------------------------------------------
# The adjudicator -- the feature that must never be confidently wrong
# ---------------------------------------------------------------------------


def _input(**overrides) -> AdjudicationInput:
    base = dict(
        week_start=date(2026, 1, 5),
        body_weight_kg=80.0,
        trend_weight_start=80.0,
        trend_weight_end=80.0,
        window_days=21,
        exercises=[
            ExerciseWeeks("a", "Squat", [100.0, 102.0, 104.0], session_count=9),
            ExerciseWeeks("b", "Bench", [80.0, 81.0, 82.0], session_count=8),
        ],
        session_count=12,
        weigh_in_count=18,
        logged_food_days=18,
        mean_protein_g=140.0,
        goal_type="gain",
        lifting_experience_months=24,
        program_overlap=1.0,
    )
    base.update(overrides)
    return AdjudicationInput(**base)  # type: ignore[arg-type]


def test_insufficient_data_when_too_few_sessions():
    result = adjudicate(_input(session_count=3))
    assert result.verdict == Verdict.insufficient_data
    assert "insufficient_data" in result.guardrails_triggered
    assert "3 workouts" in result.explanation


def test_insufficient_data_when_too_few_weigh_ins():
    result = adjudicate(_input(weigh_in_count=5))
    assert result.verdict == Verdict.insufficient_data


def test_lean_gain_detected():
    result = adjudicate(
        _input(trend_weight_start=79.0, trend_weight_end=80.2)  # +1.2 kg / 3 wk
    )
    assert result.verdict == Verdict.lean_gain
    assert result.recommended_calorie_delta == 0.0
    assert "lean mass" in result.headline.lower()


def test_fat_gain_detected_and_recommends_a_cut():
    result = adjudicate(
        _input(
            trend_weight_start=78.0,
            trend_weight_end=80.5,  # +2.5 kg -> ~1.04%/wk
            exercises=[
                ExerciseWeeks("a", "Squat", [100.0, 100.0, 100.0], session_count=9),
                ExerciseWeeks("b", "Bench", [80.0, 80.0, 80.0], session_count=8),
            ],
        )
    )
    assert result.verdict == Verdict.fat_gain
    assert result.recommended_calorie_delta == -150.0


def test_fat_gain_raises_protein_when_it_is_low():
    result = adjudicate(
        _input(
            trend_weight_start=78.0,
            trend_weight_end=80.5,
            mean_protein_g=72.0,  # 0.9 g/kg
            exercises=[
                ExerciseWeeks("a", "Squat", [100.0, 100.0, 100.0], session_count=9),
                ExerciseWeeks("b", "Bench", [80.0, 80.0, 80.0], session_count=8),
            ],
        )
    )
    assert result.verdict == Verdict.fat_gain
    assert result.recommended_protein_g == 128  # 80 kg * 1.6
    assert "1.6 g/kg" in result.explanation


def test_recomposition_detected():
    result = adjudicate(
        _input(
            trend_weight_start=80.0,
            trend_weight_end=80.05,
            exercises=[
                ExerciseWeeks("a", "Squat", [100.0, 104.0, 108.0], session_count=10),
                ExerciseWeeks("b", "Bench", [80.0, 83.0, 85.0], session_count=9),
            ],
        )
    )
    assert result.verdict == Verdict.recomposition
    assert result.recommended_calorie_delta == 0.0


def test_muscle_loss_risk_recommends_more_food_and_protein():
    result = adjudicate(
        _input(
            goal_type="lose",
            trend_weight_start=82.0,
            trend_weight_end=79.5,  # -2.5 kg -> ~-1.04%/wk
            exercises=[
                ExerciseWeeks("a", "Squat", [100.0, 96.0, 93.0], session_count=9),
                ExerciseWeeks("b", "Bench", [80.0, 77.0, 75.0], session_count=8),
            ],
        )
    )
    assert result.verdict == Verdict.muscle_loss_risk
    assert result.recommended_calorie_delta == 150.0
    assert result.recommended_protein_g == 160  # 2.0 g/kg


def test_clean_cut_detected():
    result = adjudicate(
        _input(
            goal_type="lose",
            trend_weight_start=81.5,
            trend_weight_end=80.0,
            exercises=[
                ExerciseWeeks("a", "Squat", [100.0, 100.0, 100.5], session_count=9),
                ExerciseWeeks("b", "Bench", [80.0, 80.0, 80.0], session_count=8),
            ],
        )
    )
    assert result.verdict == Verdict.clean_cut
    assert result.recommended_calorie_delta == 0.0


def test_novice_gains_are_discounted():
    experienced = adjudicate(_input(lifting_experience_months=24))
    novice = adjudicate(_input(lifting_experience_months=1))

    assert "novice_discount_applied" in novice.guardrails_triggered
    assert novice.strength_index_delta_pct < experienced.strength_index_delta_pct


def test_program_change_suppresses_the_verdict():
    result = adjudicate(_input(program_overlap=0.2))
    assert result.verdict == Verdict.insufficient_data
    assert "program" in result.headline.lower()


def test_low_food_logging_blocks_a_calorie_recommendation():
    result = adjudicate(
        _input(
            trend_weight_start=78.0,
            trend_weight_end=80.5,
            logged_food_days=6,  # 2/week
            exercises=[
                ExerciseWeeks("a", "Squat", [100.0, 100.0, 100.0], session_count=9),
                ExerciseWeeks("b", "Bench", [80.0, 80.0, 80.0], session_count=8),
            ],
        )
    )
    assert result.recommended_calorie_delta == 0.0
    assert "low_food_logging__no_calorie_verdict" in result.guardrails_triggered
    assert "isn't reliable enough" in result.explanation
    assert "6 of 21 days" in result.explanation


def test_no_strength_signal_still_reports_weight():
    result = adjudicate(
        _input(exercises=[ExerciseWeeks("a", "Squat", [100.0], session_count=9)])
    )
    assert result.verdict == Verdict.insufficient_data
    assert result.weight_delta_pct_per_week is not None
    assert "no_strength_signal" in result.guardrails_triggered


def test_ambiguous_signals_are_not_forced_into_a_verdict():
    """The most important test: refuse to guess rather than guess wrong."""
    result = adjudicate(
        _input(
            trend_weight_start=80.0,
            trend_weight_end=80.16,  # +0.16 kg, tiny
            exercises=[
                ExerciseWeeks("a", "Squat", [100.0, 100.2, 100.3], session_count=9),
                ExerciseWeeks("b", "Bench", [80.0, 80.0, 80.1], session_count=8),
            ],
        )
    )
    assert result.verdict == Verdict.insufficient_data
    assert "signals_within_noise_band" in result.guardrails_triggered
