"""Spec for the per-set strength engine.

These tests are the contract for the one thing the product must not get
wrong: telling someone they got stronger when they did not, or missing it
when they did.
"""

from __future__ import annotations

import pytest

from app.services.strength import (
    CONFIRM_BAND,
    ON_TARGET_BAND,
    REP_CEILING,
    ExerciseTrend,
    LoggedSet,
    SetVerdict,
    assess_set,
    e1rm,
    load_pct,
    prescribe_next_set,
    purple_route,
    rest_seconds,
    rpe_from_rir,
    summarise_session,
    weight_step,
)


# ---------------------------------------------------------------------------
# The estimate
# ---------------------------------------------------------------------------


def test_e1rm_uses_reps_left_in_the_tank():
    """The whole premise: a set stopped short is evidence of a heavier set.

    Ignoring RIR under-rates every set that was not taken to failure, which is
    almost all good training.
    """
    to_failure = e1rm(100, 5, rir=0)
    three_left = e1rm(100, 5, rir=3)
    assert three_left is not None and to_failure is not None
    assert three_left > to_failure


def test_e1rm_of_a_set_to_failure_is_plain_epley():
    assert e1rm(100, 5, rir=0) == pytest.approx(100 * (1 + 5 / 30), abs=0.05)


def test_e1rm_refuses_to_estimate_from_an_endurance_set():
    """Past the ceiling the formula is guessing. Refusing beats guessing."""
    assert e1rm(40, REP_CEILING + 1, rir=0) is None
    assert e1rm(40, 10, rir=8) is None  # 18 effective reps


def test_e1rm_rejects_nonsense_input():
    assert e1rm(0, 5) is None
    assert e1rm(100, 0) is None
    assert e1rm(-20, 5) is None


def test_missing_rir_is_treated_as_to_failure_not_as_a_bonus():
    """None must not silently inflate the estimate."""
    assert e1rm(100, 5, rir=None) == e1rm(100, 5, rir=0)


def test_rpe_is_the_inverse_of_rir():
    assert rpe_from_rir(2) == 8.0
    assert rpe_from_rir(0) == 10.0
    assert rpe_from_rir(None) is None


def test_load_pct_needs_a_reference():
    assert load_pct(75, 107.7) == pytest.approx(69.6, abs=0.1)
    assert load_pct(75, None) is None
    assert load_pct(75, 0) is None


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


def test_a_set_that_beats_the_record_is_purple():
    a = assess_set(weight_kg=80, reps=10, rir=2, reference_e1rm=105.0)
    assert a.verdict is SetVerdict.PURPLE
    assert "new best" in a.detail


def test_a_set_that_repeats_the_record_is_on_target():
    a = assess_set(weight_kg=75, reps=10, rir=2, reference_e1rm=105.0)
    assert a.verdict is SetVerdict.ON_TARGET
    assert "maintains your strength" in a.detail


def test_a_small_dip_is_on_target_not_a_decline():
    """e1RM noise must not be reported as losing strength every session.

    Bar speed, sleep and an honest-but-imprecise RIR call move a single-set
    estimate a couple of percent. A tracker that shouts DECLINE at that is
    crying wolf, and the lifter stops reading the verdicts.
    """
    est = e1rm(75, 10, rir=2)
    assert est is not None
    # Reference sitting just inside the band above this set's estimate.
    inside = est / (1 - ON_TARGET_BAND * 0.5)
    assert assess_set(
        weight_kg=75, reps=10, rir=2, reference_e1rm=inside
    ).verdict is SetVerdict.ON_TARGET

    # ...and just outside it, which must be called.
    outside = est / (1 - ON_TARGET_BAND * 2)
    assert assess_set(
        weight_kg=75, reps=10, rir=2, reference_e1rm=outside
    ).verdict is SetVerdict.UNDER


def test_a_real_shortfall_is_under():
    a = assess_set(weight_kg=60, reps=8, rir=2, reference_e1rm=120.0)
    assert a.verdict is SetVerdict.UNDER
    assert "under your best" in a.detail


def test_no_reference_means_unrated_not_a_fabricated_comparison():
    a = assess_set(weight_kg=75, reps=10, rir=2, reference_e1rm=None)
    assert a.verdict is SetVerdict.UNRATED
    assert a.headline == "LOGGED"
    assert "first reference" in a.detail


def test_the_coaching_line_names_both_routes_to_a_purple_set():
    """The screen must give one unambiguous thing to chase."""
    a = assess_set(
        weight_kg=75, reps=10, rir=2, reference_e1rm=105.0, equipment="barbell"
    )
    assert a.route.reps_needed is not None
    assert a.route.weight_needed_kg is not None
    assert "reps at the same effort" in a.detail
    assert "kg" in a.detail


def test_the_suggested_weight_actually_clears_the_record():
    """A rounded-down 'target' that does not beat the record is a lie."""
    ref = 105.0
    r = purple_route(
        weight_kg=75, reps=10, rir=2, reference_e1rm=ref, equipment="barbell"
    )
    assert r.weight_needed_kg is not None
    beaten = e1rm(r.weight_needed_kg, 10, rir=2)
    assert beaten is not None and beaten > ref


def test_the_suggested_reps_actually_clear_the_record():
    ref = 105.0
    r = purple_route(weight_kg=75, reps=10, rir=2, reference_e1rm=ref)
    assert r.reps_needed is not None
    beaten = e1rm(75, r.reps_needed, rir=2)
    assert beaten is not None and beaten > ref


def test_the_suggested_weight_lands_on_a_loadable_increment():
    """Telling someone to add 1.3 kg to a barbell is telling them nothing."""
    r = purple_route(
        weight_kg=75, reps=10, rir=2, reference_e1rm=105.0, equipment="barbell"
    )
    assert r.weight_needed_kg is not None
    assert (r.weight_needed_kg / 2.5) == pytest.approx(
        round(r.weight_needed_kg / 2.5), abs=1e-6
    )


def test_bodyweight_offers_no_weight_route():
    r = purple_route(
        weight_kg=80, reps=10, rir=2, reference_e1rm=112.0, equipment="bodyweight"
    )
    assert r.weight_needed_kg is None


def test_the_rep_route_disappears_rather_than_prescribing_an_endurance_set():
    """Chasing a max with 20 reps is not the same lift. Offer load instead."""
    r = purple_route(
        weight_kg=40, reps=12, rir=2, reference_e1rm=200.0, equipment="barbell"
    )
    assert r.reps_needed is None
    assert r.weight_needed_kg is not None


def test_the_suggested_reps_are_always_more_than_were_just_done():
    """A 'target' of fewer reps than you just did is incoherent."""
    r = purple_route(weight_kg=100, reps=10, rir=4, reference_e1rm=90.0)
    assert r.reps_needed is None or r.reps_needed > 10


# ---------------------------------------------------------------------------
# Equipment and rest
# ---------------------------------------------------------------------------


def test_weight_step_knows_real_gym_increments():
    assert weight_step("barbell") == 2.5
    assert weight_step("Machine") == 5.0
    assert weight_step("plate-loaded") == 5.0
    assert weight_step("bodyweight") == 0.0
    assert weight_step(None) == 2.5  # a sane default, not a crash


def test_compounds_rest_longer_than_isolation():
    assert rest_seconds(is_compound=True, rir=2) > rest_seconds(
        is_compound=False, rir=2
    )


def test_an_easy_set_earns_less_rest():
    assert rest_seconds(is_compound=True, rir=4) < rest_seconds(
        is_compound=True, rir=1
    )


# ---------------------------------------------------------------------------
# Session rollup
# ---------------------------------------------------------------------------


def _s(name, w, reps, rir=2, warm=False, ex_id=None):
    return LoggedSet(
        exercise_id=ex_id or name,
        exercise_name=name,
        weight_kg=w,
        reps=reps,
        rir=rir,
        is_warmup=warm,
    )


def test_session_totals_are_the_numbers_on_the_summary_card():
    s = summarise_session(
        [_s("Bench Press", 75, 10), _s("Bench Press", 75, 10), _s("Squat", 100, 5)],
        previous_bests={},
        duration_min=56,
    )
    assert s.total_sets == 3
    assert s.volume_kg == pytest.approx(75 * 10 * 2 + 100 * 5)
    assert s.avg_rpe == 8.0
    assert s.duration_min == 56


def test_warmups_count_in_volume_but_never_rate_a_verdict():
    """A warm-up single at 60% would otherwise read as a decline every week."""
    s = summarise_session(
        [_s("Bench Press", 40, 10, warm=True), _s("Bench Press", 75, 10)],
        previous_bests={"Bench Press": 105.0},
    )
    ex = s.exercises[0]
    assert ex.sets == 1                       # working sets only
    assert len(ex.set_verdicts) == 1
    assert ex.volume_kg == pytest.approx(40 * 10 + 75 * 10)  # all of it


def test_an_exercise_beating_its_previous_best_is_confirmed():
    s = summarise_session(
        [_s("Bench Press", 85, 10)], previous_bests={"Bench Press": 105.0}
    )
    assert s.exercises[0].trend is ExerciseTrend.CONFIRMED
    assert s.exercises[0].delta_pct is not None
    assert s.exercises[0].delta_pct > 0


def test_a_repeat_performance_is_no_change_not_a_decline():
    ref = e1rm(75, 10, rir=2)
    s = summarise_session(
        [_s("Bench Press", 75, 10)], previous_bests={"Bench Press": ref}
    )
    assert s.exercises[0].trend is ExerciseTrend.NO_CHANGE


def test_a_genuine_drop_is_reported_as_a_decline():
    s = summarise_session(
        [_s("Bench Press", 60, 8)], previous_bests={"Bench Press": 120.0}
    )
    assert s.exercises[0].trend is ExerciseTrend.DECLINE


def test_a_first_ever_session_claims_no_trend():
    """No baseline means no verdict — the INSUFFICIENT_DATA rule, per-lift."""
    s = summarise_session([_s("Bench Press", 75, 10)], previous_bests={})
    assert s.exercises[0].trend is ExerciseTrend.FIRST_TIME
    assert s.exercises[0].delta_pct is None


def test_the_noise_band_is_symmetric():
    ref = 100.0
    inside_up = summarise_session(
        [LoggedSet("x", "X", 0, 0, e1rm=ref * (1 + CONFIRM_BAND / 2))],
        previous_bests={"x": ref},
    )
    assert inside_up.exercises[0].trend is ExerciseTrend.NO_CHANGE


def test_an_empty_session_does_not_claim_anything():
    s = summarise_session([], previous_bests={})
    assert s.total_sets == 0
    assert s.avg_rpe is None
    assert "No working sets" in s.headline


def test_exercises_are_ordered_by_how_much_work_they_were():
    s = summarise_session(
        [_s("Curl", 20, 10), _s("Squat", 120, 8)], previous_bests={}
    )
    assert s.exercises[0].exercise_name == "Squat"


# ---------------------------------------------------------------------------
# Prescribing the next set
# ---------------------------------------------------------------------------


def test_load_goes_up_only_when_reps_were_genuinely_left_over():
    p = prescribe_next_set(
        last_weight_kg=75,
        last_reps=10,
        last_rir=4,
        reference_e1rm=105.0,
        is_compound=True,
        equipment="barbell",
        target_rir=2,
    )
    assert p.weight_kg == 77.5


def test_a_set_harder_than_target_repeats_rather_than_progressing():
    p = prescribe_next_set(
        last_weight_kg=75,
        last_reps=10,
        last_rir=0,
        reference_e1rm=105.0,
        is_compound=True,
        equipment="barbell",
        target_rir=2,
    )
    assert p.weight_kg == 75
    assert p.reps == 10


def test_hitting_the_target_effort_earns_a_rep_not_a_plate():
    p = prescribe_next_set(
        last_weight_kg=75,
        last_reps=10,
        last_rir=2,
        reference_e1rm=105.0,
        is_compound=True,
        equipment="barbell",
        target_rir=2,
    )
    assert p.weight_kg == 75
    assert p.reps == 11


def test_a_brand_new_lift_asks_rather_than_inventing_a_weight():
    p = prescribe_next_set(
        last_weight_kg=None,
        last_reps=None,
        last_rir=None,
        reference_e1rm=None,
        is_compound=True,
        target_rir=2,
    )
    assert p.weight_kg is None
    assert "pick a weight" in p.note.lower()
