"""The properties that make `/api/foods/search` fast, asserted without a clock.

WHY THERE IS NO LATENCY ASSERTION HERE
"search must take under 200 ms" passes on a warm page cache and fails on a
cold one, gets marked flaky, and is deleted six weeks later. The numbers live
in `app/scripts/bench_search.py`, which a human runs against the real
catalogue and reads. What is asserted here is the SHAPE of the work: one round
trip, a bounded candidate set, no N+1, and a cascade whose stages are ordered
and disjoint. Those are the things a well-meaning refactor breaks.

WHY THE CASCADE NEEDS ITS OWN TESTS
The direct arm is three gated stages -- prefix, then substring, then fuzzy --
where each later stage is skipped entirely if an earlier one already filled
the page. That is a 7.2x win on broad queries and it is also a new way to be
wrong: a mis-ordered merge would silently demote exact matches, and a
mis-written gate would drop results that should have been returned. Every
stage boundary below is a test.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event, text

from app.routers.foods import ARM_OVERFETCH, MAX_ARM_FETCH, SEARCH_SQL

pytestmark = pytest.mark.anyio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register(client) -> tuple[dict, str]:
    email = f"perf-{uuid.uuid4().hex[:10]}@example.com"
    res = await client.post("/api/auth/register", json={
        "email": email, "password": "hunter2-correct-horse", "name": "Perf"})
    assert res.status_code in (200, 201), res.text
    body = res.json()
    return _auth(body["access_token"]), body["user"]["id"]


async def _food(session, name, *, search_text=None, log_count=0, quality=0.5,
                source="curated", licence="user", tier=5,
                moderation="approved", owner=None) -> str:
    fid = str(uuid.uuid4())
    await session.execute(text("""
        INSERT INTO food_items
            (id, source, name, brand, calories, protein_g, carbs_g, fat_g,
             fiber_g, sugar_g, sodium_mg, saturated_fat_g, is_liquid,
             serving_sizes, countries, micronutrients, names_i18n,
             data_quality, is_verified, moderation_status, search_text,
             log_count, source_licence, verification_tier, name_normalized,
             created_by_user_id, created_at, updated_at)
        VALUES
            (:id, :source, :name, NULL, 100, 1, 1, 1,
             0, 0, 0, 0, false,
             '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, '{}'::jsonb,
             :quality, false, :moderation, :search_text,
             :log_count, :licence, :tier, :normalized, :owner, now(), now())
    """), {"id": fid, "source": source, "name": name, "quality": quality,
           "log_count": log_count, "moderation": moderation,
           "search_text": (search_text or name).lower(),
           "normalized": name.lower(), "licence": licence, "tier": tier,
           "owner": owner})
    return fid


async def _alias(session, food_id, normalized, *, is_active=True,
                 confidence=0.9, alias_type="regional") -> None:
    await session.execute(text("""
        INSERT INTO food_aliases
            (id, food_item_id, alias, normalized, lang, script, alias_type,
             source, confidence, is_active, created_at, updated_at)
        VALUES
            (:id, :fid, :norm, :norm, '', 'latn', :atype,
             'curated', :conf, :active, now(), now())
    """), {"id": str(uuid.uuid4()), "fid": food_id, "norm": normalized,
           "atype": alias_type, "conf": confidence, "active": is_active})


async def _search(client, headers, q, **params) -> list[dict]:
    res = await client.get("/api/foods/search", headers=headers,
                           params={"q": q, "remote": "false", **params})
    assert res.status_code == 200, res.text
    return res.json()["results"]


def _count_statements(db_engine):
    """Count statements actually sent to the server.

    Measured rather than asserted from reading the code, because an N+1 is
    exactly what a lazily-loaded attribute reintroduces silently.
    """
    box = {"n": 0, "sql": []}

    def _on(conn, cursor, statement, params, context, executemany):
        box["n"] += 1
        box["sql"].append(statement)

    event.listen(db_engine.sync_engine, "before_cursor_execute", _on)
    return box, lambda: event.remove(
        db_engine.sync_engine, "before_cursor_execute", _on
    )


# --------------------------------------------------------------- round trips


class TestOneRoundTrip:
    async def test_both_arms_travel_in_a_single_statement(
        self, client, db_session, db_engine
    ):
        """UNION ALL, not two queries and not a correlated subquery.

        The alias arm is what lets 'panir' find Paneer. Fetching it separately
        would double the round trips on every keystroke of a debounced search.
        """
        headers, _ = await _register(client)
        fid = await _food(db_session, "Paneer", search_text="paneer")
        await _alias(db_session, fid, "panir")
        await db_session.commit()

        box, stop = _count_statements(db_engine)
        try:
            results = await _search(client, headers, "panir")
        finally:
            stop()

        assert [r["name"] for r in results] == ["Paneer"]
        searches = [s for s in box["sql"] if "food_aliases" in s]
        assert len(searches) == 1, (
            f"the alias arm should ride along in the one search statement, "
            f"saw {len(searches)}"
        )
        assert "UNION ALL" in searches[0]

    async def test_query_count_does_not_grow_with_result_count(
        self, client, db_session, db_engine
    ):
        """The N+1 guard.

        Serialising a result must not cost a query per row -- neither for the
        food itself nor for its licence, which is why attribution is composed
        from an in-process table and not looked up.
        """
        headers, _ = await _register(client)
        for i in range(3):
            await _food(db_session, f"Nplus one {i}", search_text=f"nplusone {i}")
        await db_session.commit()

        box, stop = _count_statements(db_engine)
        try:
            few = await _search(client, headers, "nplusone 0")
        finally:
            stop()
        n_few = box["n"]

        for i in range(3, 25):
            await _food(db_session, f"Nplus many {i}", search_text="nplusmany")
        await db_session.commit()

        box, stop = _count_statements(db_engine)
        try:
            many = await _search(client, headers, "nplusmany")
        finally:
            stop()
        n_many = box["n"]

        assert len(many) > len(few) + 5, "fixture did not produce more results"
        assert n_many == n_few, (
            f"{len(few)} results cost {n_few} queries, {len(many)} cost "
            f"{n_many} -- the count must not depend on the result count"
        )


# ------------------------------------------------------------- bounded work


class TestBoundedCandidateSet:
    async def test_each_arm_is_capped_independently_of_the_match_count(
        self, client, db_session
    ):
        """A term matching thousands of rows still does bounded work.

        Each arm overfetches `limit * ARM_OVERFETCH` so ranking has something
        to choose between, capped at MAX_ARM_FETCH so a very popular term
        cannot turn one keystroke into a table scan's worth of transfer.
        """
        assert ARM_OVERFETCH >= 2, "ranking needs more candidates than it returns"
        assert MAX_ARM_FETCH >= 50 * ARM_OVERFETCH, (
            "the cap must not bind below the maximum allowed limit, or a "
            "limit=50 search would silently get a thinner candidate set"
        )

        headers, _ = await _register(client)
        for i in range(40):
            await _food(db_session, f"Bounded {i}", search_text="boundedterm")
        await db_session.commit()

        results = await _search(client, headers, "boundedterm", limit=5)
        assert len(results) == 5

    async def test_a_bigger_limit_returns_more_not_a_different_ordering(
        self, client, db_session
    ):
        """The overfetch must not reorder the head of the page.

        If it did, scrolling would reshuffle rows the user had already read.
        """
        headers, _ = await _register(client)
        for i in range(12):
            await _food(db_session, f"Stable {i}", search_text=f"stableterm {i}",
                        log_count=i)
        await db_session.commit()

        small = [r["id"] for r in await _search(client, headers, "stableterm", limit=5)]
        big = [r["id"] for r in await _search(client, headers, "stableterm", limit=10)]
        assert big[: len(small)] == small


# ------------------------------------------------------ the cascade's order


class TestCascadeOrdering:
    """Prefix beats substring beats fuzzy -- unconditionally.

    That ordering is not a nicety: it is the premise the whole optimisation
    rests on. The later stages are only safe to skip BECAUSE no row in them
    can ever outrank a row in an earlier one.
    """

    async def test_a_prefix_match_outranks_a_substring_match(
        self, client, db_session
    ):
        headers, _ = await _register(client)
        await _food(db_session, "Masala dosa", search_text="masala dosa")
        await _food(db_session, "Dosa batter", search_text="dosa batter")
        await db_session.commit()

        names = [r["name"] for r in await _search(client, headers, "dosa")]
        assert names.index("Dosa batter") < names.index("Masala dosa")

    async def test_a_substring_match_outranks_a_fuzzy_only_match(
        self, client, db_session
    ):
        headers, _ = await _register(client)
        await _food(db_session, "Paneer tikka", search_text="paneer tikka")
        await _food(db_session, "Panner tika", search_text="panner tika")
        await db_session.commit()

        names = [r["name"] for r in await _search(client, headers, "paneer")]
        assert names[0] == "Paneer tikka", names

    async def test_a_full_prefix_page_does_not_lose_the_exact_match(
        self, client, db_session
    ):
        """The gate's worst case: enough prefix rows to skip both later
        stages. The row named exactly the query must still come first."""
        headers, _ = await _register(client)
        for i in range(120):
            await _food(db_session, f"Gatecheck {i}", search_text=f"gatecheck {i}")
        await _food(db_session, "Gatecheck", search_text="gatecheck")
        await db_session.commit()

        results = await _search(client, headers, "gatecheck")
        assert results[0]["name"] == "Gatecheck"

    async def test_fuzzy_still_runs_when_the_earlier_stages_are_thin(
        self, client, db_session
    ):
        """Typo tolerance is the reason the fuzzy stage exists.

        A gate that skipped it too eagerly would turn 'panner tika' into no
        results -- silently, with a 200.
        """
        headers, _ = await _register(client)
        await _food(db_session, "Paneer tikka", search_text="paneer tikka masala")
        await db_session.commit()

        names = [r["name"] for r in await _search(client, headers, "panner tika")]
        assert "Paneer tikka" in names

    async def test_a_row_matching_several_stages_appears_once(
        self, client, db_session
    ):
        """The stages are disjoint by construction (`NOT ILIKE`).

        Without that, one row could occupy two of the page's slots and push a
        different food off the end.
        """
        headers, _ = await _register(client)
        await _food(db_session, "Overlap", search_text="overlapterm overlapterm")
        await db_session.commit()

        results = await _search(client, headers, "overlapterm")
        assert [r["name"] for r in results].count("Overlap") == 1

    async def test_repeated_identical_searches_return_identical_results(
        self, client, db_session
    ):
        """Determinism, including at the LIMIT boundary.

        Before the `f.id` tiebreak the SQL had no total order, so rows tied on
        every sort component were returned in whatever order the executor
        produced -- and under a parallel plan that varied between runs. On the
        live catalogue, 'mix' returned a different result SET on three
        consecutive executions of the same query.
        """
        headers, _ = await _register(client)
        for i in range(30):
            await _food(db_session, f"Tie {i}", search_text="tieterm",
                        log_count=0, quality=0.5)
        await db_session.commit()

        runs = [
            tuple(r["id"] for r in await _search(client, headers, "tieterm"))
            for _ in range(3)
        ]
        assert len(set(runs)) == 1, "the same query returned different pages"


# ------------------------------------------- predicates that must not move


class TestVisibilityPredicatesSurvivedTheRewrite:
    """Performance work is where privacy filters get lost.

    Each stage of the cascade repeats the ownership clause, so each stage is
    a place it could be dropped. These assert it in all three.
    """

    async def test_another_users_pending_food_is_never_visible(
        self, client, db_session
    ):
        headers_a, _ = await _register(client)
        headers_b, uid_b = await _register(client)
        await _food(db_session, "Bs private food", search_text="privatefood b",
                    moderation="pending", owner=uid_b, source="user")
        await db_session.commit()

        assert await _search(client, headers_a, "privatefood b") == []

    async def test_your_own_pending_food_is_visible_to_you(
        self, client, db_session
    ):
        """A private library nobody can search is not a library."""
        headers_b, uid_b = await _register(client)
        await _food(db_session, "My private food", search_text="privatefood mine",
                    moderation="pending", owner=uid_b, source="user")
        await db_session.commit()

        names = [r["name"] for r in await _search(client, headers_b, "privatefood mine")]
        assert names == ["My private food"]

    async def test_a_pending_food_is_hidden_from_the_fuzzy_stage_too(
        self, client, db_session
    ):
        """Reached by typo rather than by prefix -- a different stage, and
        historically a different place to forget the filter."""
        headers_a, _ = await _register(client)
        headers_b, uid_b = await _register(client)
        await _food(db_session, "Panner tika", search_text="panner tika",
                    moderation="pending", owner=uid_b, source="user")
        await db_session.commit()

        assert await _search(client, headers_a, "paneer tikka") == []

    async def test_inactive_aliases_never_resurface(self, client, db_session):
        headers, _ = await _register(client)
        fid = await _food(db_session, "Poha", search_text="poha")
        await _alias(db_session, fid, "avalakki", is_active=False)
        await db_session.commit()

        assert await _search(client, headers, "avalakki") == []

    async def test_the_alias_arm_still_requires_is_active_after_the_rewrite(
        self, client, db_session
    ):
        """One active, one retired, same food: exactly one path may match."""
        headers, _ = await _register(client)
        fid = await _food(db_session, "Poha", search_text="poha")
        await _alias(db_session, fid, "kandapoha", is_active=True)
        await _alias(db_session, fid, "retiredpoha", is_active=False)
        await db_session.commit()

        assert [r["name"] for r in await _search(client, headers, "kandapoha")] == ["Poha"]
        assert await _search(client, headers, "retiredpoha") == []


# ------------------------------------------------------ the statement itself


class TestStatementShape:
    """Structural assertions on SEARCH_SQL.

    Cheap, and they fail on the specific rewrites that would quietly undo the
    optimisation or the safety of it.
    """

    def test_the_gates_are_present(self):
        """Remove these and every stage runs on every query."""
        sql = str(SEARCH_SQL)
        assert "(SELECT count(*) FROM prefix_hits) < :fetch" in sql
        assert "(SELECT count(*) FROM prefix_hits)" in sql
        assert "+ (SELECT count(*) FROM substring_hits) < :fetch" in sql

    def test_the_stages_are_disjoint(self):
        sql = str(SEARCH_SQL)
        assert "NOT ILIKE :prefix" in sql
        assert "NOT ILIKE :contains" in sql

    def test_every_arm_repeats_the_ownership_clause(self):
        """Four places to forget it: three direct stages plus the alias join."""
        sql = str(SEARCH_SQL)
        assert sql.count("f.created_by_user_id = :uid") == 4
        assert sql.count("f.moderation_status = 'approved'") == 4

    def test_the_alias_arm_still_filters_on_is_active(self):
        assert "a.is_active" in str(SEARCH_SQL)

    def test_the_ordering_is_total(self):
        """`f.id` / `u.id` last, so no two runs can differ."""
        sql = str(SEARCH_SQL)
        assert "f.data_quality DESC, f.id" in sql
        assert "u.data_quality DESC,\n          u.id" in sql

    def test_it_is_still_one_statement(self):
        """Two statements would be two round trips on every keystroke.

        Comments are stripped first -- the prose in this statement contains
        semicolons, and matching on prose rather than on code is how a
        structural test turns into a false alarm somebody eventually deletes.
        """
        code = "\n".join(
            line.split("--")[0] for line in str(SEARCH_SQL).splitlines()
        ).strip().rstrip(";")
        assert ";" not in code
        # 2 merges of the 3 direct stages, plus the direct/alias merge.
        assert code.count("UNION ALL") == 3
