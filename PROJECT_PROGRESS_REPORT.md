# Trace — Project Progress Report

**Generated:** 22 August 2026
**Branch:** `master` (1 commit: `82f0260` initial import — all work below is uncommitted)
**Scope:** Full-project status. Every figure was measured against the live codebase and database at generation time, not estimated or recalled.

---

## 1. What has been completed

### Working end to end

| Area | Status | Notes |
|---|---|---|
| Email auth (register / login / refresh) | Working | Email normalised on client and server |
| Phone OTP auth | Working in dev | No SMS provider wired; codes exposed only under `DEBUG` |
| Social sign-in (Google / Apple) | Code complete, **not usable** | Blocked on OAuth credentials |
| Onboarding questionnaire → week-one targets | Working | Preview computes without saving |
| Food search (text) | **Working but unusably slow** | See §12, bug 1 |
| Barcode scan → food resolution | Working | Routes to food-search; OFF + USDA fallback |
| AI photo scan | Working | 58.6 s → 7.8 s this cycle |
| Meal logging + daily summary | Working | Nutrition snapshotted at log time |
| Recipes (build / private / publish / fork / log) | Working | Built this cycle |
| Workout logging, sets, e1RM | Working | RIR-adjusted |
| Exercise catalogue + illustrations | Working | 874 exercises |
| Activity / sports logging | Working | 104 sports |
| Streak + consistency + phase progress | Working | Built this cycle |
| Weekly budget, protein coach, fuel link, nutrient panel | Working | Built this cycle |
| Adjudication engine (gaining muscle vs fat) | Working | Returns `INSUFFICIENT_DATA` rather than guessing |
| HealthKit / Health Connect sync | Working | Requires dev build, not Expo Go |
| Cycling metrics + coverage map | **Partially built, inert** | See §12, bug 4 |
| kg/lb + bar weight display | **Service only, no UI** | See §14 |

### Measured improvements this cycle

| Metric | Before | After |
|---|---:|---:|
| AI scan latency | 58.6 s | **7.8 s** |
| Food catalogue | 273,316 | **578,773** |
| Exercises | 736 | **874** |
| Backend tests | 339 | **687** |
| Exercise illustration coverage | 36% | **~86%** |
| Sports with icons | partial | **104 / 104** |

---

## 2. Files created or changed

**38 modified, 78 new.** Nothing deleted.

### Modified — backend (19)

```
services/api/app/config.py                      services/api/app/routers/health.py
services/api/app/db.py                          services/api/app/routers/meals.py
services/api/app/main.py                        services/api/app/routers/recognition.py
services/api/app/models.py                      services/api/app/routers/weight.py
services/api/app/routers/auth.py                services/api/app/routers/workouts.py
services/api/app/routers/foods.py               services/api/app/schemas.py
services/api/app/scripts/ingest_openfoodfacts.py
services/api/app/scripts/seed_dishes.py         services/api/app/services/chat.py
services/api/app/services/food_sources.py       services/api/app/services/tdee.py
services/api/app/services/vision.py             services/api/tests/conftest.py
services/api/tests/test_integration_core.py
```

### Modified — mobile (18)

```
apps/mobile/app.json                     apps/mobile/app/(tabs)/progress.tsx
apps/mobile/app/(auth)/login.tsx         apps/mobile/app/(tabs)/train.tsx
apps/mobile/app/(auth)/signup.tsx        apps/mobile/app/_layout.tsx
apps/mobile/app/(tabs)/_layout.tsx       apps/mobile/app/scan.tsx
apps/mobile/app/(tabs)/index.tsx         apps/mobile/src/components/instrument.tsx
apps/mobile/app/(tabs)/log.tsx           apps/mobile/src/lib/api.ts
apps/mobile/package.json                 apps/mobile/src/state/useAuth.ts
apps/mobile/package-lock.json            apps/mobile/src/state/useTheme.ts
.claude/settings.json                    apps/mobile/src/theme.ts
```

### New — backend services (21)

```
fuel_link.py        micronutrients.py   nutrient_panel.py   onboarding.py
paid_sources.py     phone_auth.py       protein_coach.py    recipes.py
routes.py           social_auth.py      sports.py           strava.py
streak.py           strength.py         uncertainty.py      units.py
volume.py           week_budget.py      workout_voice.py    label_ocr.py
```

### New — backend routers (4)

```
insights.py    onboarding.py    recipes.py    rides.py (NOT REGISTERED)
```

### New — backend data & scripts (8)

```
scripts/data/indian_regional.py     scripts/data/modern_exercises.py
scripts/data/world_regional.py      scripts/data/store_brands.py
scripts/data/usda/                  scripts/ingest_usda.py
scripts/ingest_store_brands.py      scripts/seed_modern_exercises.py
scripts/probe_paid.py
```

### New — backend tests (18)

```
test_label_ocr.py     test_live_workout.py    test_maintenance.py
test_nutrient_panel.py test_nutrition_v2.py   test_onboarding.py
test_paid_sources.py  test_phone_auth.py      test_recipes.py
test_recipes_api.py   test_routes.py          test_social_auth.py
test_sports.py        test_strava.py          test_streak.py
test_strength.py      test_units.py           test_volume.py
test_workout_voice.py
```

### New — mobile screens (13)

```
app/(auth)/phone.tsx         app/nutrition/fuel.tsx      app/recipes/index.tsx
app/(onboarding)/index.tsx   app/nutrition/nutrients.tsx app/recipes/new.tsx
app/(tabs)/profile.tsx       app/nutrition/protein.tsx   app/recipes/[id].tsx
app/exercise/[id].tsx        app/nutrition/week.tsx      app/workout/[session].tsx
app/food-search.tsx          app/workout/history.tsx     app/workout/summary.tsx
                                                          app/workout/voice.tsx
```

### New — mobile components / state (11)

```
components/activities.tsx    components/certainty.tsx    components/dial.tsx
components/exercise-art.tsx  components/icons.tsx        components/log-sheet.tsx
components/maintenance-card.tsx components/muscle-map.tsx components/streak-panel.tsx
lib/social-auth.ts           state/useHealth.ts          state/useOnboarding.ts
```

### New — docs

```
docs/paid-nutrition-apis.md    docs/social-sign-in.md    .vscode/NUTRITION_UPGRADE_PLAN.md
```

---

## 3. Current architecture

### Frontend — `apps/mobile`

- **Framework:** Expo Router (file-based routing), TypeScript strict mode, React Native
- **Animation:** Reanimated 4, all animation on the UI thread via shared values — never `setState`
- **State:** Zustand stores (`useAuth`, `useTheme`, `useHealth`, `useOnboarding`, `useScan`)
- **Design system:** "Instrument panel" — near-black `#07090B`, hairlines not shadows, tabular numerals on every changing number, one accent, uppercase tracked micro-labels. All tokens in `src/theme.ts`; all primitives in `src/components/instrument.tsx` (30 exported components)
- **API client:** `src/lib/api.ts` — single `request()` with auth, token refresh, 45 s timeout
- **Lists:** FlashList with rows memoised on primitives
- **Loading:** skeleton first, fetch after `InteractionManager.runAfterInteractions`
- **Graphics:** `react-native-svg` (icons, exercise art, charts) — no native map dependency

### Backend — `services/api`

- **Framework:** FastAPI, async endpoints throughout
- **ORM:** SQLModel over async SQLAlchemy, asyncpg driver
- **Database:** PostgreSQL on Neon, with `pg_trgm` and `unaccent` extensions
- **Layering:** business logic lives in `app/services/` as **pure functions with no I/O**; `app/routers/` is a thin HTTP layer. This is the project's strongest architectural property and every test below depends on it.
- **Auth:** JWT access + refresh tokens, bcrypt passwords
- **Schema management:** `SQLModel.metadata.create_all` — **no migration tool** (see §12, bug 2)

### Registered routers (13)

```
/api/auth      /api/chat      /api/foods      /api/health     /api/insights
/api/meals     /api/onboarding /api/preparations /api/recipes  /api/recognition
/api/weight    /api/workouts  /api/adjudication
```

`/api/rides` exists on disk but is **not registered** — deliberately, as it is incomplete.

---

## 4. Current database schema

**23 tables.**

| Table | Cols | Purpose |
|---|---:|---|
| `users` | 24 | Accounts, profile, goals |
| `refresh_tokens` | 7 | Rotating refresh tokens |
| `phone_challenges` | 9 | OTP challenges |
| `food_items` | 29 | **Canonical food catalogue, nutrition per 100 g** |
| `meal_logs` | 21 | Logged meals — nutrition snapshotted, never recomputed |
| `recipes` | 31 | User recipes, cached composition, visibility |
| `recipe_ingredients` | 17 | One line per ingredient, panel copied at add time |
| `recipe_saves` | 4 | Saved (not forked) recipes |
| `recognitions` | 12 | AI photo scans, keyed by perceptual hash |
| `recognition_feedback` | 7 | **User corrections — the proprietary dataset** |
| `exercises` | 7 | Exercise catalogue |
| `workout_sessions` | 6 | Resistance training sessions |
| `set_logs` | 12 | Individual sets, RIR, computed e1RM |
| `strength_snapshots` | 8 | Weekly strength index |
| `weight_entries` | 5 | Body weight |
| `body_composition` | 13 | Weekly targets and estimates |
| `adjudications` | 17 | Muscle-vs-fat verdicts |
| `activity_days` | 15 | Daily steps / active energy |
| `sleep_nights` | 12 | Sleep from HealthKit / Health Connect |
| `external_workouts` | 13 | Imported and manual activity sessions |
| `ride_tracks` | 15 | **GPS geometry — new, unused (no router registered)** |
| `health_sync_state` | 7 | Per-metric sync cursors |
| `coach_briefings` | 13 | Generated coach output |

### Key schema properties

- Nutrition is stored **per 100 g** on `food_items`; `meal_logs` stores absolute snapshotted values so upstream corrections never rewrite history.
- `recipes` **caches** composition and recomputes on write — the opposite of `meal_logs`, deliberately, because a recipe is a living document.
- `search_text` is a denormalised lowercase blob with a GIN trigram index (currently unused — see §12).
- Nullable-not-zero is used consistently where "unknown" and "zero" differ (sodium, potassium, elevation gain).

---

## 5. Nutrition and food-database features

### Working

- **Multi-source resolution chain:** local DB → Open Food Facts → USDA → paid tier → OCR → manual, with write-back on every remote hit
- **Typo-tolerant search** via pg_trgm word similarity (`panner tika` → `Paneer Tikka`)
- **Barcode lookup** with remote fallback and local caching
- **AI photo recognition** returning low/point/high bands, never a single confident number
- **Nutrition validator** (`nutrition_validator.py`) — 10 checks including Atwater consistency, macro sum, category bands, ingredient contradiction, duplicate-panel fingerprinting. Quarantines defective rows rather than serving them.
- **As-sold → as-prepared conversion** (`preparation.py`) for ready-made mixes — hydration, evaporation, fat uptake, syrup absorption
- **Recipes** — ingredient composition, cooking-yield handling, private/published, forking, save-to-library, log by serving or gram
- **Uncertainty propagation** (`uncertainty.py`) — quadrature combination, not naive sum
- **Weekly calorie budget** (`week_budget.py`) — a budget, not a daily verdict
- **Protein coach** (`protein_coach.py`) — grams per rupee ranking
- **Fuel↔training link** (`fuel_link.py`) — Spearman rank correlation, refuses below 8 pairs
- **26-nutrient panel** (`nutrient_panel.py`) — gates each row on ≥50% calorie coverage, reports `unknown` otherwise
- **Label OCR** (`label_ocr.py`) — exists, not yet wired to a submission flow

### Recipe feature detail

- Logs by **serving** (exact regardless of cooking loss); per-100 g offered only when a measured cooked weight is supplied
- Publish gate: name ≥3 chars, ≥2 ingredients, non-zero calories, macros within 35% of stated calories
- Cautions (never blocking): missing cooked weight, no method, mostly hand-entered, looks-fried-but-carries-no-fat
- Catalogue ingredient panels are read server-side — a client cannot invent macros for a real food

---

## 6. Workout, exercise, machine and activity features

### Exercises — 874 total

| Muscle group | Count |
|---|---:|
| Legs | 246 |
| Shoulders | 137 |
| Back | 125 |
| Chest | 98 |
| Core | 90 |
| Triceps | 82 |
| Biceps | 65 |
| Forearms | 26 |
| Neck | 5 |

| Equipment | Count |
|---|---:|
| Barbell | 187 |
| Dumbbell | 149 |
| Cable | 126 |
| Other | 110 |
| Bodyweight | 100 |
| Machine | 90 |
| Kettlebell | 53 |
| Band | 20 |
| Medicine ball | 17 |
| EZ bar | 11 |
| Exercise ball | 8 |
| Smith machine | 3 |

### Features

- Set logging with weight, reps, RPE and **RIR** (reps in reserve)
- RIR-adjusted e1RM computed on write
- Live workout flow with next-set prescription
- Voice set entry (`workout_voice.py`)
- Weekly volume tracking per muscle group with in-range/under/over status
- Strength index and trend confirmation
- Exercise illustrations — 43 distinct SVG drawings resolved via 111 keyword pattern rules
- Muscle map visualisation
- Session history and summary screens

### Activities — 104 sports

| Group | Count |
|---|---:|
| Endurance | 24 |
| Team | 18 |
| Conditioning | 17 |
| Outdoor | 16 |
| Mobility | 11 |
| Everyday | 9 |
| Racket | 8 |
| Other | 1 |

- MET-based burn estimate returning **low/point/high**, not a single number
- Intensity multiplier (easy 0.78 / moderate 1.0 / hard 1.28)
- 20 sports track distance
- **Exercise calories are never added to the calorie target** — a hard product invariant; the adaptive TDEE already contains them via the weight trend

---

## 7. APIs and datasets currently used

| Source | Type | Status | Rows / use |
|---|---|---|---:|
| **Open Food Facts** | Free, crowd-sourced | Live + bulk ingest | 565,814 |
| **USDA FoodData Central** | Free, government | Ingested | 12,612 |
| **Curated Indian dishes** | Hand-built | Seeded | 347 |
| **IFCT** (Indian Food Composition Tables) | Government | **Enum slot exists, 0 rows** | 0 |
| **Google Gemini** | Paid API | Live | Vision + label OCR |
| **Nutritionix** | Paid API | Integrated, **no key** | Restaurant chains |
| **Apple HealthKit** | Device | Live (dev build only) | Steps, sleep, workouts |
| **Health Connect** | Device | Live (dev build only) | Android equivalent |
| **Strava** | OAuth API | Code complete, **deferred** | Cost postponed to ~Sep 2026 |
| **free-exercise-db** | Open dataset | Seeded | Base exercise catalogue |

### Internal datasets built for this project

| Dataset | Entries |
|---|---:|
| `world_regional.py` | 135 |
| `indian_regional.py` | 73 |
| `modern_exercises.py` | 158 |
| `store_brands.py` | brand seeds |

### Bulk download in progress

Open Food Facts full JSONL dump — **6,931 MB of 11,300 MB** at generation time, `curl` still running with `-C -` resume and 100 retries.

---

## 8. Indian and worldwide food coverage

### Measured catalogue composition — 578,773 foods

| Source | Count | Share |
|---|---:|---:|
| Open Food Facts | 565,814 | 97.8% |
| USDA FoodData Central | 12,612 | 2.2% |
| Curated | 347 | 0.06% |

### By country tag

| Country | Products |
|---|---:|
| United States | 326,891 |
| France | 72,743 |
| Germany | 28,303 |
| United Kingdom | 25,581 |
| Spain | 21,024 |
| Switzerland | 15,755 |
| Belgium | 15,615 |
| Italy | 13,140 |
| World (generic) | 12,123 |
| Netherlands | 10,533 |
| Ireland | 8,795 |
| Canada | 5,481 |
| Australia | 4,923 |
| Japan | 654 |
| **India** | **485** |
| UAE | 453 |
| South Africa | 311 |
| China | 144 |

### Honest assessment

- **Worldwide packaged food: strong for the US and Western Europe.** Kirkland, Costco and US supermarket products resolve (1,332 hits for "kirkland protein bar").
- **India: critically thin — 485 products, 0.08% of the catalogue.** This is the app's primary market and its worst-covered one.
- **Indian dishes: 347 curated entries** cover common regional dishes (dosa 274 search hits, sambar 170, poha 6, rajma chawal 8, litti chokha 1).
- **Local-language search does not work.** Only 347 rows carry any non-English name. Devanagari (`पोहे`), Tamil (`தோசை`, `சாம்பார்`) all return **zero results**.
- **Restaurant / fast-food: not covered.** Nutritionix is integrated but has no key.
- **Middle East, Africa, East Asia: very thin** (China 144, South Africa 311).

---

## 9. International exercises, machines, sports and activities

### Exercise sources

Base catalogue from the open `free-exercise-db`, extended with **158 researched entries** drawn from published training breakdowns of:

- **Jeff Nippard** — tier lists for back, chest, shoulders, quads, biceps, triceps
- **Chris Bumstead** — split, including three chest-supported row variants
- **John Meadows / Mountain Dog** — Meadows Row, Meadows Run, dual rope extensions
- **Sam Sulek** — machine-heavy split (machine low row, lat pullover, lying face pull)
- **Nick Walker / Derek Lunsford** — leg curl variants as separate entries
- **Renaissance Periodization** — programming

**Selection rule applied:** a variation earns a row only when it is a different thing to *log* — different angle, grip, unilateral/bilateral split, or machine — such that its working weight and progression are genuinely separate from the parent movement.

### Machines covered

90 machine-equipment exercises plus 3 Smith machine entries, including: chest-supported row, incline machine chest press, machine low row, machine lat pullover, pendulum squat, hack squat, leg press, standing/seated/lying leg curl, machine biceps curl, donkey calf raise, leg press calf raise.

### Sports and activities — 104

Racket (badminton, pickleball, tennis, table tennis…), Team (18), Endurance (running, cycling ×4 variants, swimming, rowing…), Conditioning (17), Outdoor (16), Mobility (11), and an **Everyday** group (housework, long shifts on your feet) — deliberately included because those are real expenditure people currently log as nothing.

---

## 10. Tests that passed

### Backend — 687 passed, 1 skipped

| Module | Tests | Module | Tests |
|---|---:|---|---:|
| `test_nutrition_v2.py` | 65 | `test_workout_voice.py` | 27 |
| `test_routes.py` | 56 | `test_food_data.py` | 26 |
| `test_recipes.py` | 48 | `test_onboarding.py` | 22 |
| `test_recipes_api.py` | 45 | `test_volume.py` | 20 |
| `test_sports.py` | 38 | `test_strava.py` | 19 |
| `test_units.py` | 35 | `test_maintenance.py` | 17 |
| `test_strength.py` | 35 | `test_label_ocr.py` | 17 |
| `test_streak.py` | 33 | `test_paid_sources.py` | 16 |
| `test_phone_auth.py` | 33 | `test_live_workout.py` | 16 |
| `test_engines.py` | 31 | `test_social_auth.py` | 15 |
| `test_nutrient_panel.py` | 28 | `test_integration_core.py` | 13 |
| `test_coach.py` | 28 | `test_chat.py` | 5 |

Runtime: 134 s. Integration tests run against a dedicated `trace_test` database with a fail-fast guard that refuses to run against any other URL.

### Frontend

- **TypeScript:** `npx tsc --noEmit` — **0 errors**
- **Jest:** 10 passed, 1 suite (`useScan.test.ts`)

---

## 11. Tests that failed

**None. 0 failures across backend, TypeScript and Jest.**

### One skipped test

`tests/test_integration_core.py::test_recognize_requires_configured_key` — skipped because it requires `GEMINI_API_KEY`, which is not set in the test environment. It is marked with an explicit reason rather than silently omitted, so the coverage gap is visible.

### Coverage gaps not represented by failing tests

- **No mobile UI tests.** Jest covers one Zustand store. No screen, component or navigation tests exist.
- **No end-to-end tests** across the mobile→API boundary.
- **`routes.py` thresholds are tuned on synthetic data**, not real GPS rides (see §13).

---

## 12. Known bugs

### 1. Food search runs a sequential scan — 7.5 to 18 seconds per query — **P0**

`EXPLAIN ANALYZE` on "amul paneer" shows `Seq Scan on food_items`, 252,997 rows removed, **8,962 ms**. The GIN trigram index `ix_food_search_trgm` is never used.

**Cause:** `routers/foods.py` compares `word_similarity()` to a constant instead of using the `<%` operator — deliberately, to avoid depending on the `pg_trgm.word_similarity_threshold` server setting. But `<%` is the only *indexable* form, and it sits in an `OR` with the `ILIKE`, dragging the whole query sequential.

**Validated fix:** use `<%` with `SET LOCAL pg_trgm.word_similarity_threshold` per transaction — keeps determinism, restores the index.

| Query | Now | Fixed | Hits before → after |
|---|---:|---:|---|
| amul paneer | 10,027 ms | **358 ms** | 67 → 67 |
| kanda poha | 10,665 ms | **338 ms** | 6 → 6 |
| kirkland protein bar | 18,319 ms | **1,442 ms** | 1,332 → 1,332 |
| panner tika *(typo)* | — | **343 ms** | 9 → 9 |

Not yet applied — awaiting approval.

### 2. No migration tool — schema cannot be altered — **blocking**

`db.py` uses `SQLModel.metadata.create_all`, which creates new tables but never `ALTER`s existing ones. Its own comment flags this. Any column addition to `food_items` (ingredients, allergens, images, cholesterol) is blocked until Alembic is adopted.

### 3. Local-language search returns nothing

Devanagari and Tamil queries return **0 results**. Only 347 rows carry any non-English name, stored in a JSONB blob that cannot be indexed for search.

### 4. `routers/rides.py` is incomplete and unregistered

Written but not added to `main.py`, and its schemas (`RideDetail`, `CoverageResponse`, `RideTrackRequest`, `TrackBounds`, `RideSummaryOut`) do not exist in `schemas.py`. **The application is unaffected** — verified `app.main` imports cleanly and all 687 tests pass. The `ride_tracks` table is created but unused.

### 5. 12,612 foods have no serving sizes

The entire USDA import. Those foods can only be logged by weight.

### 6. 14,606 foods report zero calories

Some legitimate (water, diet drinks — deliberately allowed after a fix this cycle), some genuinely defective. Not currently distinguished.

### 7. 130,076 foods have no brand

Brand-first search ranking degrades for these.

### 8. Social sign-in cannot be used

Google and Apple OAuth code is complete and tested (15 tests), but no client credentials are configured.

### 9. HealthKit does not work in Expo Go

Requires a development build. Expected platform behaviour, not a code defect, but it blocks testing on a plain Expo Go install.

---

## 13. Placeholder, estimated, fake or unverified data

This section is deliberately exhaustive. **Nothing below is presented to users as verified fact without qualification**, but all of it should be understood as estimated.

### Estimated by construction

| Item | Nature | Where |
|---|---|---|
| **22 of 104 sport METs** | Interpolated, not from the Compendium of Physical Activities | `sports.py`, flagged `estimated=True` |
| **Indian protein prices** | Market estimates as of 2026-08 | `protein_coach.py`, `PRICES_AS_OF` |
| **Bar weights (EZ, trap, safety squat)** | Vary 7–35 kg by manufacturer | `units.py`, flagged `uncertain=True` |
| **Smith machine bar weight** | **Deliberately `None`** — counterbalancing varies 6–25 kg and cannot be inferred | `units.py` |
| **`data_quality` default 0.5** | Arbitrary midpoint for unrated sources | `models.py` |
| **Coverage cell size 0.5 km** | Product decision about what "somewhere new" means, not a precision setting | `routes.py` |
| **Elevation thresholds** | `NOISE_THRESHOLD_M = 5.0`, `SMOOTH_WINDOW = 31` — **tuned on synthetic noise, never validated against a real GPS ride** | `routes.py` |
| **AI photo estimates** | Model output, always returned as low/point/high bands | `vision.py` |

### Derived from published sources, not primary measurement

| Item | Basis |
|---|---|
| **158 modern exercises** | Published *written* breakdowns of influencer routines — **not video transcripts**. I cannot watch video. |
| **Exercise tier rankings** | Published tier lists; used only to order search results, never shown as a verdict |
| **`preparation.py` transforms** | Manufacturer "makes N per pack" claims, recipe-site quantities, and published food-science papers (Sakhale et al. 2011 for samosa oil uptake; Kumar & Mishra for gulab jamun syrup) |
| **`micronutrients.py` limits** | US Dietary Guidelines / NASEM / WHO population figures — **not personalised**, and wrong for anyone with hypertension or kidney disease |

### Data quality of the catalogue itself

- **565,814 rows (97.8%) are crowd-sourced Open Food Facts data.** Public nutrition data carries roughly a 30% defect rate; `nutrition_validator.py` exists precisely because of this.
- **Only 12,928 rows (2.2%) are marked verified** — essentially just the USDA import.
- **Only 12,585 rows (2.2%) carry any micronutrient data.**
- **Only 7,738 rows (1.3%) carry a cuisine or category tag.**
- `updated_at` records **our write time, not the upstream source's freshness date**. There is no column for the latter.

### Illustration coverage

**43 distinct SVG drawings** are matched to 874 exercises by **111 keyword pattern rules**. Roughly 86% of exercises resolve to a relevant drawing; the remainder fall back to a generic silhouette. Many exercises legitimately share one drawing (all barbell curl variants use the same art) — this is by design, but it means the illustration is **indicative, not exercise-specific**.

### Not fake

No fabricated food rows, no invented nutrition panels, and no hardcoded fake entries were added. The catalogue is entirely from Open Food Facts, USDA, or hand-curated entries traceable to a source.

---

## 14. Remaining tasks

### Blocked on your decision

| Task | Blocker |
|---|---|
| Apply the search index fix | Awaiting approval |
| Adopt Alembic | Architectural change — needs your sign-off |
| IFCT ingest | Licence / redistribution terms unconfirmed |
| Nutritionix restaurant data | Requires paid key (~$50/mo) |
| Product images | Storage and bandwidth cost decision |

### Blocked on credentials

| Task | Needs |
|---|---|
| Google sign-in | OAuth client IDs (iOS, Android, Web) |
| Apple sign-in | Apple Developer service ID + key |
| Strava import | Paid API — deferred to ~Sep 2026 |

### Partially built

| Task | State |
|---|---|
| **Cycling metrics + coverage map** | `routes.py` + 56 tests and `ride_tracks` table complete. `rides.py` written but unregistered; schemas missing; **no mobile screen**. |
| **kg/lb + bar weight in UI** | `units.py` + 35 tests complete. **No screen uses it** — sets still render raw kg with no lb and no plates-only mode. |

### Not started

- **AI scan animation** — requested; a proper scanning graphic on the UI thread
- **Nutrition upgrade Phases 01–05** — alias table, dish/variant model, submissions + moderation, yield factors, ranking, micronutrient backfill
- **Food dump ingest** — download at 6,931 / 11,300 MB; re-ingest with Indian brand filtering still to do
- **Mobile test coverage** — 1 store tested, 0 screens
- **Design system migration** — `progress.tsx`, `scan-review.tsx`, `VerdictCard.tsx`, `ui.tsx` still on legacy vocabulary

### Security housekeeping

- **Rotate the Gemini API key.** It was pasted into a chat transcript. It currently lives only in the gitignored `services/api/.env`, but it should be rotated once testing is complete.
- `DEBUG=true` is set locally and must not reach production — OTP codes are exposed under it (gated three ways, but still).
- `JWT_SECRET` must be set explicitly in production or every container restart invalidates all tokens.

---

## 15. Recommended next step

**Apply the food-search index fix first.** It is the highest value-to-risk action available:

- The fix is **already validated** against the live catalogue — 28× faster, byte-identical hit counts, typo tolerance intact
- It is a change to **one SQL statement plus a `SET LOCAL`**, not an architectural change
- It removes a **7.5–18 second wait from the single most-used screen in the app**
- Everything else in the nutrition plan makes the database *bigger*, which makes this bug *worse*

Ship it with a regression test that pins both the hit counts and the query plan, so a future refactor cannot silently reintroduce the sequential scan.

**Then, in order:**

1. **Alembic** — nothing else in the nutrition plan can ship without it
2. **Local-language search** (alias table + transliteration) — turns *poha* / *avalakki* / *पोहे* into synonyms and unlocks the Indian market the app is built for
3. **Finish cycling and units wiring** — both are more than half done and currently earning nothing

The scan animation is worth building, but it is polish on a feature that already performs well (7.8 s). The search bug is the thing making the app feel slow.

---

*Report generated 22 August 2026. All figures measured against the live codebase and Neon database at generation time. No project files were modified in producing this report.*
