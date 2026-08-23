"""Tests for the deterministic alias generator.

No database, no fixtures, no I/O -- `alias_gen` is pure by construction and
these tests are the reason it has to stay that way. They are the spec for the
review artifact: if the artifact's shape changes, a test here fails first.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import pathlib
import re

import pytest

from app.services import alias_gen
from app.services.alias_gen import (
    ALIAS_SOURCES,
    ALIAS_TYPES,
    BRAND_FAMILIES,
    BRAND_ORDER,
    GENERATOR_VERSION,
    MIN_LATIN_ALIAS_LEN,
    AliasCandidate,
    FoodRecord,
    brand_family,
    collapse_possessive,
    generate,
    generate_for_food,
    is_broad,
    is_indian,
    norm,
    report_to_dict,
    report_to_json,
    spelling_variants,
    strip_brand,
)
from app.services.food_text import normalize


# --------------------------------------------------------------- fixtures

def dish(id_: str, name: str, **kw) -> FoodRecord:
    kw.setdefault("cuisine", "indian_south")
    kw.setdefault("source", "curated")
    return FoodRecord(id=id_, name=name, **kw)


def product(id_: str, name: str, brand: str, **kw) -> FoodRecord:
    kw.setdefault("source", "openfoodfacts")
    return FoodRecord(id=id_, name=name, brand=brand, **kw)


POHA = dish("00000000-0000-0000-0000-000000000001", "Poha",
            curated_aliases=("avalakki", "chivda"))
DOSA = dish("00000000-0000-0000-0000-000000000002", "Masala dosa",
            curated_aliases=("masala dose",))
BHUJIA = product("00000000-0000-0000-0000-000000000003",
                 "Haldiram's Aloo Bhujia", "Haldiram's")


# ------------------------------------------------------------ determinism

def test_generate_is_byte_identical_across_runs():
    """The whole point of the review gate: regenerate, diff, no diff."""
    records = [POHA, DOSA, BHUJIA]
    first = report_to_json(generate(records))
    for _ in range(5):
        assert report_to_json(generate(records)) == first


def test_generate_is_independent_of_input_order():
    a = report_to_json(generate([POHA, DOSA, BHUJIA]))
    b = report_to_json(generate([BHUJIA, POHA, DOSA]))
    c = report_to_json(generate([DOSA, BHUJIA, POHA]))
    assert a == b == c


def test_artifact_carries_no_timestamp():
    """A wall-clock field would break determinism and with it reviewability."""
    blob = report_to_json(generate([POHA, DOSA, BHUJIA])).lower()
    for banned in ("generated_at", "timestamp", "created_at", "utcnow"):
        assert banned not in blob


def test_input_digest_changes_only_when_input_changes():
    base = generate([POHA, DOSA]).input_digest
    assert generate([DOSA, POHA]).input_digest == base
    changed = generate([POHA, dish(DOSA.id, "Masala dosaa")]).input_digest
    assert changed != base


def test_digest_is_a_sha256():
    digest = generate([POHA]).input_digest
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64


def test_curated_alias_order_does_not_affect_output():
    """names_i18n is JSONB; array order is not stable across a dump/restore."""
    one = dish("id-1", "Poha", curated_aliases=("avalakki", "chivda"))
    two = dish("id-1", "Poha", curated_aliases=("chivda", "avalakki"))
    a = {c.normalized for c in generate([one]).accepted}
    b = {c.normalized for c in generate([two]).accepted}
    assert a == b


# ----------------------------------------------------------- normalisation

def test_possessive_is_collapsed_before_normalize():
    """normalize() alone turns Haldiram's into 'haldiram s' -- a stray token."""
    assert normalize("Haldiram's") == "haldiram s"
    assert collapse_possessive("Haldiram's") == "Haldirams"
    assert norm("Haldiram's") == "haldirams"


def test_norm_matches_project_normalize_for_plain_text():
    for s in ["Masala Dosa", "Crème Fraîche", "Kerala fish curry", "MTR Rava"]:
        assert norm(s) == normalize(s)


def test_every_candidate_normalized_field_equals_norm_of_alias():
    for rec in (POHA, DOSA, BHUJIA):
        for cand in generate_for_food(rec):
            assert cand.normalized == norm(cand.alias)


def test_accepted_aliases_are_never_empty_or_padded():
    for cand in generate([POHA, DOSA, BHUJIA]).accepted:
        assert cand.normalized
        assert cand.normalized == cand.normalized.strip()
        assert "  " not in cand.normalized


def test_diacritics_are_folded():
    rec = product("id-n", "Nestlé Milkmaid", "Nestlé India")
    assert any(c.normalized == "nestle milkmaid" for c in generate_for_food(rec))


# ------------------------------------------------------- collision: empty

def test_empty_alias_is_rejected_and_reported():
    rec = dish("id-e", "Poha", curated_aliases=(".", "   ", "###"))
    report = generate([rec])
    kinds = [f.kind for f in report.findings]
    assert kinds.count("empty") == 3
    assert all(c.normalized for c in report.accepted)


def test_empty_findings_are_blocking():
    rec = dish("id-e", "Poha", curated_aliases=(".",))
    empties = [f for f in generate([rec]).findings if f.kind == "empty"]
    assert empties and all(f.severity == "block" for f in empties)


# --------------------------------------------------- collision: duplicate

def test_duplicate_alias_on_same_food_is_collapsed():
    """Would otherwise violate uq_alias_food_norm_lang at INSERT time."""
    rec = dish("id-d", "Poha", curated_aliases=("Poha", "poha", "POHA"))
    report = generate([rec])
    normals = [c.normalized for c in report.accepted]
    assert normals.count("poha") == 1
    assert any(f.kind in ("duplicate", "case_or_punctuation_variant")
               for f in report.findings)


def test_duplicate_keeps_the_highest_confidence_rule():
    rec = dish("id-d", "Poha", curated_aliases=("poha",))
    winner = [c for c in generate([rec]).accepted if c.normalized == "poha"]
    assert len(winner) == 1
    # canonical (1.0) must beat curated_alias (0.9)
    assert winner[0].rule == "canonical_name"
    assert winner[0].confidence == 1.0


def test_case_and_punctuation_only_variants_are_reported_separately():
    """A rule overlap and a data-entry inconsistency are different problems."""
    rec = dish("id-c", "Poha", curated_aliases=("Avalakki", "avalakki!",
                                                "  AVALAKKI  "))
    report = generate([rec])
    kinds = {f.kind for f in report.findings}
    assert "case_or_punctuation_variant" in kinds
    variant = [f for f in report.findings
               if f.kind == "case_or_punctuation_variant"][0]
    assert variant.normalized == "avalakki"
    assert sum(c.normalized == "avalakki" for c in report.accepted) == 1


def test_identical_raw_text_is_a_plain_duplicate_not_a_variant():
    """Byte-identical text from two rules is a rule overlap, not a variant.

    Note the lowercase name: with "Poha" the canonical rule emits "Poha" and
    the curated rule emits "poha", which differ by case and are therefore
    correctly the OTHER kind.
    """
    rec = dish("id-p", "poha", curated_aliases=("poha",))
    kinds = {f.kind for f in generate([rec]).findings}
    assert "duplicate" in kinds
    assert "case_or_punctuation_variant" not in kinds


# ----------------------------------------------------- collision: missing

def test_alias_targeting_a_missing_food_is_rejected():
    """food_aliases.food_item_id carries an FK; a stale id aborts the batch."""
    report = generate([POHA], known_food_ids=frozenset({"some-other-id"}))
    assert report.accepted == []
    assert all(f.kind == "missing_target" for f in report.findings)
    assert all(f.severity == "block" for f in report.findings)


def test_missing_target_finding_names_the_id():
    report = generate([POHA], known_food_ids=frozenset())
    assert any(POHA.id in f.detail for f in report.findings)
    assert any(POHA.id in f.food_item_ids for f in report.findings)


def test_known_ids_omitted_means_no_target_check():
    """None disables the check; an empty frozenset rejects everything."""
    assert generate([POHA]).accepted
    assert generate([POHA], known_food_ids=None).accepted
    assert not generate([POHA], known_food_ids=frozenset()).accepted


def test_present_targets_pass_the_check():
    report = generate([POHA, DOSA],
                      known_food_ids=frozenset({POHA.id, DOSA.id}))
    assert report.accepted
    assert not [f for f in report.findings if f.kind == "missing_target"]


# ------------------------------------------------------------ idempotence

def test_regenerating_over_the_same_input_is_a_no_op():
    """The import step must be safely re-runnable, so generation must be too."""
    records = [POHA, DOSA, BHUJIA]
    a = generate(records)
    b = generate(records)
    assert [c.as_dict() for c in a.accepted] == [c.as_dict() for c in b.accepted]
    assert [f.as_dict() for f in a.findings] == [f.as_dict() for f in b.findings]
    assert a.counts == b.counts
    assert a.input_digest == b.input_digest


def test_generate_does_not_mutate_its_input():
    records = [POHA, DOSA, BHUJIA]
    before = [dataclass_snapshot(r) for r in records]
    generate(records)
    assert [dataclass_snapshot(r) for r in records] == before


def dataclass_snapshot(rec: FoodRecord) -> tuple:
    return (rec.id, rec.name, rec.brand, rec.source, rec.cuisine,
            rec.category, rec.countries, rec.curated_aliases)


def test_no_accepted_pair_shares_food_and_normalized():
    report = generate([POHA, DOSA, BHUJIA])
    keys = [(c.food_item_id, c.normalized, c.lang) for c in report.accepted]
    assert len(keys) == len(set(keys)), "would violate the UNIQUE constraint"


# --------------------------------------------------- collision: ambiguous

def test_alias_mapping_to_two_foods_is_flagged_not_dropped():
    a = dish("id-a", "Kadala curry", curated_aliases=("kadala kari",))
    b = dish("id-b", "Kerala kadala", curated_aliases=("kadala kari",))
    report = generate([a, b])
    amb = [f for f in report.findings if f.kind == "ambiguous"]
    assert any(f.normalized == "kadala kari" for f in amb)
    # Flagged for a human, NOT auto-removed: two regional variants sharing a
    # name can be legitimate.
    assert sum(c.normalized == "kadala kari" for c in report.accepted) == 2
    assert all(f.severity == "review" for f in amb)


def test_ambiguous_finding_lists_every_target():
    a = dish("id-a", "Dosa one", curated_aliases=("shared name",))
    b = dish("id-b", "Dosa two", curated_aliases=("shared name",))
    c = dish("id-c", "Dosa three", curated_aliases=("shared name",))
    amb = [f for f in generate([a, b, c]).findings
           if f.kind == "ambiguous" and f.normalized == "shared name"]
    assert len(amb) == 1
    assert set(amb[0].food_item_ids) == {"id-a", "id-b", "id-c"}


def test_unambiguous_alias_produces_no_ambiguous_finding():
    report = generate([POHA])
    assert not [f for f in report.findings if f.kind == "ambiguous"]


def test_alias_shadowing_another_foods_name_is_flagged():
    rec = dish("id-s", "Flattened rice", curated_aliases=("poha",))
    report = generate([rec], existing_food_names=frozenset({"poha"}))
    assert any(f.kind == "shadows_food_name" and f.normalized == "poha"
               for f in report.findings)


# ------------------------------------------------------- collision: broad

@pytest.mark.parametrize("alias", ["curry", "rice", "dal", "milk", "snack"])
def test_single_generic_term_is_rejected_as_broad(alias):
    rec = dish("id-b", "Kerala fish curry", curated_aliases=(alias,))
    report = generate([rec])
    assert not any(c.normalized == alias for c in report.accepted)
    assert any(f.kind == "broad" and f.normalized == alias
               for f in report.findings)


def test_all_generic_multiword_alias_is_rejected():
    assert is_broad("curry rice")[0]
    assert is_broad("milk powder")[0]


def test_short_alias_is_rejected():
    assert is_broad("idl")[0]
    assert not is_broad("idli")[0]
    assert len("idli") == MIN_LATIN_ALIAS_LEN


def test_specific_alias_survives():
    for good in ("aloo bhujia", "masala dosa", "avalakki", "kadala curry"):
        assert not is_broad(good)[0], good


def test_every_token_generic_is_broad_even_when_it_reads_naturally():
    """'fish curry' scans like a dish but names a category.

    There are dozens of fish curries; letting one row own the phrase makes it
    win a search it has no claim to. 'Kerala fish curry' qualifies it and
    survives -- the qualifier is exactly what makes it an identity.
    """
    assert is_broad("fish curry")[0]
    assert not is_broad("kerala fish curry")[0]


def test_canonical_name_is_never_rejected_as_broad():
    """A food genuinely called 'Rice' must keep its own name."""
    rec = FoodRecord(id="id-r", name="Rice", cuisine="global")
    report = generate([rec])
    assert any(c.normalized == "rice" and c.rule == "canonical_name"
               for c in report.accepted)


def test_broad_findings_are_blocking():
    rec = dish("id-b", "Fish curry", curated_aliases=("curry",))
    broad = [f for f in generate([rec]).findings if f.kind == "broad"]
    assert broad and all(f.severity == "block" for f in broad)


# ---------------------------------------------------------------- brands

def test_twelve_brand_families_exactly():
    assert len(BRAND_FAMILIES) == 12
    assert BRAND_ORDER == tuple(sorted(BRAND_FAMILIES))


def test_itc_requires_a_word_boundary():
    """ILIKE '%ITC%' matches 1,335 live rows; \\bitc\\b matches the real ones."""
    assert brand_family("ITC Limited") == "ITC"
    assert brand_family("Kitchen Treasures") is None
    assert brand_family("Mitchell's") is None
    assert brand_family("Switch Beverages") is None


def test_global_marks_are_india_gated():
    assert brand_family("Nestlé") is None
    assert brand_family("Nestlé India") == "Nestle India"
    assert brand_family("Nestlé", countries=("India",)) == "Nestle India"
    assert brand_family("Tata") is None
    assert brand_family("Tata Consumer Products India") == "Tata"


def test_ungated_brands_match_directly():
    assert brand_family("Amul") == "Amul"
    assert brand_family("Britannia Industries") == "Britannia"
    assert brand_family("Haldiram's") == "Haldiram's"
    assert brand_family("MTR Foods") == "MTR"
    assert brand_family("Mother Dairy") == "Mother Dairy"


def test_unknown_brand_returns_none():
    assert brand_family("Kellogg's") is None
    assert brand_family(None) is None
    assert brand_family("") is None


def test_brand_stripping_yields_the_searchable_residue():
    assert strip_brand(norm("Haldiram's Aloo Bhujia"), "Haldiram's") == "aloo bhujia"
    assert strip_brand("amul butter", "Amul") == "butter"


def test_brand_product_generates_brand_variants():
    types = {c.alias_type for c in generate_for_food(BHUJIA)}
    assert "brand_variant" in types
    assert any(c.normalized == "aloo bhujia" for c in generate_for_food(BHUJIA))


def test_is_indian_covers_cuisine_and_brand():
    assert is_indian(POHA)
    assert is_indian(BHUJIA)
    assert not is_indian(FoodRecord(id="x", name="Pizza", cuisine="italian"))


# ------------------------------------------------ romanisation variants

def test_spelling_variants_are_single_substitution():
    assert "alu" in spelling_variants("aloo")
    assert "panir" in spelling_variants("paneer")


def test_spelling_variants_are_bounded_and_stable():
    seed = "bhaaghee khoobaa"
    first = spelling_variants(seed)
    assert first == spelling_variants(seed)
    assert len(first) <= 6
    assert len(first) == len(set(first))


def test_spelling_variants_never_returns_the_seed():
    assert "aloo" not in spelling_variants("aloo")


def test_romanisation_is_not_applied_to_western_food():
    """'smoothie' must not become 'smootie'."""
    rec = FoodRecord(id="id-w", name="Smoothie", cuisine="american")
    assert not [c for c in generate_for_food(rec)
                if c.rule == "romanisation_variant"]


@pytest.mark.parametrize("english", [
    "cookies", "hide seek cashew butter", "beef dripping",
    "maggi masala 2 minute noodles", "cheese spread",
])
def test_english_tokens_are_never_romanised(english):
    """Measured regression: an Indian BRAND is not an Indian WORD.

    The first cut gated per-food, so Britannia's English product names were
    rewritten to cukies / hide sik / bif dripping / nudles. The gate is now
    per-token.
    """
    for variant in spelling_variants(english):
        for junk in ("cukies", "sik", "bif", "nudles", "chese"):
            assert junk not in variant.split(), (english, variant)


def test_indic_tokens_are_still_romanised_beside_english_ones():
    assert "palak panir" in spelling_variants("palak paneer")
    assert "alu tikki" in spelling_variants("aloo tikki")
    # 'butter' is English and must survive untouched next to an Indic word.
    assert any(v.startswith("panir") and v.endswith("butter")
               for v in spelling_variants("paneer butter"))


def test_pack_sizes_are_not_treated_as_words():
    assert all("280" in v for v in spelling_variants("aloo bhujia 280 gm"))


def test_spelling_variants_returns_nothing_when_every_token_is_skipped():
    assert spelling_variants("cheese noodles butter") == []


# ------------------------------------------------- review output structure

def test_artifact_top_level_keys():
    d = report_to_dict(generate([POHA, DOSA, BHUJIA]))
    assert set(d) == {"generator_version", "input_digest", "sources",
                      "counts", "findings", "aliases", "import_ready",
                      "rejected"}
    assert d["generator_version"] == GENERATOR_VERSION


def test_every_alias_record_has_the_required_review_fields():
    """Source food, alias, type and reason -- the four the reviewer needs."""
    required = {"food_item_id", "target_name", "alias", "normalized",
                "alias_type", "source", "confidence", "script", "lang",
                "rule", "reason", "status", "import_ready",
                "review_classification", "exclusion_reason"}
    for rec in report_to_dict(generate([POHA, DOSA, BHUJIA]))["aliases"]:
        assert set(rec) == required
        assert rec["reason"], "every alias must explain itself"
        assert rec["rule"]


def test_every_finding_has_the_required_fields():
    rec = dish("id-f", "Fish curry", curated_aliases=("curry", "."))
    for f in report_to_dict(generate([rec]))["findings"]:
        assert set(f) == {"kind", "severity", "normalized", "detail",
                          "food_item_ids"}
        assert f["detail"]
        assert isinstance(f["food_item_ids"], list)


def test_alias_type_and_source_match_the_check_constraints():
    report = generate([POHA, DOSA, BHUJIA])
    for cand in report.accepted + report.rejected:
        assert cand.alias_type in ALIAS_TYPES
        assert cand.source in ALIAS_SOURCES


def test_confidence_is_within_the_check_constraint_range():
    for cand in generate([POHA, DOSA, BHUJIA]).accepted:
        assert 0.0 <= cand.confidence <= 1.0


def test_counts_reconcile_with_the_lists():
    report = generate([POHA, DOSA, BHUJIA])
    c = report.counts
    assert c["accepted"] == len(report.accepted)
    assert c["rejected"] == len(report.rejected)
    assert c["findings"] == len(report.findings)
    assert c["accepted"] + c["rejected"] == c["candidates_generated"]
    assert sum(c["by_alias_type"].values()) == c["accepted"]
    assert sum(c["by_source"].values()) == c["accepted"]


def test_artifact_is_valid_json_and_round_trips():
    blob = report_to_json(generate([POHA, DOSA, BHUJIA]))
    assert blob.endswith("\n")
    assert json.loads(blob)["counts"]["input_foods"] == 3


def test_artifact_keys_are_sorted_for_clean_diffs():
    blob = report_to_json(generate([POHA]))
    parsed = json.loads(blob)
    assert list(parsed) == sorted(parsed)


def test_machine_derived_aliases_are_marked_ai():
    """Provenance is what stops a generated alias raising verification_tier."""
    for cand in generate([POHA, BHUJIA]).accepted:
        if cand.rule in ("romanisation_variant", "brand_stripped",
                         "brand_prefixed"):
            assert cand.source == "ai"
        if cand.rule in ("canonical_name", "curated_alias"):
            assert cand.source == "curated"


def test_accepted_list_is_sorted():
    accepted = generate([POHA, DOSA, BHUJIA]).accepted
    assert accepted == sorted(accepted)


def test_empty_input_produces_a_valid_empty_artifact():
    d = report_to_dict(generate([]))
    assert d["aliases"] == [] and d["findings"] == []
    assert d["counts"]["input_foods"] == 0


def test_lang_is_always_unspecified():
    """We know the script but never the language; '' is the honest value and
    the UNIQUE constraint is built to tolerate it."""
    for cand in generate([POHA, DOSA, BHUJIA]).accepted:
        assert cand.lang == ""


def test_candidate_is_frozen():
    cand = generate([POHA]).accepted[0]
    with pytest.raises(Exception):
        cand.normalized = "mutated"  # type: ignore[misc]


# ------------------------------------------------ artifact review counts

def test_artifact_reports_every_count_the_review_gate_asks_for():
    rec = dish("id-x", "Fish curry", curated_aliases=("curry", ".", "Curry"))
    counts = report_to_dict(generate([rec]))["counts"]
    for key in ("input_foods", "candidates_generated", "accepted", "rejected",
                "duplicates", "duplicates_exact",
                "duplicates_after_normalisation", "collisions",
                "collisions_multiple_targets", "collisions_with_food_names",
                "missing_targets", "broad_aliases", "empty_aliases"):
        assert key in counts, key
        assert isinstance(counts[key], int)


def test_named_rollups_agree_with_findings_by_kind():
    a = dish("id-a", "Dish one", curated_aliases=("shared", "curry", "."))
    b = dish("id-b", "Dish two", curated_aliases=("shared",))
    c = generate([a, b], existing_food_names=frozenset({"shared"})).counts
    k = c["findings_by_kind"]
    assert c["duplicates"] == (k.get("duplicate", 0)
                               + k.get("case_or_punctuation_variant", 0))
    assert c["collisions"] == (k.get("ambiguous", 0)
                               + k.get("shadows_food_name", 0))
    assert c["broad_aliases"] == k.get("broad", 0)
    assert c["empty_aliases"] == k.get("empty", 0)
    assert c["missing_targets"] == k.get("missing_target", 0)


def test_every_record_carries_a_status():
    rec = dish("id-s", "Fish curry", curated_aliases=("curry",))
    d = report_to_dict(generate([rec]))
    assert all(r["status"] == "accepted" for r in d["aliases"])
    assert all(r["status"] == "rejected" for r in d["rejected"])


def test_counts_reconcile_against_the_pre_filter_total():
    """candidates_generated must not shrink when the target filter runs."""
    full = generate([POHA]).counts["candidates_generated"]
    filtered = generate([POHA], known_food_ids=frozenset()).counts
    assert filtered["candidates_generated"] == full
    assert filtered["rejected"] == full and filtered["accepted"] == 0


# ------------------------------------------------- unicode and punctuation

def test_native_script_alias_survives_and_is_tagged():
    rec = dish("id-u", "Poha", curated_aliases=("पोहे",))
    cand = [c for c in generate([rec]).accepted if c.alias == "पोहे"]
    assert cand and cand[0].script == "deva"
    assert cand[0].normalized


def test_unicode_is_not_escaped_through_the_json_round_trip():
    rec = dish("id-u", "Poha", curated_aliases=("पोहे", "தோசை"))
    blob = report_to_json(generate([rec]))
    assert "पोहे" in blob and "தோசை" in blob
    assert any(r["alias"] == "पोहे" for r in json.loads(blob)["aliases"])


def test_punctuation_only_alias_is_never_kept():
    for junk in (".", "!!!", "---", "()"):
        rec = dish("id-j", "Poha", curated_aliases=(junk,))
        assert not [c for c in generate([rec]).accepted if c.alias == junk]


def test_combining_marks_are_preserved_for_indic_text():
    """Stripping on unicodedata.combining() would turn पोहे into पह."""
    rec = dish("id-m", "Poha", curated_aliases=("पोहे",))
    got = [c.normalized for c in generate([rec]).accepted if c.script == "deva"]
    assert got and len(got[0]) > 2


# -------------------------------------------- protection: no db, no barcode

def test_the_generator_imports_nothing_that_can_reach_a_database():
    """Purity is the safety property; this test is what enforces it."""
    src = pathlib.Path(alias_gen.__file__).read_text(encoding="utf-8")
    for banned in ("sqlalchemy", "asyncpg", "psycopg", "requests", "httpx",
                   "socket", "subprocess", "open("):
        assert banned not in src, banned


def test_food_record_cannot_carry_a_barcode():
    """An alias built from a barcode would be searchable numeric noise."""
    fields = {f.name for f in dataclasses.fields(FoodRecord)}
    assert "barcode" not in fields and "gtin14" not in fields
    with pytest.raises(TypeError):
        FoodRecord(id="i", name="n", barcode="0123456789012")  # type: ignore


def test_no_generated_alias_is_a_bare_number():
    rec = product("id-b", "Amul Butter 500 g", "Amul")
    for cand in generate([rec]).accepted:
        assert not cand.normalized.replace(" ", "").isdigit()


def test_generator_module_has_no_side_effects_on_import():
    importlib.reload(alias_gen)
    assert alias_gen.GENERATOR_VERSION == GENERATOR_VERSION


# ===================================================================
# Review decisions, enforced in code rather than only documented.
# ===================================================================

def branded(id_: str, name: str, brand: str, *aliases: str) -> FoodRecord:
    return FoodRecord(id=id_, name=name, brand=brand, cuisine="indian_south",
                      source="curated", curated_aliases=tuple(aliases))


AACHI_A = branded("aa-1", "Idli", "Aachi", "aachi", "aachi idli")
AACHI_B = branded("aa-2", "Rasam Powder", "Aachi", "aachi", "aachi rasam")
AACHI_SOLO = branded("aa-9", "Sambar Powder", "Aachi", "aachi")


# ---- decision 1: MIN_LATIN_ALIAS_LEN stays 4 -------------------------

def test_min_latin_alias_len_is_still_four():
    assert MIN_LATIN_ALIAS_LEN == 4


@pytest.mark.parametrize("short", ["mtr", "g", "nan", "osh"])
def test_the_four_short_aliases_are_rejected(short):
    """Decision 1: no automatic generation, and no exceptions added yet.

    'nan' (Naan) and 'osh' (Plov) are genuine names lost to this rule. They
    are documented in review/README.md as candidates for an explicit reviewed
    exception later -- deliberately NOT special-cased here.
    """
    rec = dish("id-short", "Some dish", curated_aliases=(short,))
    report = generate([rec])
    assert not [c for c in report.accepted if c.normalized == short]
    assert not [c for c in report.import_ready if c.normalized == short]
    assert any(f.kind == "broad" and f.normalized == short
               for f in report.findings)


def test_no_short_alias_exception_list_exists_yet():
    """If someone adds an allowlist, this test should be updated knowingly."""
    src = pathlib.Path(alias_gen.__file__).read_text(encoding="utf-8")
    for token in ("SHORT_ALIAS_EXCEPTIONS", "ALLOWED_SHORT", '"nan"', '"osh"'):
        assert token not in src, token


# ---- decision 2: bare-brand aliases excluded -------------------------

def test_bare_brand_alias_with_multiple_targets_is_excluded():
    report = generate([AACHI_A, AACHI_B])
    assert not [c for c in report.accepted if c.normalized == "aachi"]
    assert any(f.kind == "bare_brand" and f.normalized == "aachi"
               for f in report.findings)


def test_bare_brand_exclusion_is_blocking():
    bare = [f for f in generate([AACHI_A, AACHI_B]).findings
            if f.kind == "bare_brand"]
    assert bare and all(f.severity == "block" for f in bare)


def test_brand_qualified_aliases_remain_eligible():
    """Decision 2: do NOT exclude merely for containing the brand name."""
    ready = {c.normalized for c in generate([AACHI_A, AACHI_B]).import_ready}
    assert "aachi idli" in ready
    assert "aachi rasam" in ready
    assert "aachi" not in ready


def test_single_target_bare_brand_is_not_excluded():
    """Scoped to the multi-target case: one product, no ambiguity, no harm."""
    report = generate([AACHI_SOLO])
    assert any(c.normalized == "aachi" for c in report.accepted)
    assert not [f for f in report.findings if f.kind == "bare_brand"]


def test_bare_brand_detection_is_structural_not_a_blocklist():
    """A brand never named in BRAND_FAMILIES must still be caught."""
    x = branded("x-1", "Ragi Vermicelli", "Bambino", "bambino")
    y = branded("x-2", "Roasted Vermicelli", "Bambino", "bambino")
    assert any(f.kind == "bare_brand" and f.normalized == "bambino"
               for f in generate([x, y]).findings)
    # Word-boundary matched: "gits" is a substring of "digits", which appears
    # legitimately in the romanisation docstring.
    src = pathlib.Path(alias_gen.__file__).read_text(encoding="utf-8").lower()
    for name in ("bambino", "gits", "eastern", "double horse"):
        assert not re.search(r"%s" % re.escape(name), src), name


# ---- decision 3: ambiguity is deferred, never guessed ----------------

def test_ambiguous_alias_is_accepted_for_review_but_withheld_from_import():
    a = dish("am-1", "Kheer", curated_aliases=("payasam",))
    b = dish("am-2", "Palada Payasam Mix", curated_aliases=("payasam",))
    report = generate([a, b])
    assert sum(c.normalized == "payasam" for c in report.accepted) == 2
    assert not [c for c in report.import_ready if c.normalized == "payasam"]


def test_duplicate_catalogue_rows_are_a_separate_deferred_finding():
    """20 rows named 'Milo' is a data-quality issue, not alias ambiguity."""
    rows = [product("milo-%d" % i, "Milo", "Nestle India") for i in range(4)]
    findings = generate(rows).findings
    dup = [f for f in findings if f.kind == "duplicate_catalogue_row"]
    assert dup and dup[0].normalized == "milo"
    assert dup[0].severity == "deferred"
    assert len(dup[0].food_item_ids) == 4
    # Reported, not resolved: no merging, no arbitrary target chosen.
    assert not [f for f in findings if f.kind == "ambiguous"]


def test_duplicate_catalogue_rows_are_never_import_ready():
    rows = [product("milo-%d" % i, "Milo", "Nestle India") for i in range(4)]
    assert not [c for c in generate(rows).import_ready
                if c.normalized == "milo"]


def test_distinct_names_are_ambiguous_not_duplicate_rows():
    a = dish("d-1", "Dhokla", curated_aliases=("dhokla",))
    b = dish("d-2", "Khaman Dhokla Mix", curated_aliases=("dhokla",))
    kinds = {f.kind for f in generate([a, b]).findings}
    assert "ambiguous" in kinds
    assert "duplicate_catalogue_row" not in kinds


# ---- import-ready guarantees ----------------------------------------

def test_every_import_ready_candidate_has_exactly_one_target():
    report = generate([POHA, DOSA, BHUJIA, AACHI_A, AACHI_B])
    targets = {}
    for c in report.import_ready:
        targets.setdefault(c.normalized, set()).add(c.food_item_id)
    assert all(len(v) == 1 for v in targets.values())


def test_every_import_ready_candidate_has_complete_provenance():
    for c in generate([POHA, DOSA, BHUJIA, AACHI_A]).import_ready:
        assert c.food_item_id and c.alias and c.normalized
        assert c.alias_type in ALIAS_TYPES
        assert c.source in ALIAS_SOURCES
        assert c.rule and c.reason
        assert 0.0 <= c.confidence <= 1.0
        assert c.script and c.lang == ""


def test_no_import_ready_alias_is_empty_broad_duplicate_or_ambiguous():
    a = dish("g-1", "Fish curry", curated_aliases=("curry", ".", "payasam"))
    b = dish("g-2", "Kheer", curated_aliases=("payasam",))
    report = generate([a, b, AACHI_A, AACHI_B])
    seen = set()
    for c in report.import_ready:
        assert c.normalized                          # not empty
        if c.rule != "canonical_name":
            # canonical_name is exempt by design: a food genuinely called
            # "Fish curry" must keep its own name even though the phrase is
            # generic. See test_canonical_name_is_never_rejected_as_broad.
            assert not is_broad(c.normalized)[0], c.normalized
        assert (c.food_item_id, c.normalized) not in seen   # not duplicated
        seen.add((c.food_item_id, c.normalized))
    ambiguous = {f.normalized for f in report.findings
                 if f.kind in ("ambiguous", "duplicate_catalogue_row")}
    assert not ambiguous & {c.normalized for c in report.import_ready}


def test_import_ready_is_a_subset_of_accepted():
    report = generate([POHA, DOSA, BHUJIA, AACHI_A, AACHI_B])
    assert set(report.import_ready) <= set(report.accepted)
    assert report.counts["import_ready"] <= report.counts["accepted"]


def test_import_ready_plus_withheld_equals_accepted():
    c = generate([POHA, DOSA, BHUJIA, AACHI_A, AACHI_B]).counts
    assert c["import_ready"] + c["withheld_from_import"] == c["accepted"]


def test_artifact_reports_the_decision_counts():
    d = report_to_dict(generate([AACHI_A, AACHI_B]))
    for key in ("import_ready", "withheld_from_import",
                "ambiguous_candidates", "bare_brand_exclusions",
                "duplicate_catalogue_collisions"):
        assert key in d["counts"], key
    assert d["counts"]["bare_brand_exclusions"] >= 1


def test_import_ready_flag_matches_the_import_ready_list():
    d = report_to_dict(generate([POHA, AACHI_A, AACHI_B]))
    flagged = {(r["food_item_id"], r["normalized"])
               for r in d["aliases"] if r["import_ready"]}
    listed = {(r["food_item_id"], r["normalized"]) for r in d["import_ready"]}
    assert flagged == listed


def test_rejected_records_are_never_import_ready():
    d = report_to_dict(generate([AACHI_A, AACHI_B]))
    assert all(r["import_ready"] is False for r in d["rejected"])


# ---- determinism still holds after all of the above ------------------

def test_decisions_do_not_break_determinism():
    records = [POHA, DOSA, BHUJIA, AACHI_A, AACHI_B, AACHI_SOLO]
    first = report_to_json(generate(records))
    for _ in range(4):
        assert report_to_json(generate(records)) == first
    shuffled = list(reversed(records))
    assert report_to_json(generate(shuffled)) == first


def test_import_ready_list_is_sorted():
    ready = generate([POHA, DOSA, BHUJIA, AACHI_A, AACHI_B]).import_ready
    assert ready == sorted(ready)
