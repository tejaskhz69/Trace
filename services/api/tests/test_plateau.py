"""Spec for the plateau detector.

The detector's job is not really to find plateaus. It is to be RIGHT about
why a lift stopped moving, and most of the time the answer is not "plateau" --
it is missed sets, a deload, a bad month of sleep, or a different machine.
These tests weight that accordingly: eight of the ten statuses are the
detector declining to call a plateau, and each of them has to be reachable.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.plateau import (
    CONFIRM_EXPOSURES,
    MIN_EXPOSURES,
    MIN_SPAN_DAYS,
    Exposure,
    PlateauStatus,
    Series,
    SeriesKey,
    assess_plateau,
)

TODAY = date(2026, 8, 26)

BENCH = SeriesKey(
    exercise_id="ex-1",
    exercise_name="Dumbbell Bench Press",
    station_id="st-1",
    station_profile=None,
    station_name="the flat bench",
)
OTHER_STATION = SeriesKey(
    exercise_id="ex-1",
    exercise_name="Dumbbell Bench Press",
    station_id="st-2",
    station_profile=None,
    station_name="the incline bench",
)
NO_STATION = SeriesKey(
    exercise_id="ex-1", exercise_name="Barbell Squat", station_id=None
)


def expo(
    days_ago: int,
    *,
    weight: float = 20.0,
    reps: int = 8,
    e1rm: float | None = None,
    volume: float = 480.0,
    prescribed: int = 3,
    completed: int = 3,
    rir: float | None = 2.0,
    deload: bool = False,
    pain: bool = False,
    readiness: float | None = 0.8,
) -> Exposure:
    return Exposure(
        performed_on=TODAY - timedelta(days=days_ago),
        top_set_weight_kg=weight,
        top_set_reps=reps,
        top_set_e1rm=e1rm if e1rm is not None else weight * (1 + reps / 30),
        volume_load=volume,
        sets_prescribed=prescribed,
        sets_completed=completed,
        top_set_rir=rir,
        deload=deload,
        pain_flag=pain,
        readiness=readiness,
    )


def flat(n: int = 4, *, step: int = 9, **kw) -> list[Exposure]:
    """`n` identical sessions, `step` days apart, most recent today."""
    return [expo(i * step, **kw) for i in range(n)]


def one(series_list, **kw):
    return assess_plateau(series_list, today=TODAY, **kw)


# ---------------------------------------------------------------------------


class TestSuppression:
    def test_silent_while_adjudication_has_no_verdict(self):
        """The two must never contradict each other on one screen -- one
        saying "not enough data", the other naming a plateau."""
        a = one([Series(BENCH, tuple(flat(6)))], adjudication_insufficient=True)
        assert a.status is PlateauStatus.insufficient_data
        assert a.stalled_metric is None

    def test_no_history_is_insufficient_not_plateau(self):
        assert one([]).status is PlateauStatus.insufficient_data
        assert one([Series(BENCH, ())]).status is PlateauStatus.insufficient_data


class TestNotEnoughEvidence:
    def test_two_sessions_is_a_bad_week_not_a_plateau(self):
        a = one([Series(BENCH, tuple(flat(2, step=14)))])
        assert a.status is PlateauStatus.insufficient_data
        assert str(MIN_EXPOSURES) in a.reason

    def test_three_sessions_inside_a_week_still_waits_on_the_calendar(self):
        """The binding constraint. Three exposures accumulate in seven days at
        normal frequency; strength moves on a scale of weeks, so the span
        requirement is what actually governs the earliest verdict."""
        a = one([Series(BENCH, tuple(flat(3, step=2)))])
        assert a.status is PlateauStatus.insufficient_data
        assert str(MIN_SPAN_DAYS) in a.reason

    def test_exactly_at_both_thresholds_produces_a_verdict(self):
        a = one([Series(BENCH, tuple(flat(MIN_EXPOSURES, step=11)))])
        assert a.status is PlateauStatus.watch


class TestEquipmentIsALookupNotAQuestion:
    def test_moving_machine_returns_not_comparable(self):
        a = one(
            [
                Series(OTHER_STATION, (expo(30), expo(39), expo(48))),
                Series(BENCH, (expo(0), expo(4))),
            ]
        )
        assert a.status is PlateauStatus.not_comparable
        assert "incline bench" in a.reason and "flat bench" in a.reason

    def test_the_user_is_never_asked_to_confirm_the_equipment(self):
        a = one(
            [
                Series(OTHER_STATION, (expo(30), expo(39), expo(48))),
                Series(BENCH, (expo(0), expo(4))),
            ]
        )
        assert a.requires_confirmation is False
        assert "?" not in a.reason

    def test_a_cam_setting_change_is_its_own_explanation(self):
        """Same machine, same load, different setting is a different
        stimulus."""
        setting_a = SeriesKey("ex-2", "Chest Press", "st-9", "A", "the chest press")
        setting_b = SeriesKey("ex-2", "Chest Press", "st-9", "B", "the chest press")
        a = one(
            [
                Series(setting_a, (expo(30), expo(39), expo(48))),
                Series(setting_b, (expo(0), expo(4))),
            ]
        )
        assert a.status is PlateauStatus.not_comparable
        assert "setting" in a.reason.lower()

    def test_plenty_of_history_on_the_new_machine_is_not_a_switch(self):
        """Once the new setup has its own trend, the old machine is just
        history and mentioning it would be noise."""
        a = one(
            [
                Series(OTHER_STATION, (expo(80), expo(88))),
                Series(BENCH, tuple(flat(5, step=9))),
            ]
        )
        assert a.status is not PlateauStatus.not_comparable

    def test_station_less_work_is_a_legitimate_series(self):
        """A barbell squat has no station. It must still be assessable."""
        a = one([Series(NO_STATION, tuple(flat(5, step=9)))])
        assert a.status in (
            PlateauStatus.watch,
            PlateauStatus.confirmed_plateau,
        )
        assert "Not recorded" not in a.reason


class TestExecutionBeforeProgramming:
    def test_missed_sets_are_reported_as_execution_not_plateau(self):
        a = one(
            [Series(BENCH, tuple(flat(5, step=9, prescribed=4, completed=2)))]
        )
        assert a.status is PlateauStatus.incomplete_execution
        assert "%" in a.reason

    def test_just_above_the_completion_bar_is_assessed_normally(self):
        a = one(
            [Series(BENCH, tuple(flat(5, step=9, prescribed=5, completed=5)))]
        )
        assert a.status is not PlateauStatus.incomplete_execution

    def test_freestyle_logging_counts_as_complete(self):
        """Nothing was prescribed, so nothing was missed."""
        a = one(
            [Series(BENCH, tuple(flat(5, step=9, prescribed=0, completed=3)))]
        )
        assert a.status is not PlateauStatus.incomplete_execution


class TestNotAPlateau:
    def test_a_deload_is_not_a_stall(self):
        sessions = flat(5, step=9)
        sessions[0] = expo(0, deload=True)
        a = one([Series(BENCH, tuple(sessions))])
        assert a.status is PlateauStatus.deload_period

    def test_rising_e1rm_is_progress(self):
        sessions = [
            expo(27, weight=20, reps=8),
            expo(18, weight=22.5, reps=8),
            expo(9, weight=25, reps=8),
            expo(0, weight=27.5, reps=8),
        ]
        a = one([Series(BENCH, tuple(sessions))])
        assert a.status is PlateauStatus.progressing
        assert "estimated 1RM" in a.improving_metrics

    def test_more_reps_at_the_same_weight_is_progress(self):
        """Double progression. The weight has not moved and that is fine."""
        sessions = [
            expo(27, reps=6, e1rm=24.0, volume=360),
            expo(18, reps=7, e1rm=24.0, volume=420),
            expo(9, reps=8, e1rm=24.0, volume=480),
            expo(0, reps=10, e1rm=24.0, volume=600),
        ]
        a = one([Series(BENCH, tuple(sessions))])
        assert a.status is PlateauStatus.progressing
        assert "reps at the same weight" in a.improving_metrics

    def test_fewer_reps_at_a_lighter_weight_is_not_progress(self):
        """Guards the same-load requirement: dropping the weight must never
        read as improvement just because the reps went up."""
        sessions = [
            expo(27, weight=30, reps=5, e1rm=35.0, volume=450),
            expo(18, weight=25, reps=6, e1rm=30.0, volume=450),
            expo(9, weight=22.5, reps=7, e1rm=27.7, volume=450),
            expo(0, weight=20, reps=8, e1rm=25.3, volume=450),
        ]
        a = one([Series(BENCH, tuple(sessions))])
        assert a.status is not PlateauStatus.progressing

    def test_poor_readiness_confounds_rather_than_blames_the_programme(self):
        a = one([Series(BENCH, tuple(flat(5, step=9, readiness=0.3)))])
        assert a.status is PlateauStatus.confounded
        assert "sleep" in a.reason.lower()

    def test_progress_is_never_explained_away_by_low_readiness(self):
        """Order matters: a good result stands even on a bad week."""
        sessions = [
            expo(27, weight=20, readiness=0.2),
            expo(18, weight=22.5, readiness=0.2),
            expo(9, weight=25, readiness=0.2),
            expo(0, weight=27.5, readiness=0.2),
        ]
        a = one([Series(BENCH, tuple(sessions))])
        assert a.status is PlateauStatus.progressing

    def test_unknown_readiness_is_not_treated_as_good_readiness(self):
        a = one([Series(BENCH, tuple(flat(5, step=9, readiness=None)))])
        assert a.status is not PlateauStatus.confounded
        # ...but it costs confidence, because we did not ask.
        known = one([Series(BENCH, tuple(flat(5, step=9)))])
        assert a.confidence < known.confidence


class TestSafety:
    def test_pain_outranks_everything(self):
        sessions = flat(5, step=9)
        sessions[0] = expo(0, pain=True, deload=True, prescribed=4, completed=1)
        a = one([Series(BENCH, tuple(sessions))])
        assert a.status is PlateauStatus.safety_stop

    def test_a_safety_stop_gives_no_progression_advice(self):
        sessions = flat(5, step=9)
        sessions[0] = expo(0, pain=True)
        a = one([Series(BENCH, tuple(sessions))])
        text = (a.reason + " " + a.recommendation).lower()
        assert "add a set" not in text
        assert "increase" not in text
        assert "physio" in text or "clinician" in text


class TestTheTwoPlateauStatuses:
    def test_three_flat_sessions_is_watch_not_a_call(self):
        a = one([Series(BENCH, tuple(flat(3, step=11)))])
        assert a.status is PlateauStatus.watch
        assert a.requires_confirmation is False

    def test_four_flat_sessions_over_four_weeks_is_confirmed(self):
        a = one([Series(BENCH, tuple(flat(CONFIRM_EXPOSURES, step=10)))])
        assert a.status is PlateauStatus.confirmed_plateau
        assert a.requires_confirmation is True
        assert a.stalled_metric == "estimated 1RM"

    def test_six_flat_sessions_over_six_weeks_is_persistent(self):
        a = one([Series(BENCH, tuple(flat(6, step=9)))])
        assert a.status is PlateauStatus.persistent_plateau
        assert "deload" in a.recommendation.lower()

    def test_the_assessment_shows_its_working(self):
        sessions = flat(5, step=9)
        a = one([Series(BENCH, tuple(sessions))])
        assert len(a.evidence) == len(sessions)
        assert a.evidence == tuple(sorted(a.evidence))
        assert a.baseline is not None and a.current is not None
        assert a.baseline.performed_on < a.current.performed_on

    def test_all_ten_statuses_are_reachable(self):
        """A status nothing can produce is a lie in the API contract."""
        setting_a = SeriesKey("ex-2", "Chest Press", "st-9", "A", "the press")
        setting_b = SeriesKey("ex-2", "Chest Press", "st-9", "B", "the press")
        rising = [expo(27, weight=20), expo(18, weight=23), expo(0, weight=27)]
        painful = flat(5, step=9)
        painful[0] = expo(0, pain=True)
        deloaded = flat(5, step=9)
        deloaded[0] = expo(0, deload=True)

        seen = {
            one([], adjudication_insufficient=True).status,
            one([Series(BENCH, tuple(flat(2, step=14)))]).status,
            one([Series(BENCH, tuple(rising))]).status,
            one(
                [
                    Series(setting_a, (expo(30), expo(39), expo(48))),
                    Series(setting_b, (expo(0),)),
                ]
            ).status,
            one([Series(BENCH, tuple(flat(5, step=9, prescribed=4, completed=1)))]).status,
            one([Series(BENCH, tuple(deloaded))]).status,
            one([Series(BENCH, tuple(flat(5, step=9, readiness=0.2)))]).status,
            one([Series(BENCH, tuple(flat(3, step=11)))]).status,
            one([Series(BENCH, tuple(flat(CONFIRM_EXPOSURES, step=10)))]).status,
            one([Series(BENCH, tuple(flat(6, step=9)))]).status,
            one([Series(BENCH, tuple(painful))]).status,
        }
        assert seen == set(PlateauStatus)


class TestDeterminism:
    def test_identical_input_gives_identical_output_fifty_times(self):
        series = [
            Series(OTHER_STATION, tuple(flat(3, step=30))),
            Series(BENCH, tuple(flat(5, step=9))),
        ]
        first = one(series)
        for _ in range(50):
            assert one(series) == first

    def test_series_order_does_not_change_the_answer(self):
        a = Series(OTHER_STATION, tuple(flat(3, step=30)))
        b = Series(BENCH, tuple(flat(5, step=9)))
        assert one([a, b]).status == one([b, a]).status

    def test_exposure_order_does_not_change_the_answer(self):
        sessions = flat(5, step=9)
        assert one([Series(BENCH, tuple(sessions))]) == one(
            [Series(BENCH, tuple(reversed(sessions)))]
        )

    def test_the_assessment_is_frozen(self):
        a = one([Series(BENCH, tuple(flat(5, step=9)))])
        with pytest.raises(Exception):
            a.status = PlateauStatus.progressing  # type: ignore[misc]

    def test_no_wall_clock_is_read(self):
        """`today` is a parameter. A detector whose answer changes overnight
        from identical data cannot be explained to a user.

        Checked over the AST rather than the source text, so that the module
        comment explaining this rule does not itself trip it.
        """
        import ast
        import pathlib

        import app.services.plateau as mod

        tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
        called = {
            ast.unparse(n.func)
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
        }
        banned = {"date.today", "datetime.now", "datetime.utcnow", "time.time"}
        assert called & banned == set(), called & banned


class TestLanguage:
    """The spec's "Never" list, enforced on the text the user actually sees."""

    BANNED = [
        "diagnos",
        "you failed",
        "you didn't try",
        "lazy",
        "overtrained",
        "injury",
        "condition",
    ]

    def _all_text(self):
        setting_b = SeriesKey("ex-2", "Chest Press", "st-9", "B", "the press")
        painful = flat(5, step=9)
        painful[0] = expo(0, pain=True)
        cases = [
            one([Series(BENCH, tuple(flat(5, step=9)))]),
            one([Series(BENCH, tuple(flat(6, step=9)))]),
            one([Series(BENCH, tuple(flat(3, step=11)))]),
            one([Series(BENCH, tuple(painful))]),
            one([Series(BENCH, tuple(flat(5, step=9, prescribed=4, completed=1)))]),
            one([Series(BENCH, tuple(flat(5, step=9, readiness=0.2)))]),
            one(
                [
                    Series(OTHER_STATION, (expo(30), expo(39), expo(48))),
                    Series(setting_b, (expo(0),)),
                ]
            ),
        ]
        return [(c, f"{c.reason} {c.recommendation}") for c in cases]

    def test_never_diagnoses_or_blames(self):
        for assessment, text in self._all_text():
            low = text.lower()
            for word in self.BANNED:
                assert word not in low, f"{assessment.status}: {word!r} in {text!r}"

    def test_never_prescribes_a_specific_load_it_cannot_verify(self):
        """The step depends on what the station can actually load. Naming a
        number this module cannot check is worse than naming none."""
        import re

        for assessment, text in self._all_text():
            assert not re.search(r"add \d+(\.\d+)?\s*(kg|lb)", text.lower()), text

    def test_never_prescribes_a_one_rep_max_attempt(self):
        for _, text in self._all_text():
            low = text.lower()
            assert "1rm attempt" not in low
            assert "test your max" not in low

    def test_every_training_change_asks_first(self):
        """Recommended, never applied."""
        a = one([Series(BENCH, tuple(flat(CONFIRM_EXPOSURES, step=10)))])
        assert a.requires_confirmation
        assert "options:" in a.recommendation.lower()

    def test_the_explanation_names_the_lift_and_the_equipment(self):
        a = one([Series(BENCH, tuple(flat(5, step=9)))])
        assert "Dumbbell Bench Press" in a.reason
        assert "flat bench" in a.reason
