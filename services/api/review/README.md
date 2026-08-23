# Phase 3a alias review

`generated_aliases.json` is a **review artifact, not an input**. Nothing in it
has been written to the database. It exists so a human can approve the alias
set before a separate import step creates `food_aliases` rows.

## Regenerating

```bash
cd services/api
python -m app.scripts.generate_aliases --expect-db trace --check-catalogue
```

The run opens a `SET TRANSACTION READ ONLY` connection, so Postgres itself
rejects a write even if the script is later edited to attempt one.

## The property that makes this reviewable

The output is **byte-identical** across runs on unchanged input — verified at
three runs against the live catalogue. There is no timestamp, no uuid, and no
dependency on set or dict iteration order. So:

```bash
md5sum review/generated_aliases.json      # before
python -m app.scripts.generate_aliases --expect-db trace --check-catalogue
md5sum review/generated_aliases.json      # after
```

A changed hash means a real change in the rules or the catalogue — never noise.
`input_digest` fingerprints the exact input set, so a diff can be attributed to
one or the other.

## Where the input comes from

| Source | Count | Definition lives in |
|---|---|---|
| Curated dishes | 347 | `food_items WHERE source='curated'`, seeded from `app/scripts/seed_dishes.py` + `data/indian_regional.py` + `data/world_regional.py` |
| Indian brand families | 12 families → 745 rows | `BRAND_FAMILIES` in `app/services/alias_gen.py` |
| After de-duplication by id | 1,077 | — |

**The 12-family list was not pre-existing in the repo.** It is a codification of
the list approved in conversation (Amul, Britannia, Haldiram's, Parle, MTR,
Tata, Mother Dairy, Nestlé India, Aachi, Everest, Dabur, ITC). Each is a
word-boundary regex, because `ILIKE '%ITC%'` matches 1,335 live rows —
"switch", "Mitchell", "kitchen" — against a few dozen real ITC products.
`Tata` and `Nestlé` are additionally India-gated; Nestlé alone matches 581 rows
worldwide.

## Rules, and what each is worth

| Rule | Type | Confidence | Source |
|---|---|---|---|
| `canonical_name` | canonical | 1.0 | curated |
| `curated_alias` | regional / colloquial | 0.9 | curated |
| `brand_stripped` | brand_variant | 0.75 | ai |
| `brand_prefixed` | brand_variant | 0.7 | ai |
| `romanisation_variant` | misspelling | 0.6 | ai |

`source='ai'` marks every machine-derived alias. Per the `FoodAlias` docstring,
such a row is searchable but must never raise a food's `verification_tier`.

## Applied review decisions

All four are enforced in code, each with tests. None is documentation-only.

### 1. `MIN_LATIN_ALIAS_LEN` stays 4

`mtr`, `g`, `nan` and `osh` are all rejected. No exception list exists, and
`test_no_short_alias_exception_list_exists_yet` fails if one is added silently.

**Deferred:** `nan` (Naan) and `osh` (Plov) are genuine names lost to this
rule. They may be reconsidered later as *explicit reviewed exceptions* — an
allowlist of specific approved short aliases, not a lowered threshold, since
lowering to 3 would admit `mtr` (8 products).

### 2. Bare-brand aliases excluded when multi-target

An alias equal to its food's own brand, sourced from `names_i18n.aliases`, and
mapping to more than one product is rejected: `aachi`, `gits`, `eastern`,
`bambino`, `double horse`. 35 exclusions.

The test is **structural** — the alias *is* the brand string — not a
hand-maintained blocklist, so brands never named in `BRAND_FAMILIES` are caught
too. Brand-**qualified** aliases (`aachi idli`, `aachi rasam powder`) are
untouched, and a bare brand with a single target is harmless and kept.

### 3. Duplicate catalogue rows deferred, not resolved

An alias hitting several rows that all share one normalised name is reported as
`duplicate_catalogue_row` (severity `deferred`) rather than `ambiguous`: 85
findings, including 20 rows named "Milo", 13 "Nesquik", 11 "Cerelac". No
`food_items` are merged, no arbitrary target is chosen, and none is imported.
This is a pre-existing Open Food Facts import issue that alias generation
surfaced; fixing it is separate work.

### 4. Import gated behind explicit approval

At the time these decisions were taken `food_aliases` had 0 rows and no import
script existed. Both have since changed — see **Import status** below.

## accepted vs import-ready

`accepted` is the review set. `import_ready` is the strict subset safe to
INSERT without a further human call: **exactly one target**, no ambiguity, no
bare brand, non-empty, not broad, not duplicated. Anything ambiguous stays in
`accepted` for review but is withheld, because choosing among several targets
by rule is precisely the guess this project refuses to make.

Every record in the artifact carries `status` and an `import_ready` boolean,
and the `import_ready` array is the same set materialised for convenience.

**`cheeselings` → `chiselings`** is held back via `EXCLUDED_PENDING_REVIEW` for
the same reason: a Parle brand coinage, not an Indic word, so the `ee→i` rule
should not have fired. It stays in the artifact classified
`excluded_pending_review` rather than deleted.

## Import status

The reviewed set **has been imported**: 1,353 rows in `food_aliases`, inserted
once after explicit approval, verified as 0 duplicates, 0 multi-target, 0
orphans, with all eight protected `food_items` columns byte-identical to their
pre-write fingerprints.

Re-running the importer is safe. It reports `would insert: 0 / already present:
1353` and writes nothing, because the INSERT carries `ON CONFLICT ON CONSTRAINT
uq_alias_food_norm_lang DO NOTHING`.

## What is NOT done

`food_items` was not modified and no migration was applied.

Two-arm search ranking **is now wired** into `routers/foods.py`: the direct arm
is the original query unchanged, and a second arm joins `food_aliases` on
`normalized` (active rows only). Both arms are bounded separately, merged and
de-duplicated by `services/search_rank.py`, and collapsed before the limit is
applied. Results carry `matched_via` and `matched_alias` so the UI can say why
a row appeared.

Coverage is only as good as the source data: 1,353 aliases across 1,077 foods,
out of 578,773 rows. `avalakki`, for instance, was never imported — the curated
Poha row lists `kanda poha` and nothing else.

## Attribution and licensing — NEEDS HUMAN/LEGAL REVIEW

The app credits each food's data source per row: Open Food Facts (ODbL), USDA
FoodData Central (public domain), or Trace's own curated dishes. Curated and
user-created rows are never labelled as Open Food Facts, and an unrecognised
source renders "SOURCE UNKNOWN" rather than a guess.

**Nothing in this repository asserts legal compliance, and this note is not
legal advice.** The implementation credits sources; it does not claim that
crediting them discharges any obligation. Open questions for a lawyer:

1. **ODbL is share-alike.** Whether display-only attribution inside a mobile
   app is sufficient, and what the notice must say and where it must appear.
2. **Display versus redistribution.** Trace currently displays Open Food Facts
   data. Exporting it, syncing it to a third party, or exposing it through a
   public API would likely be redistribution, which carries heavier
   obligations. `services/licensing.py` already has `is_exportable` and
   `export_filter_summary` for exactly this, and `source_licence='unknown'`
   is fail-closed.
3. **Derived values.** Recipe-composed dishes built partly from ODbL rows may
   themselves be derivative works. Not analysed.

Wording in `apps/mobile/src/lib/attribution.ts` and the profile screen is
deliberately conservative and factual: it states what the database records and
stops there. Change it only with legal input.
