# Trace implementation baseline — Phase 0

**Date:** 2026-08-29 · **Branch:** `master` · **HEAD:** `ec2fa7d`
**Database:** `trace` (PostgreSQL 18.4) · **Alembic revision:** `d5f18c04e7a3`

Read-only discovery against the running application and database. **No writes,
no migrations, no imports, no staged or committed changes.**

Companion artifacts:
`artifacts/trace-baseline-counts.json` · `artifacts/trace-data-quality-findings.jsonl`

---

## 0a. The gate: the scanner has never been measured, and the eval set is empty

**R13 is not one risk among fourteen. It is the risk that gates the product,
and it belongs above the catalogue findings below.**

Everything in the twenty-phase specification is downstream of knowing whether
`POST /api/foods/recognize` is accurate. A universal taxonomy over a catalogue
read by an unmeasured scanner is scaffolding around an unknown.

### What exists

The pipeline is built and the harness is built. `services/vision.py` calls
Gemini in two stages — `gemini-3.5-flash-lite`, escalating to `gemini-3.5-flash`
below a confidence threshold, ~25% escalating — and **already emits the
low/point/high band that `eval/score.py` grades on**. `eval_vision.py` is the
runner, `eval/score.py` the scorer, and they are deliberately separate so two
scorers cannot drift.

### What does not exist

The evaluation set was replaced on 2026-09-02 with a dorm-collectable design:
26 rows, mostly `label` tier, and a scorer that opens the photo files instead
of counting them. Current state:

```
$ python eval/score.py --validate

26 rows in manifest.csv
----------------------------------------------------------
       truth_kcal filled: 0/26
PASS  No guessed truth in the scored set
FAIL  Only 0 label/weighed rows (need 10)
       Ready-to-eat pouches and packaged food carry a printed
       panel -- that is label-tier truth with no cooking.
PASS  Indian rows: 17
PASS  high hidden-fat: 13
PASS  adversarial: 4
FAIL  Real photos: 0/26
       26 missing: in-001-mtr-dal-makhani-rice.jpg, ...
----------------------------------------------------------
Not ready. Fix the above before running the eval.
```

### The guard that was not there

The previous scorer printed `Photos present: 25/25`. That was `Path.exists()`
and nothing more -- it never opened a file. All 25 files were generated
placeholder cards sharing one background triple `(21, 26, 32)` across 40.4% to
53.1% of the frame. **The set passed its photo check for months while
containing no photograph of food at all.**

The count was the lie. A file-existence check answers "is there a file", and
the question was "is there a photograph". `is_placeholder()` -- downsample,
reject if one exact RGB triple covers more than 40% -- is what closed it, and
it now runs as a FAIL line inside `--validate` rather than as a thing somebody
remembers to check. All 25 cards have been deleted.

### What blocks the measurement

| Input | State | What it takes |
|---|---|---|
| Harness | OK built, and now checks photo content | -- |
| Endpoint | OK built, emits the band the scorer grades | -- |
| Refusal signal | OK closed 2026-09-02, see below | -- |
| Photographs | **0 of 26 real** | `eval/SHOPPING.md`: ~Rs 900, one grocery run |
| `truth_kcal` | 0 of 26 filled | A kitchen scale, plus the printed panels |
| Label/weighed rows | 0, needs 10 | Same task; the validator's own bar |

Neither is engineering. Both are a scale and a shop trip. **Six rows need no
cooking**, and six rows are worth running the eval on even though validation
will still fail: they answer whether the pipeline works end to end, whether
the model is roughly right or wildly off, and whether it refuses the opaque
box. None of those three is currently known.

### Cost, and why the free tier survives

At the measured **~$0.005 per scan**, fifty users scanning three meals a day
for eight weeks is:

```
0.005 x 3 x 56 x 50  =  $42
```

**Forty-two dollars for a fifty-user, eight-week beta.** That is the number
that decides whether photo scanning can stay free, and it says it comfortably
can. It also means the eval itself is nearly free to run: 26 photos, some
escalating to two calls, is well under a dollar.

### The contract gap between runner and scorer -- CLOSED 2026-09-02

`score.py` grades the four adversarial rows on behaviour rather than accuracy,
and the first clause of that grade reads a key called `refused`:

```python
good = got.get("refused") or band > 0.4 * kcal or conf < 0.6
```

Nothing in the pipeline ever produced that key. `.get()` returned `None`, the
clause fell through to band-and-confidence, and **a model that correctly
refused scored exactly the same as one that guessed confidently**. Product
invariant 3 says refusing to answer beats answering wrong; the harness could
not see the difference, so the one behaviour most worth measuring was the one
it structurally could not measure.

Closed by wiring the key through all four links:

| Link | Change |
|---|---|
| Model | `SYSTEM_PROMPT` gained a REFUSING IS A CORRECT ANSWER section, and `TOOL_SCHEMA` two optional fields |
| `vision._sanitize()` | returns `refused` and `refusal_reason`, defaulting to `False` / `""` |
| `eval_vision.py` | writes both into `results.json`, and prints `REFUSED` rather than `0 kcal` |
| `eval/score.py` | the inline predicate is now `adversarial_ok()`, so it can be asserted on |

`services/api/tests/test_eval_contract.py` guards each link separately, because
a break in any one of them is invisible in the other three. The test that
matters feeds `adversarial_ok()` a tight, confident band that fails every other
clause -- it can only pass on `refused`, so it flips the moment the key stops
arriving.

The prompt also gained a rule that a pale sauce is not automatically dairy
cream -- yoghurt, blended paneer, cashew and roux differ by up to 3x per gram,
and `fo-009`'s truth is a paneer-curd white sauce.

---

## 0. The finding that outranks the rest

**The Open Food Facts import made Trace worse at the one thing it exists to be
best at.**

Trace's differentiator is Indian food. The catalogue contains roughly **160
Indian regional rows** against **565,814 largely European packaged rows**, and
those packaged rows do not sit quietly beside the Indian ones — they crowd them
out of the result set.

Measured, not asserted. Ten representative Indian queries run through the
production `SEARCH_SQL` and the production ranker, read-only:

| query | results | top-10 composition |
|---|---|---|
| rasam | 10 | **7 OFF**, 3 curated |
| payasam | 10 | **6 OFF**, 3 curated, 1 USDA |
| bisibele bath | **1** | 1 curated |
| poha | 10 | **8 OFF**, 1 curated, 1 USDA |
| dal makhani | 10 | **8 OFF**, 2 curated |
| thoran | 10 | **9 OFF**, 1 curated |
| avial | 10 | **8 OFF**, 1 curated, 1 USDA |
| upma | 6 | 3 OFF, 2 curated, 1 USDA |
| pongal | 5 | 4 OFF, 1 curated |
| chana masala | 10 | **9 OFF**, 1 curated |

**62 of 82 results (76%) are Open Food Facts packaged rows.**

The ranker is not broken — the correct curated row is #1 for nine of the ten
queries. Everything below it is noise:

```
thoran   ->  2. Milk, White & Dark Fairground Favourites  [Thorntons]
             4. Jolly Santa Milk Chocolate                [Thorntons]
avial    ->  2. C-Vitamin 1000+                           [Avian Medicina]
             3. 6 Almond Fingers                          [Aviateur]
payasam  ->  3. Mini Paleta Payaso                        [Ricolino]
rasam    ->  4. Ice cream (raspberry & vanilla)           [Oppo]
             5. Rasa Rumput Laut (Nori Seaweed Flavour)   [Lay's]
pongal   ->  2. bot rieng galangal powder                 [Peacock Brand]
             5. Optigal Poulet nuggets                    [Migros]
```

A phone shows about six results. A user searching **thoran** sees one correct
answer and five chocolates. **bisibele bath returns a single row** in a
578,773-row catalogue.

This is a product-strategy finding, not a data-quality one, and it belongs
ahead of every table below.

---

## 0b. Provenance of the Open Food Facts import

The specification's first absolute rule forbids importing unreviewed food or
product records. **The catalogue already breaches it.** `food_items` was 139
rows earlier in this project and is now 578,773.

| Question | Answer |
|---|---|
| When | `app/scripts/ingest_openfoodfacts.py` has existed since `82f0260` (2026-08-15). The rows are not attributable to a specific run — nothing records one. |
| Review gate | **None.** The script has `--dump`, `--stream-url`, `--min-completeness`, `--limit`. It has **no `--apply`, no dry-run default, no `--expect-db`**, and writes with `ON CONFLICT DO UPDATE` — an upsert that can silently overwrite existing rows. |
| Manifest / checksum | **Not recoverable.** No manifest, no checksum, no state file, no import log exists. |
| Moderation | All 578,773 rows are `moderation_status = 'approved'`. Nothing was ever queued for review. |
| Reversible? | **Yes, cleanly.** `source = 'openfoodfacts'` and `source_licence = 'odbl'` agree on every row — the count of rows where one holds and the other does not is **0**. All 565,814 are isolable by a single predicate. |
| User impact of removal | **Zero.** No Open Food Facts row has ever been logged by a user (0 of 3 `meal_logs`). |

The import predates the specification, so this is not a violation *of an
instruction that existed*. It is a pre-existing condition that the
specification would forbid, and it is fully reversible.

---

## 0c. ODbL is a business risk, not an export-feature constraint

**Restating R12 as a top-line risk.**

565,814 rows (97.8% of the catalogue) are Open Food Facts under the **Open
Database License**. ODbL is share-alike **for databases**. The question is
therefore not "may a user export their own data" — it is:

> **Does shipping Trace's food catalogue constitute distributing a derived
> database under ODbL, and if so, what does share-alike require of us?**

If the catalogue is a Derivative or Collective Database and Trace conveys it —
in an app bundle, an offline cache, or an API — ODbL's share-alike terms may
require publishing the derived database under the same licence. That would bear
directly on whether curated Indian rows developed as a differentiator could be
held proprietary while sharing storage and search with ODbL rows.

The ingestion script's own docstring already flags it:

> *"if you redistribute a modified database, share it back under the same
> licence... check with a lawyer before you build a proprietary derived
> database you resell."*

**This needs actual legal advice.** It cannot be settled by reading the licence
text in a repository, and it should be settled **before** a taxonomy is
designed over these rows, because the answer may be that they should not be in
the product at all.

---

## 1. Specification files — a path discrepancy and five missing documents

The task references two specs at `docs/`. At the time of discovery **both
existed at the repository root instead**, so the `@docs/` references would not
have resolved. Both were read in full from the root; the stop condition
("cannot be found") was not met.

**Since resolved:** both files have been moved into `docs/`, so the paths in
the specification now resolve as written.

| Referenced as | Was at | Now at |
|---|---|---|
| `docs/trace_universal_food_app_complete_master_prompt.md` | repo root | `docs/` ✅ |
| `docs/trace_claude_code_step_by_step_implementation_prompt.md` | repo root | `docs/` ✅ |

**Five further documents that the implementation spec instructs be read first
do not exist anywhere in the repository:**

```
trace_global_food_catalogue_research_prompt.md
trace_global_food_catalogue_universal_addendum.md
trace_ready_to_eat_indian_global_addendum.md
trace_universal_versatility_addendum.md
trace_universal_next_features_addendum.md
```

Per the spec's own rule — *"Do not recreate or guess the missing
specification"* — these have **not** been reconstructed. Whether their content
is already folded into the master prompt is an open question for the approver.

### Conflict between the task prompt and the specification

The task prompt places three files in Phase 0. The authoritative spec places
only one there, and assigns the other two to **Phase 1 (database audit)**:

| File | Task prompt | Spec |
|---|---|---|
| `docs/trace-implementation-baseline.md` | Phase 0 | Phase 0 |
| `artifacts/trace-baseline-counts.json` | Phase 0 | **Phase 1** |
| `artifacts/trace-data-quality-findings.jsonl` | Phase 0 | **Phase 1** |

**Resolved in favour of the task prompt** — all three are produced now, since
every measurement they need is read-only and the spec permits read-only schema
inspection in Phase 0. Flagged because it means part of Phase 1 is already
done, and Phase 1 should not re-derive it. `docs/trace-data-audit.md` is
**not** created; it remains Phase 1 work.

---

## 2. Architecture

```
apps/mobile/     Expo Router + TypeScript + Reanimated 4   (npm, package-lock.json)
  app/           file-based routes; (auth)/ (tabs)/ scan.tsx workout/
  src/lib/       api.ts, health.ts, barcode.ts, attribution.ts, serving-basis.ts
  src/components/instrument.tsx = the design primitives
services/api/    FastAPI + SQLModel + Alembic + asyncpg     (pip, requirements.txt)
  app/routers/   16 thin HTTP modules
  app/services/  41 pure-function modules, no I/O
  app/scripts/   ingestion, seeding, schema tooling
  alembic/       migrations
  tests/         46 test modules
eval/            nutrition evaluation set
prototype/       workout-trainer HTML prototype (not shipped)
```

- **Backend entry point:** `services/api/app/main.py` (`uvicorn app.main:app`)
- **Frontend entry point:** `apps/mobile/app/` (Expo Router, file-based)
- **ORM / migrations:** SQLModel over SQLAlchemy; Alembic
- **Worker system:** none — no Celery, RQ, or scheduler
- **CI configuration:** none found

### Commands

| Purpose | Command |
|---|---|
| Backend tests | `cd services/api && python -m pytest tests/ -q` |
| Backend server | `cd services/api && uvicorn app.main:app --reload` |
| Mobile typecheck | `cd apps/mobile && npx tsc --noEmit` |
| Mobile lint | `cd apps/mobile && npx eslint . --ext .ts,.tsx` |
| Mobile tests | `cd apps/mobile && npx jest` |
| Mobile start | `cd apps/mobile && npx expo start --clear` |

No Python linter or formatter is configured (no ruff, black, flake8, or mypy
config found). **This is a gap** if the spec's determinism requirements are to
be machine-enforced.

---

## 3. Current food data model

**One flat table**, `food_items` (578,773 rows), carrying identity, nutrition,
provenance, and search cache together.

```
identity     id · source · source_id · name · brand · barcode · gtin14
             name_normalized · names_i18n (JSONB)
nutrition    calories · protein_g · carbs_g · fat_g · fiber_g · sugar_g
             sodium_mg · saturated_fat_g · micronutrients (JSONB)
             -- ALL per 100 g, or per 100 ml where is_liquid
portions     is_liquid · serving_sizes (JSONB list)
taxonomy     cuisine (single text) · category (single text) · countries (JSONB)
provenance   source_licence · source_url · verification_tier (1-7, lower better)
             last_verified_at · data_quality (float) · is_verified
moderation   moderation_status · created_by_user_id
search       search_text (GIN trigram) · log_count
```

`food_aliases` (1,353 rows) is a proper table with `alias_type`, `lang`,
`source`, `confidence`, and a `(food_item_id, normalized, lang)` unique
constraint. `food_items.search_text` is a read cache rebuilt from it.

Supporting tables: `meal_logs`, `recipes`, `recipe_ingredients`,
`recipe_saves`, `recognitions`, `recognition_feedback`.

### What the schema can and cannot represent

| Spec requirement | Status |
|---|---|
| Ingredients, prepared dishes | ✅ as undifferentiated `food_items` rows |
| Packaged products, brands | ⚠️ `brand` is a text column — no `brands` entity |
| Aliases | ✅ `food_aliases`, with type and source |
| Translations / original scripts | ⚠️ `names_i18n` JSONB + `food_aliases.lang`, but **`lang` is `''` on all 1,353 rows** |
| Barcodes | ⚠️ one `barcode` + one `gtin14` per row — no multipack or market variants |
| Nutrition **observations** | ❌ nutrition is inline and single-valued; no history, no per-nutrient provenance |
| Serving bases (raw/cooked/drained/as-prepared) | ❌ no basis column; everything is "per 100 g" |
| Allergens | ❌ no table, no column |
| Dietary attributes | ❌ no table, no column |
| Cuisine **hierarchy** | ❌ single flat text field |
| Regional variants / food families | ❌ no relation table |
| Product markets, formulations | ❌ absent |
| Price, availability, seasonality | ❌ absent |
| Review state | ⚠️ `moderation_status` only (`approved`/`pending`/`rejected`) |
| Restaurant menu items | ❌ absent |
| Historical/append-only data | ❌ every write is destructive |

**The single largest structural gap is nutrition provenance.** The spec
requires every nutrient value to carry source, record ID, retrieval date,
dataset version, measurement type, basis, unit, confidence, and verification
state. Today provenance is **per row**, not per value, and a re-import
overwrites history.

---

## 4. Current behaviour

### Search
`GET /api/foods/search`. Staged pg_trgm: exact-prefix `ILIKE`, then substring,
then `word_similarity` with a per-transaction threshold. Ranked by
`services/search_rank.py`. Measured at ~257 ms on 578,773 rows. Non-Latin
scripts return **zero results** — no row holds a native-script name.

### Barcode
`GET /api/foods/barcode/{barcode}`, with an optional `symbology` parameter that
disambiguates UPC-E from EAN-8. Normalisation to GTIN-14 in `services/gtin.py`.
`barcode` is preserved exactly as the source sent it; `gtin14` is an additional
lookup key, never a replacement.

### Logging
`POST /api/meals/log`, `GET /api/meals/daily`, `DELETE /api/meals/{id}`.

### Recipes
Full CRUD plus `discover`, `publish-check`, `visibility`, `save`, `fork`,
`log`. Licence-aware publishing already exists.

### AI features
- **Photo:** `POST /api/recognize` → `services/vision.py`, with
  `services/image_quality.py` and `services/uncertainty.py`. Returns low/point/
  high estimates.
- **Label OCR:** `POST /api/recognize/read-label` → `services/label_ocr.py`.
- **Corrections:** `POST /api/recognize/{id}/correct` — the correction dataset.
- **Voice:** `services/workout_voice.py` — **workout only**, no food voice logging.
- **Receipts:** ❌ **not implemented.**
- **Text parse:** `POST /api/foods/parse`.

### Preparations
`GET /api/preparations`, `POST /api/preparations/convert` —
`services/preparation.py` converts raw↔cooked using a `preparation_key` read
from `names_i18n`. **This is the only serving-basis machinery that exists,
and it is keyed out of a JSONB blob.**

### 4b. AI, photo, barcode, receipt, and voice — what actually exists

The prompt asked for this explicitly and the first draft omitted it.

| Feature | Endpoint | Status |
|---|---|---|
| **Photo recognition** | `POST /api/foods/recognize` | **Implemented.** Multipart upload, 12 MB cap. |
| **Label OCR** | `POST /api/foods/recognize/read-label` | **Implemented.** `services/label_ocr.py` |
| **Correction capture** | `POST /api/foods/recognize/{id}/correct` | **Implemented.** Writes `RecognitionFeedback`. |
| **Barcode lookup** | `GET /api/foods/barcode/{barcode}` | **Implemented**, with a `symbology` parameter disambiguating UPC-E from EAN-8. |
| **Text parse** | `POST /api/foods/parse` | **Implemented.** |
| **Receipt scanning** | — | **Not implemented.** No route, no service, no model. |
| **Voice food logging** | — | **Not implemented.** `services/workout_voice.py` is workout-only. |

**How photo recognition works.** `services/vision.py` calls Gemini in two
stages: `VISION_MODEL_FAST` (`gemini-3.5-flash-lite`), escalating to
`VISION_MODEL_ACCURATE` (`gemini-3.5-flash`) when confidence falls below a
threshold. About 25% escalate; blended cost lands near $0.005/scan.
`services/image_quality.py` gates unusable images and
`services/uncertainty.py` produces the low/point/high band the UI renders as
`±`, per product invariant 2.

**Accuracy has never been measured.** An eval harness exists —
`app/scripts/eval_vision.py`, `app/scripts/eval_barcode.py`, and `eval/` with
25 photos, `manifest.csv` and `score.py`. **The `truth_kcal` column is empty
for every row**, and no scoring output exists anywhere in the repository. The
harness was built; ground truth was never filled in; it has never been run.

That matters more than any catalogue count in this document. Photo recognition
is the headline feature, its output is a number users act on, and there is no
measurement of how wrong it is.


### Privacy and deletion
**None found.** No account deletion, data export, consent, or retention
endpoint exists. `grep` for `delete_account|export|gdpr|erasure|purge` across
all routers returns nothing. Against spec Phase 15 this is a **complete gap**.

### Accessibility
Mobile components use `accessibilityLabel` / `accessibilityRole`;
`src/lib/motion-preference.ts` handles reduced motion. No audit against
WCAG 2.2 mobile guidance has been done.

---

## 5. Measured catalogue baseline

```
food_items       578,773        food_aliases     1,353
meal_logs              3        recipes              1
recognitions           3        users               24
```

| By source | rows | | By licence | rows |
|---|---|---|---|---|
| openfoodfacts | 565,814 | | odbl | 565,814 |
| usda_fdc | 12,612 | | public-domain | 12,612 |
| curated | 347 | | user | 347 |

| Verification tier | rows |
|---|---|
| 2 (USDA) | 12,612 |
| 5 (curated) | 347 |
| 6 (Open Food Facts) | 565,814 |

| Field coverage | rows | % |
|---|---|---|
| barcode | 565,839 | 97.8% |
| gtin14 | 504,850 | 87.2% |
| brand | 448,697 | 77.5% |
| source_url | 578,426 | 99.9% |
| serving_sizes | 566,161 | 97.8% |
| **cuisine** | **7,738** | **1.3%** |
| **category** | **7,738** | **1.3%** |
| **names_i18n** | **347** | **0.06%** |
| **last_verified_at** | **0** | **0%** |

**Cuisine coverage is the headline number: 98.7% of the catalogue has no
cuisine or category at all**, and of the 7,738 that do, 7,087 are the
catch-all `global`. Actual Indian regional coverage is ~160 rows across all
`indian_*` tags combined.

Aliases: 866 canonical, 139 misspelling, 136 brand_variant, 124 regional,
88 colloquial. **`lang` is `''` on all 1,353 rows** — the column exists and is
uniformly empty, so multilingual search cannot work today. Zero orphans.

---

## 6. Data-quality findings

Full records in `artifacts/trace-data-quality-findings.jsonl`.

| Finding | Count | Classification |
|---|---|---|
| Duplicate `name_normalized` groups | 53,522 | requires data review |
| Implausible energy (>900 kcal/100 g) | 11,355 | requires data review |
| Calories > 0 with all macros 0 | 4,086 | requires data review |
| Rows with no serving sizes | 12,612 | requires migration |
| Duplicate `gtin14` | 12 | safe to fix later |
| Rows with no `source_url` | 347 | informational |
| Zero-calorie rows | 14,606 | informational |
| Duplicate `barcode` | 0 | — |
| Negative macros | 0 | — |
| `source_licence = 'unknown'` | 0 | — |
| Orphaned aliases | 0 | — |

**53,522 duplicate normalized-name groups is the most consequential finding.**
It is not necessarily 53,522 defects — Open Food Facts legitimately holds the
same product name under different brands and markets — but the schema cannot
currently express that distinction, so duplicate detection and market variance
are the same unsolved problem.

**11,355 rows above 900 kcal/100 g** exceed the energy density of pure fat
(~900). Some are legitimately near it (oils); values materially above it are
unit errors. Not repaired — Phase 1 work.

---

## 7. Test baseline

```
cd services/api && python -m pytest tests/ -q
  →  1 failed, 1826 passed, 1 skipped in 1255.56s (20m55s)
```

**One failure, and it is a pre-existing regression from this session's earlier
workout-side work, not from Phase 0:**

```
FAILED tests/test_backfill_gtin_name.py::TestSafetyGuards::
       test_the_revision_guard_refuses_an_unknown_schema
```

The backfill script's revision guard was rewritten from "is the database at a
revision I recognise?" (a **database-state** check) to "does any migration file
touch my columns?" (a **code** check). A database stamped at an old revision
now passes the guard, and the script backfilled 15 rows in the test's scratch
database when it should have refused.

**This is directly relevant to this project.** The spec's import-safety rules
require an importer to *"verify host, port, current database, and migration
revision"* before writing. The revision half of that verification is currently
broken in the one script that implements it. It must be fixed before any
importer is built on the same pattern.

Mobile tests and typecheck were **not** run in Phase 0.

---

## 8. Risk register

| # | Risk | Severity | Note |
|---|---|---|---|
| R1 | Nutrition has no observation model; re-import destroys history | **High** | Spec requires append-only provenance. Needs a migration touching the largest table. |
| R2 | No serving-basis column; raw/cooked lives in a JSONB key | **High** | `preparation_key` inside `names_i18n` is load-bearing and unindexable. |
| R3 | No allergen model | **High** | Safety-critical, and the spec forbids inferring allergens from names. |
| R4 | 53,522 duplicate-name groups with no market/formulation dimension | **High** | De-duplication and market variance are the same problem. |
| R5 | Revision guard regression (§7) | **High** | Import safety depends on it. |
| R6 | Cuisine is a flat field, 1.3% populated | Medium | Spec requires a hierarchy with multiple associations. |
| R7 | `food_aliases.lang` empty on every row | Medium | Multilingual search is structurally present but unusable. |
| R8 | No privacy, export, or deletion controls | Medium | Whole spec phase unimplemented. |
| R9 | `food_items` is 641 MB; migrations need care | Medium | Constant-literal defaults only; no table rewrites. |
| R10 | No Python lint/format/typecheck configured | Low | Determinism cannot be machine-checked. |
| R11 | No CI | Low | The 21-minute suite is run manually. |
| R12 | **ODbL derived-database obligations** | **Legal — top line** | See §0c. Needs legal advice, not a code decision. |
| R13 | **Vision accuracy never measured. Eval set has 0/25 real photos and 0/25 truth values** | **GATING** | See §0a. Every other phase is downstream of this. |
| R14 | OFF import had no review gate, manifest, or checksum | **High** | See §0b. Reversible, but nothing records what was loaded. |

---

## 9. Unresolved questions

1. Are the five missing addenda in scope, and should work wait for them?
2. Is the 53,522-duplicate figure a defect count or expected market variance?
   Deciding this determines whether Phase 1 is a repair or a schema change.
3. Does "universal" require re-classifying the 565,814 Open Food Facts rows,
   or does the new taxonomy apply only to curated additions? **This is the
   single largest scoping question** — it is the difference between curating
   hundreds of rows and half a million.
4. ODbL share-alike: does any planned export or API redistribute OFF-derived
   data, and has that been reviewed?
5. Should `names_i18n` be migrated into `food_aliases`, or continue alongside
   it? It currently carries `basis`, `makes`, `data_notes`, `validation` and
   `preparation_key`, and `routers/preparations.py` reads the last at runtime.
6. Is voice **food** logging in scope for the first slice? Only workout voice
   exists.
7. Receipt scanning is entirely absent — greenfield, or deferred?

---

## 10. Recommended Phase 1 plan

Phase 1 in the spec is the read-only data audit. Given that §5 and §6 already
deliver most of its measurements, the remaining Phase 1 work is:

1. **`docs/trace-data-audit.md`** — the narrative audit, classifying every
   finding into the spec's six categories.
2. **Characterise the 53,522 duplicates.** Sample and classify: true
   duplicates, brand variants, market variants, formulation revisions. This
   answers question 2 and scopes the identity model.
3. **Characterise the 11,355 implausible-energy rows** by source, to establish
   whether it is one importer's unit bug or diffuse.
4. **Raw/cooked and generic/branded collision detection**, which the spec
   requires and which was not measured in Phase 0.
5. **Fix the revision-guard regression (R5)** before any importer work.
6. **Measure search performance** against a baseline so the taxonomy work has a
   regression target.

**Recommended before Phase 2:** a written answer to question 3. The taxonomy
design is not decidable without it.

---

## 12. Result segmentation — designed, not built

The Open Food Facts rows do not need deleting, demoting by query classifier, or
re-classifying. They need a heading.

```
Foods                     curated + USDA, ranked as now
Packaged products         OFF, capped, below
```

**Why not classify the query.** "Admit OFF only when the query looks like a
brand" needs a classifier, and a classifier that misfires puts Thorntons back
on top of thoran. Segmenting the *results* needs no model and cannot misfire:
the partition is `source` , which is already correct on every row.

- **"thoran"** — the curated row sits alone under **Foods**. Thorntons appears
  under a heading that makes it obviously a different kind of answer.
- **"Nutella"** — nothing curated matches, **Foods** is empty, and the packaged
  section carries the result. The behaviour that demotion would have broken
  keeps working.
- A phone showing six rows shows **six foods**.

### The cap

**Three packaged results when Foods is non-empty; up to ten when Foods is
empty.**

Three, because a phone viewport shows about six rows and Foods must own the
majority of them. Three is also enough to signal that branded versions exist
and are one tap away, without burying the curated answer that the ranker
already puts first. Ten when Foods is empty, because at that point the packaged
section *is* the result list and capping it would just be a worse search.

### What it actually costs — this is not purely presentational

`SEARCH_SQL` over-fetches into one pool, ranks, then truncates. **A single
`LIMIT` can return forty OFF rows and zero curated ones**, which is close to
what happens for `thoran` today. Segmentation therefore needs the *retrieval*
to be partition-aware, not just the response:

- each section bounded separately. **This is the same starvation bug the
  file already documents one level down**: `SEARCH_SQL` runs a direct arm and
  an alias arm under a shared `LIMIT`, and the comment there explains that
  one arm will otherwise eat the other's slots. Segmenting by source repeats
  the shape exactly one level up — curated rows starved by OFF rows drawn
  from the same pool. The fix is the same in both places, and it is a
  partition, not a rank adjustment;
- the response shape gains sections, so the mobile client changes;
- `services/search_rank.py` is untouched — each section is ranked by the
  existing total order.

**No schema change, no deletion, no classifier, no re-classification of
565,814 rows.**

### What it does not fix

**ODbL.** The rows are still stored and still shipped. Segmentation is a
ranking and presentation change; the derived-database question in §0c is
untouched by it and still needs legal advice.

---

## 11. Confirmations

- ✅ No production data modified — every statement was `SELECT`, asserted in
  the inspection script.
- ✅ No food records imported.
- ✅ No migrations run.
- ✅ No git changes staged or committed.
- ✅ No credentials, tokens, or connection strings printed. Only the database
  **name** (`trace`) was echoed.
- ✅ No paid or rate-limited external APIs called.
- ✅ No application code modified.
