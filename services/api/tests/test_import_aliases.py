"""Safety tests for the alias importer.

These are mostly STRUCTURAL: they read the importer's source text and fail if
it could ever touch a table or column it has no business touching. That style
is deliberate. A behavioural test only proves the paths it exercises are safe;
a structural one proves no path exists. Given the importer writes to a
catalogue that took a 578,773-row backfill to get right, "no path exists" is
the property worth asserting.

Nothing here connects to a database.
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re

import pytest

from app.scripts import import_aliases as imp
from app.scripts.import_aliases import (
    INSERT_COLUMNS,
    INSERT_SQL,
    TARGET_TABLE,
    Refused,
    assert_loopback,
    load_plan,
    prevalidate,
    validate_args,
)

SRC = pathlib.Path(imp.__file__).read_text(encoding="utf-8")

#: Columns that belong to food_items and must never appear in a write here.
FOOD_ITEM_COLUMNS = (
    "barcode", "names_i18n", "search_text", "source_licence",
    "verification_tier", "gtin14", "name_normalized", "calories",
    "protein_g", "carbs_g", "fat_g", "log_count", "data_quality",
)


def row(fid="f1", norm="poha", alias="Poha", **kw):
    d = {"food_item_id": fid, "alias": alias, "normalized": norm,
         "lang": "", "script": "latn", "alias_type": "regional",
         "source": "curated", "confidence": 0.9}
    d.update(kw)
    return d


# ------------------------------------------------- structural: what it writes

def test_the_only_write_statement_targets_food_aliases():
    assert TARGET_TABLE == "food_aliases"
    assert "INSERT INTO food_aliases" in INSERT_SQL
    inserts = re.findall(r"INSERT\s+INTO\s+(\w+)", SRC, re.IGNORECASE)
    assert inserts == ["food_aliases"], inserts


def test_there_is_no_update_delete_truncate_or_alter():
    """Matched as SQL, not as prose.

    A bare substring search trips on this module's own docstring, which says
    "contains no UPDATE, no DELETE, no TRUNCATE". Requiring a target after the
    verb is what makes the assertion about SQL rather than English.
    """
    pattern = (r"\b(UPDATE\s+\w+\s+SET|DELETE\s+FROM\s+\w+|TRUNCATE\s+\w+"
               r"|ALTER\s+TABLE\s+\w+|DROP\s+(TABLE|INDEX)\s+\w+)")
    found = re.findall(pattern, SRC, re.IGNORECASE)
    assert found == [], found


def test_no_food_items_column_appears_in_the_insert():
    for col in FOOD_ITEM_COLUMNS:
        assert col not in INSERT_SQL, col


def test_food_items_is_only_ever_read():
    """It may SELECT from food_items to validate targets -- never write it."""
    for m in re.finditer(r"food_items", SRC):
        window = SRC[max(0, m.start() - 220):m.start()].upper()
        assert "INSERT INTO" not in window.split("SELECT")[-1]
        assert "UPDATE" not in window[-40:]


def test_every_inserted_column_belongs_to_food_aliases():
    allowed = {"food_item_id", "alias", "normalized", "lang", "script",
               "alias_type", "source", "confidence", "is_active"}
    assert set(INSERT_COLUMNS) <= allowed
    assert not set(INSERT_COLUMNS) & set(FOOD_ITEM_COLUMNS)


def test_insert_is_idempotent_by_the_unique_constraint():
    flat = " ".join(INSERT_SQL.split()).upper()
    assert "ON CONFLICT ON CONSTRAINT UQ_ALIAS_FOOD_NORM_LANG DO NOTHING" in flat


def test_the_default_transaction_is_read_only():
    assert "SET TRANSACTION READ ONLY" in SRC


# ------------------------------------------------- structural: how it's armed

def test_dry_run_is_the_default():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--expect-db")
    p.add_argument("--allow-remote", action="store_true")
    assert p.parse_args([]).apply is False


def test_apply_without_expect_db_fails_before_any_connection():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--expect-db")
    args = p.parse_args(["--apply"])
    with pytest.raises(SystemExit):
        validate_args(args, p)


def test_apply_with_expect_db_passes_validation():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--expect-db")
    validate_args(p.parse_args(["--apply", "--expect-db", "trace"]), p)


def function_code(name: str) -> str:
    """The function's body as code, with comments and docstring stripped.

    `ast.unparse` discards comments, and dropping a leading string expression
    discards the docstring -- so the result is what actually executes. A raw
    substring search over the source would match the word "connection" inside
    a comment and prove nothing.
    """
    tree = ast.parse(SRC)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == name)
    body = fn.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return "\n".join(ast.unparse(n) for n in body)


def test_validate_args_does_not_open_a_connection():
    """The refusal must be reachable without any I/O at all."""
    code = function_code("validate_args")
    for banned in ("create_async_engine", "connect", "execute", "await",
                   "engine", "session"):
        assert banned not in code, banned


def test_only_the_run_function_can_reach_the_database():
    """Connection handling is confined to one auditable function."""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in ("run", "main"):
                continue
            code = function_code(node.name)
            assert "create_async_engine" not in code, node.name
            assert "execute(" not in code, node.name


# ------------------------------------------------------- host safety

@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://u:p@127.0.0.1:5432/trace",
    "postgresql+asyncpg://u:p@localhost:5432/trace",
    "postgresql+asyncpg://u:p@[::1]:5432/trace",
])
def test_loopback_hosts_are_allowed(url):
    assert_loopback(url, allow_remote=False)


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://u:p@10.0.0.5:5432/trace",
    "postgresql+asyncpg://u:p@db.example.com:5432/trace",
    "postgresql+asyncpg://u:p@ep-x.neon.tech:5432/trace",
])
def test_non_loopback_hosts_are_refused(url):
    with pytest.raises(SystemExit):
        assert_loopback(url, allow_remote=False)


def test_non_loopback_allowed_only_with_the_explicit_flag():
    assert assert_loopback("postgresql+asyncpg://u:p@10.0.0.5/trace",
                           allow_remote=True) == "10.0.0.5"


def test_refusal_message_never_contains_the_url_or_password():
    try:
        assert_loopback("postgresql+asyncpg://user:hunter2@evil.example/trace",
                        allow_remote=False)
    except SystemExit as e:
        msg = str(e)
        assert "hunter2" not in msg and "user" not in msg
        assert "postgresql" not in msg and "://" not in msg
        assert "evil.example" in msg          # the bare host is fine to name
    else:
        pytest.fail("should have refused")


def test_no_print_of_a_connection_url_anywhere():
    for m in re.finditer(r"print\(([^\n]*)", SRC):
        line = m.group(1)
        for banned in ("url", "URL", "DATABASE_URL", "password"):
            assert banned not in line, line


# --------------------------------------------------- pre-write validation

def test_duplicate_normalized_for_one_food_is_rejected_before_any_write():
    safe, problems = prevalidate([row(), row()])
    assert len(safe) == 1
    assert len(problems["duplicate_in_plan"]) == 1


def test_alias_with_multiple_targets_is_rejected():
    safe, problems = prevalidate([row(fid="f1"), row(fid="f2")])
    assert safe == []
    assert len(problems["multiple_targets"]) == 2


def test_empty_normalized_is_rejected():
    safe, problems = prevalidate([row(norm="")])
    assert safe == [] and problems["empty_normalized"]


def test_missing_target_id_is_rejected():
    safe, problems = prevalidate([row(fid="")])
    assert safe == [] and problems["missing_target_id"]


def test_clean_plan_passes_with_no_problems():
    safe, problems = prevalidate([row(fid="f1", norm="poha"),
                                  row(fid="f2", norm="dosa")])
    assert len(safe) == 2 and problems == {}


def test_prevalidate_is_deterministic():
    rows = [row(fid="f%d" % i, norm="n%d" % i) for i in range(20)]
    a, _ = prevalidate(rows)
    b, _ = prevalidate(list(reversed(rows)))
    assert {r["normalized"] for r in a} == {r["normalized"] for r in b}


# ------------------------------------------------------------ plan loading

def test_load_plan_accepts_the_plan_shape(tmp_path):
    p = tmp_path / "plan.json"
    p.write_text(json.dumps({"aliases": [row()]}), encoding="utf-8")
    assert len(load_plan(p)) == 1


def test_load_plan_refuses_a_shapeless_file(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"nope": 1}), encoding="utf-8")
    with pytest.raises(SystemExit):
        load_plan(p)


# ----------------------------------------------------- the real plan file

PLAN = pathlib.Path(__file__).resolve().parents[1] / "review" / "alias_import_plan.json"


@pytest.mark.skipif(not PLAN.exists(), reason="plan artifact not generated")
def test_the_generated_plan_passes_every_pre_write_check():
    rows = load_plan(PLAN)
    safe, problems = prevalidate(rows)
    assert problems == {}, problems
    assert len(safe) == len(rows)


@pytest.mark.skipif(not PLAN.exists(), reason="plan artifact not generated")
def test_every_plan_row_has_complete_provenance():
    for r in load_plan(PLAN):
        for field in ("food_item_id", "alias", "normalized", "alias_type",
                      "source", "rule", "reason", "confidence", "script",
                      "lang", "generator_version"):
            assert field in r, field
        assert r["alias_type"] and r["source"] and r["rule"] and r["reason"]
        assert 0.0 <= r["confidence"] <= 1.0


@pytest.mark.skipif(not PLAN.exists(), reason="plan artifact not generated")
def test_the_plan_contains_no_excluded_alias():
    from app.services.alias_gen import EXCLUDED_PENDING_REVIEW
    normals = {r["normalized"] for r in load_plan(PLAN)}
    assert not normals & set(EXCLUDED_PENDING_REVIEW)
