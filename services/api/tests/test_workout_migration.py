"""Does f6a9c2e47d85 build the workout-programming schema, and reverse cleanly?

WHY THIS EXISTS, SEPARATELY FROM test_migrations.py
That file proves the migration chain as a whole builds the models. This one
asks the two questions specific to landing a schema change next to 578,773
nutrition rows:

  1. Do the constraints actually bite? A CHECK that exists but never fires is
     worse than no CHECK, because it buys false confidence. Every bound in
     WORKOUT_SCHEMA_DESIGN.md gets a row that must be rejected.
  2. Is the nutrition catalogue provably untouched -- across the upgrade AND
     across the downgrade? The migration is additive by construction, so this
     should be boring. It is asserted anyway, because "should be" is exactly
     the reasoning that loses data.

IT NEVER TOUCHES `trace` OR `trace_test`. Every fixture builds a uniquely
named scratch database via the harness in test_migrations.py, and that
harness asserts the name before anything destructive runs. The only
non-scratch connection anywhere is to `postgres`, to issue CREATE DATABASE.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# The scratch-database harness, reused rather than reimplemented. Improvising
# a second one would mean a second chance to get the guard wrong.
from test_migrations import (  # noqa: E402
    SEED_ROWS,
    _alembic,
    _assert_ok,
    _scratch_database,
    _seed,
)

#: The revision this migration builds on -- the nutrition checkpoint.
BEFORE_WORKOUT = "e4f7b0d25c63"

#: The revision under test.
WORKOUT_REV = "f6a9c2e47d85"

NEW_TABLES = (
    "exercise_attributes",
    "exercise_substitutions",
    "training_profiles",
    "training_programmes",
    "programme_days",
    "ai_generations",
    "readiness_checkins",
    "planned_sessions",
    "prescribed_exercises",
)

NEW_INDEXES = (
    "ix_exattr_pattern",
    "ix_exattr_class",
    "ix_exsub_from",
    "uq_training_profile_user",
    "ix_programme_user_status",
    "uq_active_programme_per_user",
    "uq_programme_day",
    "ix_planned_user_date",
    "ix_planned_session",
    "uq_planned_day",
    "uq_prescribed_order",
    "ix_prescribed_session",
    "uq_readiness_user_date",
    "ix_readiness_user_date",
    "ix_aigen_user_time",
)

NEW_CHECKS = (
    "ck_exattr_movement_pattern",
    "ck_exattr_exercise_class",
    "ck_exattr_rep_min",
    "ck_exattr_rep_order",
    "ck_exattr_rep_max",
    "ck_exattr_rest",
    "ck_exattr_fatigue",
    "ck_exsub_not_self",
    "ck_exsub_rank",
    "ck_exsub_reason",
    "ck_profile_days",
    "ck_profile_minutes",
    "ck_programme_days",
    "ck_programme_status",
    "ck_programme_generated_by",
    "ck_programme_archived_at",
    "ck_programme_day_index",
    "ck_programme_day_minutes",
    "ck_planned_status",
    "ck_planned_generated_by",
    "ck_planned_minutes",
    "ck_planned_generation_ref",
    "ck_prescribed_sets",
    "ck_prescribed_rep_min",
    "ck_prescribed_rep_order",
    "ck_prescribed_rep_max",
    "ck_prescribed_rir",
    "ck_prescribed_rest",
    "ck_prescribed_order_index",
    "ck_prescribed_weight",
    "ck_prescribed_status",
    "ck_prescribed_replacement",
    "ck_readiness_energy",
    "ck_readiness_sleep",
    "ck_readiness_soreness",
    "ck_readiness_stress",
    "ck_readiness_minutes",
    "ck_aigen_kind",
    "ck_aigen_validation_status",
    "ck_aigen_rejection_reason",
)

#: (constraint, table, referenced table, delete rule). The delete rule is the
#: half that matters: RESTRICT vs CASCADE here is the difference between a
#: catalogue cleanup failing loudly and it silently erasing training history.
EXPECTED_FKS = (
    ("fk_exattr_exercise", "exercise_attributes", "exercises", "CASCADE"),
    ("fk_exsub_from", "exercise_substitutions", "exercises", "CASCADE"),
    ("fk_exsub_to", "exercise_substitutions", "exercises", "CASCADE"),
    ("fk_training_profile_user", "training_profiles", "users", "CASCADE"),
    ("fk_programme_user", "training_programmes", "users", "CASCADE"),
    ("fk_programme_day_programme", "programme_days", "training_programmes", "CASCADE"),
    ("fk_planned_user", "planned_sessions", "users", "CASCADE"),
    ("fk_planned_programme_day", "planned_sessions", "programme_days", "SET NULL"),
    ("fk_planned_session_ref", "planned_sessions", "workout_sessions", "SET NULL"),
    ("fk_planned_generation", "planned_sessions", "ai_generations", "SET NULL"),
    (
        "fk_prescribed_planned_session",
        "prescribed_exercises",
        "planned_sessions",
        "CASCADE",
    ),
    ("fk_prescribed_exercise", "prescribed_exercises", "exercises", "RESTRICT"),
    ("fk_prescribed_replacement", "prescribed_exercises", "exercises", "RESTRICT"),
    ("fk_readiness_user", "readiness_checkins", "users", "CASCADE"),
    ("fk_aigen_user", "ai_generations", "users", "CASCADE"),
)

#: Aliases written BEFORE the workout migration runs. The food rows themselves
#: come from test_migrations._seed, whose column list is already proven correct
#: -- reinventing it here would only be a second thing to get wrong.
ALIAS_SEED = """
INSERT INTO food_aliases (id, food_item_id, alias, normalized, lang, script,
                          alias_type, source, confidence, is_active,
                          created_at, updated_at)
VALUES ('wk-alias-1','seed-curated-idli','idly','idly','','latn',
        'misspelling','ai',0.6,true, now(), now());
INSERT INTO food_aliases (id, food_item_id, alias, normalized, lang, script,
                          alias_type, source, confidence, is_active,
                          created_at, updated_at)
VALUES ('wk-alias-2','seed-usda-with-id','egg','egg','','latn',
        'canonical','curated',1.0,true, now(), now());
"""

#: Users, an exercise and a performed session -- the FK targets every
#: programming row needs.
WORKOUT_SEED = """
INSERT INTO users (id, email, password_hash, goal_type, program_type,
                   activity_multiplier, lifting_experience_months, is_pro,
                   timezone, created_at, updated_at)
VALUES ('wk-user-a','a@example.test','x',CAST('maintain' AS goaltype),CAST('collaborative' AS programtype),
        1.45, 0, false, 'UTC', now(), now()),
       ('wk-user-b','b@example.test','x',CAST('maintain' AS goaltype),CAST('collaborative' AS programtype),
        1.45, 0, false, 'UTC', now(), now());

INSERT INTO exercises (id, name, muscle_group, equipment, is_compound)
VALUES ('wk-ex-1','Back Squat','quads','barbell',true),
       ('wk-ex-2','Leg Press','quads','machine',false);

INSERT INTO workout_sessions (id, user_id, started_at)
VALUES ('wk-sess-1','wk-user-a', now());
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _exec(url: str, sql: str, **params):
    """Run one or more statements in a single transaction.

    Split on `;` because asyncpg prepares every statement and refuses more
    than one per prepare ("cannot insert multiple commands into a prepared
    statement"). None of the fixture SQL contains a semicolon inside a
    literal, so a plain split is sufficient and keeps the fixtures readable.
    """
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            result = None
            for stmt in statements:
                result = await conn.execute(text(stmt), params or None)
            return result
    finally:
        await engine.dispose()


async def _scalar(url: str, sql: str, **params):
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql), params or None)).scalar()
    finally:
        await engine.dispose()


async def _names(url: str, sql: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return {r[0] for r in (await conn.execute(text(sql))).all()}
    finally:
        await engine.dispose()


async def _tables(url: str) -> set[str]:
    return await _names(
        url, "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    )


async def _indexes(url: str) -> set[str]:
    return await _names(
        url, "SELECT indexname FROM pg_indexes WHERE schemaname='public'"
    )


async def _constraints(url: str) -> set[str]:
    return await _names(url, "SELECT conname FROM pg_constraint")


async def _nutrition_fingerprint(url: str) -> dict:
    """Counts plus a checksum over every protected column.

    A count alone would miss an UPDATE. The checksum is ordered by id so it is
    stable regardless of physical row order.
    """
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            items = (
                await conn.execute(text("SELECT count(*) FROM food_items"))
            ).scalar()
            aliases = (
                await conn.execute(text("SELECT count(*) FROM food_aliases"))
            ).scalar()
            checksum = (
                await conn.execute(
                    text(
                        "SELECT md5(string_agg(concat_ws('|', id, name, barcode, "
                        "names_i18n::text, search_text, gtin14, name_normalized, "
                        "source_licence, verification_tier::text), '#' "
                        "ORDER BY id)) FROM food_items"
                    )
                )
            ).scalar()
            alias_checksum = (
                await conn.execute(
                    text(
                        "SELECT md5(string_agg(concat_ws('|', id, food_item_id, "
                        "alias, normalized, lang, alias_type, source), '#' "
                        "ORDER BY id)) FROM food_aliases"
                    )
                )
            ).scalar()
            cols = {
                r[0]
                for r in (
                    await conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name='food_items'"
                        )
                    )
                ).all()
            }
        return {
            "food_items": items,
            "food_aliases": aliases,
            "checksum": checksum,
            "alias_checksum": alias_checksum,
            "food_item_columns": cols,
        }
    finally:
        await engine.dispose()


async def _seed_programming(url: str) -> None:
    """A complete valid graph: profile, programme, day, session, prescription."""
    await _exec(
        url,
        """
        INSERT INTO training_profiles (id, user_id, created_at, updated_at)
        VALUES ('wk-prof-a','wk-user-a', now(), now());

        INSERT INTO training_programmes
               (id, user_id, name, split_type, days_per_week, status,
                started_at, created_at, updated_at)
        VALUES ('wk-prog-a','wk-user-a','Upper/Lower','upper_lower',4,'active',
                now(), now(), now());

        INSERT INTO programme_days (id, programme_id, day_index, label, created_at)
        VALUES ('wk-day-0','wk-prog-a',0,'Upper A', now());

        INSERT INTO planned_sessions
               (id, user_id, programme_day_id, scheduled_for, status,
                created_at, updated_at)
        VALUES ('wk-plan-1','wk-user-a','wk-day-0', CURRENT_DATE,'planned',
                now(), now());

        INSERT INTO prescribed_exercises
               (id, planned_session_id, exercise_id, order_index, sets,
                rep_min, rep_max, created_at, updated_at)
        VALUES ('wk-presc-1','wk-plan-1','wk-ex-1',0,3,6,8, now(), now());
        """,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _build(url: str) -> dict:
    """Seed at the nutrition checkpoint, fingerprint, then apply the revision."""
    _assert_ok(_alembic(url, "upgrade", BEFORE_WORKOUT), "upgrade to pre-workout")
    await _seed(url)
    await _exec(url, ALIAS_SEED)
    await _exec(url, WORKOUT_SEED)
    before = await _nutrition_fingerprint(url)
    _assert_ok(_alembic(url, "upgrade", WORKOUT_REV), "upgrade to workout rev")
    # A complete valid graph, so every later test has FK targets to point at.
    await _seed_programming(url)
    return before


@pytest.fixture(scope="module")
async def shared_db():
    """One scratch database for every test that cannot change it.

    WHY MODULE SCOPE. Each build is a CREATE DATABASE plus the full migration
    chain -- seconds apiece, and there are fifty-odd tests here. Every test
    using this fixture either only reads, or performs an insert that the
    database is expected to REJECT, which rolls back and leaves nothing
    behind. Tests that successfully mutate take `mutable_db` instead.
    """
    async with _scratch_database() as url:
        before = await _build(url)
        yield url, before


@pytest.fixture
async def mutable_db():
    """A fresh database for tests whose writes are expected to succeed."""
    async with _scratch_database() as url:
        before = await _build(url)
        yield url, before


@pytest.fixture(scope="module")
async def downgraded():
    """Applied for real, then genuinely reversed -- with data present."""
    async with _scratch_database() as url:
        before = await _build(url)
        _assert_ok(_alembic(url, "downgrade", BEFORE_WORKOUT), "downgrade")
        yield url, before


# ---------------------------------------------------------------------------
# 1-3. The revision applies, from the revision it claims
# ---------------------------------------------------------------------------


class TestUpgrade:
    def test_the_migration_declares_the_nutrition_checkpoint_as_its_parent(self):
        """A static read, so it fails without a database being involved."""
        import pathlib

        src = next(
            pathlib.Path(__file__).resolve().parents[1].glob(
                f"alembic/versions/{WORKOUT_REV}_*.py"
            )
        ).read_text(encoding="utf-8")
        assert f'down_revision: Union[str, Sequence[str], None] = "{BEFORE_WORKOUT}"' in src

    async def test_the_starting_revision_is_the_nutrition_checkpoint(
        self, shared_db
    ):
        """The fixture upgraded to BEFORE_WORKOUT first; head is now this rev."""
        url, _ = shared_db
        current = await _scalar(url, "SELECT version_num FROM alembic_version")
        assert current == WORKOUT_REV

    async def test_all_nine_tables_exist(self, shared_db):
        url, _ = shared_db
        found = await _tables(url)
        missing = set(NEW_TABLES) - found
        assert not missing, f"migration did not create: {sorted(missing)}"

    async def test_it_created_nothing_else(self, shared_db):
        """Nine tables, not ten. Catches a stray CREATE nobody reviewed."""
        url, _ = shared_db
        async with _scratch_database() as clean:
            _assert_ok(_alembic(clean, "upgrade", BEFORE_WORKOUT), "clean baseline")
            baseline = await _tables(clean)
        after = await _tables(url)
        assert after - baseline == set(NEW_TABLES)


# ---------------------------------------------------------------------------
# 4-5, 11. Indexes, constraints, foreign keys -- by name
# ---------------------------------------------------------------------------


class TestSchemaObjects:
    async def test_every_expected_index_exists(self, shared_db):
        url, _ = shared_db
        found = await _indexes(url)
        missing = set(NEW_INDEXES) - found
        assert not missing, f"missing indexes: {sorted(missing)}"

    async def test_the_active_programme_index_is_unique_and_partial(
        self, shared_db
    ):
        """THE ONE THAT ENFORCES ONE ACTIVE PROGRAMME.

        Rebuilt without the WHERE clause it would forbid a user from ever
        having a second programme, archived or not. Rebuilt without UNIQUE it
        would enforce nothing at all. Both failures leave the index present,
        so existence alone proves nothing.
        """
        url, _ = shared_db
        ddl = await _scalar(
            url,
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname='uq_active_programme_per_user'",
        )
        assert "UNIQUE INDEX" in ddl, ddl
        assert "WHERE (status = 'active'::text)" in ddl, ddl

    async def test_every_expected_check_constraint_exists(self, shared_db):
        url, _ = shared_db
        found = await _constraints(url)
        missing = set(NEW_CHECKS) - found
        assert not missing, f"missing CHECK constraints: {sorted(missing)}"

    async def test_every_ownership_foreign_key_exists_with_its_delete_rule(
        self, shared_db
    ):
        url, _ = shared_db
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text(
                            "SELECT rc.constraint_name, tc.table_name, "
                            "       ccu.table_name AS refs, rc.delete_rule "
                            "FROM information_schema.referential_constraints rc "
                            "JOIN information_schema.table_constraints tc "
                            "  ON tc.constraint_name = rc.constraint_name "
                            "JOIN information_schema.constraint_column_usage ccu "
                            "  ON ccu.constraint_name = rc.constraint_name "
                            "WHERE rc.constraint_name LIKE 'fk_%'"
                        )
                    )
                ).all()
        finally:
            await engine.dispose()
        found = {(r[0], r[1], r[2], r[3]) for r in rows}
        missing = set(EXPECTED_FKS) - found
        assert not missing, f"missing or mis-ruled FKs: {sorted(missing)}"


# ---------------------------------------------------------------------------
# 12. A valid graph inserts
# ---------------------------------------------------------------------------


class TestValidFixtures:
    async def test_a_complete_valid_graph_inserts(self, mutable_db):
        url, _ = mutable_db
        assert await _scalar(url, "SELECT count(*) FROM prescribed_exercises") == 1

    async def test_an_archived_programme_frees_the_active_slot(
        self, mutable_db
    ):
        """Archival is the supported path, so it must actually work."""
        url, _ = mutable_db
        await _exec(
            url,
            "UPDATE training_programmes SET status='archived', archived_at=now() "
            "WHERE id='wk-prog-a'",
        )
        await _exec(
            url,
            "INSERT INTO training_programmes (id, user_id, name, split_type, "
            "days_per_week, status, started_at, created_at, updated_at) "
            "VALUES ('wk-prog-b','wk-user-a','PPL','ppl',6,'active', now(), "
            "now(), now())",
        )
        assert await _scalar(url, "SELECT count(*) FROM training_programmes") == 2

    async def test_starting_a_session_links_plan_to_performance(
        self, mutable_db
    ):
        """The plan -> performance arrow, which is the point of the table."""
        url, _ = mutable_db
        await _exec(
            url,
            "UPDATE planned_sessions SET session_id='wk-sess-1', status='active' "
            "WHERE id='wk-plan-1'",
        )
        assert (
            await _scalar(
                url, "SELECT session_id FROM planned_sessions WHERE id='wk-plan-1'"
            )
            == "wk-sess-1"
        )

    async def test_deleting_the_performed_session_leaves_the_plan_standing(
        self, mutable_db
    ):
        """SET NULL, not CASCADE: intent survives the deletion of the record."""
        url, _ = mutable_db
        await _exec(
            url, "UPDATE planned_sessions SET session_id='wk-sess-1' WHERE id='wk-plan-1'"
        )
        await _exec(url, "DELETE FROM workout_sessions WHERE id='wk-sess-1'")
        row = await _scalar(
            url, "SELECT session_id FROM planned_sessions WHERE id='wk-plan-1'"
        )
        assert row is None
        assert await _scalar(url, "SELECT count(*) FROM planned_sessions") == 1


# ---------------------------------------------------------------------------
# 6-10, 13. Every constraint must actually bite
# ---------------------------------------------------------------------------


#: (label, SQL). Each must be REJECTED. A CHECK that exists but never fires is
#: worse than no CHECK, so every bound in the design gets a row here.
INVALID_ROWS: tuple[tuple[str, str], ...] = (
    (
        "prescribed sets = 0",
        "INSERT INTO prescribed_exercises (id, planned_session_id, exercise_id,"
        " order_index, sets, rep_min, rep_max, created_at, updated_at)"
        " VALUES ('bad','wk-plan-1','wk-ex-1',1,0,6,8, now(), now())",
    ),
    (
        "prescribed sets = 13",
        "INSERT INTO prescribed_exercises (id, planned_session_id, exercise_id,"
        " order_index, sets, rep_min, rep_max, created_at, updated_at)"
        " VALUES ('bad','wk-plan-1','wk-ex-1',1,13,6,8, now(), now())",
    ),
    (
        "rep_min > rep_max",
        "INSERT INTO prescribed_exercises (id, planned_session_id, exercise_id,"
        " order_index, sets, rep_min, rep_max, created_at, updated_at)"
        " VALUES ('bad','wk-plan-1','wk-ex-1',1,3,10,5, now(), now())",
    ),
    (
        "rep_max = 51",
        "INSERT INTO prescribed_exercises (id, planned_session_id, exercise_id,"
        " order_index, sets, rep_min, rep_max, created_at, updated_at)"
        " VALUES ('bad','wk-plan-1','wk-ex-1',1,3,6,51, now(), now())",
    ),
    (
        "target_rir = 7",
        "INSERT INTO prescribed_exercises (id, planned_session_id, exercise_id,"
        " order_index, sets, rep_min, rep_max, target_rir, created_at, updated_at)"
        " VALUES ('bad','wk-plan-1','wk-ex-1',1,3,6,8,7, now(), now())",
    ),
    (
        "rest_seconds = 10",
        "INSERT INTO prescribed_exercises (id, planned_session_id, exercise_id,"
        " order_index, sets, rep_min, rep_max, rest_seconds, created_at, updated_at)"
        " VALUES ('bad','wk-plan-1','wk-ex-1',1,3,6,8,10, now(), now())",
    ),
    (
        "negative order_index",
        "INSERT INTO prescribed_exercises (id, planned_session_id, exercise_id,"
        " order_index, sets, rep_min, rep_max, created_at, updated_at)"
        " VALUES ('bad','wk-plan-1','wk-ex-1',-1,3,6,8, now(), now())",
    ),
    (
        "suggested weight of zero",
        "INSERT INTO prescribed_exercises (id, planned_session_id, exercise_id,"
        " order_index, sets, rep_min, rep_max, suggested_weight_kg, created_at,"
        " updated_at)"
        " VALUES ('bad','wk-plan-1','wk-ex-1',1,3,6,8,0, now(), now())",
    ),
    (
        "duplicate order_index in one session",
        "INSERT INTO prescribed_exercises (id, planned_session_id, exercise_id,"
        " order_index, sets, rep_min, rep_max, created_at, updated_at)"
        " VALUES ('bad','wk-plan-1','wk-ex-2',0,3,6,8, now(), now())",
    ),
    (
        "status replaced with no replacement",
        "INSERT INTO prescribed_exercises (id, planned_session_id, exercise_id,"
        " order_index, sets, rep_min, rep_max, status, created_at, updated_at)"
        " VALUES ('bad','wk-plan-1','wk-ex-1',1,3,6,8,'replaced', now(), now())",
    ),
    (
        "days_per_week = 8",
        "INSERT INTO training_profiles (id, user_id, days_per_week, created_at,"
        " updated_at) VALUES ('bad','wk-user-b',8, now(), now())",
    ),
    (
        "preferred_minutes = 5",
        "INSERT INTO training_profiles (id, user_id, preferred_minutes, created_at,"
        " updated_at) VALUES ('bad','wk-user-b',5, now(), now())",
    ),
    (
        "day_index = 7",
        "INSERT INTO programme_days (id, programme_id, day_index, label, created_at)"
        " VALUES ('bad','wk-prog-a',7,'Nope', now())",
    ),
    (
        "archived status without archived_at",
        "INSERT INTO training_programmes (id, user_id, name, split_type,"
        " days_per_week, status, started_at, created_at, updated_at)"
        " VALUES ('bad','wk-user-b','X','ppl',3,'archived', now(), now(), now())",
    ),
    (
        "unknown programme status",
        "INSERT INTO training_programmes (id, user_id, name, split_type,"
        " days_per_week, status, started_at, created_at, updated_at)"
        " VALUES ('bad','wk-user-b','X','ppl',3,'bogus', now(), now(), now())",
    ),
    (
        "readiness energy = 6",
        "INSERT INTO readiness_checkins (id, user_id, for_date, energy, created_at,"
        " updated_at) VALUES ('bad','wk-user-a', CURRENT_DATE, 6, now(), now())",
    ),
    (
        "readiness energy = 0",
        "INSERT INTO readiness_checkins (id, user_id, for_date, energy, created_at,"
        " updated_at) VALUES ('bad','wk-user-a', CURRENT_DATE, 0, now(), now())",
    ),
    (
        "readiness stress = 9",
        "INSERT INTO readiness_checkins (id, user_id, for_date, stress, created_at,"
        " updated_at) VALUES ('bad','wk-user-a', CURRENT_DATE, 9, now(), now())",
    ),
    (
        "two readiness check-ins for one day",
        "INSERT INTO readiness_checkins (id, user_id, for_date, created_at,"
        " updated_at) VALUES ('r1','wk-user-a', CURRENT_DATE, now(), now()),"
        " ('r2','wk-user-a', CURRENT_DATE, now(), now())",
    ),
    (
        "template session citing an AI generation",
        "INSERT INTO planned_sessions (id, user_id, scheduled_for, generated_by,"
        " generation_id, created_at, updated_at)"
        " VALUES ('bad','wk-user-a', CURRENT_DATE,'template','nope', now(), now())",
    ),
    (
        "unknown planned-session status",
        "INSERT INTO planned_sessions (id, user_id, scheduled_for, status,"
        " created_at, updated_at)"
        " VALUES ('bad','wk-user-a', CURRENT_DATE,'bogus', now(), now())",
    ),
    (
        "rejected AI generation with no reason",
        "INSERT INTO ai_generations (id, user_id, kind, model, prompt_digest,"
        " validation_status, created_at)"
        " VALUES ('bad','wk-user-a','session','m','d','rejected', now())",
    ),
    (
        "accepted AI generation carrying a rejection reason",
        "INSERT INTO ai_generations (id, user_id, kind, model, prompt_digest,"
        " validation_status, rejection_reason, created_at)"
        " VALUES ('bad','wk-user-a','session','m','d','accepted','why', now())",
    ),
    (
        "exercise attribute with inverted rep range",
        "INSERT INTO exercise_attributes (exercise_id, movement_pattern,"
        " exercise_class, default_rep_min, default_rep_max, created_at, updated_at)"
        " VALUES ('wk-ex-1','squat','compound',12,6, now(), now())",
    ),
    (
        "exercise attribute with unknown movement pattern",
        "INSERT INTO exercise_attributes (exercise_id, movement_pattern,"
        " exercise_class, default_rep_min, default_rep_max, created_at, updated_at)"
        " VALUES ('wk-ex-1','wiggle','compound',6,12, now(), now())",
    ),
    (
        "substitution ranked 0",
        "INSERT INTO exercise_substitutions (id, from_exercise_id, to_exercise_id,"
        " reason, rank, created_at)"
        " VALUES ('bad','wk-ex-1','wk-ex-2','equipment',0, now())",
    ),
)


class TestConstraintsBite:
    @pytest.mark.parametrize("label,sql", INVALID_ROWS, ids=[r[0] for r in INVALID_ROWS])
    async def test_invalid_rows_are_rejected(self, shared_db, label, sql):
        url, _ = shared_db
        with pytest.raises(Exception) as exc:
            await _exec(url, sql)
        # A constraint violation, not an unrelated error such as a typo in the
        # fixture SQL -- otherwise this test would pass for the wrong reason.
        assert any(
            s in str(exc.value)
            for s in ("violates check constraint", "violates unique constraint",
                      "violates foreign key constraint", "duplicate key value")
        ), f"{label} failed for the wrong reason: {exc.value}"

    async def test_one_active_programme_per_user_is_enforced(
        self, shared_db
    ):
        """The partial unique index, proven by collision rather than by DDL."""
        url, _ = shared_db
        with pytest.raises(Exception) as exc:
            await _exec(
                url,
                "INSERT INTO training_programmes (id, user_id, name, split_type,"
                " days_per_week, status, started_at, created_at, updated_at)"
                " VALUES ('second','wk-user-a','Also active','ppl',6,'active',"
                " now(), now(), now())",
            )
        assert "uq_active_programme_per_user" in str(exc.value)

    async def test_a_second_user_may_have_their_own_active_programme(
        self, mutable_db
    ):
        """The index must scope per user, not globally."""
        url, _ = mutable_db
        await _exec(
            url,
            "INSERT INTO training_programmes (id, user_id, name, split_type,"
            " days_per_week, status, started_at, created_at, updated_at)"
            " VALUES ('other','wk-user-b','Theirs','ppl',6,'active',"
            " now(), now(), now())",
        )
        assert await _scalar(
            url, "SELECT count(*) FROM training_programmes WHERE status='active'"
        ) == 2

    async def test_one_training_profile_per_user_is_enforced(
        self, shared_db
    ):
        url, _ = shared_db
        with pytest.raises(Exception) as exc:
            await _exec(
                url,
                "INSERT INTO training_profiles (id, user_id, created_at, updated_at)"
                " VALUES ('dup','wk-user-a', now(), now())",
            )
        assert "uq_training_profile_user" in str(exc.value)

    async def test_a_substitution_may_not_point_at_itself(self, shared_db):
        url, _ = shared_db
        with pytest.raises(Exception) as exc:
            await _exec(
                url,
                "INSERT INTO exercise_substitutions (id, from_exercise_id,"
                " to_exercise_id, reason, created_at)"
                " VALUES ('self','wk-ex-1','wk-ex-1','equipment', now())",
            )
        assert "ck_exsub_not_self" in str(exc.value)

    async def test_deleting_a_prescribed_exercise_is_restricted(
        self, shared_db
    ):
        """RESTRICT, and the reason it exists.

        Cascading here would let a catalogue cleanup silently erase part of a
        user's training history. The deletion must fail loudly instead.
        """
        url, _ = shared_db
        with pytest.raises(Exception) as exc:
            await _exec(url, "DELETE FROM exercises WHERE id='wk-ex-1'")
        assert "fk_prescribed_exercise" in str(exc.value)
        assert await _scalar(url, "SELECT count(*) FROM prescribed_exercises") == 1

    async def test_deleting_an_unprescribed_exercise_cascades_its_attributes(
        self, mutable_db
    ):
        """The other direction: reference data is disposable, history is not."""
        url, _ = mutable_db
        await _exec(
            url,
            "INSERT INTO exercise_attributes (exercise_id, movement_pattern,"
            " exercise_class, default_rep_min, default_rep_max, created_at,"
            " updated_at) VALUES ('wk-ex-2','squat','machine',10,15, now(), now())",
        )
        await _exec(url, "DELETE FROM exercises WHERE id='wk-ex-2'")
        assert await _scalar(url, "SELECT count(*) FROM exercise_attributes") == 0

    async def test_deleting_a_user_cascades_every_owned_row(self, mutable_db):
        """Ownership FKs, proven by effect rather than by catalogue lookup.

        USES A USER WITH NO RECORDING HISTORY, and that detail is the finding.
        The pre-existing workout tables -- workout_sessions, set_logs,
        strength_snapshots -- declare their user FK with no ON DELETE rule at
        all, so deleting a user who has ever logged a session is refused by
        NO ACTION before any of the new cascades get a chance to run. Every
        table added here does cascade; the recording layer does not, and that
        inconsistency is pre-existing and out of scope for an additive
        migration. See the report accompanying this revision.
        """
        url, _ = mutable_db
        await _exec(
            url,
            "INSERT INTO training_profiles (id, user_id, created_at, updated_at)"
            " VALUES ('wk-prof-b','wk-user-b', now(), now());"
            "INSERT INTO training_programmes (id, user_id, name, split_type,"
            " days_per_week, status, started_at, created_at, updated_at)"
            " VALUES ('wk-prog-b','wk-user-b','Theirs','ppl',3,'active',"
            " now(), now(), now());"
            "INSERT INTO programme_days (id, programme_id, day_index, label,"
            " created_at) VALUES ('wk-day-b','wk-prog-b',0,'Push', now());"
            "INSERT INTO planned_sessions (id, user_id, programme_day_id,"
            " scheduled_for, created_at, updated_at)"
            " VALUES ('wk-plan-b','wk-user-b','wk-day-b', CURRENT_DATE,"
            " now(), now());"
            "INSERT INTO prescribed_exercises (id, planned_session_id,"
            " exercise_id, order_index, sets, rep_min, rep_max, created_at,"
            " updated_at)"
            " VALUES ('wk-presc-b','wk-plan-b','wk-ex-1',0,3,8,12, now(), now());"
            "INSERT INTO readiness_checkins (id, user_id, for_date, energy,"
            " created_at, updated_at)"
            " VALUES ('wk-ready-b','wk-user-b', CURRENT_DATE, 4, now(), now());"
            "INSERT INTO ai_generations (id, user_id, kind, model, prompt_digest,"
            " validation_status, created_at)"
            " VALUES ('wk-gen-b','wk-user-b','session','m','d','accepted', now())",
        )
        await _exec(url, "DELETE FROM users WHERE id='wk-user-b'")
        for table in ("training_profiles", "training_programmes", "programme_days",
                      "planned_sessions", "prescribed_exercises",
                      "readiness_checkins", "ai_generations"):
            left = await _scalar(
                url, f"SELECT count(*) FROM {table} WHERE id LIKE '%-b'"
            )
            assert left == 0, f"{table} did not cascade"

    async def test_the_recording_layer_still_blocks_deleting_a_lifter(
        self, mutable_db
    ):
        """The pre-existing NO ACTION rule, asserted so the gap is visible.

        This is not a defect introduced here and this migration deliberately
        does not fix it -- altering `workout_sessions` would make the change
        non-additive. It is pinned down so that if someone later adds a
        cascade there, this test tells them the behaviour changed.
        """
        url, _ = mutable_db
        with pytest.raises(Exception) as exc:
            await _exec(url, "DELETE FROM users WHERE id='wk-user-a'")
        assert "workout_sessions_user_id_fkey" in str(exc.value)


# ---------------------------------------------------------------------------
# 14-15, 18. Downgrade, and the round trip
# ---------------------------------------------------------------------------


class TestDowngrade:
    async def test_the_revision_is_reversed(self, downgraded):
        url, _ = downgraded
        assert await _scalar(url, "SELECT version_num FROM alembic_version") == (
            BEFORE_WORKOUT
        )

    async def test_all_nine_tables_are_gone(self, downgraded):
        url, _ = downgraded
        found = await _tables(url)
        survivors = set(NEW_TABLES) & found
        assert not survivors, f"survived the downgrade: {sorted(survivors)}"

    async def test_the_workout_recording_tables_survive(self, downgraded):
        """The downgrade must not be collateral damage on what predates it."""
        url, _ = downgraded
        found = await _tables(url)
        for t in ("exercises", "workout_sessions", "set_logs", "strength_snapshots"):
            assert t in found, t
        assert await _scalar(url, "SELECT count(*) FROM exercises") == 2
        assert await _scalar(url, "SELECT count(*) FROM workout_sessions") == 1

    async def test_upgrade_downgrade_upgrade_is_clean(self):
        """Idempotently testable: no residue, no duplicate-object error."""
        async with _scratch_database() as url:
            _assert_ok(_alembic(url, "upgrade", BEFORE_WORKOUT), "to pre-workout")
            _assert_ok(_alembic(url, "upgrade", WORKOUT_REV), "up 1")
            _assert_ok(_alembic(url, "downgrade", BEFORE_WORKOUT), "down 1")
            _assert_ok(_alembic(url, "upgrade", WORKOUT_REV), "up 2")
            found = await _tables(url)
            assert set(NEW_TABLES) <= found


# ---------------------------------------------------------------------------
# 16-17. The nutrition catalogue is provably untouched
# ---------------------------------------------------------------------------


class TestNutritionInvariance:
    """The migration is additive by construction, so these should be boring.

    They are asserted anyway, because "should be" is the reasoning that loses
    data. Each compares a fingerprint taken BEFORE the migration ran.
    """

    async def test_counts_are_unchanged_by_the_upgrade(self, shared_db):
        url, before = shared_db
        after = await _nutrition_fingerprint(url)
        assert after["food_items"] == before["food_items"]
        assert after["food_aliases"] == before["food_aliases"]

    async def test_protected_columns_are_byte_identical_after_the_upgrade(
        self, shared_db
    ):
        url, before = shared_db
        after = await _nutrition_fingerprint(url)
        assert after["checksum"] == before["checksum"]
        assert after["alias_checksum"] == before["alias_checksum"]

    async def test_the_food_items_column_set_is_unchanged(self, shared_db):
        url, before = shared_db
        after = await _nutrition_fingerprint(url)
        assert after["food_item_columns"] == before["food_item_columns"]

    async def test_nutrition_survives_the_downgrade_too(self, downgraded):
        url, before = downgraded
        after = await _nutrition_fingerprint(url)
        assert after["food_items"] == before["food_items"]
        assert after["food_aliases"] == before["food_aliases"]
        assert after["checksum"] == before["checksum"]
        assert after["alias_checksum"] == before["alias_checksum"]
        assert after["food_item_columns"] == before["food_item_columns"]

    async def test_the_search_index_is_never_collateral(self, downgraded):
        """ix_food_search_trgm predates all of this and must be left alone."""
        url, _ = downgraded
        found = await _indexes(url)
        assert "ix_food_search_trgm" in found
        assert "ix_alias_normalized_trgm" in found


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


class TestIsolation:
    async def test_fixtures_never_point_at_a_real_database(self, shared_db):
        url, _ = shared_db
        assert "/trace_migtest_" in url
        assert not url.rstrip("/").endswith("/trace")
        assert not url.rstrip("/").endswith("/trace_test")
