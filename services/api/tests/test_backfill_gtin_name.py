"""The spec for the gtin14 / name_normalized backfill script.

RUNS ONLY AGAINST trace_migtest_* SCRATCH DATABASES.
The scratch-database helper and its guard are imported from test_migrations
rather than copied. That is a safety decision, not a tidiness one: the helper
drops a database, and one audited copy of that code is worth more than two
convenient ones.

The script is driven through its real command line in a subprocess, with
DATABASE_URL injected per-process. That is the only way to test what actually
protects the live database -- the argparse guards, the exit codes, and the
promise that no credential reaches stdout.
"""

from __future__ import annotations

import json
import os
import subprocess
import unicodedata

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

# One audited copy of the drop-a-database guard. See the module docstring.
from test_migrations import (  # noqa: E402
    API_DIR,
    PRE_PHASE_3A,
    _alembic,
    _assert_ok,
    _scratch_database,
)

PYTHON_EXE = API_DIR / ".venv" / "Scripts" / "python.exe"
MODULE = "app.scripts.backfill_gtin_and_name"

_COLUMNS = (
    "id, source, source_id, name, brand, barcode, names_i18n, calories, "
    "protein_g, carbs_g, fat_g, fiber_g, sugar_g, sodium_mg, saturated_fat_g, "
    "micronutrients, is_liquid, serving_sizes, countries, data_quality, "
    "is_verified, moderation_status, search_text, log_count, created_at, "
    "updated_at"
)

_INSERT = text(
    "INSERT INTO food_items (" + _COLUMNS + ") VALUES ("
    " :id, CAST(:source AS foodsource), :source_id, :name, NULL, :barcode,"
    " CAST(:names_i18n AS jsonb), 100, 5, 10, 2, 1, 1, 50, 0.5,"
    " CAST('{}' AS jsonb), false, CAST('[]' AS jsonb), CAST('[]' AS jsonb),"
    " 0.85, false, 'approved', :search_text, 0, now(), now())"
)

NAMES_I18N = {
    "aliases": ["idli", "aachi idli"],
    "preparation_key": "idli_steamed",
    "data_notes": "OFF files this under a dry-mix barcode.",
}

#: (id, name, barcode, expected gtin14, expected name_normalized, reject reason)
#:
#: ids are ordered so keyset pagination walks them predictably.
CASES: tuple[tuple, ...] = (
    ("r01-upca",     "Egg",              "012345678905",  "00012345678905", "egg",            None),
    ("r02-ean13",    "Egg thirteen",     "0012345678905", "00012345678905", "egg thirteen",   None),
    ("r03-ean13b",   "Creme",            "4006381333931", "04006381333931", "creme",          None),
    ("r04-badcheck", "Bad check",        "012345678906",  None,             "bad check",      "bad_check"),
    ("r05-len9",     "Nine digits",      "123456789",     None,             "nine digits",    "bad_length"),
    ("r06-len15",    "Fifteen",          "123456789012345", None,           "fifteen",        "bad_length"),
    ("r07-instore",  "In store",         "0200000000000", None,             "in store",       "restricted"),
    ("r08-instore2", "In store four",    "0400000000006", None,             "in store four",  "restricted"),
    ("r09-junk",     "Junk barcode",     "n/a",           None,             "junk barcode",   "missing"),
    ("r10-emoji",    "Emoji barcode",    "\U0001f36b",    None,             "emoji barcode",  "missing"),
    ("r11-empty",    "Empty barcode",    "",              None,             "empty barcode",  "missing"),
    ("r12-nobar",    "No barcode",       None,            None,             "no barcode",     "missing"),
    ("r13-accent",   "Crème Fraîche", None,     None,             "creme fraiche",  "missing"),
    ("r14-deva",     "पोहे", None,    None,             "पोहे", "missing"),
    ("r15-taml",     "தோசை", None,    None,             "தோசை", "missing"),
    # PUNCTUATION-ONLY: normalises to '', which is also the column default.
    # A state-based completion predicate would re-select this row forever.
    ("r16-punct",    "---",              None,            None,             "",               "missing"),
)

PROTECTED = ("barcode", "name", "names_i18n", "search_text",
             "source_licence", "verification_tier")


def _counts(stdout: str) -> dict[str, int]:
    """Parse the results block into {label: number}.

    Beats substring matching on a formatted report: the assertions then say
    what they mean and do not silently pass when the layout shifts.
    """
    out: dict[str, int] = {}
    for line in stdout.splitlines():
        stripped = line.strip()
        parts = stripped.rsplit(None, 1)
        if len(parts) == 2 and parts[1].replace(",", "").isdigit():
            out[parts[0].strip()] = int(parts[1].replace(",", ""))
    return out


def _run(url: str, *args: str) -> subprocess.CompletedProcess:
    """Invoke the script's real command line against ONE scratch database."""
    env = dict(os.environ, DATABASE_URL=url, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [str(PYTHON_EXE), "-m", MODULE, *args],
        cwd=str(API_DIR), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


async def _seed(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            for row_id, name, barcode, *_ in CASES:
                await conn.execute(_INSERT, {
                    "id": row_id, "source": "curated", "source_id": row_id,
                    "name": name, "barcode": barcode,
                    "names_i18n": json.dumps(NAMES_I18N),
                    "search_text": f"seed {row_id}",
                })
    finally:
        await engine.dispose()


async def _all(url: str) -> dict[str, dict]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(
                text("SELECT * FROM food_items ORDER BY id")
            )).mappings().all()
        return {r["id"]: dict(r) for r in rows}
    finally:
        await engine.dispose()


async def _fingerprint(url: str) -> list[tuple]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return [tuple(r) for r in (await conn.execute(text(
                f"SELECT id, {', '.join(PROTECTED)} FROM food_items ORDER BY id"
            ))).all()]
    finally:
        await engine.dispose()


class _MaskedUrl(str):
    """A connection URL that will not print its own password.

    pytest renders fixture values in a failure traceback. A plain URL string
    therefore puts the database password into the test log the first time
    anything fails -- which is exactly when someone pastes the output
    somewhere. Behaves as a str everywhere it is used; only repr() differs.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"<scratch db {self.rsplit('/', 1)[-1]}>"


@pytest.fixture
async def db():
    """A scratch database at head, seeded with the cases above."""
    async with _scratch_database() as url:
        _assert_ok(_alembic(url, "upgrade", "head"), "upgrade to head")
        await _seed(url)
        yield _MaskedUrl(url)


class TestSafetyGuards:
    async def test_dry_run_is_the_default_and_writes_nothing(self, db, tmp_path):
        before = await _all(db)
        r = _run(db, "--state", str(tmp_path / "s.json"))
        assert r.returncode == 0, r.stderr
        assert "DRY RUN" in r.stdout
        assert await _all(db) == before, "dry run modified the database"

    async def test_apply_without_expect_db_is_rejected(self, db, tmp_path):
        before = await _all(db)
        r = _run(db, "--apply", "--state", str(tmp_path / "s.json"))
        assert r.returncode != 0
        assert "--expect-db" in (r.stderr + r.stdout)
        assert await _all(db) == before, "a rejected run still wrote"

    async def test_apply_with_the_wrong_expect_db_is_rejected(self, db, tmp_path):
        before = await _all(db)
        r = _run(db, "--apply", "--expect-db", "trace",
                 "--state", str(tmp_path / "s.json"))
        assert r.returncode != 0
        assert "REFUSED" in r.stderr
        assert await _all(db) == before

    async def test_the_revision_guard_refuses_an_unknown_schema(self, db, tmp_path):
        """Stamped back to pre-Phase-3a: columns exist, revision does not match."""
        _assert_ok(_alembic(db, "stamp", PRE_PHASE_3A), "stamp back")
        name = db.rsplit("/", 1)[1]
        r = _run(db, "--apply", "--expect-db", name,
                 "--state", str(tmp_path / "s.json"))
        assert r.returncode != 0
        assert "REFUSED" in r.stderr and PRE_PHASE_3A in r.stderr

    async def test_no_credential_ever_reaches_the_output(self, db, tmp_path):
        r = _run(db, "--state", str(tmp_path / "s.json"))
        out = r.stdout + r.stderr
        password = get_settings().DATABASE_URL.split("//", 1)[1].split("@")[0]
        # Deliberately generic messages: a failure must not print the secret.
        assert password not in out, "output contained the database credential"
        assert "postgresql" not in out, "output contained a connection scheme"
        assert "@" not in out, "output contained a userinfo separator"

    async def test_version_states_the_safety_contract(self, db):
        r = _run(db, "--version")
        assert r.returncode == 0
        for phrase in ("dry-run is the DEFAULT", "--expect-db",
                       "gtin14 and name_normalized", "never printed"):
            assert phrase in r.stdout


class TestNormalisation:
    @pytest.fixture
    async def applied(self, db, tmp_path):
        name = db.rsplit("/", 1)[1]
        r = _run(db, "--apply", "--expect-db", name,
                 "--state", str(tmp_path / "s.json"))
        assert r.returncode == 0, r.stderr + r.stdout
        return db, r

    @pytest.mark.parametrize(
        "row_id,expected_gtin",
        [(c[0], c[3]) for c in CASES],
    )
    async def test_gtin14(self, applied, row_id, expected_gtin):
        db, _ = applied
        assert (await _all(db))[row_id]["gtin14"] == expected_gtin

    async def test_upca_and_ean13_converge(self, applied):
        db, _ = applied
        rows = await _all(db)
        assert rows["r01-upca"]["gtin14"] == rows["r02-ean13"]["gtin14"]
        assert rows["r01-upca"]["gtin14"] is not None

    @pytest.mark.parametrize(
        "row_id,expected_name",
        [(c[0], c[4]) for c in CASES],
    )
    async def test_name_normalized(self, applied, row_id, expected_name):
        """Compared in NFC, because normalize() legitimately decomposes.

        normalize() applies NFKD, and Tamil O (U+0BCB) canonically decomposes
        into U+0BC7 + U+0BBE. The stored value is canonically equivalent to the
        expectation without being codepoint-identical, so a raw == comparison
        fails on a correct result. Devanagari O has no decomposition, which is
        why only the Tamil case exposes this.
        """
        db, _ = applied
        got = (await _all(db))[row_id]["name_normalized"]
        assert unicodedata.normalize("NFC", got) == unicodedata.normalize(
            "NFC", expected_name
        )

    async def test_indic_marks_are_not_stripped(self, applied):
        db, _ = applied
        rows = await _all(db)
        assert unicodedata.normalize(
            "NFC", rows["r14-deva"]["name_normalized"]
        ) == "पोहे"
        assert rows["r15-taml"]["name_normalized"] != ""

    async def test_rejection_categories_are_reported_separately(self, applied):
        _, r = applied
        assert "bad check digit" in r.stdout
        assert "invalid length" in r.stdout
        assert "restricted prefix" in r.stdout
        assert "missing" in r.stdout

    async def test_no_errors(self, applied):
        _, r = applied
        assert _counts(r.stdout)["errors"] == 0, r.stdout


class TestProtectedColumns:
    async def test_nothing_but_the_two_targets_changes(self, db, tmp_path):
        before = await _fingerprint(db)
        name = db.rsplit("/", 1)[1]
        r = _run(db, "--apply", "--expect-db", name,
                 "--state", str(tmp_path / "s.json"))
        assert r.returncode == 0, r.stderr
        assert await _fingerprint(db) == before, "a protected column changed"

    async def test_preparation_key_survives(self, db, tmp_path):
        name = db.rsplit("/", 1)[1]
        _run(db, "--apply", "--expect-db", name, "--state", str(tmp_path / "s.json"))
        rows = await _all(db)
        assert rows["r01-upca"]["names_i18n"]["preparation_key"] == "idli_steamed"
        assert rows["r01-upca"]["names_i18n"] == NAMES_I18N

    async def test_the_script_contains_exactly_one_set_clause(self):
        """A structural guard on the blast radius.

        Cheaper and more durable than trusting review: if someone adds a
        second SET to this script, this fails before the data does.
        """
        src = (API_DIR / "app" / "scripts" / "backfill_gtin_and_name.py").read_text(
            encoding="utf-8"
        )
        assert src.count("SET gtin14") == 1
        for forbidden in ("SET barcode", "SET names_i18n", "SET search_text",
                          "SET source_licence", "SET verification_tier",
                          "SET name ="):
            assert forbidden not in src, forbidden


class TestIdempotenceAndResume:
    async def test_second_run_changes_nothing(self, db, tmp_path):
        name = db.rsplit("/", 1)[1]
        state = str(tmp_path / "s.json")
        first = _run(db, "--apply", "--expect-db", name, "--state", state)
        assert first.returncode == 0, first.stderr
        after_first = await _all(db)

        second = _run(db, "--apply", "--expect-db", name, "--state", state,
                      "--restart")
        assert second.returncode == 0, second.stderr
        counts = _counts(second.stdout)
        assert counts["rows updated"] == 0, counts
        assert counts["already correct"] == len(CASES), counts
        assert await _all(db) == after_first, "the second run rewrote rows"

    async def test_punctuation_only_name_is_not_reprocessed(self, db, tmp_path):
        """THE NON-TERMINATION TRAP.

        '---' normalises to '', which is also the column default. A completion
        predicate of `name_normalized = ''` would re-select this row on every
        pass forever -- the same shape of bug that `ifct` set for the M5
        backfill. The cursor is what makes it terminate.
        """
        name = db.rsplit("/", 1)[1]
        state = str(tmp_path / "s.json")
        _run(db, "--apply", "--expect-db", name, "--state", state)
        second = _run(db, "--apply", "--expect-db", name, "--state", state,
                      "--restart")
        assert second.returncode == 0, second.stderr
        assert (await _all(db))["r16-punct"]["name_normalized"] == ""
        counts = _counts(second.stdout)
        # Terminated, and treated the punctuation row as done rather than
        # rewriting it on every pass.
        assert counts["rows updated"] == 0, counts
        assert counts["already correct"] == len(CASES), counts

    async def test_resumes_from_the_stored_cursor(self, db, tmp_path):
        """Stop after one small batch, then resume and converge."""
        name = db.rsplit("/", 1)[1]
        state = tmp_path / "s.json"

        partial = _run(db, "--apply", "--expect-db", name, "--state", str(state),
                       "--batch", "4", "--limit", "4")
        assert partial.returncode == 0, partial.stderr
        assert state.exists(), "no cursor was written"
        cursor = json.loads(state.read_text())["last_id"]
        assert cursor == CASES[3][0], cursor

        mid = await _all(db)
        assert mid["r01-upca"]["name_normalized"] == "egg"
        assert mid["r05-len9"]["name_normalized"] == "", "resume point overshot"

        rest = _run(db, "--apply", "--expect-db", name, "--state", str(state))
        assert rest.returncode == 0, rest.stderr

        final = await _all(db)
        for row_id, _n, _b, exp_gtin, exp_name, _r in CASES:
            assert final[row_id]["gtin14"] == exp_gtin, row_id
            assert unicodedata.normalize(
                "NFC", final[row_id]["name_normalized"]
            ) == unicodedata.normalize("NFC", exp_name), row_id

    async def test_a_lost_state_file_is_survivable(self, db, tmp_path):
        """Resumability is an optimisation; correctness must not depend on it."""
        name = db.rsplit("/", 1)[1]
        _run(db, "--apply", "--expect-db", name,
             "--state", str(tmp_path / "gone.json"), "--batch", "4", "--limit", "4")
        again = _run(db, "--apply", "--expect-db", name,
                     "--state", str(tmp_path / "never-existed.json"))
        assert again.returncode == 0, again.stderr
        final = await _all(db)
        for row_id, _n, _b, exp_gtin, exp_name, _r in CASES:
            assert final[row_id]["gtin14"] == exp_gtin, row_id
            assert unicodedata.normalize(
                "NFC", final[row_id]["name_normalized"]
            ) == unicodedata.normalize("NFC", exp_name), row_id


class TestIsolation:
    async def test_only_scratch_databases_are_used(self, db):
        assert "/trace_migtest_" in db
        assert not db.rstrip("/").endswith("/trace")
        assert not db.rstrip("/").endswith("/trace_test")
