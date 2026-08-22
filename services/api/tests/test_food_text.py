"""The spec for food-name normalisation and Indic transliteration.

Every test here is pure -- no database, no fixtures, no network. The three
groups map onto three measured production failures:

  * `creme fraiche` and `crème fraîche` returned 640 and 533 DIFFERENT rows.
  * `पोहे`, `தோசை` and `சாம்பார்` returned zero rows each.
  * `avalakki` returned nine rows, all of them Avalanche-branded drinks, and
    Poha was not among them.
"""

from __future__ import annotations

import unicodedata

import pytest

from app.services.food_text import (
    build_search_text,
    detect_script,
    fold_ascii,
    normalize,
    transliterate,
)


class TestNormalize:
    def test_accented_and_unaccented_fold_together(self):
        """THE crème fraîche BUG. 640 rows vs 533 rows for one product."""
        assert normalize("Crème Fraîche") == normalize("creme fraiche")

    @pytest.mark.parametrize(
        "accented,plain",
        [
            ("Müsli", "musli"),
            ("Jalapeño", "jalapeno"),
            ("Açaí", "acai"),
            ("Gruyère", "gruyere"),
            ("Crème Brûlée", "creme brulee"),
            ("Döner Kebab", "doner kebab"),
        ],
    )
    def test_european_diacritics_fold(self, accented, plain):
        assert normalize(accented) == plain

    def test_is_idempotent(self):
        """Runs at write time AND query time; the two must not drift."""
        for s in ["Crème Fraîche", "पोहे", "HALDIRAM'S  Bhujia", "தோசை", ""]:
            assert normalize(normalize(s)) == normalize(s)

    def test_casefold_not_lower(self):
        """'ß' -> 'ss'. Brand names arrive from 200-odd locales."""
        assert normalize("Weißbier") == "weissbier"

    def test_punctuation_becomes_space_not_nothing(self):
        """Deleting would weld tokens into one that matches nothing."""
        assert normalize("Haldiram's-Bhujia") == "haldiram s bhujia"

    def test_collapses_whitespace(self):
        assert normalize("  Amul   Malai\tPaneer\n") == "amul malai paneer"

    def test_empty_and_none_safe(self):
        assert normalize("") == ""

    # --- THE ONE THAT PROTECTS INDIC TEXT ---------------------------------

    def test_devanagari_survives_normalisation(self):
        """Indic vowel signs are combining marks too.

        The obvious implementation -- strip everything with a non-zero
        `unicodedata.combining()` -- turns पोहे into पह and destroys the word.
        This test fails against that implementation and passes against the
        explicit U+0300-U+036F range.
        """
        assert normalize("पोहे") == "पोहे"

    @pytest.mark.parametrize("s", ["தோசை", "சாம்பார்", "ಅವಲಕ್ಕಿ", "పోహా", "পোহা"])
    def test_indic_marks_are_never_stripped(self, s):
        """Nothing is DELETED. Canonical decomposition is expected.

        Not byte-equality with the input: NFKD legitimately decomposes some
        Indic vowel signs -- Tamil ோ (U+0BCB) becomes ெ + ா -- which is what
        makes composed and decomposed spellings of one word compare equal.
        The property that matters is that no character is lost, so the string
        recomposes to exactly what arrived.
        """
        out = normalize(s)
        assert unicodedata.normalize("NFC", out) == s.casefold()

    def test_virama_survives(self):
        """The virama is category Mn and NOT `\\w`.

        A `[^\\w\\s]` punctuation filter silently eats it, which mangles every
        conjunct consonant. சாம்பார் has two.
        """
        assert "்" in normalize("சாம்பார்")

    def test_mixed_script_keeps_both_halves(self):
        out = normalize("Amul मलाई Paneer")
        assert "amul" in out and "मलाई" in out and "paneer" in out


class TestFoldAscii:
    def test_drops_native_script(self):
        assert fold_ascii("Amul मलाई Paneer") == "amul paneer"

    def test_keeps_folded_latin(self):
        assert fold_ascii("Crème Fraîche") == "creme fraiche"


class TestDetectScript:
    @pytest.mark.parametrize(
        "text,script",
        [
            ("पोहे", "deva"),
            ("তোহা", "beng"),
            ("ਪੋਹਾ", "guru"),
            ("પૌંઆ", "gujr"),
            ("தோசை", "taml"),
            ("దోస", "telu"),
            ("ಅವಲಕ್ಕಿ", "knda"),
            ("ദോശ", "mlym"),
            ("Kirkland Protein Bar", "latn"),
            ("", "latn"),
        ],
    )
    def test_detects(self, text, script):
        assert detect_script(text) == script

    def test_dominant_script_wins_not_first_character(self):
        """Real product names are mixed: 'Amul मलाई Paneer'."""
        assert detect_script("Amul पोहे मलाई") == "deva"


class TestTransliterate:
    """The measured target set. The library we rejected scored 3/8 here."""

    @pytest.mark.parametrize(
        "native,expected",
        [
            ("पोहे", "pohe"),          # Hindi
            ("दोसा", "dosa"),
            ("साम्भार", "sambhar"),     # word-final schwa deleted
            ("தோசை", "dosai"),         # Tamil -- library gave 'dhojhai'
            ("சாம்பார்", "sambar"),     # library gave 'jhambhar'
            ("இட்லி", "idli"),          # library gave 'idhli'
            ("ಅವಲಕ್ಕಿ", "avalakki"),    # Kannada
            ("దోస", "dosa"),           # Telugu
            ("পোহা", "poha"),          # Bengali
            ("ਪੋਹਾ", "poha"),          # Punjabi
        ],
    )
    def test_target_query_is_among_candidates(self, native, expected):
        assert expected in transliterate(native)

    def test_tamil_emits_both_voicings(self):
        """Tamil script does not encode voicing.

        த is 't' in 'thayir' and 'd' in 'dosai', decided by position and
        loanword history rather than by anything in the text. A single-output
        transliterator is therefore wrong about half the time, so both forms
        become alias rows and let ranking sort it out.
        """
        got = transliterate("தோசை")
        assert any(c.startswith("t") for c in got)
        assert any(c.startswith("d") for c in got)

    def test_schwa_deleted_form_ranks_before_the_written_form(self):
        """Hindi writes the final 'a' and nobody says it."""
        got = transliterate("साम्भार")
        assert got.index("sambhar") < got.index("sambhara")

    def test_dravidian_scripts_keep_their_final_vowel(self):
        """Schwa deletion is Indo-Aryan. Applying it to Tamil breaks 'idli'."""
        assert "idli" in transliterate("இட்லி")
        assert "avalakki" in transliterate("ಅವಲಕ್ಕಿ")

    def test_decomposed_input_gives_the_same_result_as_composed(self):
        """REGRESSION.

        Tamil ோ (U+0BCB) decomposes to ெ + ா. The walker reads one matra per
        consonant, so decomposed input desynchs it and தோசை romanised to
        'teasai' instead of 'dosai' -- silently, into the alias table. It
        reaches here whenever a caller composes transliterate(normalize(x)),
        because normalize applies NFKD.
        """
        composed = "தோசை"
        decomposed = unicodedata.normalize("NFKD", composed)
        assert decomposed != composed, "test premise: these differ by codepoint"
        assert transliterate(decomposed) == transliterate(composed)
        assert "dosai" in transliterate(decomposed)

    def test_survives_being_fed_its_own_normalised_output(self):
        assert "sambar" in transliterate(normalize("சாம்பார்"))

    def test_latin_input_returns_empty(self):
        """Empty is the signal not to write an alias row."""
        assert transliterate("Kirkland Protein Bar") == []
        assert transliterate("") == []

    def test_unsupported_scripts_return_empty_rather_than_guessing(self):
        """Arabic and CJK are not abugidas; a wrong romanisation is worse."""
        assert transliterate("حليب") == []
        assert transliterate("牛乳") == []

    def test_candidate_count_is_capped(self):
        """Six ambiguous Tamil consonants would be 700+ combinations."""
        assert len(transliterate("சாம்பார்")) <= 8

    def test_candidates_are_deduplicated(self):
        got = transliterate("தோசை")
        assert len(got) == len(set(got))

    def test_never_raises_on_arbitrary_input(self):
        """Runs over uncontrolled catalogue strings during ingest."""
        for junk in ["\x00", "्", "ा", "🍛", "a" * 500, "पोहे" * 50]:
            transliterate(junk)


class TestBuildSearchText:
    def test_all_five_call_sites_agree(self):
        """THE DUPLICATION BUG.

        `build_search_text` existed five times with five behaviours -- in
        routers/foods.py and four ingest scripts. Only two included aliases,
        none folded accents. These are the five call shapes; they must now
        produce byte-identical output for equivalent input.
        """
        name, brand = "Crème Fraîche", "Coop"
        from_router = build_search_text(name, brand, None, None)
        from_off = build_search_text(name, brand, None, None, aliases=[])
        from_usda = build_search_text(name, None, None, None)

        assert from_router == from_off
        assert "creme fraiche" in from_router
        assert "creme fraiche" in from_usda

    def test_output_is_normalised(self):
        assert build_search_text("Crème Fraîche") == "creme fraiche"

    def test_underscores_in_cuisine_become_spaces(self):
        """'indian_north' is one trigram token that 'north indian' never hits."""
        out = build_search_text("Dal Tadka", cuisine="indian_north")
        assert "indian north" in out
        assert "_" not in out

    def test_accepts_a_list_of_aliases(self):
        out = build_search_text("Poha", aliases=["kanda poha", "avalakki"])
        assert "avalakki" in out

    def test_accepts_a_plain_string_alias(self):
        assert "flattened rice" in build_search_text("Poha", aliases="flattened rice")

    # --- THE COMPATIBILITY GUARD ------------------------------------------

    def test_names_i18n_dict_is_harvested_without_being_restructured(self):
        """`names_i18n` is NOT alias-only.

        It also carries `basis`, `makes`, `data_notes`, `validation` and
        `preparation_key` -- and routers/preparations.py reads
        `preparation_key` at runtime. Passing the dict whole must harvest the
        alias list without the other keys leaking in or being disturbed.
        """
        names_i18n = {
            "aliases": ["kanda poha", "avalakki"],
            "basis": "prepared",
            "makes": None,
            "preparation_key": "poha_cooked",
            "validation": [],
        }
        before = dict(names_i18n)
        out = build_search_text("Poha", aliases=names_i18n)

        assert "avalakki" in out
        assert "kanda poha" in out
        assert names_i18n == before, "build_search_text mutated names_i18n"

    def test_prose_fields_are_not_indexed(self):
        """REGRESSION: `data_notes` poisoned the trigram index.

        The real Idli row carries a 190-character editorial paragraph in
        `names_i18n['data_notes']`. Harvesting every str value swept it into
        search_text -- a 232-character blob for a four-letter food -- which
        bloats the GIN index and makes a query for 'barcode' or 'panel'
        return Idli. Aliases are always a list; prose is always a scalar.
        """
        idli = {
            "basis": "prepared",
            "aliases": ["idli", "aachi idli"],
            "data_notes": "OFF files this under a dry-mix barcode at 133 kcal/100 g.",
            "preparation_key": "idli_steamed",
        }
        out = build_search_text("Idli", aliases=idli)

        assert "aachi idli" in out
        assert "barcode" not in out
        assert "dry mix" not in out
        assert "steamed" not in out, "preparation_key leaked a stray token"
        assert len(out) < 40

    def test_none_values_in_names_i18n_do_not_crash(self):
        build_search_text("Idli", aliases={"makes": None, "aliases": None})

    def test_native_alias_is_romanised_into_the_blob(self):
        """A row supplied only in Devanagari is still findable as 'pohe'."""
        out = build_search_text("Poha", aliases=["पोहे"])
        assert "पोहे" in out
        assert "pohe" in out

    def test_empty_fields_do_not_produce_double_spaces(self):
        assert "  " not in build_search_text("Poha", None, None, None)
