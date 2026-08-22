"""One normalisation of a food name, shared by every writer and the reader.

WHY THIS FILE EXISTS
`build_search_text` was implemented FIVE times -- in routers/foods.py and in
four ingest scripts -- with five different behaviours. Only two of them
included aliases. None of them stripped accents. The measurable consequence,
on the live catalogue:

    'creme fraiche'  -> 640 rows
    'crème fraîche'  -> 533 rows      DIFFERENT SETS

Two spellings of one product, two disjoint answers, because the row was
indexed under whichever spelling its ingest script happened to write. A search
index is only as consistent as the function that fills it, so there has to be
exactly one of those functions and everything has to call it.

TRANSLITERATION: PRAGMATIC, NOT SCHOLARLY
The obvious move is `indic-transliteration`. It was measured and rejected. It
pulls eleven transitive packages (typer, rich, regex, tqdm...) into a FastAPI
service, and more importantly it implements ISO-15919, which is built for
Sanskrit corpora rather than for search:

    தோசை     -> 'dhojhai'    (we need 'dosai' / 'dosa')
    சாம்பார்  -> 'jhambhar'   (we need 'sambar')
    இட்லி    -> 'idhli'      (we need 'idli')

3 of 8 target queries, 0 of 3 in Tamil. Strict romanisation is exactly wrong
here: Tamil script does not encode voicing, so த is 't' in one word and 'd' in
the next, and no single-output transliterator can be right for both. This
module therefore emits a CANDIDATE SET -- 'tosai', 'dosai', 'dosa' -- and lets
all of them become alias rows pointing at one food. Recall is what search
needs; precision is what the alias table's `confidence` column is for.

THE CODEPOINT TRICK
Indic blocks are laid out in parallel, 0x80 apart, inherited from ISCII:
Devanagari 0x0900, Bengali 0x0980, Gurmukhi 0x0A00, Gujarati 0x0A80,
Oriya 0x0B00, Tamil 0x0B80, Telugu 0x0C00, Kannada 0x0C80, Malayalam 0x0D00.
So ಕ (0x0C95) - 0x0C80 + 0x0900 = क. Eight scripts fold onto one table
instead of eight hand-maintained ones, and a bug fixed in the Devanagari map
is fixed everywhere. Tamil is the one script that needs phonetic overrides on
top, because its consonant inventory is genuinely smaller.

Pure functions, no I/O, no database. Every branch is unit-testable.
"""

from __future__ import annotations

import itertools
import re
import unicodedata

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

#: Combining Diacritical Marks, U+0300-U+036F. THIS RANGE, NOT
#: `unicodedata.combining()`.
#:
#: The obvious implementation -- decompose, then drop every character with a
#: non-zero combining class -- destroys Indic text. Devanagari vowel signs and
#: the virama are combining marks too, so `unicodedata.combining()` is True for
#: them, and stripping on that test turns पोहे into पह: every vowel gone, the
#: word unrecoverable. This block covers the Latin/Greek/Cyrillic diacritics we
#: actually want to fold and stops well short of U+0900.
_LATIN_MARKS = re.compile(r"[̀-ͯ]")

#: Replaced with a space, not deleted -- "haldiram's-bhujia" must become three
#: tokens, and deletion would weld them into one that matches nothing.
#:
#: An explicit set rather than `[^\w\s]`: `\w` excludes the Devanagari virama
#: (category Mn, not alphanumeric), so the negated-class version silently
#: stripped viramas and mangled every conjunct consonant.
_PUNCT = re.compile(r"[!-/:-@\[-`{-~‐-‧‰-⁞]")

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Fold a food name to its canonical comparable form.

    NFKD -> strip Latin diacritics -> casefold -> punctuation to space ->
    collapse whitespace. Indic text passes through with its marks intact.

    Idempotent: `normalize(normalize(x)) == normalize(x)` for all x, which is
    what lets it run at both write time and query time without drift.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = _LATIN_MARKS.sub("", decomposed)
    # casefold, not lower: 'ß' -> 'ss', and the Turkish dotted/dotless i pair
    # compare equal. Brand names arrive from 200-odd locales.
    folded = stripped.casefold()
    spaced = _PUNCT.sub(" ", folded)
    return _WS.sub(" ", spaced).strip()


def fold_ascii(text: str) -> str:
    """Normalise, then drop anything outside ASCII.

    Used for the Latin-script alias of a native-script name, where the caller
    wants something a US keyboard can type.
    """
    return _WS.sub(" ", "".join(c for c in normalize(text) if c.isascii())).strip()


# ---------------------------------------------------------------------------
# Script detection
# ---------------------------------------------------------------------------

#: ISO 15924 code -> (block start, block end). Ordered by how likely we are to
#: see it, which only affects the scan cost.
_BLOCKS: tuple[tuple[str, int, int], ...] = (
    ("deva", 0x0900, 0x097F),   # Hindi, Marathi, Nepali, Sanskrit
    ("beng", 0x0980, 0x09FF),   # Bengali, Assamese
    ("guru", 0x0A00, 0x0A7F),   # Punjabi
    ("gujr", 0x0A80, 0x0AFF),   # Gujarati
    ("orya", 0x0B00, 0x0B7F),   # Odia
    ("taml", 0x0B80, 0x0BFF),   # Tamil
    ("telu", 0x0C00, 0x0C7F),   # Telugu
    ("knda", 0x0C80, 0x0CFF),   # Kannada
    ("mlym", 0x0D00, 0x0D7F),   # Malayalam
    ("arab", 0x0600, 0x06FF),   # Urdu
    ("hans", 0x4E00, 0x9FFF),   # CJK
)

#: Every Indic block above sits 0x80 apart and shares Devanagari's internal
#: ordering. This is what lets one table serve eight scripts.
_DEVA_BASE = 0x0900


def detect_script(text: str) -> str:
    """ISO 15924 code for the dominant script, or 'latn'.

    Counts characters per block rather than trusting the first one, because a
    real product name is routinely mixed: 'Amul मलाई Paneer'.
    """
    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        for code, lo, hi in _BLOCKS:
            if lo <= cp <= hi:
                counts[code] = counts.get(code, 0) + 1
                break
    if not counts:
        return "latn"
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _to_devanagari(text: str, script: str) -> str:
    """Shift an Indic string onto the Devanagari block. See the module note."""
    for code, lo, _hi in _BLOCKS:
        if code == script and code not in ("arab", "hans", "latn"):
            offset = _DEVA_BASE - lo
            return "".join(
                chr(ord(c) + offset) if lo <= ord(c) <= lo + 0x7F else c
                for c in text
            )
    return text


# ---------------------------------------------------------------------------
# The Devanagari -> Latin table
# ---------------------------------------------------------------------------

#: Independent vowels. Long forms fold to short in the second candidate; a
#: search index gains nothing from the distinction and 'saambaar' would only
#: ever be typed as 'sambar'.
_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ii",
    "उ": "u", "ऊ": "uu", "ऋ": "ri", "ए": "e",
    "ऐ": "ai", "ओ": "o", "औ": "au", "ऍ": "e",
    "ऑ": "o",
}

#: Vowel signs (matras). Attach to the preceding consonant and REPLACE its
#: inherent 'a' -- that replacement is the whole of abugida handling.
_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ii", "ु": "u",
    "ू": "uu", "ृ": "ri", "े": "e", "ै": "ai",
    "ो": "o", "ौ": "au", "ॅ": "e", "ॉ": "o",
}

_VIRAMA = "्"

#: Consonants, carrying an inherent 'a' unless a matra or virama follows.
_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "k", "ख़": "kh", "ग़": "g", "ज़": "z",
    "ड़": "r", "ढ़": "rh", "फ़": "f", "ऩ": "n",
}

#: Anusvara / chandrabindu / visarga.
_SIGNS = {"ं": "n", "ँ": "n", "ः": "h"}

#: TAMIL PHONETIC OVERRIDES, applied after the codepoint shift.
#:
#: Tamil writes one letter where Devanagari writes four, and does not mark
#: voicing at all: த is 't' in 'thayir' and 'd' in 'dosai', decided by position
#: and by loanword history, not by anything in the text. A single output is
#: therefore wrong roughly half the time, so these map to CANDIDATE SETS.
#:
#: ச is the one that matters most. ISO renders it 'c' and the library we
#: measured renders it 'jh'; a Tamil speaker searching for சாம்பார் types
#: 'sambar'. 's' leads the tuple because it is what users actually type.
_TAMIL_ALT: dict[str, tuple[str, ...]] = {
    "च": ("s", "ch", "c"),          # ச
    "त": ("t", "d", "th"),          # த
    "क": ("k", "g"),                # க
    "प": ("p", "b"),                # ப
    "ट": ("t", "d"),                # ட
    "स": ("s",),                    # ஸ
}

#: Cap on emitted candidates. Six ambiguous consonants in one word is 700+
#: combinations, and rows past the first handful are noise that would only
#: dilute the alias table.
_MAX_CANDIDATES = 8

_LONG_VOWELS = (("aa", "a"), ("ii", "i"), ("uu", "u"), ("ee", "e"), ("oo", "o"))

#: Scripts whose languages delete the word-final inherent vowel.
#:
#: Hindi, Bengali, Gujarati and Punjabi all write the schwa and none of them
#: pronounce it at the end of a word: साम्भार is 'sambhar', not 'sambhara'.
#: The Dravidian scripts do NOT do this -- Tamil 'idli' and Kannada 'avalakki'
#: keep their final vowel -- so applying the rule to them would break exactly
#: the queries this module exists to fix.
_SCHWA_DELETING = frozenset({"deva", "beng", "gujr", "guru", "orya"})


def _shorten(text: str) -> str:
    """'saambaar' -> 'sambar'. The form a user actually types."""
    for long, short in _LONG_VOWELS:
        text = text.replace(long, short)
    return text


def _deva_to_latin(deva: str, tamil: bool) -> list[str]:
    """Walk the abugida, emitting one token list per character.

    Each token is a tuple of alternatives; the product of them is the candidate
    set. For non-Tamil input every tuple has length one and the product is a
    single string.
    """
    tokens: list[tuple[str, ...]] = []
    i = 0
    n = len(deva)
    while i < n:
        ch = deva[i]
        if ch in _CONSONANTS:
            alts = _TAMIL_ALT.get(ch) if tamil else None
            base: tuple[str, ...] = alts or (_CONSONANTS[ch],)
            nxt = deva[i + 1] if i + 1 < n else ""
            if nxt == _VIRAMA:
                tokens.append(base)          # bare consonant, no inherent vowel
                i += 2
                continue
            if nxt in _MATRAS:
                m = _MATRAS[nxt]
                tokens.append(tuple(b + m for b in base))
                i += 2
                continue
            tokens.append(tuple(b + "a" for b in base))   # inherent 'a'
            i += 1
            continue
        if ch in _VOWELS:
            tokens.append((_VOWELS[ch],))
        elif ch in _SIGNS:
            tokens.append((_SIGNS[ch],))
        elif ch in _MATRAS:
            # A matra with no consonant before it -- malformed input, or a
            # fragment. Take it at face value rather than dropping the word.
            tokens.append((_MATRAS[ch],))
        elif ch.isspace():
            tokens.append((" ",))
        elif ch.isascii():
            tokens.append((ch,))
        i += 1

    if not tokens:
        return []

    out: list[str] = []
    for combo in itertools.product(*tokens):
        out.append("".join(combo))
        if len(out) >= _MAX_CANDIDATES:
            break
    return out


def transliterate(text: str) -> list[str]:
    """Romanise an Indic food name into ranked search candidates.

    Returns [] for Latin input -- there is nothing to transliterate, and an
    empty list is what tells the caller not to write an alias row.

    Most likely form first. Both the long-vowel form and its shortened variant
    are emitted, deduplicated, because users type either.

    >>> transliterate("पोहे")
    ['pohe']
    >>> transliterate("சாம்பார்")[0]
    'sambar'
    """
    if not text:
        return []

    # COMPOSE FIRST. This is load-bearing, not tidiness.
    #
    # Several Indic vowel signs are canonically decomposable: Tamil ோ (U+0BCB)
    # is ெ (U+0BC7) + ா (U+0BBE), and Bengali ো likewise. The walker below
    # reads one matra per consonant, so a decomposed source string desynchs it
    # and தோசை romanises to 'teasai' instead of 'dosai' -- silently, with no
    # error, straight into the alias table.
    #
    # It reaches here two ways: real-world data arrives in both forms, and
    # `normalize()` applies NFKD, so `transliterate(normalize(x))` decomposes
    # by construction. NFC makes both spellings converge before the walk.
    text = unicodedata.normalize("NFC", text)

    script = detect_script(text)
    if script in ("latn", "arab", "hans"):
        # Arabic and CJK are not abugidas; this table cannot serve them, and a
        # wrong romanisation is worse than none.
        return []

    deva = _to_devanagari(text, script)
    raw = _deva_to_latin(deva, tamil=(script == "taml"))

    # Word-final schwa deletion, and only where the language actually does it.
    # Applied when the source ends on a bare consonant -- i.e. the trailing
    # 'a' came from the inherent vowel rather than from a matra the writer
    # chose to put there.
    drop_schwa = script in _SCHWA_DELETING and deva and deva[-1] in _CONSONANTS

    seen: dict[str, None] = {}
    for candidate in raw:
        forms = [_shorten(candidate), candidate]
        if drop_schwa:
            # Deleted form FIRST: it is what a speaker types.
            forms = [f[:-1] for f in forms if f.endswith("a")] + forms
        for form in forms:
            cleaned = _WS.sub(" ", form).strip()
            if cleaned and cleaned not in seen:
                seen[cleaned] = None
    return list(seen)[:_MAX_CANDIDATES]


# ---------------------------------------------------------------------------
# The one search-text builder
# ---------------------------------------------------------------------------


def build_search_text(
    name: str,
    brand: str | None = None,
    category: str | None = None,
    cuisine: str | None = None,
    aliases: object = (),
    extra: object = (),
) -> str:
    """The denormalised blob `ix_food_search_trgm` indexes.

    THE SIGNATURE IS A UNION OF THE FIVE IT REPLACES, deliberately: foods.py
    passed (name, brand, names_i18n, category), seed_dishes passed cuisine and
    aliases, ingest_usda passed a category string, ingest_store_brands passed a
    retailer. Every one of those maps onto a parameter here, so the call sites
    converge on one implementation without any of them losing a field.

    `aliases` and `extra` accept a str, a list, or the whole `names_i18n` dict.
    That dict is NOT alias-only -- it also carries `basis`, `makes`,
    `data_notes`, `validation` and `preparation_key`, the last of which
    routers/preparations.py reads at runtime. Only list and str values are
    harvested, so passing the dict whole is safe and the other keys are left
    exactly as they are.

    Underscores become spaces: cuisines are stored as 'indian_north', and a
    trigram index treats 'indian_north' as one long token that 'north indian'
    never matches.
    """
    parts: list[str] = [name or "", brand or "", category or "", cuisine or ""]

    for source in (aliases, extra):
        if isinstance(source, str):
            parts.append(source)
        elif isinstance(source, dict):
            # LIST VALUES ONLY -- scalar strings in this dict are prose, not
            # names, and indexing them poisons search.
            #
            # The Idli row's `data_notes` is a 190-character paragraph about
            # how Open Food Facts mis-files the product. Harvesting every str
            # value swept it into search_text, giving a 232-character blob for
            # a four-letter food, bloating the GIN index and making a query
            # for 'barcode' or 'panel' return Idli. `basis` and
            # `preparation_key` leak the same way ('poha_cooked' -> a stray
            # 'cooked' token).
            #
            # Aliases are always a list. Restricting to list values takes them
            # all and leaves the prose behind.
            for value in source.values():
                if isinstance(value, (list, tuple)):
                    parts.extend(str(v) for v in value if isinstance(v, str))
        elif isinstance(source, (list, tuple, set)):
            parts.extend(str(v) for v in source if isinstance(v, str))

    # Native-script aliases get their romanisation folded in too, so a row is
    # findable by 'pohe' even when only 'पोहे' was supplied.
    romanised: list[str] = []
    for part in parts:
        if part and detect_script(part) not in ("latn", "arab", "hans"):
            romanised.extend(transliterate(part))
    parts.extend(romanised)

    joined = " ".join(p for p in parts if p).replace("_", " ")
    return normalize(joined)
