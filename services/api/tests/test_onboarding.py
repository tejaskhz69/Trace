"""Spec for the day-one plan builder (app/services/onboarding.py).

The invariant that matters most is in `test_cycling_preserves_the_weekly_total`:
training days must be funded by borrowing from rest days, never by adding
calories back. That is CLAUDE.md non-negotiable #1 restated in the one place a
future refactor is most likely to break it -- "give training days +10%" is an
extremely easy thing to implement as +10% of nothing.
"""

from __future__ import annotations

import pytest

from app.services.onboarding import (
    ADAPTATION_MAX,
    MULTIPLIER_CEILING,
    MULTIPLIER_FLOOR,
    activity_multiplier,
    build_plan,
    metabolic_history,
    plan_week,
)

# ---------------------------------------------------------------------------
# Activity multiplier
# ---------------------------------------------------------------------------


def test_multiplier_rises_with_steps():
    sedentary = activity_multiplier(daily_steps=2_000, cardio_sessions_per_week=0)
    walker = activity_multiplier(daily_steps=9_000, cardio_sessions_per_week=0)
    labourer = activity_multiplier(daily_steps=20_000, cardio_sessions_per_week=0)
    assert sedentary < walker < labourer


def test_multiplier_is_bounded_against_absurd_input():
    """A user claiming 90,000 steps and daily cardio is describing a fantasy.

    Clamping matters because this number multiplies BMR: an unbounded
    multiplier hands someone a 6,000 kcal target on their first day.
    """
    absurd = activity_multiplier(
        daily_steps=90_000, cardio_sessions_per_week=14, lifting_sessions_per_week=14
    )
    assert absurd <= MULTIPLIER_CEILING

    negative = activity_multiplier(daily_steps=-500, cardio_sessions_per_week=-3)
    assert negative >= MULTIPLIER_FLOOR


def test_cardio_bonus_saturates():
    four = activity_multiplier(daily_steps=8_000, cardio_sessions_per_week=4)
    twelve = activity_multiplier(daily_steps=8_000, cardio_sessions_per_week=12)
    # Twelve sessions is not three times the metabolic reality of four.
    assert twelve - four < 0.10


# ---------------------------------------------------------------------------
# Metabolic history -- the "have you ever weighed 200 lbs?" question
# ---------------------------------------------------------------------------


def test_no_history_means_no_adaptation():
    h = metabolic_history(weight_kg=70.0, highest_weight_kg=None)
    assert h.adaptation_factor == 1.0


def test_unknown_history_is_not_treated_as_never_been_heavier():
    """None means "we didn't ask", which must not silently become "no history".

    Both currently return a factor of 1.0, but for different reasons, and the
    note is what the UI shows -- an unknown history must not claim a finding.
    """
    unknown = metabolic_history(weight_kg=70.0, highest_weight_kg=None)
    assert "No weight-loss history recorded" in unknown.note


def test_formerly_heavier_user_gets_a_lower_prior():
    """The headline case: 70 kg now, 91 kg at peak (~23% below)."""
    h = metabolic_history(weight_kg=70.0, highest_weight_kg=91.0)
    assert h.adaptation_factor < 1.0
    assert h.pct_below_peak == pytest.approx(23.1, abs=0.2)


def test_small_fluctuation_is_noise_not_history():
    """Everyone has been 2 kg heavier. That is not metabolic adaptation."""
    h = metabolic_history(weight_kg=70.0, highest_weight_kg=72.0)
    assert h.adaptation_factor == 1.0


def test_adaptation_is_capped():
    """Someone down from 180 kg to 70 kg is 61% below peak.

    Uncapped, the linear rule would dock ~24% off their TDEE and start them
    on a target low enough to be actively harmful.
    """
    h = metabolic_history(weight_kg=70.0, highest_weight_kg=180.0)
    assert h.adaptation_factor >= 1.0 - ADAPTATION_MAX


def test_higher_current_weight_than_peak_is_handled():
    """Peak below current weight is contradictory input, not a crash."""
    h = metabolic_history(weight_kg=90.0, highest_weight_kg=70.0)
    assert h.adaptation_factor == 1.0


# ---------------------------------------------------------------------------
# The seven-day plan
# ---------------------------------------------------------------------------


def test_cycling_preserves_the_weekly_total():
    """THE invariant. Training days borrow from rest days; they do not add.

    Rounding each day to the nearest 10 kcal means the total can drift by a
    few kcal across seven days, which is why this is an approximate rather
    than exact comparison -- but it must not drift by a meal.
    """
    plan = plan_week(
        calorie_target=2_450,
        protein_target_g=170,
        fat_target_g=70,
        training_day_indices=(0, 2, 4),
    )
    assert plan.weekly_calories == pytest.approx(2_450 * 7, abs=35)


def test_training_days_are_higher_than_rest_days():
    plan = plan_week(
        calorie_target=2_450,
        protein_target_g=170,
        fat_target_g=70,
        training_day_indices=(0, 2, 4),
    )
    training = [d.calories for d in plan.days if d.day_type == "training"]
    rest = [d.calories for d in plan.days if d.day_type == "rest"]
    assert min(training) > max(rest)


def test_protein_is_constant_every_day():
    """Protein floors are daily, not weekly -- the strength verdict depends on
    it, so a low-protein rest day is not an acceptable trade."""
    plan = plan_week(
        calorie_target=2_450,
        protein_target_g=170,
        fat_target_g=70,
        training_day_indices=(0, 2, 4),
    )
    assert len({d.protein_g for d in plan.days}) == 1


@pytest.mark.parametrize("training", [(), (0, 1, 2, 3, 4, 5, 6)])
def test_all_or_nothing_training_weeks_do_not_divide_by_zero(training):
    plan = plan_week(
        calorie_target=2_000,
        protein_target_g=150,
        fat_target_g=60,
        training_day_indices=training,
    )
    assert len(plan.days) == 7
    assert all(d.calories == 2_000 for d in plan.days)


def test_carbs_never_go_negative():
    """An aggressive cut with a high protein floor can leave no room at all.

    Displaying "-40 g carbs" would be a bug; clamping to zero is the correct
    behaviour even though the resulting plan is one a coach should reject.
    """
    plan = plan_week(
        calorie_target=1_000,
        protein_target_g=200,
        fat_target_g=60,
        training_day_indices=(0, 2, 4),
    )
    assert all(d.carbs_g >= 0 for d in plan.days)


def test_seven_days_are_named_and_ordered():
    plan = plan_week(
        calorie_target=2_000, protein_target_g=150, fat_target_g=60,
        training_day_indices=(1,),
    )
    assert [d.day for d in plan.days] == [
        "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"
    ]


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------


def _answers(**overrides):
    base = dict(
        sex="male",
        age_years=28,
        height_cm=178,
        weight_kg=70.0,
        highest_weight_kg=None,
        daily_steps=8_000,
        cardio_sessions_per_week=2,
        lifting_sessions_per_week=4,
        lifting_experience_months=6,
        goal_type="gain",
    )
    base.update(overrides)
    return base


def test_build_plan_produces_seven_days_and_a_target():
    plan = build_plan(**_answers())
    assert len(plan.week.days) == 7
    assert plan.calorie_target > 0
    assert plan.tdee_prior > plan.bmr  # multiplier must actually apply


def test_novice_bulks_faster_than_an_advanced_lifter():
    """The one place lifting experience changes a number.

    A 10-year lifter surplusing at a novice's rate is mostly buying fat.
    """
    novice = build_plan(**_answers(lifting_experience_months=3))
    advanced = build_plan(**_answers(lifting_experience_months=120))
    assert novice.goal_rate_pct_per_week > advanced.goal_rate_pct_per_week
    assert novice.calorie_target > advanced.calorie_target


def test_weight_history_lowers_the_starting_target():
    """Two identical 70 kg users, one of whom dieted down from 91 kg."""
    fresh = build_plan(**_answers(goal_type="maintain"))
    reduced = build_plan(**_answers(goal_type="maintain", highest_weight_kg=91.0))
    assert reduced.calorie_target < fresh.calorie_target


def test_cut_never_prescribes_below_the_safety_floor():
    plan = build_plan(
        **_answers(
            goal_type="lose",
            weight_kg=55.0,
            height_cm=155,
            daily_steps=1_500,
            cardio_sessions_per_week=0,
            lifting_sessions_per_week=0,
        )
    )
    assert plan.calorie_target >= plan.bmr * 1.1


def test_training_days_match_stated_lifting_frequency():
    plan = build_plan(**_answers(lifting_sessions_per_week=3))
    assert plan.week.training_days == 3


def test_plan_always_says_the_numbers_are_provisional():
    """Non-negotiable #2 in spirit: never present an estimate as a fact."""
    plan = build_plan(**_answers())
    assert any("three weeks" in n for n in plan.notes)
