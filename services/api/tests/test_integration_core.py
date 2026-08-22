"""End-to-end smoke tests for the core user journeys, run against the
dedicated `trace_test` database (see conftest.py) over an in-process ASGI
client -- real routers, real DB round-trips, real auth, no mocking of the
app's own code. This is the layer the existing 89 pure-function tests don't
cover: HTTP status codes, auth wiring, and actual Postgres round-trips.

Each test registers its own user rather than sharing one, so tests can run
in any order; `_clean_tables` in conftest.py also truncates between tests as
a second line of defense.

NOT covered here: POST /api/foods/recognize (photo scan). It requires
GEMINI_API_KEY, which is not configured in this environment -- see
test_recognize_requires_configured_key below, which documents that gap
explicitly rather than silently omitting it.
"""

from __future__ import annotations

import uuid

import pytest

from app.models import Exercise


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:12]}@example.com"


async def _register(client, **overrides) -> dict:
    payload = {
        "email": _unique_email(),
        "password": "correct-horse-battery-staple",
        "display_name": "Test Athlete",
        **overrides,
    }
    res = await client.post("/api/auth/register", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


async def test_health(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_register_login_me(client):
    auth = await _register(client)
    assert auth["access_token"]
    assert auth["user"]["email"]

    me = await client.get("/api/auth/me", headers=_auth_headers(auth["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == auth["user"]["email"]

    # Login with the same credentials, independent of the register response.
    login = await client.post(
        "/api/auth/login",
        json={"email": auth["user"]["email"], "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == auth["user"]["id"]


async def test_me_rejects_missing_and_garbage_tokens(client):
    missing = await client.get("/api/auth/me")
    assert missing.status_code == 401
    assert "Missing Authorization header" in missing.json()["detail"]

    garbage = await client.get("/api/auth/me", headers=_auth_headers("not-a-real-token"))
    assert garbage.status_code == 401


# ---------------------------------------------------------------------------
# AI Trainer chat (see app/routers/chat.py)
# ---------------------------------------------------------------------------


async def test_chat_ask_without_configured_key_returns_503(client, monkeypatch):
    """The unconfigured case must be SET UP, not inherited from the machine.

    This test used to assert 503 while relying on the developer simply not
    having a key in .env -- so it passed for the wrong reason, and started
    failing the moment a real GEMINI_API_KEY was added. The condition under
    test is "no key configured", so the test has to establish that itself.
    """
    from app.routers import chat as chat_router

    monkeypatch.setattr(chat_router.settings, "GEMINI_API_KEY", None)

    res = await client.post("/api/chat/ask", json={"question": "How does Trace work?"})
    assert res.status_code == 503
    assert "isn't configured" in res.json()["detail"]


async def test_chat_ask_rejects_empty_question(client):
    res = await client.post("/api/chat/ask", json={"question": ""})
    assert res.status_code == 422


@pytest.mark.skip(
    reason="Requires GEMINI_API_KEY, which is not configured in this "
    "environment -- not testable here, tracked explicitly rather than "
    "silently omitted from the suite."
)
async def test_recognize_requires_configured_key():
    ...


# ---------------------------------------------------------------------------
# Foods
# ---------------------------------------------------------------------------


async def test_custom_food_and_search(client, db_session):
    auth = await _register(client)
    headers = _auth_headers(auth["access_token"])

    custom = await client.post(
        "/api/foods/custom",
        headers=headers,
        json={
            "name": "Test Protein Bar",
            "calories": 380,
            "protein_g": 30,
            "carbs_g": 35,
            "fat_g": 12,
        },
    )
    assert custom.status_code == 201, custom.text
    assert custom.json()["name"] == "Test Protein Bar"

    # A custom food starts "pending" and won't show in search -- seed an
    # already-approved item directly to exercise the real pg_trgm search
    # path (this is also a check that the extension + index actually work
    # on a freshly created database, not just that the endpoint responds).
    from app.models import FoodItem

    db_session.add(
        FoodItem(
            name="Paneer Tikka",
            calories=250,
            protein_g=18,
            search_text="paneer tikka",
            moderation_status="approved",
        )
    )
    await db_session.commit()

    search = await client.get(
        "/api/foods/search", headers=headers, params={"q": "panner tika", "remote": "false"}
    )
    assert search.status_code == 200, search.text
    names = [r["name"] for r in search.json()["results"]]
    assert "Paneer Tikka" in names  # typo-tolerant match, the whole point of pg_trgm


# ---------------------------------------------------------------------------
# Meals
# ---------------------------------------------------------------------------


async def test_log_meal_and_daily_summary(client):
    auth = await _register(client)
    headers = _auth_headers(auth["access_token"])

    logged = await client.post(
        "/api/meals/log",
        headers=headers,
        json={
            "display_name": "Chicken and rice",
            "grams": 350,
            "calories": 520,
            "protein_g": 45,
            "carbs_g": 60,
            "fat_g": 10,
        },
    )
    assert logged.status_code == 201, logged.text

    summary = await client.get("/api/meals/daily", headers=headers)
    assert summary.status_code == 200
    body = summary.json()
    assert body["calories"] == 520
    assert len(body["meals"]) == 1


# ---------------------------------------------------------------------------
# Weight
# ---------------------------------------------------------------------------


async def test_log_weight_and_trend(client):
    auth = await _register(client)
    headers = _auth_headers(auth["access_token"])

    logged = await client.post("/api/weight/log", headers=headers, json={"weight_kg": 82.4})
    assert logged.status_code == 201, logged.text

    trend = await client.get("/api/weight/trend", headers=headers, params={"days": 30})
    assert trend.status_code == 200
    points = trend.json()
    assert len(points) == 1
    assert points[0]["raw_kg"] == 82.4


# ---------------------------------------------------------------------------
# Workouts
# ---------------------------------------------------------------------------


async def test_workout_session_and_set_log(client, db_session):
    auth = await _register(client)
    headers = _auth_headers(auth["access_token"])

    exercise = Exercise(name="Barbell Back Squat", muscle_group="legs")
    db_session.add(exercise)
    await db_session.commit()
    await db_session.refresh(exercise)

    session_res = await client.post(
        "/api/workouts/sessions", headers=headers, json={"routine_name": "Leg day"}
    )
    assert session_res.status_code == 201, session_res.text
    session_id = session_res.json()["id"]

    set_res = await client.post(
        f"/api/workouts/sessions/{session_id}/sets",
        headers=headers,
        json={"exercise_id": exercise.id, "weight_kg": 100, "reps": 5},
    )
    assert set_res.status_code == 201, set_res.text
    assert set_res.json()["e1rm"] is not None


# ---------------------------------------------------------------------------
# Adjudication
# ---------------------------------------------------------------------------


async def test_weekly_verdict_is_insufficient_data_for_new_user(client):
    """Not a failure: INSUFFICIENT_DATA is the documented correct behavior
    for a user without ~3 weeks of weigh-ins (CLAUDE.md non-negotiable #3)."""
    auth = await _register(client)
    headers = _auth_headers(auth["access_token"])

    res = await client.get("/api/adjudication/weekly", headers=headers)
    assert res.status_code == 422
    assert "weigh-ins" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Search: the word-similarity regression
# ---------------------------------------------------------------------------


async def test_search_finds_a_dish_by_a_word_in_the_middle_of_its_name(
    client, db_session
):
    """Regression: searching "biryani" returned NOTHING for "Chicken biryani".

    `search_text` is a blob of name + brand + category + tags, and the old
    query used whole-string `similarity()`. A short query against a long blob
    scores low by construction -- 'biryani' vs 'chicken biryani indian north
    rice biriyani' measured 0.216, under the 0.3 threshold -- so richer
    metadata made a food HARDER to find.

    This test fails against `similarity()` and passes against
    `word_similarity()`.
    """
    from app.models import FoodItem

    auth = await _register(client)
    headers = _auth_headers(auth["access_token"])

    db_session.add(
        FoodItem(
            name="Chicken biryani",
            calories=165,
            protein_g=9,
            # A realistic blob, not a bare name -- the bug only appears when
            # the indexed text is much longer than the query.
            search_text="chicken biryani indian north rice biriyani dum hyderabadi",
            moderation_status="approved",
        )
    )
    await db_session.commit()

    res = await client.get(
        "/api/foods/search", headers=headers, params={"q": "biryani", "remote": "false"}
    )
    assert res.status_code == 200, res.text
    assert "Chicken biryani" in [r["name"] for r in res.json()["results"]]


async def test_search_still_tolerates_typos_after_the_fix(client, db_session):
    """The word-similarity floor must not be so strict it kills fuzzy match."""
    from app.models import FoodItem

    auth = await _register(client)
    headers = _auth_headers(auth["access_token"])

    db_session.add(
        FoodItem(
            name="Paneer tikka",
            calories=250,
            protein_g=18,
            search_text="paneer tikka indian north starter grilled",
            moderation_status="approved",
        )
    )
    await db_session.commit()

    res = await client.get(
        "/api/foods/search",
        headers=headers,
        params={"q": "panner tika", "remote": "false"},
    )
    assert res.status_code == 200, res.text
    assert "Paneer tikka" in [r["name"] for r in res.json()["results"]]
