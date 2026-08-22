"""Spec for the per-muscle volume report.

The value of this screen is the verdict, not the tally. These tests pin the
verdict: who is under-trained, who is past useful, and what the app tells them
to do about it.
"""

from __future__ import annotations

import pytest

from app.services.volume import (
    LANDMARKS,
    SECONDARY_CREDIT,
    VolumeStatus,
    build_report,
    landmarks_for,
)


def _sets(primary, n, secondaries=(), vol=1000.0, day="mon"):
    return [(primary, list(secondaries), vol, day) for _ in range(n)]


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------


def test_direct_sets_count_as_one_each():
    r = build_report(_sets("chest", 12))
    chest = next(m for m in r.muscles if m.muscle == "chest")
    assert chest.sets == 12
    assert chest.direct_sets == 12


def test_a_secondary_muscle_gets_partial_credit_not_zero():
    """A bench press trains the triceps. Counting that as zero tells a lifter
    to add arm work they do not need."""
    r = build_report(_sets("chest", 10, secondaries=["triceps", "shoulders"]))
    tri = next(m for m in r.muscles if m.muscle == "triceps")
    assert tri.sets == pytest.approx(10 * SECONDARY_CREDIT)
    assert tri.direct_sets == 0


def test_a_muscle_listed_as_its_own_secondary_is_not_double_counted():
    r = build_report(_sets("chest", 8, secondaries=["chest", "triceps"]))
    chest = next(m for m in r.muscles if m.muscle == "chest")
    assert chest.sets == 8


def test_sessions_count_distinct_days_not_sets():
    rows = _sets("back", 5, day="mon") + _sets("back", 5, day="thu")
    r = build_report(rows)
    back = next(m for m in r.muscles if m.muscle == "back")
    assert back.sessions == 2
    assert back.sets == 10


def test_untrained_muscles_still_appear():
    """A muscle you have not touched is the most useful row on the screen.
    Omitting it because the count is zero hides exactly what matters."""
    r = build_report(_sets("chest", 10))
    names = {m.muscle for m in r.muscles}
    assert "back" in names
    back = next(m for m in r.muscles if m.muscle == "back")
    assert back.sets == 0
    assert back.status is VolumeStatus.UNTRAINED


def test_muscles_are_ordered_by_how_much_they_were_trained():
    r = build_report(_sets("biceps", 4) + _sets("legs", 15))
    assert r.muscles[0].muscle == "legs"


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


def test_too_few_sets_reads_as_maintaining_not_building():
    lo, _ = LANDMARKS["chest"]
    r = build_report(_sets("chest", int(lo) - 4))
    chest = next(m for m in r.muscles if m.muscle == "chest")
    assert chest.status is VolumeStatus.UNDER
    assert "maintaining" in chest.note


def test_the_under_note_says_how_many_more_sets_are_needed():
    """Naming the gap is what makes the screen actionable."""
    r = build_report(_sets("chest", 6))
    chest = next(m for m in r.muscles if m.muscle == "chest")
    assert "more" in chest.note


def test_a_productive_amount_is_in_range():
    lo, hi = LANDMARKS["back"]
    r = build_report(_sets("back", int((lo + hi) / 2)))
    back = next(m for m in r.muscles if m.muscle == "back")
    assert back.status is VolumeStatus.IN_RANGE


def test_too_many_sets_is_called_out_as_no_longer_paying():
    _, hi = LANDMARKS["triceps"]
    r = build_report(_sets("triceps", int(hi) + 8))
    tri = next(m for m in r.muscles if m.muscle == "triceps")
    assert tri.status is VolumeStatus.OVER
    assert "past the point" in tri.note


def test_muscles_with_no_required_direct_work_are_not_nagged():
    """Nobody needs prescribed ab work to be healthy."""
    r = build_report(_sets("chest", 12))
    core = next(m for m in r.muscles if m.muscle == "core")
    assert core.min_effective == 0
    assert "That is fine" in core.note


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------


def test_landmarks_scale_with_the_reporting_window():
    """The published numbers are per WEEK. Judging a 30-day count against a
    weekly band would tell everyone they are massively over-training."""
    week_lo, week_hi = landmarks_for("chest", 7)
    month_lo, month_hi = landmarks_for("chest", 30)
    assert month_lo > week_lo
    assert month_hi > week_hi
    assert month_hi == pytest.approx(week_hi * 30 / 7, abs=0.15)


def test_a_months_worth_of_weekly_training_still_reads_as_in_range():
    """The regression this guards: correct training reported as over-training
    the moment the user taps '30 days'."""
    lo, hi = LANDMARKS["chest"]
    weekly = int((lo + hi) / 2)
    rows = []
    for week in range(4):
        rows += _sets("chest", weekly, day=f"w{week}")
    r = build_report(rows, days=28)
    chest = next(m for m in r.muscles if m.muscle == "chest")
    assert chest.status is VolumeStatus.IN_RANGE


def test_an_unknown_muscle_gets_a_default_band_rather_than_crashing():
    r = build_report(_sets("tail", 10))
    tail = next(m for m in r.muscles if m.muscle == "tail")
    assert tail.productive_max > 0


# ---------------------------------------------------------------------------
# The headline
# ---------------------------------------------------------------------------


def _covered(**overrides):
    """Every muscle with a floor trained to its minimum, then overridden.

    Without this, an untrained muscle sitting at a 100% deficit wins the
    "weakest" comparison every time -- which is correct behaviour, but it
    makes it impossible to test the ranking BETWEEN two under-trained ones.
    """
    rows = []
    for name, (lo, _) in LANDMARKS.items():
        n = overrides.get(name, int(lo))
        rows += _sets(name, n)
    return rows


def test_the_weakest_link_is_the_biggest_relative_shortfall():
    """2 of 10 chest sets is a worse gap than 6 of 8 triceps sets, even though
    the raw difference is smaller."""
    r = build_report(_covered(chest=2, triceps=6))
    assert r.weakest == "chest"


def test_a_muscle_never_trained_is_a_bigger_gap_than_one_merely_under():
    """A 0/10 back beats a 2/10 chest. Nothing is the worst amount."""
    r = build_report(_covered(chest=2, back=0))
    assert r.weakest == "back"


def test_a_muscle_with_no_floor_can_never_be_the_weakest_link():
    r = build_report(_sets("chest", 20) + _sets("back", 20) + _sets("legs", 20))
    assert r.weakest not in ("core", "forearms", "neck")


def test_the_headline_names_the_gap_when_there_is_one():
    r = build_report(_covered(chest=2))
    assert "Chest" in r.headline


def test_an_empty_week_names_no_weakest_link():
    """Every muscle sits at a 100% deficit, so picking one would be picking
    alphabetically and dressing it up as advice."""
    r = build_report([])
    assert r.total_sets == 0
    assert "No sets logged" in r.headline
    assert r.weakest is None


def test_totals_only_count_real_sets_not_partial_credit():
    """16 credited triceps sets from 32 bench presses is not 48 sets done."""
    r = build_report(_sets("chest", 32, secondaries=["triceps"]))
    assert r.total_sets == 32
