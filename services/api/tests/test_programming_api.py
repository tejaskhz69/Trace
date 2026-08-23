"""The programming HTTP surface, against the dedicated trace_test database.

Two groups matter more than the rest.

TestOwnership is the security surface. A programme, a planned session and a
prescription are all reachable by id, and every one of them must be invisible
to anyone but its owner -- returning 404 rather than 403, because a 403
confirms the row exists.

TestPerformedHistory is the data-integrity surface. Programming may create a
WorkoutSession and link to it. It may never modify or replace one, and it may
never stand between a user and the existing set-logging flow.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models import Exercise, ExerciseAttributes, ExerciseSubstitution


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register(client, label="Lifter") -> dict:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": f"prog-{uuid.uuid4().hex[:12]}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": label,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _hdr(auth: dict) -> dict:
    return {"Authorization": f"Bearer {auth['access_token']}"}


#: (id, name, equipment, muscle, pattern, class, rep_min, rep_max, rest)
_CATALOGUE = [
    ("goblet-squat", "Goblet squat", "dumbbell", "quads", "squat", "compound", 6, 10, 120),
    ("db-rdl", "Dumbbell RDL", "dumbbell", "hamstrings", "hinge", "compound", 8, 12, 120),
    ("db-bench", "Dumbbell bench press", "dumbbell", "chest", "push_horizontal", "compound", 6, 10, 120),
    ("db-row", "Dumbbell row", "dumbbell", "back", "pull_horizontal", "compound", 8, 12, 90),
    ("db-press", "Dumbbell shoulder press", "dumbbell", "shoulders", "push_vertical", "compound", 6, 10, 120),
    ("pull-up", "Pull-up", "bodyweight", "back", "pull_vertical", "compound", 4, 8, 150),
    ("push-up", "Push-up", "bodyweight", "chest", "push_horizontal", "compound", 8, 15, 90),
    ("farmer-carry", "Farmer carry", "dumbbell", "traps", "carry", "compound", 1, 3, 90),
    ("db-curl", "Dumbbell curl", "dumbbell", "biceps", "isolation", "isolation", 10, 15, 60),
    ("bb-squat", "Barbell squat", "barbell", "quads", "squat", "compound", 5, 8, 180),
]


async def _seed_catalogue(db_session) -> None:
    """A small classified catalogue plus one substitution edge.

    `bb-squat` is deliberately included and deliberately barbell: it is what
    proves a beginner is not handed a barbell just because the catalogue has
    one.
    """
    for ex_id, name, equip, muscle, pattern, klass, rmin, rmax, rest in _CATALOGUE:
        db_session.add(
            Exercise(
                id=ex_id,
                name=name,
                muscle_group=muscle,
                secondary_muscles=["core"],
                equipment=equip,
                is_compound=klass == "compound",
            )
        )
        db_session.add(
            ExerciseAttributes(
                exercise_id=ex_id,
                movement_pattern=pattern,
                exercise_class=klass,
                default_rep_min=rmin,
                default_rep_max=rmax,
                default_rest_seconds=rest,
                fatigue_cost=3,
            )
        )
    db_session.add(
        ExerciseSubstitution(
            from_exercise_id="db-bench",
            to_exercise_id="push-up",
            reason="equipment",
            rank=1,
        )
    )
    await db_session.commit()


async def _profile(client, auth, **over) -> dict:
    body = {"days_per_week": 3, "preferred_minutes": 60}
    body.update(over)
    res = await client.post("/api/workouts/training-profile", json=body, headers=_hdr(auth))
    assert res.status_code == 201, res.text
    return res.json()


async def _programme(client, auth) -> dict:
    res = await client.post("/api/workouts/programmes", json={}, headers=_hdr(auth))
    assert res.status_code == 201, res.text
    return res.json()


async def _planned(client, auth, **body) -> dict:
    res = await client.post(
        "/api/workouts/planned-sessions", json=body, headers=_hdr(auth)
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/api/workouts/training-profile"),
            ("post", "/api/workouts/training-profile"),
            ("patch", "/api/workouts/training-profile"),
            ("post", "/api/workouts/programmes"),
            ("get", "/api/workouts/programmes/active"),
            ("post", "/api/workouts/programmes/x/archive"),
            ("get", "/api/workouts/programmes/x/days"),
            ("post", "/api/workouts/planned-sessions"),
            ("get", "/api/workouts/planned-sessions/x"),
            ("post", "/api/workouts/planned-sessions/x/start"),
            ("patch", "/api/workouts/prescribed-exercises/x"),
        ],
    )
    async def test_every_endpoint_requires_a_token(self, client, method, path):
        # httpx's get() takes no json kwarg, and a GET body would be ignored
        # anyway -- what is under test is the absence of a token.
        kwargs = {} if method == "get" else {"json": {}}
        res = await getattr(client, method)(path, **kwargs)
        assert res.status_code == 401, f"{method} {path} -> {res.status_code}"


# ---------------------------------------------------------------------------
# Training profile
# ---------------------------------------------------------------------------


class TestTrainingProfile:
    async def test_absent_before_it_is_created(self, client):
        auth = await _register(client)
        res = await client.get("/api/workouts/training-profile", headers=_hdr(auth))
        assert res.status_code == 404

    async def test_create_then_read(self, client):
        auth = await _register(client)
        created = await _profile(client, auth, days_per_week=4, preferred_minutes=45)
        res = await client.get("/api/workouts/training-profile", headers=_hdr(auth))
        assert res.status_code == 200
        assert res.json()["id"] == created["id"]
        assert res.json()["days_per_week"] == 4
        assert res.json()["preferred_minutes"] == 45

    async def test_a_second_create_is_refused(self, client):
        """uq_training_profile_user, surfaced as a 409 rather than a 500."""
        auth = await _register(client)
        await _profile(client, auth)
        res = await client.post(
            "/api/workouts/training-profile", json={}, headers=_hdr(auth)
        )
        assert res.status_code == 409

    async def test_patch_changes_only_what_was_sent(self, client):
        """The property that makes this a real PATCH. Without exclude_unset
        every partial update would silently reset the fields it omitted."""
        auth = await _register(client)
        await _profile(client, auth, days_per_week=3, preferred_minutes=60,
                       equipment=["dumbbell"])
        res = await client.patch(
            "/api/workouts/training-profile",
            json={"days_per_week": 5},
            headers=_hdr(auth),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["days_per_week"] == 5
        assert body["preferred_minutes"] == 60
        assert body["equipment"] == ["dumbbell"]

    async def test_patch_can_clear_limitations(self, client):
        auth = await _register(client)
        await _profile(client, auth, limitations="sore left wrist")
        res = await client.patch(
            "/api/workouts/training-profile",
            json={"limitations": None},
            headers=_hdr(auth),
        )
        assert res.status_code == 200
        assert res.json()["limitations"] is None

    async def test_patch_before_create_is_404(self, client):
        auth = await _register(client)
        res = await client.patch(
            "/api/workouts/training-profile", json={"days_per_week": 4},
            headers=_hdr(auth),
        )
        assert res.status_code == 404

    @pytest.mark.parametrize(
        "body",
        [
            {"days_per_week": 0},
            {"days_per_week": 8},
            {"preferred_minutes": 5},
            {"preferred_minutes": 500},
        ],
    )
    async def test_invalid_input_is_rejected_before_the_database(self, client, body):
        auth = await _register(client)
        res = await client.post(
            "/api/workouts/training-profile", json=body, headers=_hdr(auth)
        )
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# Programme generation
# ---------------------------------------------------------------------------


class TestProgrammeGeneration:
    async def test_generates_a_full_body_split_for_three_days(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth, days_per_week=3)
        prog = await _programme(client, auth)
        assert prog["split_type"] == "full_body"
        assert prog["days_per_week"] == 3
        assert len(prog["days"]) == 3
        assert [d["day_index"] for d in prog["days"]] == [0, 1, 2]

    async def test_generates_upper_lower_for_four_days(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth, days_per_week=4)
        prog = await _programme(client, auth)
        assert prog["split_type"] == "upper_lower"
        assert len(prog["days"]) == 4

    async def test_the_request_body_can_override_the_profile(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth, days_per_week=3)
        res = await client.post(
            "/api/workouts/programmes", json={"days_per_week": 5}, headers=_hdr(auth)
        )
        assert res.status_code == 201
        assert res.json()["days_per_week"] == 5

    async def test_requires_a_profile_first(self, client):
        auth = await _register(client)
        res = await client.post("/api/workouts/programmes", json={}, headers=_hdr(auth))
        assert res.status_code == 404

    async def test_active_programme_is_readable(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        created = await _programme(client, auth)
        res = await client.get("/api/workouts/programmes/active", headers=_hdr(auth))
        assert res.status_code == 200
        assert res.json()["id"] == created["id"]

    async def test_no_active_programme_is_404_not_an_empty_object(self, client):
        auth = await _register(client)
        await _profile(client, auth)
        res = await client.get("/api/workouts/programmes/active", headers=_hdr(auth))
        assert res.status_code == 404

    async def test_days_endpoint_is_ordered(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth, days_per_week=4)
        prog = await _programme(client, auth)
        res = await client.get(
            f"/api/workouts/programmes/{prog['id']}/days", headers=_hdr(auth)
        )
        assert res.status_code == 200
        assert [d["day_index"] for d in res.json()] == [0, 1, 2, 3]


class TestOneActiveProgramme:
    async def test_generating_a_second_archives_the_first(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        first = await _programme(client, auth)
        second = await _programme(client, auth)
        assert first["id"] != second["id"]

        active = await client.get("/api/workouts/programmes/active", headers=_hdr(auth))
        assert active.json()["id"] == second["id"]

    async def test_the_archived_programme_still_exists(self, client, db_session):
        """Archive, never delete: it is the explanation for every session
        beneath it."""
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        first = await _programme(client, auth)
        await _programme(client, auth)
        res = await client.get(
            f"/api/workouts/programmes/{first['id']}/days", headers=_hdr(auth)
        )
        assert res.status_code == 200

    async def test_explicit_archive_clears_the_active_slot(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        prog = await _programme(client, auth)
        res = await client.post(
            f"/api/workouts/programmes/{prog['id']}/archive", headers=_hdr(auth)
        )
        assert res.status_code == 200
        assert res.json()["status"] == "archived"
        assert res.json()["archived_at"] is not None
        after = await client.get("/api/workouts/programmes/active", headers=_hdr(auth))
        assert after.status_code == 404

    async def test_archiving_twice_is_a_no_op_not_an_error(self, client, db_session):
        """A retried request should not fail."""
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        prog = await _programme(client, auth)
        first = await client.post(
            f"/api/workouts/programmes/{prog['id']}/archive", headers=_hdr(auth)
        )
        second = await client.post(
            f"/api/workouts/programmes/{prog['id']}/archive", headers=_hdr(auth)
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["archived_at"] == second.json()["archived_at"]

    async def test_two_users_may_each_have_an_active_programme(self, client, db_session):
        """The constraint scopes per user, not globally."""
        await _seed_catalogue(db_session)
        a, b = await _register(client, "A"), await _register(client, "B")
        for auth in (a, b):
            await _profile(client, auth)
            await _programme(client, auth)
        for auth in (a, b):
            res = await client.get("/api/workouts/programmes/active", headers=_hdr(auth))
            assert res.status_code == 200


# ---------------------------------------------------------------------------
# Beginner selection
# ---------------------------------------------------------------------------


class TestBeginnerSelection:
    async def test_a_new_user_is_never_prescribed_a_barbell(self, client, db_session):
        """THE BEGINNER-SAFETY TEST. `bb-squat` is in the catalogue and is the
        best squat by every other measure. A new lifter must still not get it."""
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        planned = await _planned(client, auth)
        equipment = {e["equipment"] for e in planned["exercises"]}
        assert equipment <= {"bodyweight", "dumbbell"}, equipment
        assert "bb-squat" not in {e["exercise_id"] for e in planned["exercises"]}

    async def test_every_prescription_is_conservative(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        planned = await _planned(client, auth)
        assert planned["exercises"]
        for ex in planned["exercises"]:
            assert ex["target_rir"] == 3
            assert 2 <= ex["sets"] <= 3
            assert ex["rep_min"] <= ex["rep_max"]
            assert ex["progression_rule"] == "double_progression"

    async def test_no_weight_is_suggested_without_history(self, client, db_session):
        """No logged sets means no basis for a number. An em dash, not a guess."""
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        planned = await _planned(client, auth)
        assert all(e["suggested_weight_kg"] is None for e in planned["exercises"])

    async def test_education_metadata_is_present_where_the_catalogue_has_it(
        self, client, db_session
    ):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        planned = await _planned(client, auth)
        for ex in planned["exercises"]:
            edu = ex["education"]
            assert edu is not None
            assert edu["primary_muscle"]
            assert edu["movement_pattern"]
            assert edu["form_cue"]
            low = edu["form_cue"].lower()
            for banned in ("injur", "pain", "doctor", "medical", "diagnos"):
                assert banned not in low

    async def test_disliked_exercises_are_not_prescribed(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth, disliked_exercise_ids=["goblet-squat"])
        await _programme(client, auth)
        planned = await _planned(client, auth)
        assert "goblet-squat" not in {e["exercise_id"] for e in planned["exercises"]}

    async def test_an_unclassified_catalogue_refuses_rather_than_guessing(
        self, client, db_session
    ):
        """An exercise with no attributes row is not classified, so it is not
        prescribable. With none classified at all, the honest answer is 422."""
        db_session.add(
            Exercise(id="mystery", name="Mystery lift", muscle_group="quads",
                     equipment="dumbbell", is_compound=True)
        )
        await db_session.commit()
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        res = await client.post(
            "/api/workouts/planned-sessions", json={}, headers=_hdr(auth)
        )
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# Planned sessions
# ---------------------------------------------------------------------------


class TestPlannedSessions:
    async def test_materialisation_creates_a_session_with_prescriptions(
        self, client, db_session
    ):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        res = await client.post(
            "/api/workouts/planned-sessions", json={}, headers=_hdr(auth)
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["exercises"]
        assert body["status"] == "planned"
        assert body["generated_by"] == "template"
        assert body["notes"]
        assert body["programme_day_label"]

    async def test_ordering_is_dense_and_deterministic(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        planned = await _planned(client, auth)
        indices = [e["order_index"] for e in planned["exercises"]]
        assert indices == sorted(indices) == list(range(len(indices)))

    async def test_repeated_materialisation_is_idempotent(self, client, db_session):
        """A double-tap or a retry must not produce two plans for one day."""
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        first = await client.post(
            "/api/workouts/planned-sessions", json={"scheduled_for": "2026-09-01"},
            headers=_hdr(auth),
        )
        second = await client.post(
            "/api/workouts/planned-sessions", json={"scheduled_for": "2026-09-01"},
            headers=_hdr(auth),
        )
        assert first.status_code == 201
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]

    async def test_the_rotation_advances_across_days(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth, days_per_week=4)
        await _programme(client, auth)
        labels = []
        for day in ("2026-09-01", "2026-09-02", "2026-09-03"):
            planned = await _planned(client, auth, scheduled_for=day)
            labels.append(planned["programme_day_label"])
        assert labels[0] != labels[1]

    async def test_an_explicit_day_can_be_requested(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth, days_per_week=4)
        prog = await _programme(client, auth)
        target = prog["days"][2]
        planned = await _planned(
            client, auth, scheduled_for="2026-09-05", programme_day_id=target["id"]
        )
        assert planned["programme_day_id"] == target["id"]
        assert planned["programme_day_label"] == target["label"]

    async def test_requires_an_active_programme(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        res = await client.post(
            "/api/workouts/planned-sessions", json={}, headers=_hdr(auth)
        )
        assert res.status_code == 404

    async def test_retrieval_by_id(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        planned = await _planned(client, auth, scheduled_for="2026-09-01")
        one = await client.get(
            f"/api/workouts/planned-sessions/{planned['id']}", headers=_hdr(auth)
        )
        assert one.status_code == 200
        assert one.json()["id"] == planned["id"]

    async def test_a_missing_session_is_404(self, client):
        auth = await _register(client)
        res = await client.get(
            "/api/workouts/planned-sessions/does-not-exist", headers=_hdr(auth)
        )
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Prescribed exercises
# ---------------------------------------------------------------------------


class TestPrescribedExercise:
    async def _one(self, client, db_session, exercise_id=None):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        planned = await _planned(client, auth)
        chosen = planned["exercises"][0]
        if exercise_id:
            chosen = next(
                (e for e in planned["exercises"] if e["exercise_id"] == exercise_id),
                chosen,
            )
        return auth, planned, chosen

    async def test_skip_sets_a_status_and_keeps_the_row(self, client, db_session):
        """What was prescribed and declined is exactly the signal the deferred
        preference learning will need. Deleting it throws that away."""
        auth, planned, ex = await self._one(client, db_session)
        res = await client.patch(
            f"/api/workouts/prescribed-exercises/{ex['id']}",
            json={"status": "skipped"},
            headers=_hdr(auth),
        )
        assert res.status_code == 200
        assert res.json()["status"] == "skipped"
        again = await client.get(
            f"/api/workouts/planned-sessions/{planned['id']}", headers=_hdr(auth)
        )
        assert len(again.json()["exercises"]) == len(planned["exercises"])

    async def test_an_offered_substitution_is_accepted(self, client, db_session):
        auth, _planned, ex = await self._one(client, db_session, "db-bench")
        if ex["exercise_id"] != "db-bench":
            pytest.skip("db-bench was not selected for this day")
        res = await client.patch(
            f"/api/workouts/prescribed-exercises/{ex['id']}",
            json={"status": "replaced", "replaced_with_exercise_id": "push-up"},
            headers=_hdr(auth),
        )
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "replaced"
        assert res.json()["replaced_with_exercise_id"] == "push-up"

    async def test_an_arbitrary_substitution_is_refused(self, client, db_session):
        """The substitution list is the reviewed set. Accepting anything else
        would let a client write a prescription nobody checked."""
        auth, _planned, ex = await self._one(client, db_session)
        res = await client.patch(
            f"/api/workouts/prescribed-exercises/{ex['id']}",
            json={"status": "replaced", "replaced_with_exercise_id": "bb-squat"},
            headers=_hdr(auth),
        )
        assert res.status_code == 422

    async def test_an_unknown_exercise_id_is_refused(self, client, db_session):
        auth, _planned, ex = await self._one(client, db_session)
        res = await client.patch(
            f"/api/workouts/prescribed-exercises/{ex['id']}",
            json={"status": "replaced", "replaced_with_exercise_id": "not-an-exercise"},
            headers=_hdr(auth),
        )
        assert res.status_code == 422

    async def test_replacing_without_a_target_is_refused(self, client, db_session):
        auth, _planned, ex = await self._one(client, db_session)
        res = await client.patch(
            f"/api/workouts/prescribed-exercises/{ex['id']}",
            json={"status": "replaced"},
            headers=_hdr(auth),
        )
        assert res.status_code == 422

    async def test_an_invalid_status_is_refused(self, client, db_session):
        auth, _planned, ex = await self._one(client, db_session)
        res = await client.patch(
            f"/api/workouts/prescribed-exercises/{ex['id']}",
            json={"status": "obliterated"},
            headers=_hdr(auth),
        )
        assert res.status_code == 422

    async def test_a_skip_can_be_undone(self, client, db_session):
        auth, _planned, ex = await self._one(client, db_session)
        await client.patch(
            f"/api/workouts/prescribed-exercises/{ex['id']}",
            json={"status": "skipped"}, headers=_hdr(auth),
        )
        res = await client.patch(
            f"/api/workouts/prescribed-exercises/{ex['id']}",
            json={"status": "prescribed"}, headers=_hdr(auth),
        )
        assert res.status_code == 200
        assert res.json()["status"] == "prescribed"
        assert res.json()["replaced_with_exercise_id"] is None

    async def test_a_missing_prescription_is_404(self, client):
        auth = await _register(client)
        res = await client.patch(
            "/api/workouts/prescribed-exercises/nope",
            json={"status": "skipped"}, headers=_hdr(auth),
        )
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Starting a session, and the handoff
# ---------------------------------------------------------------------------


class TestStartAndHandoff:
    async def _started(self, client, db_session):
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        planned = await _planned(client, auth)
        res = await client.post(
            f"/api/workouts/planned-sessions/{planned['id']}/start", headers=_hdr(auth)
        )
        assert res.status_code == 201, res.text
        return auth, planned, res.json()

    async def test_starting_creates_and_links_a_workout_session(
        self, client, db_session
    ):
        auth, planned, start = await self._started(client, db_session)
        assert start["created"] is True
        assert start["session_id"]
        again = await client.get(
            f"/api/workouts/planned-sessions/{planned['id']}", headers=_hdr(auth)
        )
        assert again.json()["session_id"] == start["session_id"]
        assert again.json()["status"] == "active"

    async def test_starting_twice_returns_the_same_session(self, client, db_session):
        """A retry is not new evidence that a second workout happened."""
        auth, planned, first = await self._started(client, db_session)
        second = await client.post(
            f"/api/workouts/planned-sessions/{planned['id']}/start", headers=_hdr(auth)
        )
        assert second.status_code == 200
        assert second.json()["created"] is False
        assert second.json()["session_id"] == first["session_id"]

    async def test_the_returned_session_accepts_sets_from_the_existing_endpoint(
        self, client, db_session
    ):
        """THE HANDOFF. Programming stops at the door of the logging flow that
        already exists -- it does not wrap, proxy or re-implement it."""
        auth, _planned, start = await self._started(client, db_session)
        res = await client.post(
            f"/api/workouts/sessions/{start['session_id']}/sets",
            json={"exercise_id": "goblet-squat", "weight_kg": 20, "reps": 8, "rir": 3},
            headers=_hdr(auth),
        )
        assert res.status_code == 201, res.text

    async def test_starting_a_session_you_do_not_own_is_404(self, client, db_session):
        _auth, planned, _start = await self._started(client, db_session)
        intruder = await _register(client, "Intruder")
        res = await client.post(
            f"/api/workouts/planned-sessions/{planned['id']}/start",
            headers=_hdr(intruder),
        )
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Performed history is never modified
# ---------------------------------------------------------------------------


class TestPerformedHistory:
    async def test_manual_logging_works_with_no_programme_at_all(
        self, client, db_session
    ):
        """Generated programming is offered, never required. A user with no
        profile, no programme and no planned session logs exactly as before."""
        await _seed_catalogue(db_session)
        auth = await _register(client)
        created = await client.post(
            "/api/workouts/sessions", json={"routine_name": "Whatever I feel like"},
            headers=_hdr(auth),
        )
        assert created.status_code == 201, created.text
        session_id = created.json()["id"]
        logged = await client.post(
            f"/api/workouts/sessions/{session_id}/sets",
            json={"exercise_id": "goblet-squat", "weight_kg": 30, "reps": 10},
            headers=_hdr(auth),
        )
        assert logged.status_code == 201, logged.text

        profile = await client.get("/api/workouts/training-profile", headers=_hdr(auth))
        assert profile.status_code == 404  # still no profile, and that is fine

    async def test_starting_again_does_not_disturb_logged_sets(
        self, client, db_session
    ):
        """Programming may create a WorkoutSession and link to it. It may
        never modify or replace one."""
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        planned = await _planned(client, auth)
        start = await client.post(
            f"/api/workouts/planned-sessions/{planned['id']}/start", headers=_hdr(auth)
        )
        session_id = start.json()["session_id"]
        await client.post(
            f"/api/workouts/sessions/{session_id}/sets",
            json={"exercise_id": "goblet-squat", "weight_kg": 40, "reps": 6, "rir": 2},
            headers=_hdr(auth),
        )
        before = await client.get(
            f"/api/workouts/sessions/{session_id}/summary", headers=_hdr(auth)
        )
        await client.post(
            f"/api/workouts/planned-sessions/{planned['id']}/start", headers=_hdr(auth)
        )
        after = await client.get(
            f"/api/workouts/sessions/{session_id}/summary", headers=_hdr(auth)
        )
        assert before.status_code == after.status_code == 200
        assert before.json() == after.json()

    async def test_a_prescription_and_a_performed_set_stay_separate(
        self, client, db_session
    ):
        """Logging a heavier set than prescribed changes the record of what
        happened, never the record of what was asked for."""
        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        planned = await _planned(client, auth)
        target = planned["exercises"][0]
        start = await client.post(
            f"/api/workouts/planned-sessions/{planned['id']}/start", headers=_hdr(auth)
        )
        await client.post(
            f"/api/workouts/sessions/{start.json()['session_id']}/sets",
            json={
                "exercise_id": target["exercise_id"],
                "weight_kg": 100,
                "reps": target["rep_max"] + 5,
            },
            headers=_hdr(auth),
        )
        again = await client.get(
            f"/api/workouts/planned-sessions/{planned['id']}", headers=_hdr(auth)
        )
        unchanged = next(
            e for e in again.json()["exercises"] if e["id"] == target["id"]
        )
        assert unchanged["rep_max"] == target["rep_max"]
        assert unchanged["sets"] == target["sets"]
        assert unchanged["suggested_weight_kg"] is None


# ---------------------------------------------------------------------------
# Ownership isolation
# ---------------------------------------------------------------------------


class TestOwnership:
    async def _two_users(self, client, db_session):
        await _seed_catalogue(db_session)
        owner = await _register(client, "Owner")
        intruder = await _register(client, "Intruder")
        await _profile(client, owner)
        prog = await _programme(client, owner)
        planned = await _planned(client, owner)
        return owner, intruder, prog, planned

    async def test_another_users_programme_days_are_invisible(self, client, db_session):
        _owner, intruder, prog, _planned = await self._two_users(client, db_session)
        res = await client.get(
            f"/api/workouts/programmes/{prog['id']}/days", headers=_hdr(intruder)
        )
        assert res.status_code == 404

    async def test_another_users_programme_cannot_be_archived(self, client, db_session):
        _owner, intruder, prog, _planned = await self._two_users(client, db_session)
        res = await client.post(
            f"/api/workouts/programmes/{prog['id']}/archive", headers=_hdr(intruder)
        )
        assert res.status_code == 404

    async def test_another_users_planned_session_is_invisible(self, client, db_session):
        _owner, intruder, _prog, planned = await self._two_users(client, db_session)
        res = await client.get(
            f"/api/workouts/planned-sessions/{planned['id']}", headers=_hdr(intruder)
        )
        assert res.status_code == 404

    async def test_another_users_prescription_cannot_be_patched(
        self, client, db_session
    ):
        _owner, intruder, _prog, planned = await self._two_users(client, db_session)
        target = planned["exercises"][0]
        res = await client.patch(
            f"/api/workouts/prescribed-exercises/{target['id']}",
            json={"status": "skipped"}, headers=_hdr(intruder),
        )
        assert res.status_code == 404

    async def test_materialising_never_returns_another_users_session(
        self, client, db_session
    ):
        """The intruder has no programme, so they get 404 -- not the owner's
        session for the same date."""
        _owner, intruder, _prog, _planned = await self._two_users(client, db_session)
        await _profile(client, intruder)
        res = await client.post(
            "/api/workouts/planned-sessions", json={}, headers=_hdr(intruder)
        )
        assert res.status_code == 404

    async def test_not_found_and_not_yours_are_indistinguishable(
        self, client, db_session
    ):
        """A 403 would confirm the row exists, which is itself the leak."""
        _owner, intruder, _prog, planned = await self._two_users(client, db_session)
        theirs = await client.get(
            f"/api/workouts/planned-sessions/{planned['id']}", headers=_hdr(intruder)
        )
        nothing = await client.get(
            "/api/workouts/planned-sessions/entirely-made-up", headers=_hdr(intruder)
        )
        assert theirs.status_code == nothing.status_code == 404
        assert theirs.json() == nothing.json()

    async def test_a_second_user_cannot_see_the_first_users_profile(
        self, client, db_session
    ):
        owner, intruder, _prog, _planned = await self._two_users(client, db_session)
        res = await client.get("/api/workouts/training-profile", headers=_hdr(intruder))
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Nutrition invariance
# ---------------------------------------------------------------------------


class TestNutritionInvariance:
    async def test_the_whole_programming_flow_touches_no_nutrition_table(
        self, client, db_session
    ):
        """Programming has no nutrition foreign key and must never acquire one
        by accident. Counts before and after an end-to-end run."""
        before = {}
        for table in ("food_items", "food_aliases", "meal_logs"):
            before[table] = (
                await db_session.execute(text(f"SELECT count(*) FROM {table}"))
            ).scalar()

        await _seed_catalogue(db_session)
        auth = await _register(client)
        await _profile(client, auth)
        await _programme(client, auth)
        planned = await _planned(client, auth)
        await client.patch(
            f"/api/workouts/prescribed-exercises/{planned['exercises'][0]['id']}",
            json={"status": "skipped"}, headers=_hdr(auth),
        )
        start = await client.post(
            f"/api/workouts/planned-sessions/{planned['id']}/start", headers=_hdr(auth)
        )
        await client.post(
            f"/api/workouts/sessions/{start.json()['session_id']}/sets",
            json={"exercise_id": "goblet-squat", "weight_kg": 20, "reps": 8},
            headers=_hdr(auth),
        )

        for table, count in before.items():
            after = (
                await db_session.execute(text(f"SELECT count(*) FROM {table}"))
            ).scalar()
            assert after == count, f"{table} changed: {count} -> {after}"


# ---------------------------------------------------------------------------
# Query shape
# ---------------------------------------------------------------------------


class TestNoNPlusOne:
    """Rendering a session must not cost one query per exercise.

    Asserted by counting statements rather than by reading the code, because
    an N+1 is exactly the kind of regression that a lazy-loaded attribute
    reintroduces silently.
    """

    @staticmethod
    def _counter(db_engine):
        from sqlalchemy import event

        box = {"n": 0}

        def _count(conn, cursor, statement, params, context, executemany):
            box["n"] += 1

        event.listen(db_engine.sync_engine, "before_cursor_execute", _count)
        return box, lambda: event.remove(
            db_engine.sync_engine, "before_cursor_execute", _count
        )

    async def _session_with(self, client, db_session, minutes):
        auth = await _register(client)
        await _profile(client, auth, preferred_minutes=minutes)
        await _programme(client, auth)
        planned = await _planned(client, auth)
        return auth, planned

    async def test_reading_a_session_costs_the_same_however_many_exercises(
        self, client, db_session, db_engine
    ):
        await _seed_catalogue(db_session)

        auth_small, small = await self._session_with(client, db_session, 15)
        auth_big, big = await self._session_with(client, db_session, 180)
        assert len(big["exercises"]) > len(small["exercises"]), (
            "fixture failed to produce sessions of different sizes"
        )

        counts = []
        for auth, planned in ((auth_small, small), (auth_big, big)):
            box, stop = self._counter(db_engine)
            try:
                res = await client.get(
                    f"/api/workouts/planned-sessions/{planned['id']}",
                    headers=_hdr(auth),
                )
                assert res.status_code == 200
            finally:
                stop()
            counts.append(box["n"])

        assert counts[0] == counts[1], (
            f"query count scales with exercise count: {counts[0]} vs {counts[1]} "
            "-- an N+1 has been reintroduced"
        )
