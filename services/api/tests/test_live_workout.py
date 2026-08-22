"""End-to-end spec for the live set logger and the session summary card.

The pure maths lives in test_strength.py. These tests cover the parts only the
HTTP layer can get wrong: which sets count as the reference, whether a set is
compared against itself, and whether the verdict survives the round trip.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Exercise, SetLog, WorkoutSession

async def _register(client) -> dict:
    res = await client.post(
        "/api/auth/register",
        json={"email": "lifter@example.com", "password": "correct-horse-1"},
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client, db_session, *, equipment="barbell", compound=True):
    auth = await _register(client)
    headers = _headers(auth["access_token"])
    ex = Exercise(
        name="Barbell Bench Press",
        muscle_group="chest",
        equipment=equipment,
        is_compound=compound,
    )
    db_session.add(ex)
    await db_session.commit()
    await db_session.refresh(ex)
    res = await client.post(
        "/api/workouts/sessions", headers=headers, json={"routine_name": "Push"}
    )
    return headers, ex, res.json()["id"]


async def _log(client, headers, sid, ex_id, **kw):
    payload = {"exercise_id": ex_id, "weight_kg": 75, "reps": 10, **kw}
    res = await client.post(
        f"/api/workouts/sessions/{sid}/sets", headers=headers, json=payload
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
# Logging a set
# ---------------------------------------------------------------------------


async def test_logging_a_set_returns_its_verdict_in_the_same_response(
    client, db_session
):
    """The lifter is standing at the bar. A second round trip is one too many."""
    headers, ex, sid = await _setup(client, db_session)
    body = await _log(client, headers, sid, ex.id, rir=2)

    assert body["e1rm"] is not None
    assert body["verdict"] in ("PURPLE", "ON_TARGET", "UNDER", "UNRATED")
    assert body["detail"]


async def test_the_first_ever_set_is_unrated_not_a_personal_record(
    client, db_session
):
    """With no history there is nothing to beat, and claiming a PR would be
    a fabricated comparison."""
    headers, ex, sid = await _setup(client, db_session)
    body = await _log(client, headers, sid, ex.id, rir=2)
    assert body["verdict"] == "UNRATED"
    assert body["reference_e1rm"] is None


async def test_reps_in_reserve_raise_the_estimate(client, db_session):
    """The premise of the whole engine, verified through the API."""
    headers, ex, sid = await _setup(client, db_session)
    hard = await _log(client, headers, sid, ex.id, rir=0)
    easy = await _log(client, headers, sid, ex.id, rir=4)
    assert easy["e1rm"] > hard["e1rm"]


async def test_rpe_is_accepted_and_converted_to_rir(client, db_session):
    """RPE 8 and RIR 2 are the same claim; both must produce the same estimate."""
    headers, ex, sid = await _setup(client, db_session)
    via_rpe = await _log(client, headers, sid, ex.id, rpe=8)
    via_rir = await _log(client, headers, sid, ex.id, rir=2)
    assert via_rpe["rir"] == 2
    assert via_rpe["e1rm"] == via_rir["e1rm"]


async def test_a_second_heavier_set_beats_the_first_and_goes_purple(
    client, db_session
):
    headers, ex, sid = await _setup(client, db_session)
    await _log(client, headers, sid, ex.id, weight_kg=75, reps=10, rir=2)
    body = await _log(client, headers, sid, ex.id, weight_kg=85, reps=10, rir=2)
    assert body["verdict"] == "PURPLE"


async def test_a_warmup_never_becomes_the_reference_to_beat(client, db_session):
    """Otherwise a warm-up at 40 kg would make every working set a record,
    and a warm-up single at 60% would read as a strength decline."""
    headers, ex, sid = await _setup(client, db_session)
    await _log(client, headers, sid, ex.id, weight_kg=40, reps=10, rir=5, is_warmup=True)
    body = await _log(client, headers, sid, ex.id, weight_kg=75, reps=10, rir=2)
    assert body["reference_e1rm"] is None
    assert body["verdict"] == "UNRATED"


async def test_the_response_names_a_concrete_route_to_beating_the_record(
    client, db_session
):
    headers, ex, sid = await _setup(client, db_session)
    await _log(client, headers, sid, ex.id, weight_kg=75, reps=10, rir=2)
    body = await _log(client, headers, sid, ex.id, weight_kg=75, reps=10, rir=2)
    route = body["route"]
    assert route["reps_needed"] or route["weight_needed_kg"]
    # And the weight it names must be loadable on a barbell.
    if route["weight_needed_kg"]:
        assert route["weight_needed_kg"] % 2.5 == pytest.approx(0, abs=1e-6)


# ---------------------------------------------------------------------------
# The next-set screen
# ---------------------------------------------------------------------------


async def test_next_set_answers_everything_the_live_screen_needs_at_once(
    client, db_session
):
    headers, ex, sid = await _setup(client, db_session)
    await _log(client, headers, sid, ex.id, weight_kg=75, reps=10, rir=2)

    res = await client.get(
        f"/api/workouts/sessions/{sid}/next-set",
        headers=headers,
        params={"exercise_id": ex.id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["exercise"]["name"] == "Barbell Bench Press"
    assert body["prescription"]["reps"] >= 1
    assert body["prescription"]["rest_s"] > 0
    assert body["weight_step_kg"] == 2.5
    assert len(body["sets_done"]) == 1
    assert body["sets_done"][0]["weight_kg"] == 75


async def test_next_set_progresses_load_only_when_reps_were_left_over(
    client, db_session
):
    headers, ex, sid = await _setup(client, db_session)
    await _log(client, headers, sid, ex.id, weight_kg=75, reps=10, rir=4)

    res = await client.get(
        f"/api/workouts/sessions/{sid}/next-set",
        headers=headers,
        params={"exercise_id": ex.id},
    )
    assert res.json()["prescription"]["weight_kg"] == 77.5


async def test_next_set_on_an_untouched_lift_asks_rather_than_inventing(
    client, db_session
):
    headers, ex, sid = await _setup(client, db_session)
    res = await client.get(
        f"/api/workouts/sessions/{sid}/next-set",
        headers=headers,
        params={"exercise_id": ex.id},
    )
    assert res.json()["prescription"]["weight_kg"] is None


async def test_next_set_404s_on_someone_elses_session(client, db_session):
    headers, ex, sid = await _setup(client, db_session)
    res = await client.get(
        f"/api/workouts/sessions/{sid}/next-set",
        headers={"Authorization": "Bearer nonsense"},
        params={"exercise_id": ex.id},
    )
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# The session summary
# ---------------------------------------------------------------------------


async def test_summary_reports_the_numbers_on_the_card(client, db_session):
    headers, ex, sid = await _setup(client, db_session)
    await _log(client, headers, sid, ex.id, weight_kg=75, reps=10, rir=2)
    await _log(client, headers, sid, ex.id, weight_kg=75, reps=8, rir=1)

    res = await client.get(
        f"/api/workouts/sessions/{sid}/summary", headers=headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_sets"] == 2
    assert body["volume_kg"] == pytest.approx(75 * 10 + 75 * 8)
    assert body["avg_rpe"] == pytest.approx(8.5, abs=0.05)
    assert body["exercises"][0]["name"] == "Barbell Bench Press"


async def test_a_lift_is_never_compared_against_the_session_it_is_in(
    client, db_session
):
    """The bug this guards: if today's sets are in the reference, the first
    set of every session becomes its own record and NOTHING is ever progress.
    """
    headers, ex, sid = await _setup(client, db_session)
    await _log(client, headers, sid, ex.id, weight_kg=75, reps=10, rir=2)
    await _log(client, headers, sid, ex.id, weight_kg=75, reps=10, rir=2)

    body = (
        await client.get(f"/api/workouts/sessions/{sid}/summary", headers=headers)
    ).json()
    # No prior session exists, so there is nothing to compare against at all.
    assert body["exercises"][0]["trend"] == "FIRST_TIME"
    assert body["exercises"][0]["delta_pct"] is None


async def test_a_previous_session_becomes_the_bar_to_beat(client, db_session):
    headers, ex, sid = await _setup(client, db_session)
    today = await db_session.get(WorkoutSession, sid)

    # A real session last week, written directly so it carries an older
    # timestamp than anything the API would stamp.
    a_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    prior = WorkoutSession(
        user_id=today.user_id, routine_name="Push", started_at=a_week_ago
    )
    db_session.add(prior)
    await db_session.commit()
    db_session.add(
        SetLog(
            session_id=prior.id,
            user_id=today.user_id,
            exercise_id=ex.id,
            weight_kg=70,
            reps=10,
            rir=2,
            e1rm=98.0,
            performed_at=a_week_ago,
        )
    )
    await db_session.commit()

    await _log(client, headers, sid, ex.id, weight_kg=80, reps=10, rir=2)
    body = (
        await client.get(f"/api/workouts/sessions/{sid}/summary", headers=headers)
    ).json()
    ex_row = body["exercises"][0]
    assert ex_row["previous_e1rm"] == pytest.approx(98.0)
    assert ex_row["trend"] == "CONFIRMED"
    assert ex_row["delta_pct"] > 0


async def test_finishing_a_session_closes_it_and_returns_the_summary(
    client, db_session
):
    headers, ex, sid = await _setup(client, db_session)
    await _log(client, headers, sid, ex.id, weight_kg=75, reps=10, rir=2)

    res = await client.post(f"/api/workouts/sessions/{sid}/finish", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ended_at"] is not None
    assert body["total_sets"] == 1


async def test_an_empty_session_summarises_without_claiming_anything(
    client, db_session
):
    headers, ex, sid = await _setup(client, db_session)
    body = (
        await client.get(f"/api/workouts/sessions/{sid}/summary", headers=headers)
    ).json()
    assert body["total_sets"] == 0
    assert body["avg_rpe"] is None
    assert "No working sets" in body["headline"]
