"""Consistency and phase progress. These are the spec.

The class at the bottom is the important one: it pins the rule that a streak
may never be shown as an achievement without the verdict that says whether the
thing being done consistently is working.
"""

from datetime import date, timedelta

import pytest

from app.services import streak
from app.services.streak import PhaseVerdict

TODAY = date(2026, 8, 20)


def days_back(*offsets: int) -> set[date]:
    return {TODAY - timedelta(days=o) for o in offsets}


def run_of(n: int, *, ending_days_ago: int = 0) -> set[date]:
    return {TODAY - timedelta(days=ending_days_ago + i) for i in range(n)}


class TestStreak:
    def test_no_history_is_zero(self):
        assert streak.compute_streak(set(), TODAY) == (0, 0)

    def test_counts_an_unbroken_run(self):
        current, longest = streak.compute_streak(run_of(5), TODAY)
        assert current == 5
        assert longest == 5

    def test_today_being_blank_does_not_break_the_streak(self):
        # The day is not over. Resetting to zero every morning would be both
        # wrong and demoralising at exactly the wrong moment.
        current, _ = streak.compute_streak(run_of(5, ending_days_ago=1), TODAY)
        assert current == 5

    def test_one_missed_day_is_forgiven(self):
        # Logged today and the 2 days before, missed 3 days ago, then 4 more.
        logged = days_back(0, 1, 2, 4, 5, 6, 7)
        current, _ = streak.compute_streak(logged, TODAY)
        assert current == 7

    def test_a_forgiven_day_is_not_a_credited_day(self):
        # The chain survives the gap, but the count is days actually logged.
        logged = days_back(0, 1, 2, 4, 5, 6, 7)
        current, _ = streak.compute_streak(logged, TODAY)
        assert current == len(logged)

    def test_two_missed_days_in_a_row_ends_it(self):
        logged = days_back(0, 1, 2, 5, 6, 7)
        current, _ = streak.compute_streak(logged, TODAY)
        assert current == 3

    def test_longest_survives_a_broken_current(self):
        old = {TODAY - timedelta(days=100 + i) for i in range(20)}
        current, longest = streak.compute_streak(old | days_back(0), TODAY)
        assert current == 1
        assert longest >= 20

    def test_longest_is_never_below_current(self):
        current, longest = streak.compute_streak(run_of(12), TODAY)
        assert longest >= current


class TestConsistency:
    def test_percentage_is_logged_days_over_the_window(self):
        r = streak.consistency(run_of(15), TODAY, window_days=30)
        assert r.days_logged == 15
        assert r.consistency_pct == pytest.approx(0.5)

    def test_only_counts_days_inside_the_window(self):
        old = {TODAY - timedelta(days=200 + i) for i in range(50)}
        r = streak.consistency(old | run_of(3), TODAY, window_days=30)
        assert r.days_logged == 3

    def test_knows_whether_today_is_done(self):
        assert streak.consistency(run_of(3), TODAY).logged_today is True
        assert (
            streak.consistency(run_of(3, ending_days_ago=1), TODAY).logged_today
            is False
        )

    def test_confidence_rises_then_saturates(self):
        thin = streak.consistency(run_of(5), TODAY).data_confidence
        ok = streak.consistency(run_of(21), TODAY).data_confidence
        more = streak.consistency(run_of(30), TODAY).data_confidence
        assert thin < ok
        assert ok == 1.0
        # Past three weeks, more data barely improves the estimate. Implying
        # otherwise would make 95% look meaningfully better than 85%.
        assert more == ok

    def test_reports_a_milestone_exactly_when_reached(self):
        assert streak.consistency(run_of(7), TODAY).milestone == "One week"
        assert streak.consistency(run_of(8), TODAY).milestone is None

    def test_always_names_the_next_milestone_and_the_gap(self):
        r = streak.consistency(run_of(4), TODAY)
        assert r.next_milestone == "One week"
        assert r.days_to_next == 3

    def test_first_milestones_are_early_enough_to_matter(self):
        # A first badge at 30 days is a badge nobody ever sees.
        assert streak.MILESTONES[0][0] <= 3

    def test_a_zero_streak_gets_a_way_back_in(self):
        r = streak.consistency(set(), TODAY)
        assert r.current_streak == 0
        assert "today" in r.headline.lower()

    def test_headline_is_never_empty(self):
        for n in (0, 1, 3, 7, 12, 40):
            assert streak.consistency(run_of(n) if n else set(), TODAY).headline


class TestPhaseProgress:
    def _call(self, goal, start, current, weeks, target):
        return streak.phase_progress(
            goal, start, current, TODAY - timedelta(weeks=weeks), TODAY, target
        )

    def test_refuses_without_weigh_ins(self):
        r = streak.phase_progress("gain", None, None, None, TODAY, 0.25)
        assert r.verdict is PhaseVerdict.insufficient_data

    def test_refuses_before_two_weeks(self):
        # Water, glycogen and gut content swamp real tissue change.
        r = self._call("gain", 80.0, 81.0, 1, 0.25)
        assert r.verdict is PhaseVerdict.insufficient_data

    def test_on_track_bulk(self):
        r = self._call("gain", 80.0, 81.0, 4, 0.25)
        assert r.verdict is PhaseVerdict.on_track
        assert r.rate_kg_per_week == pytest.approx(0.25, abs=0.01)

    def test_too_fast_bulk_is_called_out_as_fat(self):
        r = self._call("gain", 80.0, 83.0, 4, 0.25)
        assert r.verdict is PhaseVerdict.too_fast
        assert "fat" in " ".join(r.notes).lower()

    def test_too_slow_bulk_suspects_logging_first(self):
        r = self._call("gain", 80.0, 80.2, 4, 0.25)
        assert r.verdict is PhaseVerdict.too_slow
        assert "logging" in " ".join(r.notes).lower()

    def test_on_track_cut(self):
        r = self._call("lose", 90.0, 88.0, 4, -0.5)
        assert r.verdict is PhaseVerdict.on_track

    def test_too_fast_cut_warns_about_muscle(self):
        r = self._call("lose", 90.0, 84.0, 4, -0.5)
        assert r.verdict is PhaseVerdict.too_fast
        assert "lift" in " ".join(r.notes).lower()

    def test_gaining_on_a_cut_is_wrong_way(self):
        r = self._call("lose", 90.0, 92.0, 4, -0.5)
        assert r.verdict is PhaseVerdict.wrong_way

    def test_losing_on_a_bulk_is_wrong_way(self):
        r = self._call("gain", 80.0, 78.0, 4, 0.25)
        assert r.verdict is PhaseVerdict.wrong_way

    def test_wrong_way_checks_logging_before_touching_calories(self):
        # Non-negotiable #5: calories are the LAST lever.
        r = self._call("gain", 80.0, 78.0, 4, 0.25)
        assert "logged" in " ".join(r.notes).lower()

    def test_recomp_is_judged_on_stillness(self):
        assert self._call("recomp", 80.0, 80.1, 6, None).verdict is PhaseVerdict.on_track
        assert self._call("recomp", 80.0, 83.0, 6, None).verdict is PhaseVerdict.wrong_way

    def test_recomp_defers_to_the_lifts(self):
        r = self._call("recomp", 80.0, 80.1, 6, None)
        assert "lift" in " ".join(r.notes).lower()

    def test_reports_the_arithmetic_it_used(self):
        r = self._call("gain", 80.0, 81.0, 4, 0.25)
        assert r.total_change_kg == pytest.approx(1.0)
        assert r.weeks_elapsed == pytest.approx(4.0, abs=0.1)
        assert "1.0 kg" in r.detail


class TestStreakNeverStandsAlone:
    """A streak must never be presentable as success on its own.

    A 40-day streak on a bulk that has added nothing but fat is not an
    achievement, and the shape of these types is what stops the UI showing
    one without the other.
    """

    def test_consistency_carries_no_verdict_of_its_own(self):
        r = streak.consistency(run_of(40), TODAY)
        assert not hasattr(r, "verdict")
        assert not hasattr(r, "success")

    def test_a_long_streak_does_not_imply_a_good_phase(self):
        long_streak = streak.consistency(run_of(40), TODAY)
        bad_phase = streak.phase_progress(
            "gain", 80.0, 86.0, TODAY - timedelta(weeks=5), TODAY, 0.25
        )
        assert long_streak.current_streak == 40
        assert bad_phase.verdict is PhaseVerdict.too_fast

    def test_phase_report_always_carries_a_headline_to_show_beside_it(self):
        for goal in ("gain", "lose", "recomp"):
            r = streak.phase_progress(
                goal, 80.0, 81.0, TODAY - timedelta(weeks=4), TODAY, 0.25
            )
            assert r.headline
