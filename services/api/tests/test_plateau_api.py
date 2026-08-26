"""`GET /api/workouts/plateau` -- the read-only half of the contract.

The detector's logic is specced in `test_plateau.py`. This file covers the
three things only the endpoint can get wrong: that it writes nothing, that it
segments by station the same way `/strength/progress` does, and that it stays
quiet while the adjudication engine has nothing to say.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Exercise, SetLog, Station, WorkoutSession
from app.services.adjudication import MIN_SESSIONS

pytestmark = pytest.mark.asyncio


async def _register(client, email: str = "plateau@example.com") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "password": "correct-horse-1"}
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _exercise(db_session) -> Exercise:
    ex = Exercise(
        name="Chest-Supported Row",
        muscle_group="back",
        equipment="machine",
        is_compound=True,
        aliases=["prime row"],
    )
    db_session.add(ex)
    await db_session.commit()
    await db_session.refresh(ex)
    return ex


async def _station(db_session, exercise_id: str, user_id: str, name: str) -> Station:
    st = Station(
        name=name,
        exercise_id=exercise_id,
        created_by_user_id=user_id,
        loading="plate",
    )
    db_session.add(st)
    await db_session.commit()
    await db_session.refresh(st)
    return st


async def _log(
    db_session,
    *,
    user_id: str,
    exercise_id: str,
    days_ago: int,
    weight: float = 60.0,
    reps: int = 8,
    e1rm: float | None = None,
    station_id: str | None = None,
    profile: str | None = None,
) -> None:
    """One session with one working set."""
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    sess = WorkoutSession(user_id=user_id, started_at=when, ended_at=when)
    db_session.add(sess)
    await db_session.commit()
    db_session.add(
        SetLog(
            session_id=sess.id,
            user_id=user_id,
            exercise_id=exercise_id,
            weight_kg=weight,
            reps=reps,
            e1rm=e1rm if e1rm is not None else round(weight * (1 + reps / 30), 1),
            station_id=station_id,
            station_profile=profile,
            performed_at=when,
        )
    )
    await db_session.commit()


class TestSuppressedUntilAdjudicationCanSpeak:
    async def test_thin_history_returns_insufficient_data(self, client, db_session):
        reg = await _register(client)
        ex = await _exercise(db_session)
        for i in range(3):
            await _log(
                db_session,
                user_id=reg["user"]["id"],
                exercise_id=ex.id,
                days_ago=i * 10,
            )

        res = await client.get(
            "/api/workouts/plateau",
            params={"exercise_id": ex.id},
            headers=_headers(reg["access_token"]),
        )
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "insufficient_data"

    async def test_no_history_at_all_is_still_a_clean_200(self, client, db_session):
        """An empty answer is a real answer here, not a 404."""
        reg = await _register(client, "empty@example.com")
        ex = await _exercise(db_session)

        res = await client.get(
            "/api/workouts/plateau",
            params={"exercise_id": ex.id},
            headers=_headers(reg["access_token"]),
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "insufficient_data"
        assert body["evidence_sessions"] == []
        assert body["stalled_metric"] is None

    async def test_unknown_exercise_is_a_404(self, client, db_session):
        reg = await _register(client, "unknown@example.com")
        res = await client.get(
            "/api/workouts/plateau",
            params={"exercise_id": "no-such-exercise"},
            headers=_headers(reg["access_token"]),
        )
        assert res.status_code == 404

    async def test_requires_auth(self, client, db_session):
        ex = await _exercise(db_session)
        res = await client.get(
            "/api/workouts/plateau", params={"exercise_id": ex.id}
        )
        assert res.status_code in (401, 403)


class TestItReadsAndNeverWrites:
    async def test_the_endpoint_creates_no_rows(self, client, db_session):
        """No plateau-event table in phase one, and no side effects at all.
        An assessment endpoint that mutates is one nobody can safely poll."""
        from sqlalchemy import func, select

        reg = await _register(client, "readonly@example.com")
        ex = await _exercise(db_session)
        for i in range(MIN_SESSIONS + 2):
            await _log(
                db_session,
                user_id=reg["user"]["id"],
                exercise_id=ex.id,
                days_ago=i * 7,
            )

        async def counts() -> tuple[int, int]:
            sets = await db_session.scalar(select(func.count(SetLog.id)))
            sessions = await db_session.scalar(
                select(func.count(WorkoutSession.id))
            )
            return sets, sessions

        before = await counts()
        for _ in range(3):
            res = await client.get(
                "/api/workouts/plateau",
                params={"exercise_id": ex.id},
                headers=_headers(reg["access_token"]),
            )
            assert res.status_code == 200
        assert await counts() == before

    async def test_repeated_calls_return_the_same_assessment(
        self, client, db_session
    ):
        reg = await _register(client, "stable@example.com")
        ex = await _exercise(db_session)
        for i in range(MIN_SESSIONS + 2):
            await _log(
                db_session,
                user_id=reg["user"]["id"],
                exercise_id=ex.id,
                days_ago=i * 7,
            )

        seen = set()
        for _ in range(5):
            res = await client.get(
                "/api/workouts/plateau",
                params={"exercise_id": ex.id},
                headers=_headers(reg["access_token"]),
            )
            body = res.json()
            seen.add((body["status"], body["reason"], body["confidence"]))
        assert len(seen) == 1


class TestSegmentation:
    async def test_a_flat_lift_on_one_machine_is_called(self, client, db_session):
        reg = await _register(client, "flat@example.com")
        ex = await _exercise(db_session)
        st = await _station(db_session, ex.id, reg["user"]["id"], "the blue row machine")
        for i in range(MIN_SESSIONS + 2):
            await _log(
                db_session,
                user_id=reg["user"]["id"],
                exercise_id=ex.id,
                days_ago=i * 7,
                station_id=st.id,
            )

        body = (
            await client.get(
                "/api/workouts/plateau",
                params={"exercise_id": ex.id},
                headers=_headers(reg["access_token"]),
            )
        ).json()
        assert body["status"] in ("watch", "confirmed_plateau", "persistent_plateau")
        assert body["station_name"] == "the blue row machine"
        assert "blue row machine" in body["reason"]
        assert len(body["evidence_sessions"]) >= 3

    async def test_changing_machine_is_reported_not_asked(
        self, client, db_session
    ):
        """The user is never asked whether the equipment was the same --
        SetLog already knows."""
        reg = await _register(client, "moved@example.com")
        ex = await _exercise(db_session)
        old = await _station(db_session, ex.id, reg["user"]["id"], "the Hammer row")
        new = await _station(db_session, ex.id, reg["user"]["id"], "the PRIME row")

        for i in range(MIN_SESSIONS):
            await _log(
                db_session,
                user_id=reg["user"]["id"],
                exercise_id=ex.id,
                days_ago=30 + i * 7,
                station_id=old.id,
            )
        for days in (0, 4):
            await _log(
                db_session,
                user_id=reg["user"]["id"],
                exercise_id=ex.id,
                days_ago=days,
                station_id=new.id,
            )

        body = (
            await client.get(
                "/api/workouts/plateau",
                params={"exercise_id": ex.id},
                headers=_headers(reg["access_token"]),
            )
        ).json()
        assert body["status"] == "not_comparable"
        assert "Hammer row" in body["reason"] and "PRIME row" in body["reason"]
        assert body["requires_confirmation"] is False

    async def test_station_less_sets_are_a_named_series(self, client, db_session):
        """"I didn't record the machine" is permanent and legitimate."""
        reg = await _register(client, "nostation@example.com")
        ex = await _exercise(db_session)
        for i in range(MIN_SESSIONS + 2):
            await _log(
                db_session,
                user_id=reg["user"]["id"],
                exercise_id=ex.id,
                days_ago=i * 7,
            )

        body = (
            await client.get(
                "/api/workouts/plateau",
                params={"exercise_id": ex.id},
                headers=_headers(reg["access_token"]),
            )
        ).json()
        assert body["station_name"] == "Not recorded"
        assert body["station_id"] is None

    async def test_rising_load_is_progressing_not_plateau(
        self, client, db_session
    ):
        reg = await _register(client, "rising@example.com")
        ex = await _exercise(db_session)
        st = await _station(db_session, ex.id, reg["user"]["id"], "the row machine")
        for i in range(MIN_SESSIONS + 2):
            await _log(
                db_session,
                user_id=reg["user"]["id"],
                exercise_id=ex.id,
                days_ago=(MIN_SESSIONS + 1 - i) * 7,
                weight=50.0 + i * 2.5,
                station_id=st.id,
            )

        body = (
            await client.get(
                "/api/workouts/plateau",
                params={"exercise_id": ex.id},
                headers=_headers(reg["access_token"]),
            )
        ).json()
        assert body["status"] == "progressing"
        assert "estimated 1RM" in body["improving_metrics"]


class TestNoCrossStationConversion:
    async def test_the_response_carries_no_normalised_load(
        self, client, db_session
    ):
        """There is no comparable-load field, no ratio, and no combined
        number across machines -- and there must never be one."""
        reg = await _register(client, "noconv@example.com")
        ex = await _exercise(db_session)
        st = await _station(db_session, ex.id, reg["user"]["id"], "the row machine")
        for i in range(MIN_SESSIONS + 2):
            await _log(
                db_session,
                user_id=reg["user"]["id"],
                exercise_id=ex.id,
                days_ago=i * 7,
                station_id=st.id,
            )

        body = (
            await client.get(
                "/api/workouts/plateau",
                params={"exercise_id": ex.id},
                headers=_headers(reg["access_token"]),
            )
        ).json()
        banned = ("ratio", "normalis", "normaliz", "equivalent_load", "converted")
        blob = str(body).lower()
        for word in banned:
            assert word not in blob, word
