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


# ---------------------------------------------------------------------------
# Search performance -- the trigram index
#
# These guard the fix for the sequential scan that made every food search take
# 7.5-18 seconds against 578,773 rows. Between them they pin the two things
# that can silently regress: the query plan, and the similarity threshold.
# ---------------------------------------------------------------------------


async def test_search_uses_the_trigram_index(db_session):
    """THE REGRESSION GUARD. If this fails, search just got 28x slower.

    The WHERE clause must stay expressed with the `<%` OPERATOR. Postgres
    registers an index strategy for the operator but not for the return value
    of `word_similarity()`, and because this arm sits in an OR -- where a
    disjunction is only index-usable if EVERY arm is -- writing it as a
    function comparison drags the whole query to a sequential scan.

    Someone "simplifying" this back to `word_similarity(:q, x) >= 0.45`
    reintroduces an 8-second search with no test failure anywhere else,
    which is exactly why this asserts on the PLAN rather than on results.

    WHY THIS DISABLES seqscan RATHER THAN READING THE DEFAULT PLAN
    `trace_test` is truncated before every test, so the table here holds a
    handful of rows and Postgres correctly prefers a sequential scan -- at
    that size it IS cheaper, and asserting otherwise would only prove the
    table is small. What actually needs guarding is whether the predicate is
    index-*able* at all, which is a property of how it is written, not of the
    row count.

    So: make a seq scan prohibitively expensive and see whether an index path
    exists. With `<%` one does. With `word_similarity(...) >= 0.45` none does,
    and Postgres falls back to the seq scan it was told to avoid -- which is
    the regression this catches. Verified to fail against the old form.
    """
    from sqlalchemy import text

    await db_session.execute(
        text("SET LOCAL pg_trgm.word_similarity_threshold = 0.45")
    )
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    plan_rows = (
        await db_session.execute(
            text(
                """
                EXPLAIN SELECT id FROM food_items
                WHERE (moderation_status = 'approved' OR created_by_user_id = :uid)
                  AND (search_text ILIKE :contains OR CAST(:q AS text) <% search_text)
                LIMIT 25
                """
            ),
            {"uid": "nobody", "q": "paneer tikka", "contains": "%paneer tikka%"},
        )
    ).all()
    plan = "\n".join(r[0] for r in plan_rows)

    assert "ix_food_search_trgm" in plan, (
        "Food search can no longer use the trigram index, so it will "
        "sequentially scan the whole catalogue. The `<%` operator was "
        "probably replaced with a word_similarity() comparison -- Postgres "
        "registers an index strategy for the operator, not for the "
        f"function's return value.\n\n{plan}"
    )


async def test_search_threshold_is_actually_applied(client, db_session):
    """SET LOCAL must reach the query, or typo tolerance quietly degrades.

    The threshold now lives in `pg_trgm.word_similarity_threshold` rather than
    in the SQL. That is what makes the operator indexable -- and it introduces
    a failure mode with no error attached: if the SET LOCAL stops applying
    (a session that no longer holds an open transaction, a pooler that resets
    it), Postgres falls back to its 0.6 default and search silently gets
    STRICTER. Nothing raises. Fuzzy matches just stop arriving.

    'panner tika' -> 'paneer tikka' scores 0.471, which clears our 0.45 floor
    and fails 0.6. So this test passes only when the SET LOCAL took effect.
    """
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
    names = [r["name"] for r in res.json()["results"]]
    assert "Paneer tikka" in names, (
        "A 0.471-similarity typo was rejected. The threshold is most likely "
        "sitting at Postgres's 0.6 default, meaning SET LOCAL did not apply."
    )


async def test_search_ranking_survives_the_index_change(client, db_session):
    """Exact and prefix matches must still outrank fuzzy ones.

    The ORDER BY was deliberately left untouched by the index fix, but the
    filter feeding it changed -- so this pins the outcome rather than the
    clause.
    """
    from app.models import FoodItem

    auth = await _register(client)
    headers = _auth_headers(auth["access_token"])

    for name, blob in [
        ("Dosa", "dosa indian south breakfast crepe"),
        ("Masala dosa potato filled", "masala dosa potato filled indian south"),
        ("Dosakaya pappu", "dosakaya pappu andhra dal yellow"),
    ]:
        db_session.add(
            FoodItem(
                name=name,
                calories=150,
                search_text=blob,
                moderation_status="approved",
            )
        )
    await db_session.commit()

    res = await client.get(
        "/api/foods/search", headers=headers, params={"q": "dosa", "remote": "false"}
    )
    assert res.status_code == 200, res.text
    names = [r["name"] for r in res.json()["results"]]
    assert names, "search returned nothing"
    # "Dosa" starts with the query; the others merely contain or fuzzy-match it.
    assert names[0] == "Dosa", f"prefix match lost its rank: {names}"
