"""Integration tests for two-arm food search over the real HTTP surface.

Runs against the scratch test database via the project's ASGI client -- no
socket, no separate server process, and never against `trace`.

Every search here passes `remote=false`. The remote fan-out path calls
`persist_resolved`, which WRITES to `food_items`; leaving it on would make
these tests mutate the catalogue they are asserting about.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.anyio


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register(client) -> dict:
    email = f"search-{uuid.uuid4().hex[:10]}@example.com"
    res = await client.post("/api/auth/register", json={
        "email": email, "password": "hunter2-correct-horse", "name": "Search"})
    assert res.status_code in (200, 201), res.text
    return _auth_headers(res.json()["access_token"])


async def _food(session, name, *, search_text=None, normalized=None,
                log_count=0, quality=0.5, source="curated",
                licence="user", tier=5, brand=None) -> str:
    fid = str(uuid.uuid4())
    await session.execute(text("""
        INSERT INTO food_items
            (id, source, name, brand, calories, protein_g, carbs_g, fat_g,
             fiber_g, sugar_g, sodium_mg, saturated_fat_g, is_liquid,
             serving_sizes, countries, micronutrients, names_i18n,
             data_quality, is_verified, moderation_status, search_text,
             log_count, source_licence, verification_tier, name_normalized,
             created_at, updated_at)
        VALUES
            (:id, :source, :name, :brand, 100, 1, 1, 1,
             0, 0, 0, 0, false,
             '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, '{}'::jsonb,
             :quality, false, 'approved', :search_text,
             :log_count, :licence, :tier, :normalized, now(), now())
    """), {"id": fid, "source": source, "name": name, "brand": brand,
           "quality": quality, "log_count": log_count,
           "search_text": (search_text or name).lower(),
           "normalized": (normalized or name).lower(),
           "licence": licence, "tier": tier})
    return fid


async def _alias(session, food_id, normalized, *, alias=None,
                 alias_type="regional", source="curated", confidence=0.9,
                 is_active=True, lang="", script="latn") -> None:
    await session.execute(text("""
        INSERT INTO food_aliases
            (id, food_item_id, alias, normalized, lang, script, alias_type,
             source, confidence, is_active, created_at, updated_at)
        VALUES
            (:id, :fid, :alias, :norm, :lang, :script, :atype,
             :src, :conf, :active, now(), now())
    """), {"id": str(uuid.uuid4()), "fid": food_id, "alias": alias or normalized,
           "norm": normalized, "lang": lang, "script": script,
           "atype": alias_type, "src": source, "conf": confidence,
           "active": is_active})


async def _search(client, headers, q, **params):
    res = await client.get("/api/foods/search", headers=headers,
                           params={"q": q, "remote": "false", **params})
    assert res.status_code == 200, res.text
    return res.json()["results"]


# ------------------------------------------------------- canonical matching

async def test_exact_canonical_match_ranks_first(client, db_session):
    headers = await _register(client)
    await _food(db_session, "Dosa", search_text="dosa indian breakfast")
    await _food(db_session, "Masala dosa", search_text="masala dosa indian")
    await _food(db_session, "Dosa batter", search_text="dosa batter indian")
    await db_session.commit()

    results = await _search(client, headers, "dosa")
    assert results[0]["name"] == "Dosa"
    assert results[0]["matched_via"] == "direct"


async def test_canonical_prefix_beats_substring(client, db_session):
    headers = await _register(client)
    await _food(db_session, "Dosa batter", search_text="dosa batter")
    await _food(db_session, "Masala dosa", search_text="masala dosa")
    await db_session.commit()

    names = [r["name"] for r in await _search(client, headers, "dosa")]
    assert names.index("Dosa batter") < names.index("Masala dosa")


async def test_canonical_substring_still_matches(client, db_session):
    headers = await _register(client)
    await _food(db_session, "Masala dosa", search_text="masala dosa")
    await db_session.commit()
    assert [r["name"] for r in await _search(client, headers, "dosa")] == \
        ["Masala dosa"]


# ----------------------------------------------------------- alias matching

async def test_exact_alias_match_finds_its_target(client, db_session):
    headers = await _register(client)
    fid = await _food(db_session, "Plain dosa", search_text="plain dosa")
    await _alias(db_session, fid, "dosai")
    await db_session.commit()

    results = await _search(client, headers, "dosai")
    assert [r["name"] for r in results] == ["Plain dosa"]
    assert results[0]["matched_via"] == "alias"
    assert results[0]["matched_alias"] == "dosai"


async def test_alias_prefix_match(client, db_session):
    headers = await _register(client)
    fid = await _food(db_session, "Poha", search_text="poha")
    await _alias(db_session, fid, "kanda poha")
    await db_session.commit()
    assert [r["name"] for r in await _search(client, headers, "kanda")] == ["Poha"]


async def test_exact_canonical_outranks_exact_alias(client, db_session):
    """The food actually called that must win over one merely aliased to it."""
    headers = await _register(client)
    await _food(db_session, "Poha", search_text="poha")
    other = await _food(db_session, "Chivda", search_text="chivda")
    await _alias(db_session, other, "poha", confidence=1.0)
    await db_session.commit()

    results = await _search(client, headers, "poha")
    assert results[0]["name"] == "Poha"
    assert results[0]["matched_via"] == "direct"


async def test_exact_alias_beats_weak_canonical(client, db_session):
    headers = await _register(client)
    await _food(db_session, "Dosai special plate", search_text="dosai special plate")
    fid = await _food(db_session, "Plain dosa", search_text="plain dosa")
    await _alias(db_session, fid, "dosai")
    await db_session.commit()

    results = await _search(client, headers, "dosai")
    assert results[0]["name"] == "Plain dosa"


async def test_curated_alias_outranks_generated_alias(client, db_session):
    headers = await _register(client)
    a = await _food(db_session, "Paneer", search_text="paneer")
    b = await _food(db_session, "Paneer bhurji", search_text="paneer bhurji")
    await _alias(db_session, a, "panir", confidence=0.9, source="curated")
    await _alias(db_session, b, "panir", confidence=0.6, source="ai",
                 alias_type="misspelling")
    await db_session.commit()

    assert (await _search(client, headers, "panir"))[0]["name"] == "Paneer"


# ------------------------------------------------------- duplicate collapse

async def test_multiple_aliases_to_one_food_collapse_to_one_result(
        client, db_session):
    headers = await _register(client)
    fid = await _food(db_session, "Poha", search_text="poha flattened rice")
    for n in ("poha variant one", "poha variant two", "poha variant three"):
        await _alias(db_session, fid, n)
    await db_session.commit()

    results = await _search(client, headers, "poha")
    assert len(results) == 1
    assert len({r["id"] for r in results}) == 1


async def test_food_reachable_both_directly_and_by_alias_appears_once(
        client, db_session):
    headers = await _register(client)
    fid = await _food(db_session, "Dosa", search_text="dosa")
    await _alias(db_session, fid, "dosa plain")
    await db_session.commit()

    results = await _search(client, headers, "dosa")
    assert len(results) == 1
    assert results[0]["matched_via"] == "direct"   # strongest match wins


# ------------------------------------------------------------ inactive

async def test_inactive_aliases_are_never_returned(client, db_session):
    headers = await _register(client)
    fid = await _food(db_session, "Retired food", search_text="retired food")
    await _alias(db_session, fid, "zzqqx retired handle", is_active=False)
    await db_session.commit()
    assert await _search(client, headers, "zzqqx") == []


async def test_deactivating_one_alias_leaves_the_other(client, db_session):
    headers = await _register(client)
    fid = await _food(db_session, "Idli", search_text="idli")
    await _alias(db_session, fid, "zzqqx live handle", is_active=True)
    await _alias(db_session, fid, "zzqqx dead handle", is_active=False)
    await db_session.commit()

    results = await _search(client, headers, "zzqqx")
    assert len(results) == 1
    assert results[0]["matched_alias"] == "zzqqx live handle"


# ------------------------------------------------- no aliases / regression

async def test_no_alias_matches_leaves_direct_results_untouched(
        client, db_session):
    """The production case on day one: aliases exist but match nothing."""
    headers = await _register(client)
    await _food(db_session, "Rajma", search_text="rajma kidney beans",
                log_count=10)
    await _food(db_session, "Rajma chawal", search_text="rajma chawal",
                log_count=99)
    other = await _food(db_session, "Unrelated", search_text="unrelated")
    await _alias(db_session, other, "nothing to do with the query")
    await db_session.commit()

    names = [r["name"] for r in await _search(client, headers, "rajma")]
    assert names == ["Rajma", "Rajma chawal"]
    assert all(r["matched_via"] == "direct"
               for r in await _search(client, headers, "rajma"))


async def test_search_works_with_no_alias_rows_at_all(client, db_session):
    headers = await _register(client)
    await _food(db_session, "Upma", search_text="upma")
    await db_session.commit()
    assert [r["name"] for r in await _search(client, headers, "upma")] == ["Upma"]


async def test_typo_tolerance_survives_the_two_arm_rewrite(client, db_session):
    """Regression: the trigram arm must still work. See WORD_SIMILARITY_FLOOR."""
    headers = await _register(client)
    await _food(db_session, "Paneer tikka", search_text="paneer tikka")
    await db_session.commit()
    names = [r["name"] for r in await _search(client, headers, "panner tika")]
    assert "Paneer tikka" in names


# ----------------------------------------------------------- determinism

async def test_ranking_is_stable_across_repeated_calls(client, db_session):
    headers = await _register(client)
    for i in range(6):
        await _food(db_session, f"Tie food {i}", search_text="tie food",
                    log_count=5, quality=0.5)
    await db_session.commit()

    first = [r["id"] for r in await _search(client, headers, "tie food")]
    for _ in range(4):
        assert [r["id"] for r in await _search(client, headers, "tie food")] == first


# ------------------------------------------------------------ pagination

async def test_limit_is_respected(client, db_session):
    headers = await _register(client)
    for i in range(12):
        await _food(db_session, f"Paged item {i}", search_text="paged item")
    await db_session.commit()

    assert len(await _search(client, headers, "paged item", limit=5)) == 5
    assert len(await _search(client, headers, "paged item", limit=10)) == 10


async def test_limit_applies_after_collapsing_not_before(client, db_session):
    """Aliases must not consume slots that duplicates would have taken."""
    headers = await _register(client)
    for i in range(4):
        fid = await _food(db_session, f"Collapse {i}", search_text="collapse item")
        for k in range(3):
            await _alias(db_session, fid, f"collapse item alias {i}{k}")
    await db_session.commit()

    results = await _search(client, headers, "collapse item", limit=4)
    assert len(results) == 4
    assert len({r["id"] for r in results}) == 4


async def test_limit_over_the_cap_is_rejected(client):
    headers = await _register(client)
    res = await client.get("/api/foods/search", headers=headers,
                           params={"q": "x", "limit": 500, "remote": "false"})
    assert res.status_code == 422


# --------------------------------------------------------- invalid input

async def test_empty_query_is_rejected(client):
    headers = await _register(client)
    res = await client.get("/api/foods/search", headers=headers,
                           params={"q": "", "remote": "false"})
    assert res.status_code == 422


async def test_overlong_query_is_rejected(client):
    headers = await _register(client)
    res = await client.get("/api/foods/search", headers=headers,
                           params={"q": "x" * 200, "remote": "false"})
    assert res.status_code == 422


async def test_query_matching_nothing_returns_empty_not_an_error(client):
    headers = await _register(client)
    assert await _search(client, headers, "zzzzqqqqxxxx no such food") == []


async def test_search_requires_authentication(client):
    res = await client.get("/api/foods/search", params={"q": "dosa"})
    assert res.status_code in (401, 403)


# ------------------------------------------------------------ attribution

async def test_off_row_reports_odbl_licence(client, db_session):
    headers = await _register(client)
    await _food(db_session, "Branded biscuit", search_text="branded biscuit",
                source="openfoodfacts", licence="odbl", tier=6)
    await db_session.commit()

    r = (await _search(client, headers, "branded biscuit"))[0]
    assert r["source"] == "openfoodfacts"
    assert r["source_licence"] == "odbl"
    assert r["verification_tier"] == 6


async def test_curated_row_is_not_labelled_open_food_facts(client, db_session):
    headers = await _register(client)
    await _food(db_session, "Curated dish", search_text="curated dish",
                source="curated", licence="user", tier=5)
    await db_session.commit()

    r = (await _search(client, headers, "curated dish"))[0]
    assert r["source"] == "curated"
    assert r["source_licence"] != "odbl"


async def test_usda_row_reports_public_domain(client, db_session):
    headers = await _register(client)
    await _food(db_session, "Usda thing", search_text="usda thing",
                source="usda_fdc", licence="public-domain", tier=2)
    await db_session.commit()

    r = (await _search(client, headers, "usda thing"))[0]
    assert r["source_licence"] == "public-domain"
    assert r["verification_tier"] == 2


async def test_results_can_carry_mixed_licences_in_one_response(client, db_session):
    """A blanket notice would be wrong; the response proves per-row licensing."""
    headers = await _register(client)
    await _food(db_session, "Mixed off", search_text="mixedlic thing",
                source="openfoodfacts", licence="odbl")
    await _food(db_session, "Mixed usda", search_text="mixedlic thing",
                source="usda_fdc", licence="public-domain")
    await db_session.commit()

    licences = {r["source_licence"]
                for r in await _search(client, headers, "mixedlic thing")}
    assert licences == {"odbl", "public-domain"}


async def test_no_internal_fields_leak_into_the_response(client, db_session):
    headers = await _register(client)
    await _food(db_session, "Leaky check", search_text="leaky check")
    await db_session.commit()

    r = (await _search(client, headers, "leaky check"))[0]
    for banned in ("search_text", "name_normalized", "gtin14", "log_count",
                   "created_by_user_id", "moderation_status"):
        assert banned not in r, banned


# ------------------------------------------- server-composed attribution
#
# `source_name` and `attribution` are composed by services/licensing.py and
# sent down with every result. They exist because the client used to hold its
# own copy of the source->wording mapping and the copy drifted: `nutritionix`
# reached the API and never reached the client, so metered rows rendered
# "SOURCE UNKNOWN" -- dropping a credit owed by contract, silently, in a way
# no user could detect. These tests are the guard on the replacement.


async def test_off_row_carries_open_food_facts_attribution(client, db_session):
    headers = await _register(client)
    await _food(db_session, "Attrib off", search_text="attribone thing",
                source="openfoodfacts", licence="odbl", tier=6)
    await db_session.commit()

    r = (await _search(client, headers, "attribone thing"))[0]
    assert r["source_name"] == "Open Food Facts"
    assert "Open Food Facts" in r["attribution"]
    assert "Open Database License (ODbL)" in r["attribution"]


async def test_usda_row_is_credited_public_domain_not_odbl(client, db_session):
    headers = await _register(client)
    await _food(db_session, "Attrib usda", search_text="attribtwo thing",
                source="usda_fdc", licence="public-domain", tier=2)
    await db_session.commit()

    r = (await _search(client, headers, "attribtwo thing"))[0]
    assert r["source_name"] == "USDA FoodData Central"
    assert "public domain" in r["attribution"]
    assert "ODbL" not in r["attribution"]
    assert "Open Food Facts" not in r["attribution"]


@pytest.mark.parametrize("source,licence", [
    ("curated", "user"),
    ("user", "user"),
    ("ai_estimated", "user"),
])
async def test_our_own_rows_carry_no_attribution(
    client, db_session, source, licence
):
    """`attribution: null` is the signal to render nothing.

    An empty string would render an empty notice with a divider above it, and
    labelling our own dish as somebody else's data is the error this whole
    feature exists to prevent.
    """
    headers = await _register(client)
    await _food(db_session, "Ours", search_text=f"ourrow {source}",
                source=source, licence=licence, tier=5)
    await db_session.commit()

    r = (await _search(client, headers, f"ourrow {source}"))[0]
    assert r["attribution"] is None
    assert r["source_name"] is not None       # we still know WHAT it is
    assert "Open Food Facts" not in (r["source_name"] or "")


async def test_metered_source_is_credited_rather_than_called_unknown(
    client, db_session
):
    """The regression that motivated moving this to the server."""
    headers = await _register(client)
    await _food(db_session, "Metered", search_text="meteredrow thing",
                source="nutritionix", licence="proprietary", tier=3)
    await db_session.commit()

    r = (await _search(client, headers, "meteredrow thing"))[0]
    assert r["source_name"] == "Nutritionix"
    assert "Nutritionix" in r["attribution"]
    assert "unknown" not in r["attribution"].lower()


async def test_a_row_with_an_unrecorded_licence_says_so(client, db_session):
    """Must not inherit ODbL from the source table.

    The row's own column is the authority; the mapping is only a fallback.
    """
    headers = await _register(client)
    await _food(db_session, "No licence", search_text="nolicrow thing",
                source="openfoodfacts", licence="unknown", tier=6)
    await db_session.commit()

    r = (await _search(client, headers, "nolicrow thing"))[0]
    assert "Open Food Facts" in r["attribution"]
    assert "licence not recorded" in r["attribution"]
    assert "ODbL" not in r["attribution"]


async def test_an_unparseable_licence_degrades_instead_of_500ing(
    client, db_session
):
    """`source_licence` is a plain text column, so a hand-edited or
    future value must not take search down."""
    headers = await _register(client)
    await _food(db_session, "Odd licence", search_text="oddlicrow thing",
                source="openfoodfacts", licence="cc-by-sa-9.9", tier=6)
    await db_session.commit()

    r = (await _search(client, headers, "oddlicrow thing"))[0]
    assert r["source_name"] == "Open Food Facts"
    assert "licence not recorded" in r["attribution"]
    # The stored value is still reported verbatim -- we do not rewrite data.
    assert r["source_licence"] == "cc-by-sa-9.9"


async def test_mixed_source_results_are_attributed_per_row(client, db_session):
    """The whole reason attribution is per row and not a blanket notice."""
    headers = await _register(client)
    await _food(db_session, "Mix off", search_text="mixattrib thing",
                source="openfoodfacts", licence="odbl")
    await _food(db_session, "Mix usda", search_text="mixattrib thing",
                source="usda_fdc", licence="public-domain")
    await _food(db_session, "Mix ours", search_text="mixattrib thing",
                source="curated", licence="user")
    await db_session.commit()

    rows = await _search(client, headers, "mixattrib thing")
    by_name = {r["source_name"]: r["attribution"] for r in rows}
    assert len(rows) == 3
    assert "Open Database License (ODbL)" in by_name["Open Food Facts"]
    assert "public domain" in by_name["USDA FoodData Central"]
    assert by_name["Trace"] is None
    # No row borrows another row's credit.
    assert "Open Food Facts" not in (by_name["USDA FoodData Central"] or "")


async def test_attribution_never_leaks_ids_urls_or_credentials(
    client, db_session
):
    headers = await _register(client)
    await _food(db_session, "Leak check", search_text="leakattrib thing",
                source="openfoodfacts", licence="odbl")
    await db_session.commit()

    r = (await _search(client, headers, "leakattrib thing"))[0]
    text_shown = f"{r['source_name']} {r['attribution']}"
    for banned in ("http://", "https://", "postgres", "@", "key", "token",
                   "password", r["id"]):
        assert banned not in text_shown.lower(), banned


async def test_attribution_fields_are_optional_for_older_clients(
    client, db_session
):
    """Additive and nullable: a client that has never heard of these fields
    keeps working, which is why they were added rather than replacing
    `source` and `source_licence`."""
    headers = await _register(client)
    await _food(db_session, "Back compat", search_text="backcompat thing",
                source="openfoodfacts", licence="odbl")
    await db_session.commit()

    r = (await _search(client, headers, "backcompat thing"))[0]
    for legacy in ("source", "source_licence", "verification_tier",
                   "matched_via", "matched_alias"):
        assert legacy in r, legacy


# ------------------------------------- attribution on every food-bearing route
#
# `/search` was the only endpoint that attributed anything. The other five
# built a FoodItemPublic directly and returned no credit at all -- including
# `/barcode/{barcode}`, which is the most Open-Food-Facts-heavy route there is:
# scanning a packaged product is precisely how an ODbL row reaches a screen.
# A credit that is correct on one route and missing on another is worse than
# one that is consistently wrong, because nobody notices.


async def test_barcode_lookup_carries_attribution(client, db_session):
    """The route where ODbL data most often surfaces."""
    headers = await _register(client)
    code = "5000112552126"
    await db_session.execute(text("""
        INSERT INTO food_items
            (id, source, name, barcode, calories, protein_g, carbs_g, fat_g,
             fiber_g, sugar_g, sodium_mg, saturated_fat_g, is_liquid,
             serving_sizes, countries, micronutrients, names_i18n,
             data_quality, is_verified, moderation_status, search_text,
             log_count, source_licence, verification_tier, name_normalized,
             created_at, updated_at)
        VALUES
            (:id, 'openfoodfacts', 'Scanned cola', :code, 42, 0, 10, 0,
             0, 10, 0, 0, true,
             '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, '{}'::jsonb,
             0.5, false, 'approved', 'scanned cola',
             0, 'odbl', 6, 'scanned cola', now(), now())
    """), {"id": str(uuid.uuid4()), "code": code})
    await db_session.commit()

    res = await client.get(f"/api/foods/barcode/{code}", headers=headers)
    assert res.status_code == 200, res.text
    item = res.json()["item"]
    assert item["source_name"] == "Open Food Facts"
    assert "Open Database License (ODbL)" in item["attribution"]
    assert item["source_licence"] == "odbl"


async def test_recent_foods_carry_attribution(client, db_session):
    """A re-logged food is displayed exactly like a searched one.

    Logged through the real endpoint rather than a hand-written INSERT: the
    snapshot columns on `meal_logs` are the router's business, and a fixture
    that guesses at them tests the fixture.
    """
    headers = await _register(client)
    fid = await _food(db_session, "Recent off", search_text="recentoff thing",
                      source="openfoodfacts", licence="odbl", tier=6)
    await db_session.commit()

    logged = await client.post("/api/meals/log", headers=headers,
                               json={"food_item_id": fid, "grams": 100})
    assert logged.status_code == 201, logged.text

    res = await client.get("/api/foods/recent", headers=headers)
    assert res.status_code == 200, res.text
    rows = [r for r in res.json() if r["id"] == fid]
    assert rows, "the logged food did not come back from /recent"
    assert rows[0]["source_name"] == "Open Food Facts"
    assert "ODbL" in rows[0]["attribution"]


async def test_a_custom_food_is_not_labelled_as_third_party_data(
    client, db_session
):
    headers = await _register(client)
    res = await client.post("/api/foods/custom", headers=headers, json={
        "name": "My own protein shake",
        "calories": 180, "protein_g": 30, "carbs_g": 5, "fat_g": 3,
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["source"] == "user"
    assert body["attribution"] is None
    assert body["source_name"] == "You"


def test_every_food_bearing_route_uses_the_same_serialiser():
    """Structural: nothing may build a FoodItemPublic by hand again.

    Asserted on the module rather than by exercising all six routes, because
    the failure mode is a NEW route added later that forgets -- and no test of
    the existing five would catch that.

    OVER THE AST, NOT OVER THE TEXT. A `src.count(...)` version of this test
    matched the phrase inside `_public`'s own docstring and failed on prose
    while the code was correct. A structural test that greps is a structural
    test that lies.
    """
    import ast
    import inspect

    from app.routers import foods as foods_module

    tree = ast.parse(inspect.getsource(foods_module))

    def calls_in(node) -> int:
        return sum(
            1
            for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "model_validate"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "FoodItemPublic"
        )

    total = calls_in(tree)
    inside = sum(
        calls_in(fn)
        for fn in ast.walk(tree)
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        and fn.name == "_public"
    )
    assert total == inside == 1, (
        f"{total - inside} food(s) are serialised outside _public(), so they "
        "will be returned without attribution"
    )


def test_an_unmapped_source_sends_no_composed_attribution():
    """The handoff contract, at its one dangerous edge.

    The client reads `source_name` as "this response carries composed
    attribution" and `attribution: null` as "nothing to credit". A placeholder
    name plus a null sentence would therefore make an UNKNOWN source render as
    SILENTLY OURS. Sending neither field makes the client fall back to its own
    table, which says SOURCE UNKNOWN.

    `test_every_source_is_mapped` means production cannot reach this. It is
    tested because "unreachable" and "safe when reached" are different claims.
    """
    from app.services.licensing import (
        DISPLAY_NAMES,
        attribution_line,
        display_name_for,
    )

    unmapped = "some_feed_added_next_year"
    assert unmapped not in DISPLAY_NAMES
    # What _public() sends for it:
    assert (display_name_for(unmapped) if unmapped in DISPLAY_NAMES else None) is None
    assert attribution_line(unmapped) is None
