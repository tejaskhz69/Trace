"""Spec for voice workout logging.

Two things are being pinned here.

The MATCHER: mapping a spoken phrase onto one of 736 catalogue rows is a
deterministic problem with a right answer, so it is our job, not the model's.
That makes it testable and stops it drifting when the model changes.

The PARSER: one object per set, never a count. A lifter who ramps up performed
three different sets, and collapsing that loses the session.
"""

from __future__ import annotations

import pytest

from app.services.workout_voice import (
    MAX_REPS,
    MAX_SETS,
    MAX_WEIGHT_KG,
    match_exercise,
    normalise,
    normalise_entry,
)

CATALOGUE = [
    ("e1", "Barbell Bench Press"),
    ("e2", "Dumbbell Bench Press"),
    ("e3", "Incline Dumbbell Press"),
    ("e4", "Bench Dips"),
    ("e5", "Romanian Deadlift"),
    ("e6", "Conventional Deadlift"),
    ("e7", "Barbell Squat"),
    ("e8", "Squat With Chains"),
    ("e9", "Lat Pulldown"),
    ("e10", "Overhead Press"),
]


def _entry(phrase="bench press", **over):
    base = {"exercise_phrase": phrase, "unit": "kg", "confidence": 0.9}
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# The matcher
# ---------------------------------------------------------------------------


def test_an_unqualified_lift_resolves_to_the_barbell_version():
    """What a lifter means by "bench press" is the barbell one."""
    m = match_exercise("bench press", CATALOGUE)
    assert m.name == "Barbell Bench Press"


def test_the_match_is_deterministic_across_machines():
    """Ties used to break on exercise_id, which is a random UUID -- so the
    same phrase resolved differently on different machines."""
    first = match_exercise("bench press", CATALOGUE).exercise_id
    shuffled = list(reversed(CATALOGUE))
    assert match_exercise("bench press", shuffled).exercise_id == first


def test_bench_dips_does_not_become_bench_press():
    """The synonym 'bench' -> 'bench press' must not fire inside a longer
    phrase; expanding in place turned this into 'bench press dips'."""
    assert match_exercise("bench dips", CATALOGUE).name == "Bench Dips"


def test_bare_bench_does_expand_when_it_is_the_whole_phrase():
    assert match_exercise("bench", CATALOGUE).name == "Barbell Bench Press"


def test_abbreviations_are_expanded():
    assert match_exercise("rdl", CATALOGUE).name == "Romanian Deadlift"
    assert match_exercise("incline db press", CATALOGUE).name == "Incline Dumbbell Press"


def test_a_qualified_phrase_beats_the_shorter_name():
    assert match_exercise("dumbbell bench press", CATALOGUE).name == "Dumbbell Bench Press"


def test_the_shorter_name_wins_when_the_user_said_less():
    assert match_exercise("squat", CATALOGUE).name == "Barbell Squat"


def test_synonyms_are_never_applied_to_catalogue_names():
    """Expanding names corrupts them: 'Bench Dips' would become 'bench press
    dips' and then out-rank the real bench press for the phrase 'bench press'.
    """
    assert normalise("Bench Dips", expand=False) == "bench dips"
    assert normalise("bench", expand=True) == "bench press"


def test_nonsense_matches_nothing_and_offers_alternatives():
    """Silently logging bench press because someone said something unclear is
    the failure this floor exists to prevent."""
    m = match_exercise("something entirely unrelated", CATALOGUE)
    assert m.exercise_id is None
    assert len(m.alternatives) > 0


def test_an_empty_phrase_matches_nothing():
    assert match_exercise("", CATALOGUE).exercise_id is None


# ---------------------------------------------------------------------------
# One object per set
# ---------------------------------------------------------------------------


def test_a_ramp_up_survives_as_three_different_sets():
    """"Sixty for five, eighty for five, a hundred for three" is the case the
    whole per-set array exists for. Collapsing it to "3 sets" throws away the
    session and makes the e1RM meaningless."""
    e = normalise_entry(
        _entry(
            "squat",
            sets=[
                {"reps": 5, "weight": 60},
                {"reps": 5, "weight": 80},
                {"reps": 3, "weight": 100},
            ],
        ),
        CATALOGUE,
    )
    assert [s.weight_kg for s in e.sets] == [60, 80, 100]
    assert [s.reps for s in e.sets] == [5, 5, 3]


def test_differing_reps_at_one_weight_survive():
    """"Sixty kilos, ten, ten, eight" — the last set dropped off, and that IS
    the information."""
    e = normalise_entry(
        _entry(sets=[{"reps": 10, "weight": 60}, {"reps": 10}, {"reps": 8}]),
        CATALOGUE,
    )
    assert [s.reps for s in e.sets] == [10, 10, 8]


def test_weight_carries_forward_within_an_exercise():
    """People say the load once and then just call the reps. Re-asking for it
    on every set is the typing this feature exists to remove."""
    e = normalise_entry(
        _entry(sets=[{"reps": 10, "weight": 60}, {"reps": 10}, {"reps": 8}]),
        CATALOGUE,
    )
    assert [s.weight_kg for s in e.sets] == [60, 60, 60]


def test_a_scalar_set_count_is_expanded_rather_than_dropped():
    """The model occasionally falls back to the old shape under load. Losing
    a real set over that is worse than expanding it."""
    e = normalise_entry(
        _entry(sets=3, weight=60, reps_low=10, reps_high=10), CATALOGUE
    )
    assert len(e.sets) == 3
    assert all(s.weight_kg == 60 and s.reps == 10 for s in e.sets)


def test_bodyweight_sets_carry_no_weight_rather_than_zero():
    e = normalise_entry(
        _entry("bench dips", sets=[{"reps": 12}, {"reps": 10}]), CATALOGUE
    )
    assert all(s.weight_kg is None for s in e.sets)


def test_reps_in_reserve_is_captured_per_set():
    e = normalise_entry(
        _entry(sets=[{"reps": 10, "weight": 60, "rir": 3}, {"reps": 8, "rir": 0}]),
        CATALOGUE,
    )
    assert [s.rir for s in e.sets] == [3, 0]


def test_a_warmup_set_is_flagged():
    e = normalise_entry(
        _entry(sets=[{"reps": 10, "weight": 20, "is_warmup": True}, {"reps": 8, "weight": 60}]),
        CATALOGUE,
    )
    assert e.sets[0].is_warmup is True
    assert e.sets[1].is_warmup is False


# ---------------------------------------------------------------------------
# Ranges and units
# ---------------------------------------------------------------------------


def test_a_spoken_range_is_preserved_and_prefilled_at_the_low_end():
    """A range is a target the lifter described, not a count they hit. Filling
    the middle invents precision; filling the LOW end means an unedited
    confirm can only ever under-claim."""
    e = normalise_entry(
        _entry(sets=[{"reps_low": 10, "reps_high": 15, "weight": 60}]), CATALOGUE
    )
    s = e.sets[0]
    assert (s.reps_low, s.reps_high) == (10, 15)
    assert s.reps == 10


def test_a_reversed_range_is_put_back_in_order():
    e = normalise_entry(
        _entry(sets=[{"reps_low": 15, "reps_high": 10}]), CATALOGUE
    )
    assert (e.sets[0].reps_low, e.sets[0].reps_high) == (10, 15)


def test_pounds_are_converted_to_kilos():
    e = normalise_entry(
        _entry(unit="lb", sets=[{"reps": 5, "weight": 225}]), CATALOGUE
    )
    assert e.sets[0].weight_kg == pytest.approx(102.1, abs=0.2)
    assert e.weight_was_converted is True


def test_an_unspoken_unit_is_assumed_and_the_assumption_is_surfaced():
    """Silently guessing the unit is a 2.2x error in the training history."""
    e = normalise_entry(
        _entry(unit="unknown", sets=[{"reps": 5, "weight": 100}]), CATALOGUE
    )
    assert e.unit_assumed is True
    assert any("assumed" in w for w in e.warnings)


def test_no_weight_means_no_unit_warning():
    """Warning about an assumed unit on a bodyweight set is noise."""
    e = normalise_entry(
        _entry("bench dips", unit="unknown", sets=[{"reps": 12}]), CATALOGUE
    )
    assert e.unit_assumed is False


# ---------------------------------------------------------------------------
# Bounds — these exist so a mis-transcription cannot enter the history
# ---------------------------------------------------------------------------


def test_an_impossible_weight_is_refused_not_stored():
    """"One hundred and sixty" misheard as "six hundred" must not become a
    personal record."""
    e = normalise_entry(
        _entry(sets=[{"reps": 5, "weight": MAX_WEIGHT_KG + 100}]), CATALOGUE
    )
    assert e.sets[0].weight_kg is None
    assert any("world record" in w for w in e.warnings)


def test_reps_are_clamped():
    e = normalise_entry(
        _entry(sets=[{"reps": MAX_REPS + 500, "weight": 60}]), CATALOGUE
    )
    assert e.sets[0].reps == MAX_REPS


def test_absurdly_many_sets_are_truncated_with_a_warning():
    e = normalise_entry(
        _entry(sets=[{"reps": 10, "weight": 60}] * (MAX_SETS + 10)), CATALOGUE
    )
    assert len(e.sets) == MAX_SETS
    assert any("kept the first" in w for w in e.warnings)


def test_an_entry_with_no_exercise_phrase_is_dropped():
    assert normalise_entry(_entry(""), CATALOGUE) is None


def test_an_unmatched_exercise_is_surfaced_rather_than_dropped():
    """A user who spoke a set and sees nothing appear stops trusting the
    feature. Show it, flag it, make them pick."""
    e = normalise_entry(
        _entry("the thing with the ropes", sets=[{"reps": 10}]), CATALOGUE
    )
    assert e is not None
    assert e.exercise_id is None
    assert any("Couldn't match" in w for w in e.warnings)
    assert len(e.alternatives) > 0
