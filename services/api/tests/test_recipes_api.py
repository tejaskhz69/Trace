"""Recipe HTTP surface, against the real trace_test database.

The privacy tests in TestVisibility are the ones that matter. A private
recipe leaking is a different class of bug from a wrong calorie count.
"""

from __future__ import annotations

import uuid

import pytest

from app.models import FoodItem, FoodSource


def _unique_email() -> str:
    return f"recipe-{uuid.uuid4().hex[:12]}@example.com"


async def _register(client, name="Cook") -> dict:
    res = await client.post(
        "/api/auth/register",
        json={
            "email": _unique_email(),
            "password": "correct-horse-battery-staple",
            "display_name": name,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _hdr(auth: dict) -> dict:
    return {"Authorization": f"Bearer {auth['access_token']}"}


async def _seed_foods(db_session) -> dict[str, str]:
    """Two real foods, so ingredient panels come from the catalogue."""
    rice = FoodItem(
        source=FoodSource.curated,
        source_id=f"rice-{uuid.uuid4().hex[:8]}",
        name="Cooked white rice",
        calories=130,
        protein_g=2.7,
        carbs_g=28.2,
        fat_g=0.3,
        fiber_g=0.4,
        search_text="cooked white rice",
    )
    chicken = FoodItem(
        source=FoodSource.curated,
        source_id=f"chicken-{uuid.uuid4().hex[:8]}",
        name="Chicken breast",
        calories=165,
        protein_g=31.0,
        carbs_g=0.0,
        fat_g=3.6,
        search_text="chicken breast",
    )
    db_session.add(rice)
    db_session.add(chicken)
    await db_session.commit()
    return {"rice": rice.id, "chicken": chicken.id}


def _body(foods, **over):
    payload = {
        "name": "Chicken rice bowl",
        "servings": 2,
        "steps": ["Cook the rice", "Grill the chicken", "Combine"],
        "ingredients": [
            {"food_item_id": foods["rice"], "display_name": "Rice", "grams": 300},
            {"food_item_id": foods["chicken"], "display_name": "Chicken", "grams": 200},
        ],
    }
    payload.update(over)
    return payload


# ---------------------------------------------------------------------------


class TestCreate:
    async def test_creates_a_private_recipe_by_default(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        res = await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["visibility"] == "private"
        assert body["is_owner"] is True

    async def test_totals_are_computed_from_the_catalogue(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        res = await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        # 300 g rice = 390 kcal, 200 g chicken = 330 kcal
        assert res.json()["total"]["calories"] == pytest.approx(720, abs=1)

    async def test_per_serving_divides_the_total(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        res = await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        assert res.json()["per_serving"]["calories"] == pytest.approx(360, abs=1)

    async def test_a_client_cannot_invent_macros_for_a_real_food(
        self, client, db_session
    ):
        """food_item_id wins over anything the body claims.

        Otherwise a modified client could publish a recipe asserting chicken
        has 900 kcal, and the totals would carry it.
        """
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        body = _body(foods)
        body["ingredients"][1]["calories"] = 900
        body["ingredients"][1]["protein_g"] = 0
        res = await client.post("/api/recipes", json=body, headers=_hdr(auth))
        assert res.json()["total"]["calories"] == pytest.approx(720, abs=1)

    async def test_hand_entered_lines_are_allowed(self, client, db_session):
        auth = await _register(client)
        body = {
            "name": "Grandmother's rasam",
            "servings": 4,
            "ingredients": [
                {"display_name": "Tamarind broth", "grams": 600, "calories": 20},
                {"display_name": "Ghee", "grams": 15, "calories": 900, "fat_g": 100},
            ],
        }
        res = await client.post("/api/recipes", json=body, headers=_hdr(auth))
        assert res.status_code == 201, res.text
        assert res.json()["sourced_fraction"] == 0.0

    async def test_an_unknown_food_id_is_rejected(self, client, db_session):
        auth = await _register(client)
        body = {
            "name": "Ghost stew",
            "ingredients": [
                {"food_item_id": "does-not-exist", "display_name": "X", "grams": 100}
            ],
        }
        res = await client.post("/api/recipes", json=body, headers=_hdr(auth))
        assert res.status_code == 404

    async def test_auth_is_required(self, client):
        res = await client.post("/api/recipes", json={"name": "Anon"})
        assert res.status_code == 401


class TestYieldOverHttp:
    async def test_no_cooked_weight_means_no_per_100g(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        res = await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        body = res.json()
        assert body["yield_estimated"] is True
        assert body["per_100g"] is None
        assert body["serving_grams"] is None

    async def test_a_cooked_weight_unlocks_per_100g(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        res = await client.post(
            "/api/recipes", json=_body(foods, cooked_weight_g=400), headers=_hdr(auth)
        )
        body = res.json()
        assert body["yield_estimated"] is False
        assert body["per_100g"]["calories"] == pytest.approx(180, abs=1)
        assert body["serving_grams"] == 200


class TestVisibility:
    """Private means private. These are the tests to keep."""

    async def test_another_user_cannot_read_a_private_recipe(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        stranger = await _register(client, "Stranger")
        rid = (
            await client.post("/api/recipes", json=_body(foods), headers=_hdr(author))
        ).json()["id"]

        res = await client.get(f"/api/recipes/{rid}", headers=_hdr(stranger))
        assert res.status_code == 404

    async def test_the_404_does_not_confirm_the_recipe_exists(
        self, client, db_session
    ):
        # A 403 would leak that this id is real and belongs to someone.
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        stranger = await _register(client, "Stranger")
        rid = (
            await client.post("/api/recipes", json=_body(foods), headers=_hdr(author))
        ).json()["id"]

        real = await client.get(f"/api/recipes/{rid}", headers=_hdr(stranger))
        fake = await client.get("/api/recipes/nope", headers=_hdr(stranger))
        assert real.status_code == fake.status_code == 404

    async def test_a_private_recipe_never_appears_in_discover(
        self, client, db_session
    ):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        stranger = await _register(client, "Stranger")
        await client.post("/api/recipes", json=_body(foods), headers=_hdr(author))

        res = await client.get("/api/recipes/discover", headers=_hdr(stranger))
        assert res.json()["recipes"] == []

    async def test_publishing_makes_it_readable(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        stranger = await _register(client, "Stranger")
        rid = (
            await client.post("/api/recipes", json=_body(foods), headers=_hdr(author))
        ).json()["id"]

        pub = await client.post(
            f"/api/recipes/{rid}/visibility",
            json={"visibility": "published"},
            headers=_hdr(author),
        )
        assert pub.status_code == 200
        assert pub.json()["published_at"] is not None

        res = await client.get(f"/api/recipes/{rid}", headers=_hdr(stranger))
        assert res.status_code == 200
        assert res.json()["is_owner"] is False
        assert res.json()["author_name"] == "Author"

    async def test_unpublishing_takes_it_back_out_of_reach(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        stranger = await _register(client, "Stranger")
        rid = (
            await client.post(
                "/api/recipes",
                json=_body(foods, visibility="published"),
                headers=_hdr(author),
            )
        ).json()["id"]
        assert (
            await client.get(f"/api/recipes/{rid}", headers=_hdr(stranger))
        ).status_code == 200

        await client.post(
            f"/api/recipes/{rid}/visibility",
            json={"visibility": "private"},
            headers=_hdr(author),
        )
        assert (
            await client.get(f"/api/recipes/{rid}", headers=_hdr(stranger))
        ).status_code == 404

    async def test_a_stranger_cannot_edit(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        stranger = await _register(client, "Stranger")
        rid = (
            await client.post(
                "/api/recipes",
                json=_body(foods, visibility="published"),
                headers=_hdr(author),
            )
        ).json()["id"]

        res = await client.put(
            f"/api/recipes/{rid}", json=_body(foods, name="Hijacked"), headers=_hdr(stranger)
        )
        assert res.status_code == 403

    async def test_a_stranger_cannot_delete(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        stranger = await _register(client, "Stranger")
        rid = (
            await client.post(
                "/api/recipes",
                json=_body(foods, visibility="published"),
                headers=_hdr(author),
            )
        ).json()["id"]
        res = await client.delete(f"/api/recipes/{rid}", headers=_hdr(stranger))
        assert res.status_code == 403


class TestPublishGateOverHttp:
    async def test_a_one_ingredient_recipe_cannot_publish(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        body = _body(foods, visibility="published")
        body["ingredients"] = body["ingredients"][:1]
        res = await client.post("/api/recipes", json=body, headers=_hdr(auth))
        assert res.status_code == 422
        assert res.json()["detail"]["ok"] is False
        assert any("custom food" in b for b in res.json()["detail"]["blockers"])

    async def test_a_refused_publish_leaves_nothing_behind(self, client, db_session):
        """The transaction rolls back -- no orphan private recipe appears."""
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        body = _body(foods, visibility="published")
        body["ingredients"] = body["ingredients"][:1]
        await client.post("/api/recipes", json=body, headers=_hdr(auth))

        lib = await client.get("/api/recipes?scope=mine", headers=_hdr(auth))
        assert lib.json()["recipes"] == []

    async def test_the_dry_run_agrees_with_the_real_thing(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        rid = (
            await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        ).json()["id"]

        check = await client.get(f"/api/recipes/{rid}/publish-check", headers=_hdr(auth))
        assert check.json()["ok"] is True
        pub = await client.post(
            f"/api/recipes/{rid}/visibility",
            json={"visibility": "published"},
            headers=_hdr(auth),
        )
        assert pub.status_code == 200

    async def test_cautions_do_not_prevent_publishing(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        # No cooked weight and no steps -> two cautions, zero blockers.
        body = _body(foods, visibility="published", steps=[])
        res = await client.post("/api/recipes", json=body, headers=_hdr(auth))
        assert res.status_code == 201
        assert res.json()["visibility"] == "published"

    async def test_an_edit_cannot_break_a_live_recipe(self, client, db_session):
        """Editing a published recipe into an unpublishable state is refused
        rather than silently retracting it."""
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        rid = (
            await client.post(
                "/api/recipes",
                json=_body(foods, visibility="published"),
                headers=_hdr(auth),
            )
        ).json()["id"]

        broken = _body(foods)
        broken["ingredients"] = broken["ingredients"][:1]
        res = await client.put(f"/api/recipes/{rid}", json=broken, headers=_hdr(auth))
        assert res.status_code == 422

        still = await client.get(f"/api/recipes/{rid}", headers=_hdr(auth))
        assert still.json()["visibility"] == "published"
        assert len(still.json()["ingredients"]) == 2


class TestLibrary:
    async def test_mine_lists_my_recipes(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        res = await client.get("/api/recipes?scope=mine", headers=_hdr(auth))
        assert res.json()["total"] == 1
        assert res.json()["recipes"][0]["ingredient_count"] == 2

    async def test_mine_includes_private_and_published(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        await client.post(
            "/api/recipes",
            json=_body(foods, name="Public bowl", visibility="published"),
            headers=_hdr(auth),
        )
        res = await client.get("/api/recipes?scope=mine", headers=_hdr(auth))
        assert res.json()["total"] == 2

    async def test_the_summary_uses_per_serving_numbers(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        row = (await client.get("/api/recipes", headers=_hdr(auth))).json()["recipes"][0]
        assert row["calories_per_serving"] == pytest.approx(360, abs=1)

    async def test_i_do_not_see_other_peoples_libraries(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        stranger = await _register(client, "Stranger")
        await client.post("/api/recipes", json=_body(foods), headers=_hdr(author))
        res = await client.get("/api/recipes?scope=all", headers=_hdr(stranger))
        assert res.json()["recipes"] == []

    async def test_search_filters_by_ingredient_too(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        hit = await client.get("/api/recipes?q=chicken", headers=_hdr(auth))
        miss = await client.get("/api/recipes?q=aubergine", headers=_hdr(auth))
        assert hit.json()["total"] == 1
        assert miss.json()["total"] == 0


class TestSaveAndFork:
    async def test_saving_puts_it_on_my_shelf(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        me = await _register(client, "Me")
        rid = (
            await client.post(
                "/api/recipes",
                json=_body(foods, visibility="published"),
                headers=_hdr(author),
            )
        ).json()["id"]

        assert (
            await client.post(f"/api/recipes/{rid}/save", headers=_hdr(me))
        ).status_code == 204
        lib = await client.get("/api/recipes?scope=saved", headers=_hdr(me))
        assert lib.json()["total"] == 1
        assert lib.json()["recipes"][0]["is_owner"] is False

    async def test_saving_twice_is_not_an_error_and_counts_once(
        self, client, db_session
    ):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        me = await _register(client, "Me")
        rid = (
            await client.post(
                "/api/recipes",
                json=_body(foods, visibility="published"),
                headers=_hdr(author),
            )
        ).json()["id"]
        await client.post(f"/api/recipes/{rid}/save", headers=_hdr(me))
        await client.post(f"/api/recipes/{rid}/save", headers=_hdr(me))
        detail = await client.get(f"/api/recipes/{rid}", headers=_hdr(me))
        assert detail.json()["save_count"] == 1

    async def test_unsaving_removes_it(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        me = await _register(client, "Me")
        rid = (
            await client.post(
                "/api/recipes",
                json=_body(foods, visibility="published"),
                headers=_hdr(author),
            )
        ).json()["id"]
        await client.post(f"/api/recipes/{rid}/save", headers=_hdr(me))
        await client.delete(f"/api/recipes/{rid}/save", headers=_hdr(me))
        lib = await client.get("/api/recipes?scope=saved", headers=_hdr(me))
        assert lib.json()["total"] == 0

    async def test_a_fork_is_mine_and_private(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        me = await _register(client, "Me")
        rid = (
            await client.post(
                "/api/recipes",
                json=_body(foods, visibility="published"),
                headers=_hdr(author),
            )
        ).json()["id"]

        fork = await client.post(f"/api/recipes/{rid}/fork", headers=_hdr(me))
        assert fork.status_code == 201
        body = fork.json()
        assert body["is_owner"] is True
        assert body["visibility"] == "private"
        assert body["forked_from_id"] == rid
        assert len(body["ingredients"]) == 2

    async def test_a_fork_does_not_follow_the_original(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        me = await _register(client, "Me")
        rid = (
            await client.post(
                "/api/recipes",
                json=_body(foods, visibility="published"),
                headers=_hdr(author),
            )
        ).json()["id"]
        fid = (await client.post(f"/api/recipes/{rid}/fork", headers=_hdr(me))).json()["id"]

        await client.put(
            f"/api/recipes/{rid}",
            json=_body(foods, name="Renamed", visibility="published"),
            headers=_hdr(author),
        )
        mine = await client.get(f"/api/recipes/{fid}", headers=_hdr(me))
        assert mine.json()["name"] == "Chicken rice bowl"

    async def test_deleting_the_original_leaves_the_fork_alone(
        self, client, db_session
    ):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        me = await _register(client, "Me")
        rid = (
            await client.post(
                "/api/recipes",
                json=_body(foods, visibility="published"),
                headers=_hdr(author),
            )
        ).json()["id"]
        fid = (await client.post(f"/api/recipes/{rid}/fork", headers=_hdr(me))).json()["id"]

        assert (
            await client.delete(f"/api/recipes/{rid}", headers=_hdr(author))
        ).status_code == 204
        still = await client.get(f"/api/recipes/{fid}", headers=_hdr(me))
        assert still.status_code == 200
        assert still.json()["forked_from_id"] is None


class TestLogging:
    async def test_logging_a_serving_creates_a_meal(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        rid = (
            await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        ).json()["id"]

        res = await client.post(
            f"/api/recipes/{rid}/log",
            json={"servings": 1, "meal_type": "lunch"},
            headers=_hdr(auth),
        )
        assert res.status_code == 201, res.text
        assert res.json()["calories"] == pytest.approx(360, abs=1)
        assert res.json()["serving_label"] == "1 serving"

    async def test_the_meal_shows_up_in_the_daily_summary(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        rid = (
            await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        ).json()["id"]
        await client.post(
            f"/api/recipes/{rid}/log", json={"servings": 2}, headers=_hdr(auth)
        )
        day = await client.get("/api/meals/daily", headers=_hdr(auth))
        assert day.json()["calories"] == pytest.approx(720, abs=1)

    async def test_grams_are_refused_without_a_measured_weight(
        self, client, db_session
    ):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        rid = (
            await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        ).json()["id"]
        res = await client.post(
            f"/api/recipes/{rid}/log", json={"grams": 250}, headers=_hdr(auth)
        )
        assert res.status_code == 422
        assert "by serving" in res.json()["detail"]

    async def test_grams_work_once_the_weight_is_known(self, client, db_session):
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        rid = (
            await client.post(
                "/api/recipes", json=_body(foods, cooked_weight_g=400), headers=_hdr(auth)
            )
        ).json()["id"]
        res = await client.post(
            f"/api/recipes/{rid}/log", json={"grams": 200}, headers=_hdr(auth)
        )
        assert res.status_code == 201
        assert res.json()["calories"] == pytest.approx(360, abs=2)

    async def test_editing_the_recipe_does_not_rewrite_a_logged_meal(
        self, client, db_session
    ):
        """The invariant MealLog exists to protect, reached through recipes."""
        foods = await _seed_foods(db_session)
        auth = await _register(client)
        rid = (
            await client.post("/api/recipes", json=_body(foods), headers=_hdr(auth))
        ).json()["id"]
        await client.post(
            f"/api/recipes/{rid}/log", json={"servings": 1}, headers=_hdr(auth)
        )

        doubled = _body(foods)
        doubled["ingredients"][1]["grams"] = 800
        await client.put(f"/api/recipes/{rid}", json=doubled, headers=_hdr(auth))

        day = await client.get("/api/meals/daily", headers=_hdr(auth))
        assert day.json()["calories"] == pytest.approx(360, abs=1)

    async def test_i_can_log_someone_elses_published_recipe(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        me = await _register(client, "Me")
        rid = (
            await client.post(
                "/api/recipes",
                json=_body(foods, visibility="published"),
                headers=_hdr(author),
            )
        ).json()["id"]
        res = await client.post(
            f"/api/recipes/{rid}/log", json={"servings": 1}, headers=_hdr(me)
        )
        assert res.status_code == 201

    async def test_i_cannot_log_someone_elses_private_recipe(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        me = await _register(client, "Me")
        rid = (
            await client.post("/api/recipes", json=_body(foods), headers=_hdr(author))
        ).json()["id"]
        res = await client.post(
            f"/api/recipes/{rid}/log", json={"servings": 1}, headers=_hdr(me)
        )
        assert res.status_code == 404


class TestDiscover:
    async def test_published_recipes_are_listed(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        me = await _register(client, "Me")
        await client.post(
            "/api/recipes",
            json=_body(foods, visibility="published"),
            headers=_hdr(author),
        )
        res = await client.get("/api/recipes/discover", headers=_hdr(me))
        assert res.json()["total"] == 1
        assert res.json()["recipes"][0]["author_name"] == "Author"

    async def test_protein_sort_is_per_serving_not_per_pot(self, client, db_session):
        """A recipe must not out-rank another by simply being bigger."""
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        me = await _register(client, "Me")

        # Same dish, one batch-cooked for 10. Per serving it is the weaker one.
        await client.post(
            "/api/recipes",
            json=_body(foods, name="Big batch", servings=10, visibility="published"),
            headers=_hdr(author),
        )
        await client.post(
            "/api/recipes",
            json=_body(foods, name="Single portion", servings=1, visibility="published"),
            headers=_hdr(author),
        )
        res = await client.get(
            "/api/recipes/discover?sort=protein", headers=_hdr(me)
        )
        assert res.json()["recipes"][0]["name"] == "Single portion"

    async def test_search_matches_the_name(self, client, db_session):
        foods = await _seed_foods(db_session)
        author = await _register(client, "Author")
        me = await _register(client, "Me")
        await client.post(
            "/api/recipes",
            json=_body(foods, name="Paneer bhurji", visibility="published"),
            headers=_hdr(author),
        )
        hit = await client.get("/api/recipes/discover?q=paneer", headers=_hdr(me))
        miss = await client.get("/api/recipes/discover?q=lasagne", headers=_hdr(me))
        assert hit.json()["total"] == 1
        assert miss.json()["total"] == 0


class TestOwnCustomFoodsAreSearchable:
    """A custom food is filed as 'pending' and called "private to its author".

    Search used to filter on moderation_status = 'approved' alone, so the
    author could not find it either -- a private library nobody can search is
    not a library, it is a write-only hole. These pin the scoping: mine are
    visible to me, and to nobody else.
    """

    async def _make_custom(self, client, auth, name="Ammas special podi"):
        res = await client.post(
            "/api/foods/custom",
            json={
                "name": name,
                "calories": 400,
                "protein_g": 15,
                "carbs_g": 40,
                "fat_g": 20,
            },
            headers=_hdr(auth),
        )
        assert res.status_code == 201, res.text
        return res.json()

    async def test_i_can_find_my_own_custom_food(self, client):
        auth = await _register(client)
        await self._make_custom(client, auth)
        res = await client.get(
            "/api/foods/search?q=podi&remote=false", headers=_hdr(auth)
        )
        names = [r["name"] for r in res.json()["results"]]
        assert "Ammas special podi" in names

    async def test_nobody_else_can(self, client):
        author = await _register(client, "Author")
        stranger = await _register(client, "Stranger")
        await self._make_custom(client, author)
        res = await client.get(
            "/api/foods/search?q=podi&remote=false", headers=_hdr(stranger)
        )
        assert res.json()["results"] == []

    async def test_it_can_be_used_as_a_recipe_ingredient(self, client):
        """The point of the fix -- an unfindable food cannot be cooked with."""
        auth = await _register(client)
        food = await self._make_custom(client, auth)
        res = await client.post(
            "/api/recipes",
            json={
                "name": "Podi rice",
                "servings": 2,
                "ingredients": [
                    {"food_item_id": food["id"], "display_name": "Podi", "grams": 30},
                    {"display_name": "Rice", "grams": 300, "calories": 130},
                ],
            },
            headers=_hdr(auth),
        )
        assert res.status_code == 201, res.text
        assert res.json()["total"]["calories"] == pytest.approx(510, abs=1)
