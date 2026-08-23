"""Tests for two-arm search ranking.

Pure functions, no database. The ordering rules are stated here directly rather
than inferred from whatever Postgres returns, which is the only way to keep
"exact beats prefix" from silently regressing.
"""

from __future__ import annotations

import pytest

from app.services.search_rank import (
    ARM_ALIAS,
    ARM_DIRECT,
    TIER_EXACT,
    TIER_FUZZY,
    TIER_PREFIX,
    TIER_SUBSTRING,
    Candidate,
    alias_candidate,
    direct_candidate,
    match_tier,
    rank,
)


def direct(fid: str, name: str, matched: str | None = None, **kw) -> Candidate:
    return Candidate(food_item_id=fid, name=name,
                     matched_text=matched if matched is not None else name.lower(),
                     arm=ARM_DIRECT, **kw)


def alias(fid: str, name: str, matched: str, **kw) -> Candidate:
    return Candidate(food_item_id=fid, name=name, matched_text=matched,
                     arm=ARM_ALIAS, **kw)


# ------------------------------------------------------------- match tiers

def test_exact_match_is_the_best_tier():
    assert match_tier("poha", "poha") == TIER_EXACT


def test_prefix_beats_substring():
    assert match_tier("dosa", "dosa masala") == TIER_PREFIX
    assert match_tier("dosa", "masala dosa") == TIER_SUBSTRING
    assert TIER_PREFIX < TIER_SUBSTRING


def test_no_overlap_is_fuzzy():
    assert match_tier("poha", "biryani") == TIER_FUZZY


def test_empty_query_or_text_is_fuzzy():
    assert match_tier("", "poha") == TIER_FUZZY
    assert match_tier("poha", "") == TIER_FUZZY


# ------------------------------------------------------------ ordering

def test_exact_direct_outranks_everything():
    out = rank("poha", [
        direct("f2", "Masala poha", "masala poha"),
        alias("f3", "Flattened rice", "poha", alias_confidence=1.0),
        direct("f1", "Poha", "poha"),
    ])
    assert out[0].food_item_id == "f1"
    assert out[0].tier == TIER_EXACT and out[0].arm == ARM_DIRECT


def test_exact_direct_beats_exact_alias():
    """An alias must never displace the food actually called that."""
    out = rank("poha", [
        alias("f2", "Chivda", "poha", alias_confidence=1.0),
        direct("f1", "Poha", "poha"),
    ])
    assert [r.food_item_id for r in out] == ["f1", "f2"]


def test_exact_alias_beats_weaker_direct():
    """Arm is a tiebreak within a tier, not a demotion across tiers."""
    out = rank("avalakki", [
        direct("f1", "Avalakki upma", "avalakki upma"),   # prefix
        alias("f2", "Poha", "avalakki"),                  # exact
    ])
    assert out[0].food_item_id == "f2"
    assert out[0].tier == TIER_EXACT


def test_prefix_then_substring_then_fuzzy():
    out = rank("dosa", [
        direct("f3", "Rava idli", "rava idli", similarity=0.2),
        direct("f2", "Masala dosa", "masala dosa"),
        direct("f1", "Dosa batter", "dosa batter"),
    ])
    assert [r.food_item_id for r in out] == ["f1", "f2", "f3"]
    assert [r.tier for r in out] == [TIER_PREFIX, TIER_SUBSTRING, TIER_FUZZY]


def test_curated_alias_outranks_generated_alias():
    out = rank("avalakki", [
        alias("f2", "Chivda", "avalakki", alias_confidence=0.6),
        alias("f1", "Poha", "avalakki", alias_confidence=1.0),
    ])
    assert [r.food_item_id for r in out] == ["f1", "f2"]


def test_similarity_then_popularity_then_quality_break_ties():
    out = rank("x", [
        direct("f3", "A", "x", similarity=0.9, log_count=1, data_quality=0.1),
        direct("f2", "B", "x", similarity=0.9, log_count=5, data_quality=0.1),
        direct("f1", "C", "x", similarity=0.95, log_count=0, data_quality=0.1),
    ])
    assert [r.food_item_id for r in out] == ["f1", "f2", "f3"]


def test_ranking_is_deterministic_and_total():
    """Identical candidates differing only by id must still order stably."""
    cands = [direct("f%d" % i, "Same", "same") for i in range(6)]
    first = [r.food_item_id for r in rank("same", cands)]
    for _ in range(5):
        assert [r.food_item_id for r in rank("same", list(reversed(cands)))] == first
    assert first == sorted(first)


# ------------------------------------------------------- duplicate collapse

def test_same_food_from_both_arms_collapses_to_one_result():
    out = rank("poha", [
        direct("f1", "Poha", "poha"),
        alias("f1", "Poha", "avalakki"),
        alias("f1", "Poha", "chivda"),
    ])
    assert len(out) == 1
    assert out[0].food_item_id == "f1"


def test_collapse_keeps_the_strongest_match():
    out = rank("poha", [
        alias("f1", "Poha", "avalakki", alias_confidence=0.6),
        direct("f1", "Poha", "poha"),
    ])
    assert out[0].arm == ARM_DIRECT
    assert out[0].tier == TIER_EXACT


def test_collapse_records_the_other_ways_it_matched():
    out = rank("poha", [
        direct("f1", "Poha", "poha"),
        alias("f1", "Poha", "avalakki"),
    ])
    assert out[0].also_matched == ("avalakki",)


def test_collapse_does_not_record_a_repeat_of_the_winning_text():
    out = rank("poha", [
        direct("f1", "Poha", "poha"),
        alias("f1", "Poha", "poha"),
    ])
    assert out[0].also_matched == ()


def test_distinct_foods_are_not_collapsed():
    out = rank("poha", [direct("f1", "Poha", "poha"),
                        direct("f2", "Poha", "poha")])
    assert len(out) == 2


# ------------------------------------------- no regression without aliases

def test_direct_only_ordering_is_unchanged_by_the_alias_machinery():
    """food_aliases has zero rows today; this is the production case."""
    cands = [
        direct("f3", "Rava dosa", "rava dosa", log_count=99),
        direct("f1", "Dosa", "dosa", log_count=1),
        direct("f2", "Dosa mix", "dosa mix", log_count=50),
    ]
    assert [r.food_item_id for r in rank("dosa", cands)] == ["f1", "f2", "f3"]
    assert all(r.arm == ARM_DIRECT for r in rank("dosa", cands))
    assert all(not r.via_alias for r in rank("dosa", cands))


def test_empty_alias_arm_changes_nothing():
    cands = [direct("f1", "Poha", "poha"), direct("f2", "Poha mix", "poha mix")]
    assert rank("poha", cands) == rank("poha", cands + [])


def test_empty_candidate_list_returns_empty():
    assert rank("anything", []) == []


def test_empty_query_returns_all_as_fuzzy_not_a_crash():
    out = rank("", [direct("f1", "Poha", "poha")])
    assert len(out) == 1 and out[0].tier == TIER_FUZZY


# --------------------------------------------------------------- limit

def test_limit_truncates_after_collapsing_not_before():
    """Truncating first would let duplicates eat the page."""
    cands = [direct("f1", "Poha", "poha"), alias("f1", "Poha", "avalakki"),
             direct("f2", "Poha mix", "poha mix")]
    out = rank("poha", cands, limit=2)
    assert [r.food_item_id for r in out] == ["f1", "f2"]


def test_limit_none_returns_everything():
    cands = [direct("f%d" % i, "N", "n%d" % i) for i in range(5)]
    assert len(rank("n", cands, limit=None)) == 5


# --------------------------------------------------------------- adapters

def test_direct_candidate_prefers_the_backfilled_column():
    c = direct_candidate({"id": "f1", "name": "Poha",
                          "name_normalized": "poha", "sim": 0.5,
                          "log_count": 3, "data_quality": 0.9})
    assert c.arm == ARM_DIRECT and c.matched_text == "poha"
    assert c.similarity == 0.5 and c.log_count == 3


def test_direct_candidate_falls_back_to_normalising_the_name():
    c = direct_candidate({"id": "f1", "name": "Crème Fraîche",
                          "name_normalized": ""})
    assert c.matched_text == "creme fraiche"


def test_direct_candidate_tolerates_nulls():
    c = direct_candidate({"id": "f1", "name": "Poha", "sim": None,
                          "log_count": None, "data_quality": None})
    assert c.similarity == 0.0 and c.log_count == 0


def test_alias_candidate_carries_target_and_provenance():
    c = alias_candidate({"food_item_id": "f9", "name": "Poha",
                         "normalized": "avalakki", "alias_type": "regional",
                         "confidence": 0.9})
    assert c.arm == ARM_ALIAS and c.food_item_id == "f9"
    assert c.alias_type == "regional" and c.alias_confidence == 0.9


def test_alias_match_identifies_its_target():
    out = rank("avalakki", [alias_candidate(
        {"food_item_id": "f9", "name": "Poha", "normalized": "avalakki",
         "alias_type": "regional", "confidence": 0.9})])
    assert out[0].food_item_id == "f9"
    assert out[0].name == "Poha"
    assert out[0].via_alias and out[0].alias_type == "regional"


def test_unknown_arm_is_rejected():
    with pytest.raises(ValueError):
        Candidate(food_item_id="f1", name="n", matched_text="n", arm="sideways")
