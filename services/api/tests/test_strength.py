"""Spec for the per-set strength engine.

These tests are the contract for the one thing the product must not get
wrong: telling someone they got stronger when they did not, or missing it
when they did.
"""

from __future__ import annotations

from datetime import date

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
    ewma,
    ewma_over_weeks,
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


# ---------------------------------------------------------------------------
# The two e1RM contracts
#
# `e1rm` and `trend_e1rm` share one Epley core and differ deliberately. These
# tests exist so that a future "tidy these two similar functions into one"
# fails loudly instead of silently shifting the strength index. See the block
# comment above `_epley` in app/services/strength.py.
# ---------------------------------------------------------------------------


class TestTheTwoE1rmContractsMustNotBeMerged:
    def test_one_rep_is_exact_for_the_trend_and_estimated_per_set(self):
        """A single at 100 kg proves a max of at least 100 kg. The trend must
        record 100, not Epley's 103.3, or every series that opens with a
        single reads as a 3.3% gain that never happened."""
        from app.services.strength import trend_e1rm

        assert trend_e1rm(100, 1) == 100
        assert e1rm(100, 1) == 103.3

    def test_they_disagree_on_real_inputs(self):
        """Not a rounding difference. If this ever reaches zero disagreements
        the two contracts have quietly become one."""
        from app.services.strength import trend_e1rm

        disagreements = [
            (w, r)
            for w in (60, 80, 100, 120)
            for r in range(1, 13)
            if trend_e1rm(w, r) != e1rm(w, r)
        ]
        assert len(disagreements) > 0

    def test_only_the_per_set_estimate_accepts_rir(self):
        """A set stopped 3 short of failure is evidence of a heavier set. The
        weekly trend is built from bests where that information is gone."""
        from app.services.strength import trend_e1rm

        assert e1rm(100, 5, rir=3) > e1rm(100, 5, rir=0)
        with pytest.raises(TypeError):
            trend_e1rm(100, 5, 3)  # type: ignore[call-arg]

    def test_the_caps_differ_and_both_are_enforced(self):
        from app.services.strength import TREND_REP_CAP, trend_e1rm

        assert TREND_REP_CAP < REP_CEILING
        assert trend_e1rm(100, TREND_REP_CAP + 1) is None
        # The per-set ceiling counts effective reps, so it sits higher.
        assert e1rm(100, TREND_REP_CAP + 1) is not None
        assert e1rm(100, REP_CEILING + 1) is None

    def test_the_formula_itself_is_defined_once(self):
        """Both wrappers resolve to `_epley`. The contracts may differ; the
        arithmetic may not."""
        import app.services.strength as strength

        calls: list[tuple[float, float]] = []
        original = strength._epley

        def spy(w, r):
            calls.append((w, r))
            return original(w, r)

        strength._epley = spy
        try:
            strength.e1rm(100, 5, rir=2)
            strength.trend_e1rm(100, 5)
        finally:
            strength._epley = original

        assert len(calls) == 2, "a caller is re-deriving Epley locally"
        assert calls[0] == (100, 7.0)  # reps + RIR
        assert calls[1] == (100, 5)    # raw reps


class TestAdjudicationReadsTheSameImplementation:
    def test_adjudication_does_not_define_its_own(self):
        """Step 1 of the upgrade plan: one shared implementation, imported --
        not a second copy that can drift."""
        from app.services import adjudication
        from app.services.strength import ewma, trend_e1rm

        assert adjudication.epley_e1rm is trend_e1rm
        assert adjudication.ewma is ewma

    def test_the_published_names_still_work(self):
        """These are adjudication's vocabulary and other modules import them.
        The move must not have renamed anything out from under a caller."""
        from app.services import adjudication

        assert adjudication.E1RM_REP_CAP == 12
        assert adjudication.E1RM_EWMA_ALPHA == 0.4
        assert adjudication.epley_e1rm(100, 1) == 100
        assert adjudication.ewma([100, 100, 100]) == 100


class TestTheSmoothingIsPinnedToRealArithmetic:
    """`ewma([100, 100, 100]) == 100` was the only coverage this had.

    That assertion passes for any alpha, and it also passes for a plain mean,
    for "return the last element", and for "return the first". It pins
    nothing. These compute the series by hand instead.
    """

    def test_a_hand_computed_series(self):
        # acc = 100
        # acc = 100 + 0.4 * (110 - 100) = 104.0
        # acc = 104 + 0.4 * (105 - 104) = 104.4
        assert ewma([100.0, 110.0, 105.0]) == pytest.approx(104.4)

    def test_a_second_hand_computed_series(self):
        # acc = 50, 50, 50, then 50 + 0.4 * (100 - 50) = 70
        assert ewma([50.0, 50.0, 50.0, 100.0]) == pytest.approx(70.0)

    def test_it_is_not_the_mean_nor_the_latest_value(self):
        """The three cheap wrong implementations, ruled out explicitly."""
        got = ewma([100.0, 200.0])
        assert got == pytest.approx(140.0)
        assert got != pytest.approx(150.0)  # mean
        assert got != pytest.approx(200.0)  # latest
        assert got != pytest.approx(100.0)  # first

    def test_the_first_session_is_itself_not_a_fraction_of_itself(self):
        """Seeding the accumulator at zero is the classic EWMA bug: the first
        point would come back as 40 kg for a 100 kg lift, and the opening
        weeks of every series would read as a climb that never happened."""
        assert ewma([100.0]) == 100.0

    def test_an_empty_series_refuses_rather_than_returning_zero(self):
        """Zero would render as a real e1RM of 0 kg."""
        assert ewma([]) is None

    def test_alpha_is_load_bearing_and_pinned(self):
        from app.services.strength import EWMA_ALPHA

        assert EWMA_ALPHA == 0.4
        assert ewma([100.0, 200.0], alpha=0.4) != ewma([100.0, 200.0], alpha=0.6)


class TestALayoffEndsTheSeriesRatherThanInterruptingIt:
    """A lifter trains through March, disappears for six weeks, comes back.

    The weekly series is built by grouping sets into ISO weeks, and weeks
    with no training are ABSENT from that grouping rather than present with
    a null. So the plain `ewma()` sees two adjacent numbers and smooths
    straight across the gap -- the return reads as a continuation of
    pre-layoff form.
    """

    #: Four weeks at 100, six weeks off, then three weeks back at 80.
    LAYOFF = [
        (date(2026, 3, 2), 100.0),
        (date(2026, 3, 9), 100.0),
        (date(2026, 3, 16), 100.0),
        (date(2026, 3, 23), 100.0),
        # six weeks of nothing
        (date(2026, 5, 4), 80.0),
        (date(2026, 5, 11), 82.0),
        (date(2026, 5, 18), 84.0),
    ]

    def test_the_undated_smoother_cannot_see_the_gap(self):
        """Not a failure of `ewma` -- a demonstration of why the dated one
        has to exist. Given only the values, the first session back is
        smoothed to 92, i.e. mostly the lifter's pre-layoff self."""
        values = [v for _d, v in self.LAYOFF]
        assert ewma(values[:5]) == pytest.approx(92.0)

    def test_the_first_session_back_is_a_new_baseline(self):
        smoothed = ewma_over_weeks(self.LAYOFF)
        assert smoothed[3] == pytest.approx(100.0)  # last week before the break
        assert smoothed[4] == pytest.approx(80.0)   # first week back: itself

    def test_the_return_is_not_smoothed_towards_pre_layoff_form(self):
        smoothed = ewma_over_weeks(self.LAYOFF)
        assert smoothed[4] < 85.0, (
            "the first session back was smoothed towards the pre-layoff "
            "reference, which is the bug this function exists to prevent"
        )

    def test_the_rebuild_smooths_normally_once_training_resumes(self):
        """Resetting must not mean "never smooth again"."""
        smoothed = ewma_over_weeks(self.LAYOFF)
        # 80, then 80 + 0.4*(82-80) = 80.8, then 80.8 + 0.4*(84-80.8) = 82.08
        assert smoothed[5] == pytest.approx(80.8)
        assert smoothed[6] == pytest.approx(82.08)

    def test_an_ordinary_week_off_is_not_a_layoff(self):
        """Missing one week is normal life -- illness, travel, a deload. It
        must not reset the trend or nobody's series ever smooths."""
        points = [
            (date(2026, 3, 2), 100.0),
            (date(2026, 3, 9), 100.0),
            # one week missed
            (date(2026, 3, 23), 120.0),
        ]
        smoothed = ewma_over_weeks(points)
        assert smoothed[2] == pytest.approx(108.0)  # smoothed, not reset

    def test_it_agrees_with_the_plain_smoother_on_an_unbroken_series(self):
        """The two must not disagree when there is no gap to disagree about."""
        points = [
            (date(2026, 3, 2), 100.0),
            (date(2026, 3, 9), 110.0),
            (date(2026, 3, 16), 105.0),
        ]
        assert ewma_over_weeks(points)[-1] == pytest.approx(
            ewma([v for _d, v in points])
        )

    def test_an_empty_series_is_empty_not_a_crash(self):
        assert ewma_over_weeks([]) == []
