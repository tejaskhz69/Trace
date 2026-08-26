"""Exercises are movements; stations are machines. The spec for that split.

THE ONE BEHAVIOUR EVERYTHING ELSE SCAFFOLDS
`prime row` and `hammer strength row` must both return Chest-Supported Row.
If alias search breaks, the only way for somebody to find their machine is to
give it its own catalogue row -- which splits one trend into five and pushes
`adjudication.MIN_SESSIONS = 8` forty weeks out for anybody training a lift
once a week. Everything else in this file protects that, or protects the
matching promise on the other side: that finding your machine never costs you
the continuity of your trend.

WHAT IS DELIBERATELY NOT TESTED HERE
Any conversion of load between stations, because none exists and none may be
added. There is a test at the bottom that asserts its absence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Exercise, Gym, SetLog, Station, WorkoutSession

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _register(client, email: str = "lifter@example.com") -> dict:
    res = await client.post(
        "/api/auth/register", json={"email": email, "password": "correct-horse-1"}
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _row_exercise(db_session) -> Exercise:
    """The movement from the design doc, with the aliases that matter."""
    ex = Exercise(
        name="Chest-Supported Row",
        muscle_group="back",
        secondary_muscles=["biceps", "rear delts"],
        equipment="machine",
        is_compound=True,
        aliases=[
            "hammer strength row",
            "iso lateral row",
            "hammer row",
            "prime row",
            "prime extreme row",
            "seal row",
            "h-pull",
        ],
    )
    db_session.add(ex)
    await db_session.commit()
    await db_session.refresh(ex)
    return ex


async def _station(client, headers, exercise_id: str, name: str, **kw) -> dict:
    res = await client.post(
        "/api/workouts/stations",
        headers=headers,
        json={"exercise_id": exercise_id, "name": name, **kw},
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _session_id(client, headers) -> str:
    res = await client.post(
        "/api/workouts/sessions", headers=headers, json={"routine_name": "Pull"}
    )
    return res.json()["id"]


async def _log(client, headers, sid, ex_id, **kw):
    payload = {"exercise_id": ex_id, "weight_kg": 60, "reps": 10, "rir": 2, **kw}
    res = await client.post(
        f"/api/workouts/sessions/{sid}/sets", headers=headers, json=payload
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _backdate(db_session, user_id, ex_id, *, weeks_ago, e1rm,
                    station_id=None, profile=None):
    """Write a performed set directly, so a multi-week trend can exist."""
    when = datetime.now(timezone.utc) - timedelta(weeks=weeks_ago)
    ws = WorkoutSession(user_id=user_id, started_at=when)
    db_session.add(ws)
    await db_session.commit()
    await db_session.refresh(ws)
    db_session.add(
        SetLog(
            session_id=ws.id,
            user_id=user_id,
            exercise_id=ex_id,
            weight_kg=e1rm * 0.8,
            reps=10,
            rir=2.0,
            e1rm=e1rm,
            station_id=station_id,
            station_profile=profile,
            performed_at=when,
        )
    )
    await db_session.commit()


# ---------------------------------------------------------------------------
# 1 · alias search -- the load-bearing behaviour
# ---------------------------------------------------------------------------


class TestAliasSearchFindsTheMachine:
    @pytest.mark.parametrize(
        "query",
        [
            "prime row",
            "hammer strength row",
            "PRIME ROW",
            "hammer",
            "iso lateral",
            "seal row",
        ],
    )
    async def test_brand_terms_resolve_to_the_movement(
        self, client, db_session, query
    ):
        """The exact queries from the design doc, plus their neighbours."""
        auth = await _register(client)
        ex = await _row_exercise(db_session)

        res = await client.get(
            "/api/workouts/exercises",
            headers=_headers(auth["access_token"]),
            params={"q": query},
        )
        assert res.status_code == 200, res.text
        names = [r["name"] for r in res.json()]
        assert "Chest-Supported Row" in names, f"{query!r} did not find it: {names}"

    async def test_the_movement_is_returned_once_not_per_alias(
        self, client, db_session
    ):
        """Seven aliases must not become seven search results.

        A join against the alias array instead of an EXISTS would return the
        row once per matching element, and the client would render duplicates.
        """
        auth = await _register(client)
        await _row_exercise(db_session)
        res = await client.get(
            "/api/workouts/exercises",
            headers=_headers(auth["access_token"]),
            params={"q": "row"},
        )
        names = [r["name"] for r in res.json()]
        assert names.count("Chest-Supported Row") == 1, names

    async def test_a_name_match_outranks_an_alias_match(self, client, db_session):
        """Typing a movement's own name puts it first."""
        auth = await _register(client)
        await _row_exercise(db_session)
        other = Exercise(
            name="Seated Cable Row",
            muscle_group="back",
            equipment="cable",
            aliases=["chest-supported row alternative"],
        )
        db_session.add(other)
        await db_session.commit()

        res = await client.get(
            "/api/workouts/exercises",
            headers=_headers(auth["access_token"]),
            params={"q": "Chest-Supported Row"},
        )
        assert res.json()[0]["name"] == "Chest-Supported Row"

    async def test_an_alias_does_not_match_across_element_boundaries(
        self, client, db_session
    ):
        """The reason search is an EXISTS and not a cast-to-text LIKE.

        Casting the array renders it as `["prime row", "seal row"]`. A naive
        LIKE would then let a query spanning the `", "` separator match, and
        the user would be shown a movement that contains no such alias.
        """
        auth = await _register(client)
        ex = Exercise(
            name="Pendulum Squat",
            muscle_group="quads",
            equipment="machine",
            aliases=["pendulum", "prime pendulum squat"],
        )
        db_session.add(ex)
        await db_session.commit()

        res = await client.get(
            "/api/workouts/exercises",
            headers=_headers(auth["access_token"]),
            params={"q": 'pendulum", "prime'},
        )
        assert res.json() == []

    async def test_search_still_matches_on_name_alone(self, client, db_session):
        """Aliases are additive. Name search must not have regressed."""
        auth = await _register(client)
        await _row_exercise(db_session)
        res = await client.get(
            "/api/workouts/exercises",
            headers=_headers(auth["access_token"]),
            params={"q": "chest-supported"},
        )
        assert [r["name"] for r in res.json()] == ["Chest-Supported Row"]

    async def test_no_query_returns_the_catalogue(self, client, db_session):
        auth = await _register(client)
        await _row_exercise(db_session)
        res = await client.get(
            "/api/workouts/exercises", headers=_headers(auth["access_token"])
        )
        assert res.status_code == 200
        assert len(res.json()) >= 1


# ---------------------------------------------------------------------------
# 2 · logging without a station must never be worse than logging with one
# ---------------------------------------------------------------------------


class TestStationlessLoggingKeepsWorking:
    async def test_a_set_with_no_station_is_accepted(self, client, db_session):
        """A barbell squat has no machine. This is the common case."""
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)
        sid = await _session_id(client, headers)

        body = await _log(client, headers, sid, ex.id)
        assert body["id"]

        stored = await db_session.get(SetLog, body["id"])
        assert stored is not None
        assert stored.station_id is None
        assert stored.station_profile is None

    async def test_a_stationless_set_still_produces_a_trend(
        self, client, db_session
    ):
        """The whole point of the column being nullable.

        Every set logged before stations existed has no station, and those
        histories must keep trending exactly as they did.
        """
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)
        user_id = auth["user"]["id"]

        for weeks, e1rm in ((3, 80.0), (2, 82.5), (1, 85.0)):
            await _backdate(db_session, user_id, ex.id, weeks_ago=weeks, e1rm=e1rm)

        res = await client.get(
            "/api/workouts/strength/progress",
            headers=headers,
            params={"exercise_id": ex.id},
        )
        assert res.status_code == 200, res.text
        series = res.json()
        assert len(series) == 1
        assert series[0]["station_id"] is None
        assert len(series[0]["points"]) == 3
        assert series[0]["points"][-1]["best_e1rm"] == 85.0

    async def test_the_stationless_series_is_named_not_blank(
        self, client, db_session
    ):
        """A chart legend with an anonymous line on it is a bug."""
        auth = await _register(client)
        ex = await _row_exercise(db_session)
        await _backdate(db_session, auth["user"]["id"], ex.id, weeks_ago=1, e1rm=80.0)

        res = await client.get(
            "/api/workouts/strength/progress",
            headers=_headers(auth["access_token"]),
            params={"exercise_id": ex.id},
        )
        assert res.json()[0]["station_name"] == "Not recorded"


# ---------------------------------------------------------------------------
# 3 · two stations, two trends
# ---------------------------------------------------------------------------


class TestOneMovementManyMachines:
    async def test_two_stations_produce_two_separate_trends(
        self, client, db_session
    ):
        """The heart of the design.

        Moving from the Hammer row to the PRIME row can change the plates by
        twenty kilos with no change in the lifter. Pooled into one line that
        reads as a jump or a collapse, and the strength verdict is wrong.
        """
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)
        user_id = auth["user"]["id"]

        hammer = await _station(client, headers, ex.id, "Hammer Iso-Lateral Row")
        prime = await _station(client, headers, ex.id, "PRIME Extreme Row")

        for weeks, e1rm in ((4, 70.0), (3, 72.5)):
            await _backdate(
                db_session, user_id, ex.id, weeks_ago=weeks, e1rm=e1rm,
                station_id=hammer["id"],
            )
        for weeks, e1rm in ((2, 95.0), (1, 97.5)):
            await _backdate(
                db_session, user_id, ex.id, weeks_ago=weeks, e1rm=e1rm,
                station_id=prime["id"],
            )

        res = await client.get(
            "/api/workouts/strength/progress",
            headers=headers,
            params={"exercise_id": ex.id},
        )
        series = res.json()
        assert len(series) == 2, series

        by_id = {s["station_id"]: s for s in series}
        assert set(by_id) == {hammer["id"], prime["id"]}
        assert by_id[hammer["id"]]["station_name"] == "Hammer Iso-Lateral Row"
        assert by_id[prime["id"]]["station_name"] == "PRIME Extreme Row"

        # Neither series carries the other's numbers.
        hammer_bests = [p["best_e1rm"] for p in by_id[hammer["id"]]["points"]]
        prime_bests = [p["best_e1rm"] for p in by_id[prime["id"]]["points"]]
        assert hammer_bests == [70.0, 72.5]
        assert prime_bests == [95.0, 97.5]

    async def test_a_machine_change_does_not_read_as_a_strength_change(
        self, client, db_session
    ):
        """Each series trends on its own merits.

        The 25 kg gap between the two machines appears nowhere as a delta,
        because the two are never subtracted from one another.
        """
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)
        user_id = auth["user"]["id"]

        old = await _station(client, headers, ex.id, "Old gym row")
        new = await _station(client, headers, ex.id, "New gym row")
        await _backdate(db_session, user_id, ex.id, weeks_ago=2, e1rm=70.0,
                        station_id=old["id"])
        await _backdate(db_session, user_id, ex.id, weeks_ago=1, e1rm=95.0,
                        station_id=new["id"])

        series = (
            await client.get(
                "/api/workouts/strength/progress",
                headers=headers,
                params={"exercise_id": ex.id},
            )
        ).json()
        for s in series:
            assert len(s["points"]) == 1, "a single machine's history got merged"

    async def test_a_cam_setting_segments_the_trend(self, client, db_session):
        """Same machine, same load, different setting is a different exercise.

        Setting 1 peaks mid-range, 3 at the stretch. Pooling them would
        average two different resistance profiles into one meaningless line.
        """
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)
        user_id = auth["user"]["id"]

        st = await _station(
            client, headers, ex.id, "PRIME Extreme Row",
            has_adjustable_profile=True, profile_settings=["1", "2", "3"],
        )
        await _backdate(db_session, user_id, ex.id, weeks_ago=2, e1rm=80.0,
                        station_id=st["id"], profile="1")
        await _backdate(db_session, user_id, ex.id, weeks_ago=1, e1rm=72.0,
                        station_id=st["id"], profile="3")

        series = (
            await client.get(
                "/api/workouts/strength/progress",
                headers=headers,
                params={"exercise_id": ex.id},
            )
        ).json()
        assert len(series) == 2
        profiles = sorted(s["station_profile"] for s in series)
        assert profiles == ["1", "3"]
        assert any("setting 1" in s["station_name"] for s in series)

    async def test_stationed_and_stationless_sets_do_not_contaminate(
        self, client, db_session
    ):
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)
        user_id = auth["user"]["id"]

        st = await _station(client, headers, ex.id, "The blue row machine")
        await _backdate(db_session, user_id, ex.id, weeks_ago=2, e1rm=60.0)
        await _backdate(db_session, user_id, ex.id, weeks_ago=1, e1rm=90.0,
                        station_id=st["id"])

        series = (
            await client.get(
                "/api/workouts/strength/progress",
                headers=headers,
                params={"exercise_id": ex.id},
            )
        ).json()
        assert len(series) == 2
        names = sorted(s["station_name"] for s in series)
        assert names == ["Not recorded", "The blue row machine"]


# ---------------------------------------------------------------------------
# 4 · creating and finding stations
# ---------------------------------------------------------------------------


class TestStationLifecycle:
    async def test_name_is_the_only_required_field(self, client, db_session):
        """No gym setup, ever. A name and nothing else is a valid station."""
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)

        body = await _station(client, headers, ex.id, "the blue row machine")
        assert body["name"] == "the blue row machine"
        assert body["gym_id"] is None
        assert body["loading"] is None
        assert body["stack_ranges"] == []
        assert body["is_mine"] is True

    async def test_free_text_names_are_accepted_verbatim(self, client, db_session):
        """Most machines in Indian gyms are unbranded or locally fabricated.

        A controlled brand vocabulary would exclude them entirely.
        """
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)
        body = await _station(client, headers, ex.id, "नीली रोइंग मशीन")
        assert body["name"] == "नीली रोइंग मशीन"

    async def test_a_non_uniform_stack_is_stored_as_a_list_of_ranges(
        self, client, db_session
    ):
        """5 kg steps to 25, then 10, then 15 -- on one machine.

        A single `increment` column would tell the user to load weights this
        stack does not have.
        """
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)
        body = await _station(
            client, headers, ex.id, "Pin-loaded row",
            loading="pin",
            stack_ranges=[
                {"start": 15, "end": 25, "step": 5},
                {"start": 25, "end": 55, "step": 10},
                {"start": 55, "end": 190, "step": 15},
            ],
        )
        assert len(body["stack_ranges"]) == 3
        assert body["stack_ranges"][2]["step"] == 15

    async def test_stations_are_listed_most_used_first(self, client, db_session):
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)
        sid = await _session_id(client, headers)

        rare = await _station(client, headers, ex.id, "Rarely used row")
        common = await _station(client, headers, ex.id, "Everyday row")
        for _ in range(3):
            await _log(client, headers, sid, ex.id, station_id=common["id"])

        res = await client.get(
            "/api/workouts/stations", headers=headers, params={"exercise_id": ex.id}
        )
        names = [s["name"] for s in res.json()]
        assert names[0] == "Everyday row", names
        assert rare["name"] in names

    async def test_a_public_station_is_visible_to_other_members(
        self, client, db_session
    ):
        """THE MECHANISM THAT MAKES THIS SCALE.

        Once one member names the PRIME Extreme Row, everybody who joins that
        gym later finds it already there. We are never going to maintain a
        worldwide hardware database.
        """
        first = await _register(client, "first@example.com")
        second = await _register(client, "second@example.com")
        ex = await _row_exercise(db_session)

        gym = Gym(name="Iron Yard", city="Kochi",
                  created_by_user_id=first["user"]["id"])
        db_session.add(gym)
        await db_session.commit()
        await db_session.refresh(gym)

        await _station(
            client, _headers(first["access_token"]), ex.id, "PRIME Extreme Row",
            gym_id=gym.id, is_public=True,
        )

        res = await client.get(
            "/api/workouts/stations",
            headers=_headers(second["access_token"]),
            params={"exercise_id": ex.id, "gym_id": gym.id},
        )
        found = res.json()
        assert [s["name"] for s in found] == ["PRIME Extreme Row"]
        assert found[0]["is_mine"] is False

    async def test_a_private_station_is_not_visible_to_others(
        self, client, db_session
    ):
        first = await _register(client, "first@example.com")
        second = await _register(client, "second@example.com")
        ex = await _row_exercise(db_session)

        gym = Gym(name="Iron Yard", created_by_user_id=first["user"]["id"])
        db_session.add(gym)
        await db_session.commit()
        await db_session.refresh(gym)

        await _station(
            client, _headers(first["access_token"]), ex.id, "My garage row",
            gym_id=gym.id, is_public=False,
        )

        res = await client.get(
            "/api/workouts/stations",
            headers=_headers(second["access_token"]),
            params={"exercise_id": ex.id, "gym_id": gym.id},
        )
        assert res.json() == []

    async def test_a_station_from_another_exercise_is_not_offered(
        self, client, db_session
    ):
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        row = await _row_exercise(db_session)
        press = Exercise(name="Chest Press Machine", muscle_group="chest",
                         equipment="machine", aliases=[])
        db_session.add(press)
        await db_session.commit()
        await db_session.refresh(press)

        await _station(client, headers, press.id, "Hammer chest press")
        res = await client.get(
            "/api/workouts/stations", headers=headers,
            params={"exercise_id": row.id},
        )
        assert res.json() == []

    async def test_logging_against_an_unknown_station_is_rejected(
        self, client, db_session
    ):
        """Not silently nulled.

        Dropping the reference would move the set into the "not recorded"
        series without telling anybody -- an invisible trend split, which is
        the exact failure this model exists to prevent.
        """
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)
        sid = await _session_id(client, headers)

        res = await client.post(
            f"/api/workouts/sessions/{sid}/sets",
            headers=headers,
            json={
                "exercise_id": ex.id, "weight_kg": 60, "reps": 10,
                "station_id": "does-not-exist",
            },
        )
        assert res.status_code == 422

    async def test_a_setting_the_machine_does_not_have_is_rejected(
        self, client, db_session
    ):
        auth = await _register(client)
        headers = _headers(auth["access_token"])
        ex = await _row_exercise(db_session)
        sid = await _session_id(client, headers)
        st = await _station(
            client, headers, ex.id, "PRIME Extreme Row",
            has_adjustable_profile=True, profile_settings=["1", "2", "3"],
        )

        res = await client.post(
            f"/api/workouts/sessions/{sid}/sets",
            headers=headers,
            json={
                "exercise_id": ex.id, "weight_kg": 60, "reps": 10,
                "station_id": st["id"], "station_profile": "9",
            },
        )
        assert res.status_code == 422

    async def test_creating_a_station_for_a_missing_exercise_is_404(self, client):
        auth = await _register(client)
        res = await client.post(
            "/api/workouts/stations",
            headers=_headers(auth["access_token"]),
            json={"exercise_id": "nope", "name": "Ghost machine"},
        )
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# 5 · the absence that is a feature
# ---------------------------------------------------------------------------


@pytest.mark.filterwarnings('ignore::pytest.PytestWarning')
class TestNoLoadConversion:
    def test_no_conversion_field_exists_on_the_model(self):
        """Plate leverage runs 2:1 to 5:1, unpublished, and varies through the
        range of motion. A ratio column would be invented precision wearing
        the costume of a measurement.

        This test exists so that adding one is a deliberate act with a failing
        test attached, rather than a helpful-looking afternoon commit.
        """
        columns = {c.name for c in Station.__table__.columns}
        for banned in (
            "effective_load_ratio",
            "load_ratio",
            "leverage_ratio",
            "normalised_weight",
            "normalized_weight",
            "conversion_factor",
            "equivalent_weight_kg",
        ):
            assert banned not in columns, f"Station gained {banned}"

    def test_no_conversion_helper_exists_in_the_service_layer(self):
        """No function, class or attribute anywhere converts load between
        stations.

        Checked over the AST rather than the raw text, so that *documenting*
        the ban -- which several modules do at length -- does not trip it. The
        prose is welcome; the identifier is not.
        """
        import ast
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "app"
        banned = (
            "effective_load", "load_ratio", "leverage_ratio",
            "normalise_load", "normalize_load", "normalised_weight",
            "normalized_weight", "convert_station", "station_equivalent",
            "conversion_factor",
        )
        offenders: list[str] = []
        for path in root.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:  # pragma: no cover - not our file to fix
                continue
            for node in ast.walk(tree):
                name = None
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    name = node.name
                elif isinstance(node, ast.Name):
                    name = node.id
                elif isinstance(node, ast.Attribute):
                    name = node.attr
                elif isinstance(node, ast.arg):
                    name = node.arg
                if not name:
                    continue
                lowered = name.lower()
                for needle in banned:
                    if needle in lowered:
                        offenders.append(f"{path.name}:{name}")
        assert not offenders, offenders
