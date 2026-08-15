"""Tests for the activity analysis and coaching engine.

The rule these protect: the coach must reach for the CHEAPEST fixable lever
first. Sleep before activity, activity before calories. If a refactor ever
makes it say "cut 150 kcal" to someone who is sleeping 5 hours and has stopped
walking, that's a product failure, not a cosmetic one.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.activity import (
    ActivityDay,
    ActivityTrend,
    SleepNight,
    activity_stability,
    analyse_neat,
    analyse_sleep,
    reconcile_energy,
    should_prompt_weigh_in,
)
from app.services.adjudication import AdjudicationResult, Verdict
from app.services.coach import CoachInput, Lever, Urgency, build_briefing


START = date(2026, 6, 1)


def steps_history(pattern: list[int], start: date = START) -> list[ActivityDay]:
    return [
        ActivityDay(day=start + timedelta(days=i), steps=s)
        for i, s in enumerate(pattern)
    ]


# ===========================================================================
# NEAT drift -- the headline feature
# ===========================================================================


def test_neat_drift_detects_a_real_drop():
    """28 days at ~9,400 steps, then 7 days at ~6,100."""
    history = steps_history([9400] * 28 + [6100] * 7)
    result = analyse_neat(history, body_weight_kg=80)

    assert result.trend is ActivityTrend.falling
    assert result.is_significant
    assert result.baseline_steps == pytest.approx(9400, abs=50)
    assert result.recent_steps == pytest.approx(6100, abs=50)
    assert result.delta_steps == pytest.approx(-3300, abs=100)
    # ~3300 steps * 0.0005 * 80kg = ~132 kcal
    assert result.estimated_kcal_delta == pytest.approx(-132, abs=15)
    assert "6,100" in (result.message or "")


def test_neat_drift_ignores_noise():
    history = steps_history([9000, 9500, 8800, 9200, 9100] * 7)
    result = analyse_neat(history, body_weight_kg=80)
    assert result.trend is ActivityTrend.stable
    assert not result.is_significant
    assert result.message is None


def test_neat_drift_detects_an_increase():
    history = steps_history([5000] * 28 + [9000] * 7)
    result = analyse_neat(history, body_weight_kg=80)
    assert result.trend is ActivityTrend.rising
    assert result.estimated_kcal_delta > 0


def test_neat_requires_two_weeks():
    result = analyse_neat(steps_history([8000] * 5), body_weight_kg=80)
    assert result.trend is ActivityTrend.insufficient_data
    assert not result.is_significant


def test_neat_compares_against_the_users_own_baseline():
    """A 5,000-step user who drops to 3,000 is drifting; the absolute number
    is irrelevant. '10,000 steps' is a 1960s pedometer marketing figure."""
    low = analyse_neat(steps_history([5000] * 28 + [3000] * 7), body_weight_kg=70)
    assert low.trend is ActivityTrend.falling
    assert low.is_significant


# ===========================================================================
# Activity stability
# ===========================================================================


def test_stability_high_for_consistent_activity():
    assert activity_stability(steps_history([8000] * 21)) == 1.0


def test_stability_low_for_chaotic_activity():
    chaotic = steps_history([2000, 18000, 3000, 20000, 1500, 15000, 2500] * 3)
    assert activity_stability(chaotic) < 0.7


def test_stability_neutral_without_data():
    assert activity_stability(steps_history([8000] * 3)) == 0.5


# ===========================================================================
# Sleep
# ===========================================================================


def nights(hours: list[float]) -> list[SleepNight]:
    return [
        SleepNight(night_of=START + timedelta(days=i), asleep_hours=h, in_bed_hours=h + 0.5)
        for i, h in enumerate(hours)
    ]


def test_sleep_debt_flagged():
    result = analyse_sleep(nights([5.0, 5.5, 6.0, 5.0, 6.5, 5.5, 6.0]))
    assert result.is_concerning
    assert result.mean_hours < 6.0
    assert result.debt_hours > 3.0
    assert "not a nutrition problem" in (result.message or "")


def test_good_sleep_not_flagged():
    result = analyse_sleep(nights([7.5, 8.0, 7.8, 8.2, 7.6, 8.1, 7.9]))
    assert not result.is_concerning
    assert result.message is None


def test_sleep_needs_three_nights():
    result = analyse_sleep(nights([5.0, 5.0]))
    assert not result.is_concerning
    assert result.mean_hours is None


# ===========================================================================
# Energy reconciliation -- watch vs scale
# ===========================================================================


def test_wearable_overestimate_is_called_out():
    """Watch claims 3,000 kcal/day; the scale proves 2,400. A 25% gap is
    typical for consumer wearables on non-steady-state activity."""
    days = [
        ActivityDay(
            day=START + timedelta(days=i),
            active_energy_kcal=1200,
            resting_energy_kcal=1800,
        )
        for i in range(14)
    ]
    result = reconcile_energy(days, observed_tdee=2400)
    assert result.verdict == "wearable_overestimates"
    assert result.ratio == pytest.approx(1.25)
    assert "use your scale rather than your watch" in (result.message or "")


def test_small_wearable_gap_is_treated_as_agreement():
    """12% is within the noise of both methods -- don't cry wolf."""
    days = [
        ActivityDay(
            day=START + timedelta(days=i),
            active_energy_kcal=900,
            resting_energy_kcal=1800,
        )
        for i in range(14)
    ]
    assert reconcile_energy(days, observed_tdee=2400).verdict == "agrees"


def test_wearable_agreement_is_reported_positively():
    days = [
        ActivityDay(
            day=START + timedelta(days=i),
            active_energy_kcal=600,
            resting_energy_kcal=1800,
        )
        for i in range(14)
    ]
    result = reconcile_energy(days, observed_tdee=2400)
    assert result.verdict == "agrees"


# ===========================================================================
# Weigh-in prompting
# ===========================================================================


def test_workout_defers_weigh_in_to_tomorrow():
    """Post-workout weight is 0.5-1.5kg of sweat. Prompting then trains
    people to log noise."""
    should, msg = should_prompt_weigh_in(
        last_weigh_in=START - timedelta(days=1),
        today=START,
        workout_just_finished=True,
        weigh_ins_last_14_days=5,
    )
    assert should
    assert "tomorrow" in msg
    assert "sweat" in msg


def test_never_prompts_twice_in_a_day():
    should, _ = should_prompt_weigh_in(
        last_weigh_in=START,
        today=START,
        workout_just_finished=True,
        weigh_ins_last_14_days=5,
    )
    assert not should


def test_backs_off_for_consistent_weighers():
    should, _ = should_prompt_weigh_in(
        last_weigh_in=START - timedelta(days=1),
        today=START,
        workout_just_finished=False,
        weigh_ins_last_14_days=13,
    )
    assert not should


def test_nudges_after_a_gap():
    should, msg = should_prompt_weigh_in(
        last_weigh_in=START - timedelta(days=4),
        today=START,
        workout_just_finished=False,
        weigh_ins_last_14_days=4,
    )
    assert should
    assert "4 days" in msg


# ===========================================================================
# The coach -- lever ordering is the thing that matters
# ===========================================================================


def base_input(**overrides) -> CoachInput:
    defaults = dict(
        today=START,
        body_weight_kg=80.0,
        goal_type="lose",
        logged_days_last_14=12,
        mean_protein_g=140.0,
        mean_calories=2400.0,
        sessions_last_7=4,
        sessions_last_14=8,
        mean_sessions_baseline=4.0,
        weigh_ins_last_14=12,
    )
    defaults.update(overrides)
    return CoachInput(**defaults)  # type: ignore[arg-type]


def test_sleep_outranks_everything():
    """Under-slept, every other signal is unreliable. Fix sleep first."""
    briefing = build_briefing(
        base_input(
            sleep=analyse_sleep(nights([5.0] * 7)),
            neat=analyse_neat(steps_history([9000] * 28 + [5500] * 7), 80),
            mean_protein_g=80.0,  # also low
        )
    )
    assert briefing.primary is not None
    assert briefing.primary.lever is Lever.sleep
    assert briefing.primary.urgency is Urgency.critical


def test_neat_drift_beats_a_calorie_cut():
    """THE key behaviour. Someone stalled with collapsed steps should be told
    to walk, not to eat less — walking is the same energy and far easier to
    sustain."""
    verdict = AdjudicationResult(
        verdict=Verdict.fat_gain,
        headline="That gain isn't showing up in the bar",
        explanation="...",
        recommended_calorie_delta=-150.0,
    )
    briefing = build_briefing(
        base_input(
            adjudication=verdict,
            neat=analyse_neat(steps_history([9400] * 28 + [6100] * 7), 80),
            sleep=analyse_sleep(nights([7.8] * 7)),
        )
    )
    assert briefing.primary is not None
    assert briefing.primary.lever is Lever.activity
    assert "steps" in briefing.primary.detail.lower()
    assert "before we cut your calories" in (briefing.primary.action or "")


def test_calorie_advice_survives_when_activity_is_fine():
    verdict = AdjudicationResult(
        verdict=Verdict.fat_gain,
        headline="That gain isn't showing up in the bar",
        explanation="You've added weight but strength is flat.",
        recommended_calorie_delta=-150.0,
    )
    briefing = build_briefing(
        base_input(
            adjudication=verdict,
            neat=analyse_neat(steps_history([9000] * 35), 80),
            sleep=analyse_sleep(nights([7.8] * 7)),
        )
    )
    assert briefing.primary is not None
    assert briefing.primary.lever is Lever.calories
    assert "Cut 150" in (briefing.primary.action or "")


def test_low_logging_blocks_confident_coaching():
    briefing = build_briefing(base_input(logged_days_last_14=4))
    assert briefing.primary is not None
    assert briefing.primary.lever is Lever.adherence
    assert briefing.primary.confidence > 0.9


def test_low_protein_surfaces():
    briefing = build_briefing(
        base_input(mean_protein_g=80.0, sleep=analyse_sleep(nights([8.0] * 7)))
    )
    assert briefing.primary is not None
    assert briefing.primary.lever is Lever.protein
    assert briefing.primary.evidence["target_g"] == 128


def test_positive_reinforcement_is_specific():
    """'Everything's on track' is a churn message. Give them a number."""
    verdict = AdjudicationResult(
        verdict=Verdict.clean_cut,
        headline="Clean cut — you're keeping your strength",
        explanation="Down 1.2 kg with your strength index at +0.3%.",
        recommended_calorie_delta=0.0,
    )
    briefing = build_briefing(
        base_input(adjudication=verdict, sleep=analyse_sleep(nights([8.0] * 7)))
    )
    assert briefing.primary is not None
    assert briefing.primary.urgency is Urgency.low
    assert "1.2 kg" in briefing.primary.detail


def test_training_stoppage_is_noticed():
    briefing = build_briefing(
        base_input(
            sessions_last_7=0,
            mean_sessions_baseline=4.0,
            sleep=analyse_sleep(nights([8.0] * 7)),
        )
    )
    keys = {briefing.primary.key} | {s.key for s in briefing.secondary}
    assert "training_stopped" in keys


def test_only_one_insight_per_lever():
    """A coach says one thing per lever, not a dashboard of five."""
    briefing = build_briefing(
        base_input(
            logged_days_last_14=4,
            weigh_ins_last_14=2,  # both are adherence
            sleep=analyse_sleep(nights([8.0] * 7)),
        )
    )
    all_insights = [briefing.primary] + briefing.secondary
    levers = [i.lever for i in all_insights if i and i.lever is not Lever.none]
    assert len(levers) == len(set(levers))


def test_data_completeness_reflects_what_we_have():
    empty = build_briefing(
        CoachInput(today=START, body_weight_kg=80.0, goal_type="lose")
    )
    assert empty.data_completeness < 0.3

    full = build_briefing(
        base_input(
            adjudication=AdjudicationResult(
                verdict=Verdict.clean_cut, headline="x", explanation="y"
            ),
            neat=analyse_neat(steps_history([9000] * 35), 80),
            sleep=analyse_sleep(nights([8.0] * 7)),
        )
    )
    assert full.data_completeness == 1.0


def test_weigh_in_prompt_is_surfaced():
    briefing = build_briefing(
        base_input(weigh_in_prompt="Nice session. Weigh in first thing tomorrow.")
    )
    assert briefing.prompts == ["Nice session. Weigh in first thing tomorrow."]
