"""Spec for Strava import (app/services/strava.py).

The test that matters most is `test_import_never_changes_the_calorie_target`.
Everything else here is arithmetic; that one is the product.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.strava import (
    CYCLING_GROSS_EFFICIENCY,
    KJ_PER_KCAL,
    MAX_PLAUSIBLE_KCAL_PER_HOUR,
    calorie_target_delta,
    estimate_energy,
    import_effects,
    is_duplicate,
    kcal_from_kilojoules,
    normalise_sport,
    parse_activity,
)


def _ride(**overrides) -> dict:
    base = {
        "id": 987654321,
        "name": "Sarjapur loop",
        "sport_type": "Ride",
        "type": "Ride",
        "start_date": "2026-08-13T05:42:00Z",
        "moving_time": 4920,  # 1 h 22
        "elapsed_time": 5400,
        "distance": 34600.0,
        "total_elevation_gain": 412.0,
        "kilojoules": 1012.0,
        "calories": 831.0,
        "average_heartrate": 141.0,
        "max_heartrate": 172.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# THE INVARIANT
# ---------------------------------------------------------------------------


def test_import_never_changes_the_calorie_target():
    """CLAUDE.md non-negotiable #1, stated as a test.

    The adaptive TDEE already contains this ride via the weight trend. Adding
    it to the target double-counts, and double-counts a figure consumer
    devices overestimate by 25-90%.
    """
    rides = [parse_activity(_ride()), parse_activity(_ride(id=2, kilojoules=3000))]
    assert calorie_target_delta([r for r in rides if r]) == 0.0


def test_review_screen_says_the_target_is_unchanged():
    """The invariant must be VISIBLE, not merely true.

    A user who imports an 842 kcal ride and sees nothing about their target
    will assume it went up. The review list has to say otherwise in words.
    """
    act = parse_activity(_ride())
    assert act is not None
    effects = import_effects(act)

    target_row = next(e for e in effects if "calorie target" in e.label.lower())
    assert target_row.outcome == "Unchanged"
    assert target_row.changed is False


# ---------------------------------------------------------------------------
# Energy from measured work
# ---------------------------------------------------------------------------


def test_kilojoules_convert_via_real_physiology():
    """Not the "kJ ≈ kcal" shortcut -- the actual arithmetic.

    Changing CYCLING_GROSS_EFFICIENCY must change the answer, which is the
    whole point of not hardcoding the coincidence.
    """
    expected = (1012.0 / KJ_PER_KCAL) / CYCLING_GROSS_EFFICIENCY
    assert kcal_from_kilojoules(1012.0) == pytest.approx(expected)


def test_power_is_preferred_over_stravas_model():
    """Measured work outranks somebody else's estimate."""
    opts = estimate_energy(
        kilojoules=1012.0,
        strava_calories=831.0,
        duration_minutes=82.0,
        activity_type="cycling",
    )
    assert opts is not None
    assert opts.chosen.source == "power"
    assert opts.chosen.is_measured is True
    # Strava's number is still offered, so the user can see both.
    assert any(a.source == "strava" for a in opts.alternatives)


def test_both_estimates_are_labelled_for_the_user():
    opts = estimate_energy(
        kilojoules=1012.0,
        strava_calories=831.0,
        duration_minutes=82.0,
        activity_type="cycling",
    )
    assert opts is not None
    assert "kJ measured" in opts.chosen.detail
    assert opts.alternatives[0].label == "Strava est."


def test_kilojoules_are_ignored_for_sports_with_no_power_meter():
    """A run reporting kilojoules is a derived guess, not measured work."""
    opts = estimate_energy(
        kilojoules=900.0,
        strava_calories=600.0,
        duration_minutes=50.0,
        activity_type="running",
    )
    assert opts is not None
    assert opts.chosen.source == "strava"


def test_falls_back_to_met_when_nothing_else_exists():
    opts = estimate_energy(
        kilojoules=None,
        strava_calories=None,
        duration_minutes=90.0,
        activity_type="badminton",
        weight_kg=70.0,
    )
    assert opts is not None
    assert opts.chosen.source == "duration"
    assert opts.chosen.is_measured is False


def test_refuses_rather_than_inventing_a_number():
    """Non-negotiable #3. No weight, no sensor data, no answer.

    Storing 0 would read to the user as "you burned nothing", which is a
    different and wronger claim than "we don't know".
    """
    assert (
        estimate_energy(
            kilojoules=None,
            strava_calories=None,
            duration_minutes=45.0,
            activity_type="cricket",
            weight_kg=None,
        )
        is None
    )


def test_absurd_energy_is_rejected():
    """Corrupt data must not reach the weekly training load."""
    opts = estimate_energy(
        kilojoules=None,
        strava_calories=40_000.0,
        duration_minutes=60.0,
        activity_type="cycling",
    )
    assert opts is None


def test_plausibility_bound_scales_with_duration():
    """A six-hour ride legitimately burns more than a one-hour ride."""
    long_ride = estimate_energy(
        kilojoules=None,
        strava_calories=MAX_PLAUSIBLE_KCAL_PER_HOUR * 5,
        duration_minutes=360.0,
        activity_type="cycling",
    )
    assert long_ride is not None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_ride():
    act = parse_activity(_ride())
    assert act is not None
    assert act.name == "Sarjapur loop"
    assert act.activity_type == "cycling"
    assert act.distance_km == pytest.approx(34.6)
    assert act.duration_minutes == pytest.approx(82.0)
    assert act.kcal is not None


def test_parse_skips_activities_too_short_to_matter():
    assert parse_activity(_ride(moving_time=20, elapsed_time=20)) is None


def test_parse_survives_junk_in_numeric_fields():
    """Strava returns nulls and strings in numeric fields. One bad value must
    degrade one number, not fail the whole import."""
    act = parse_activity(
        _ride(distance="not-a-number", average_heartrate=None, kilojoules=True)
    )
    assert act is not None
    assert act.distance_km is None
    assert act.mean_heart_rate is None


def test_parse_handles_a_bad_start_date():
    act = parse_activity(_ride(start_date="yesterday-ish"))
    assert act is not None
    assert act.started_at.tzinfo is not None


def test_unknown_sport_is_filed_not_dropped():
    """Losing a session silently is worse than a generic label."""
    assert normalise_sport("UnderwaterBasketWeaving") == "workout"
    assert normalise_sport("GravelRide") == "cycling"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_same_ride_from_two_devices_is_one_session():
    """A rider with Strava AND an Apple Watch is the normal case."""
    act = parse_activity(_ride())
    assert act is not None
    assert is_duplicate(
        act,
        existing_start=act.started_at + timedelta(minutes=3),
        existing_type="cycling",
        existing_duration_minutes=80.0,
    )


def test_different_sports_at_the_same_time_are_not_duplicates():
    act = parse_activity(_ride())
    assert act is not None
    assert not is_duplicate(
        act,
        existing_start=act.started_at,
        existing_type="running",
        existing_duration_minutes=82.0,
    )


def test_a_short_warmup_is_not_swallowed_by_a_long_ride():
    """Same sport, same start, wildly different length -- two real sessions."""
    act = parse_activity(_ride(moving_time=1200))  # 20 min
    assert act is not None
    assert not is_duplicate(
        act,
        existing_start=act.started_at,
        existing_type="cycling",
        existing_duration_minutes=180.0,
    )


def test_rides_hours_apart_are_not_duplicates():
    act = parse_activity(_ride())
    assert act is not None
    assert not is_duplicate(
        act,
        existing_start=act.started_at + timedelta(hours=5),
        existing_type="cycling",
        existing_duration_minutes=82.0,
    )
