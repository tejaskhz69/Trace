# Claude Code Implementation Prompt
## Trace Universal Food App — step-by-step implementation plan

You are Claude Code working inside the Trace repository.

Trace is an AI-powered fitness, calorie-tracking, food logging, nutrition, recipe, packaged-food, and meal-planning application. It must become useful across countries, cultures, languages, dietary patterns, budgets, cooking abilities, household situations, and levels of connectivity.

This prompt is an implementation contract. Follow the phases in order. Do not skip discovery, safety, testing, licensing, or migration gates merely because a later feature appears straightforward.

## Documents to read first

Before coding, find and read these documents if they are present in the repository or working directory:

- `trace_universal_food_app_complete_master_prompt.md`;
- `trace_global_food_catalogue_research_prompt.md`;
- `trace_global_food_catalogue_universal_addendum.md`;
- `trace_ready_to_eat_indian_global_addendum.md`;
- `trace_universal_versatility_addendum.md`;
- `trace_universal_next_features_addendum.md`;
- project README and contributor instructions;
- repository-specific AGENTS.md, CLAUDE.md, or instruction files.

Treat the complete master prompt as the product scope. If the repository contains a newer instruction file, follow the repository instruction hierarchy and report any conflict before implementing.

## Absolute rules

Do not:

- write to the production database;
- import unreviewed food or product records;
- alter user food logs;
- delete or truncate existing food, alias, nutrition, barcode, or user tables;
- silently overwrite existing records;
- silently replace nutrition values;
- silently merge distinct foods or regional dishes;
- invent nutrition, allergens, prices, brands, barcodes, licences, or cultural classifications;
- copy restricted recipe text or images;
- expose secrets, tokens, API keys, passwords, database URLs, private user data, or environment values;
- call paid or rate-limited APIs from tests;
- modify unrelated workout, authentication, billing, or production files unless a compatibility issue is proven;
- stage or commit changes automatically;
- use destructive Git commands;
- run a production import before explicit approval.

Use read-only inspection, local fixtures, mocks, scratch databases, dry-run commands, and deterministic generated files.

When any instruction is ambiguous, stop and report the ambiguity instead of guessing.

---

# Operating protocol

## Change-report format

At the end of every phase, report:

- phase name;
- files read;
- files created;
- files modified;
- migrations created;
- commands run;
- tests run and results;
- database touched, if any;
- risks and unresolved questions;
- exact next step;
- whether you are stopping for approval.

## Database protection

Before opening any database connection, determine whether the command is read-only, scratch-only, or a write operation.

For any importer or migration command:

- default to dry-run;
- require `--apply` for a write;
- require `--expect-db trace` for a production write;
- verify host, port, database name, and migration revision;
- reject non-loopback hosts unless explicitly allowed;
- never print the complete database URL;
- never print passwords or tokens;
- create a backup and rollback plan;
- record the exact input manifest and checksum.

Production writes are forbidden until the final approval gate.

## Determinism

All research, normalization, candidate generation, collision detection, and import-plan files must be deterministic:

- stable sorting;
- stable identifiers;
- stable serialization;
- normalized Unicode;
- no timestamps in content unless explicitly passed as an input;
- no random identifiers without a deterministic seed;
- no network calls during tests;
- repeated runs produce identical output for identical inputs.

---

# Phase 0 — repository and environment discovery

Do not edit application code yet.

Inspect:

- repository tree;
- package managers and lockfiles;
- language and framework;
- backend entry point;
- frontend entry point;
- API routes;
- database ORM and migrations;
- task/worker system;
- test commands;
- lint/format/typecheck commands;
- CI configuration;
- environment-example files;
- existing seed/import scripts;
- existing food/nutrition/product modules;
- authentication and user-preference modules;
- AI/photo/barcode/receipt/voice features;
- documentation.

Run only safe local commands such as:

- `git status --short`;
- repository file listing;
- package metadata inspection;
- test discovery;
- typecheck/lint discovery;
- read-only schema inspection;
- existing test suite if it does not require production credentials.

Create:

- `docs/trace-implementation-baseline.md`.

The baseline must include:

- current architecture;
- current food data model;
- current API/UI flow for logging food;
- existing search and alias behaviour;
- existing barcode behaviour;
- current nutrition basis;
- existing privacy and deletion controls;
- current feature gaps;
- exact commands used;
- test baseline;
- risk register.

Stop if the repository cannot be safely identified or if a command might touch production.

---

# Phase 1 — current database and data audit

Use read-only access or a scratch copy.

Measure and report:

- food-item count;
- alias count;
- translation/name count;
- nutrition count;
- barcode/GTIN count;
- source count;
- records by source/licence;
- records by cuisine/category;
- records by entity type if available;
- records with missing serving basis;
- records with missing nutrition basis;
- records with missing provenance;
- duplicate names;
- duplicate normalized names;
- duplicate barcodes;
- aliases pointing to missing records;
- raw/cooked collisions;
- generic/branded collisions;
- product/food collisions;
- current search performance if measurable.

Do not repair records yet.

Create:

- `docs/trace-data-audit.md`;
- `artifacts/trace-baseline-counts.json`;
- `artifacts/trace-data-quality-findings.jsonl`.

Classify findings as:

- informational;
- safe to fix later;
- requires migration;
- requires data review;
- potentially destructive;
- blocked by missing provenance.

Stop for approval if the current schema or data has destructive ambiguities.

---

# Phase 2 — product requirements and vertical slices

Create:

- `docs/trace-product-requirements.md`;
- `docs/trace-user-stories.md`;
- `docs/trace-acceptance-matrix.csv`.

Define user stories for:

1. Logging a generic ingredient.
2. Logging raw versus cooked food.
3. Logging a regional Indian dish.
4. Logging payasam and selecting a named variant.
5. Logging rasam and selecting a named variant.
6. Scanning a packaged product barcode.
7. Adding a ready-to-eat product.
8. Adding a heat-and-eat product.
9. Adding a ready-to-cook mix.
10. Comparing generic food and packaged food.
11. Logging restaurant food with an uncertainty range.
12. Searching by original script and transliteration.
13. Filtering by allergens.
14. Filtering by dietary pattern.
15. Switching units.
16. Scaling a recipe.
17. Planning a budget meal.
18. Planning from pantry inventory.
19. Using Trace offline.
20. Correcting an incorrect food record.
21. Exporting personal food data.
22. Using a screen reader or large text.
23. Reviewing AI photo/voice/receipt candidates.
24. Preserving a historical product formulation.

For each story define:

- user;
- preconditions;
- action;
- expected result;
- uncertainty state;
- source/provenance requirement;
- accessibility requirement;
- error state;
- tests.

Group work into vertical slices rather than building a huge unused schema first.

---

# Phase 3 — source, provenance, and licence architecture

Create a source registry design before importing data.

A source record should support:

- source name;
- organization;
- source type;
- country/region;
- dataset name/version;
- source URL/reference;
- fields used;
- retrieval date;
- licence;
- attribution requirement;
- redistribution restriction;
- derived-data permission;
- source quality tier;
- confidence;
- review status.

Source policy:

- use FAO/INFOODS and national food-composition tables for generic nutrition where permitted;
- use USDA FoodData Central for suitable generic foods;
- use Open Food Facts for permitted packaged-product discovery and product-label fields;
- use official manufacturer pages for current branded product labels where possible;
- use reliable public sources for cuisine identity, names, and regional classification;
- do not copy restricted data merely because it is visible online;
- do not copy full copyrighted recipes or images without permission.

Create:

- `docs/trace-source-policy.md`;
- `docs/trace-licence-matrix.md`;
- `config/food_sources.yaml` or project-equivalent;
- source fixtures for tests.

For Open Food Facts, preserve source product code, retrieval/version metadata, attribution, and ODbL information. Respect API documentation, User-Agent requirements, rate limits, and bulk-download guidance. Keep community-contributed data distinguishable from official label verification.

Stop if a proposed source has unclear redistribution rights.

---

# Phase 4 — canonical taxonomy and identity model

Design the taxonomy without damaging existing records.

Support entity types:

- ingredient;
- cooked ingredient;
- prepared dish;
- regional dish variant;
- condiment;
- sauce;
- chutney;
- pickle;
- spice blend;
- fermented food;
- preserved food;
- snack;
- dessert;
- beverage;
- packaged product;
- restaurant menu item;
- recipe.

Support preparation/product classes:

- raw;
- cooked;
- dried;
- frozen;
- canned;
- jarred;
- dehydrated;
- ready-to-eat;
- heat-and-eat;
- ready-to-cook;
- instant;
- meal mix;
- frozen prepared meal;
- chilled prepared meal;
- retort pouch;
- microwave meal.

Support relations:

- `variant_of`;
- `prepared_form_of`;
- `product_of`;
- `similar_to`;
- `substitute_for`;
- `ingredient_of`;
- `regional_association`;
- `historical_association`;
- `supersedes`;
- `same_product_different_market`.

Do not merge:

- generic and branded records;
- raw and cooked records;
- dry and cooked pulses;
- dish families and named variants;
- restaurant items and composition-table foods;
- product formulations from different markets;
- transliteration aliases and genuinely distinct foods.

Design a stable source key that is deterministic and does not depend only on display name.

Create:

- `docs/trace-taxonomy.md`;
- `artifacts/trace-taxonomy.json`;
- taxonomy validation tests.

---

# Phase 5 — regional and global catalogue coverage

Create a coverage matrix with target counts, source plan, review requirement, and status for:

## India

North, South, East, West, Northeast, Himalayan, Kashmiri, Punjabi, Gujarati, Rajasthani, Bengali, Odia, Marathi, Goan, Kerala, Tamil, Telugu, Andhra, Telangana, Karnataka, Chettinad, Konkani, and Assamese foods.

Include payasam, rasam, sambar, bisibele bath, pongal, rice dishes, idli, dosa, appam, vada, upma, avial, kootu, poriyal, thoran, pachadi, olan, erissery, pulissery, theeyal, kuzhambu, pulusu, gongura, dal, paneer, biryani, pulao, breads, street foods, snacks, sweets, beverages, chutneys, pickles, podis, masalas, spice pastes, papads, flours, pulses, and oils.

## Asia

Pakistan, Bangladesh, Sri Lanka, Nepal, Bhutan, Maldives, Afghanistan, Chinese regional cuisines, Japan, Korea, Taiwan, Mongolia, Thailand, Vietnam, Indonesia, Malaysia, Singapore, Philippines, Myanmar, Cambodia, Laos, Brunei, Uzbekistan, Kazakhstan, Kyrgyzstan, Tajikistan, and Turkmenistan.

## Europe and Eurasia

Russia, Ukraine, Belarus, Poland, Czechia, Slovakia, Bulgaria, Serbia, Croatia, Bosnia and Herzegovina, Slovenia, Montenegro, North Macedonia, Romania, Moldova, Hungary, Lithuania, Latvia, Estonia, Germany, Austria, Switzerland, France, Belgium, Netherlands, Britain, Ireland, Italy, Spain, Portugal, Greece, Turkey, Denmark, Sweden, Norway, Finland, Iceland, Malta, Cyprus, Georgia, Armenia, and Azerbaijan.

Use former Yugoslavia as a historical/broader tag, not as the only modern category.

## Other regions

Middle East, Iran/Persia, Levant, Gulf, Iraq, Egypt, Maghreb, Sudan, Ethiopia, Eritrea, Somalia, West Africa, Nigeria, Ghana, Senegal, Kenya, Tanzania, Southern Africa, Madagascar, Mexico, Central America, Caribbean, Brazil, Peru, Colombia, Venezuela, Chile, Argentina, Uruguay, Bolivia, Ecuador, North America, Australia, New Zealand, Māori, Hawaii, Melanesia, Micronesia, Polynesia, Fiji, Samoa, Tonga, and Papua New Guinea.

For every region seek balanced coverage of:

- staples;
- grains;
- pulses;
- produce;
- meat/seafood;
- breads/noodles;
- soups/stews;
- snacks;
- desserts;
- beverages;
- condiments;
- preserved and fermented foods;
- convenience foods.

Do not inflate the count with trivial spelling variants.

Generate candidate files only. Do not import yet.

---

# Phase 6 — multilingual and culturally respectful naming

Implement or specify:

- display name;
- canonical name;
- original script;
- local-language name;
- romanization/transliteration;
- diaspora spelling;
- aliases;
- pronunciation metadata only if supported;
- language/script code;
- source for each name;
- review state.

Support Latin, Cyrillic, Greek, Arabic/Persian, Indic scripts, Chinese, Japanese, Korean, Thai, Vietnamese, Georgian, Armenian, and Hebrew where relevant.

Use Unicode normalization carefully. Keep original names. Do not make transliteration the only identity.

Tests must cover:

- accent-insensitive search;
- script search;
- transliteration search;
- typo tolerance;
- alias collisions;
- ambiguous names;
- one food with multiple spellings;
- multiple foods sharing one English name.

Do not assign shared dishes to one country without evidence. Add community/cultural review status where needed.

---

# Phase 7 — nutrition, portions, and preparation state

Implement a nutrition-observation model or safe extension with:

- nutrient;
- value;
- unit;
- basis;
- serving quantity;
- serving unit;
- raw/cooked state;
- edible/drained/prepared state;
- source;
- source record ID;
- retrieval date;
- version;
- verification type;
- confidence;
- reviewer notes.

Support:

- per 100 g;
- per 100 ml;
- edible portion;
- per serving;
- per package;
- dry matter;
- raw;
- cooked;
- drained;
- as sold;
- as prepared.

Add nutrients where the current product scope supports them:

- calories;
- protein;
- carbohydrate;
- fat;
- saturated fat;
- trans fat;
- fibre;
- total sugars;
- added sugars;
- sodium;
- salt;
- cholesterol;
- micronutrients;
- caffeine;
- alcohol.

Use explicit null/unknown. Do not use zero for missing data.

Implement validation for:

- negative values;
- implausible values;
- macro-energy consistency;
- serving-size validity;
- unit validity;
- sodium/salt conversion;
- raw/cooked mismatch;
- as-sold/as-prepared mismatch;
- conflicting observations;
- duplicate observations.

Do not silently select one conflicting source. Preserve observations and mark review status.

---

# Phase 8 — allergens and dietary attributes

Create structured observations for:

- milk;
- egg;
- peanut;
- tree nuts;
- fish;
- crustaceans;
- molluscs;
- soy;
- gluten-containing cereals;
- sesame;
- sulphites;
- other market-specific allergens.

Each observation should support:

- contains;
- may contain;
- facility/shared equipment;
- not present according to label;
- unknown/not evaluated;
- source label wording;
- source/market/date;
- confidence.

Keep allergens separate from:

- vegetarian;
- vegan;
- pescatarian;
- halal;
- kosher;
- Jain;
- sattvic;
- Buddhist vegetarian;
- no-beef;
- no-pork;
- no-alcohol;
- gluten-free preference;
- lactose-free preference;
- medical diet.

Use three user-preference states:

- must avoid;
- prefer to avoid;
- no preference.

Never infer allergy safety from a food name. Show a safety notice for severe allergies.

---

# Phase 9 — branded products and convenience foods

Create or safely extend separate entities for:

- brands;
- products;
- product variants;
- markets/countries;
- formulations;
- labels;
- barcodes;
- package sizes;
- product status;
- product-to-generic relationships.

Support:

- GTIN-8;
- GTIN-12;
- GTIN-13;
- GTIN-14;
- UPC/EAN normalization;
- multipack versus single item;
- package size;
- market-specific formulation;
- current/discontinued/historical status;
- formulation/version date;
- label retrieval date.

Product acceptance requires:

- stable identity;
- verified brand and product name;
- product class;
- market;
- source and retrieval date;
- nutrition basis;
- ingredients or explicit missing value;
- allergen statement or explicit unknown;
- barcode or explicit missing value;
- licence state;
- duplicate result;
- review state.

Reject or hold for review when only a search snippet exists, barcode conflicts, pack size is unclear, market is unknown, nutrition is unsourced, or licence is incompatible.

Use dry-run product imports and local fixtures. Do not crawl retail sites aggressively.

---

# Phase 10 — recipes, substitutions, pantry, shopping, and budgets

Implement or plan:

- recipes;
- recipe source/licence;
- ingredient quantities;
- batch yield;
- servings;
- scaling;
- preparation and cook time;
- equipment;
- skill level;
- freezer suitability;
- leftovers;
- substitution relations;
- pantry inventory;
- expiry/storage guidance;
- shopping list;
- list deduplication;
- budget ceiling;
- price observations;
- price per serving;
- local availability;
- seasonal availability.

Substitutions must consider allergen safety, diet, region, availability, budget, cooking function, and nutrition differences.

Do not copy complete copyrighted recipe text or images without permission.

---

# Phase 11 — restaurant and street-food support

Create a restaurant/menu-item model or implementation plan with:

- restaurant;
- location;
- menu item;
- cuisine/region;
- menu source;
- retrieval date;
- serving estimate/range;
- ingredients;
- preparation;
- customization;
- nutrition confidence;
- allergen uncertainty;
- menu version.

Show ranges when portions and recipes are uncertain. Do not present restaurant estimates as measured values.

---

# Phase 12 — user preferences and household modes

Support user goals:

- weight loss;
- maintenance;
- gain;
- muscle;
- sport;
- budget;
- time saving;
- food waste reduction;
- neutral tracking;
- clinician-directed plan with professional-advice warning.

Support optional modes for adults, children with guardian controls, older adults, students, shift workers, travellers, athletes, pregnancy/postpartum with professional guidance, and shared households.

Never force weight loss. Never diagnose or prescribe.

Keep sensitive preferences private by default.

---

# Phase 13 — search, recommendations, and AI

Search filters:

- cuisine;
- country;
- region;
- language/script;
- dietary pattern;
- allergens;
- preparation time;
- equipment;
- packaged/generic;
- ready-to-eat/ready-to-cook;
- price;
- availability;
- nutrition target;
- raw/cooked state;
- season;
- pantry status.

Recommendation modes:

- What can I eat now?
- What can I make with what I have?
- Under my budget.
- No cooking.
- High protein.
- Low sodium.
- My regional foods.
- Similar food from another cuisine.
- Replace this ingredient.
- Use this leftover.
- Find the packaged equivalent.
- Find the generic equivalent.

AI photo, receipt, barcode, voice, and label flows must show:

- candidates;
- confidence;
- source/evidence;
- editable food;
- editable portion;
- uncertainty;
- confirmation before logging;
- not-found option;
- error recovery.

A photo must not be treated as proof of exact ingredients, allergens, oil, portion weight, or nutrition.

---

# Phase 14 — accessibility, offline, and internationalization

Target WCAG 2.2 mobile guidance.

Test:

- screen readers;
- large text;
- high contrast;
- reduced motion;
- colour-blind operation;
- keyboard/switch access;
- voice input;
- text-to-speech;
- low literacy;
- dyslexia-friendly presentation;
- one-handed use;
- low bandwidth;
- offline use;
- old/low-memory devices.

Never use colour alone for allergen or safety warnings.

Cache locally:

- recent foods;
- favourites;
- common regional foods;
- barcodes;
- translations;
- recipes;
- pantry;
- essential nutrition;
- pending logs.

Add deterministic conflict resolution and never silently overwrite offline user logs.

Internationalize:

- language;
- script;
- date;
- time;
- decimal separator;
- currency;
- units;
- pluralization;
- sorting;
- number formatting;
- right-to-left layout where required.

---

# Phase 15 — privacy, security, and governance

Treat as sensitive:

- allergies;
- medical diets;
- weight;
- goals;
- eating patterns;
- food photos;
- receipts;
- location;
- shopping behaviour;
- religious preferences.

Implement or document:

- consent;
- private-by-default settings;
- export/delete;
- data minimization;
- retention policy;
- model-training consent;
- source visibility;
- correction history;
- no hidden diagnosis;
- no sale of sensitive preferences without consent;
- safe logging with secrets redacted.

Implement community review states:

- submitted;
- needs evidence;
- community-supported;
- source-verified;
- nutrition-reviewed;
- culturally reviewed;
- disputed;
- superseded;
- rejected.

Keep an audit trail. Do not let an unverified correction silently overwrite a source-backed record.

---

# Phase 16 — implementation sequencing

Implement in vertical slices.

## Slice A: baseline and safety

Deliver:

- baseline audit;
- source/licence registry;
- safe taxonomy extension;
- nutrition observation basis;
- allergen model;
- dietary-preference model;
- duplicate detection;
- provenance display;
- tests.

Stop for review of schema impact.

## Slice B: generic global catalogue

Deliver:

- regional taxonomy;
- Indian payasam/rasam families;
- Indian/Asian/European/global candidate files;
- multilingual names;
- raw/cooked forms;
- condiments and spice blends;
- deterministic review package;
- dry-run only.

Stop for review of coverage, cultural classification, and sources.

## Slice C: packaged products

Deliver:

- brand/product/market/formulation model;
- GTIN normalization;
- product label observations;
- ready-to-eat/heat-and-eat/ready-to-cook classes;
- MTR and other brand research queue;
- Open Food Facts adapter only if licence and API rules are satisfied;
- product/generic relationships;
- dry-run product import.

Stop for licence and data-quality approval.

## Slice D: recipes and daily planning

Deliver:

- recipe model;
- scaling;
- substitutions;
- pantry;
- shopping list;
- budget;
- availability;
- leftovers;
- storage.

Stop for UX review.

## Slice E: search and recommendations

Deliver:

- multilingual search;
- cuisine/region filters;
- dietary/allergen filters;
- convenience filters;
- product/generic search;
- recommendation explanations;
- confidence display.

Stop for search-quality review.

## Slice F: restaurant and AI flows

Deliver:

- restaurant items;
- photo/receipt/barcode/voice candidate flows;
- portion editing;
- uncertainty and confirmation;
- error recovery;
- audit events.

Stop for safety and usability review.

## Slice G: accessibility, offline, privacy, and export

Deliver:

- accessibility tests;
- offline cache/sync;
- export/delete;
- privacy controls;
- localization;
- low-bandwidth testing;
- device testing.

Stop for release review.

## Slice H: controlled import and production rollout

Only after explicit approval:

- backup;
- migration in staging;
- import approved manifest only;
- verify counts and checksums;
- run integrity tests;
- run search and barcode checks;
- verify attribution;
- monitor performance;
- perform controlled production rollout;
- document rollback.

No production import is permitted before approval.

---

# Phase 17 — migrations and compatibility

For every schema change provide:

- rationale;
- old schema;
- new schema;
- nullable/backfill strategy;
- indexes;
- foreign-key behaviour;
- rollback migration;
- data-volume estimate;
- lock/performance risk;
- API compatibility;
- UI compatibility;
- test fixtures;
- backup requirement.

Prefer additive migrations. Do not rewrite or destroy old observations. Do not backfill uncertain data as if it were verified.

If a new feature can be implemented without a migration, prefer the lower-risk solution and explain the trade-off.

---

# Phase 18 — test plan

Run and add tests for:

## Data tests

- taxonomy;
- region hierarchy;
- entity types;
- names and scripts;
- transliteration;
- aliases;
- duplicate detection;
- shared dishes;
- raw/cooked state;
- product/generic separation;
- formulation history;
- source/licence fields;
- missing provenance;
- nutrition basis;
- nutrient sanity;
- allergen uncertainty;
- dietary filters;
- barcode uniqueness.

## Import tests

- deterministic generation;
- dry-run output;
- idempotency;
- approved-manifest scope;
- production-target guard;
- no silent overwrite;
- rollback;
- partial failure handling;
- retry safety;
- checksum verification.

## API/UI tests

- search;
- filters;
- units;
- portions;
- recipe scaling;
- product scanning;
- AI confirmation;
- restaurant uncertainty;
- offline sync;
- export/delete;
- accessibility;
- localization;
- right-to-left layouts where supported.

## Security/privacy tests

- secret redaction;
- authorization;
- sensitive preference privacy;
- deletion;
- export;
- audit logs;
- malicious input;
- rate limits;
- source-content sanitization.

Do not call real external APIs from tests.

---

# Phase 19 — observability and quality metrics

Add metrics for:

- search success;
- no-result searches;
- duplicate rate;
- barcode match accuracy;
- AI confirmation rate;
- AI correction rate;
- false allergen-safe results;
- missing nutrition rate;
- regional/language coverage;
- offline conflict rate;
- import rejection rate;
- source verification rate;
- accessibility failures;
- API latency;
- database query performance;
- user correction rate.

Do not optimize only for total catalogue size or calorie-log count.

---

# Phase 20 — final deliverables and approval gate

Before requesting approval, create:

- `docs/trace-implementation-plan.md`;
- `docs/trace-architecture-decisions.md`;
- `docs/trace-schema-impact.md`;
- `docs/trace-migration-plan.md`;
- `docs/trace-rollback-plan.md`;
- `docs/trace-source-policy.md`;
- `docs/trace-licence-matrix.md`;
- `docs/trace-accessibility-plan.md`;
- `docs/trace-privacy-plan.md`;
- `docs/trace-ai-safety-plan.md`;
- `docs/trace-gap-report.md`;
- `docs/trace-phased-roadmap.md`;
- `artifacts/food_catalogue_taxonomy.json`;
- `artifacts/food_catalogue_coverage_matrix.csv`;
- `artifacts/food_catalogue_candidates.jsonl`;
- `artifacts/food_catalogue_products.jsonl`;
- `artifacts/food_catalogue_rejections.jsonl`;
- `artifacts/food_catalogue_collisions.json`;
- `artifacts/food_catalogue_import_plan.json`;
- `artifacts/food_catalogue_summary.md`.

Final report must contain:

1. Exact current counts.
2. Exact proposed additions.
3. Projected final counts.
4. Coverage by region, cuisine, country, language, and entity type.
5. Indian payasam/rasam and regional coverage.
6. Condiment and spice-blend coverage.
7. Ready-food and packaged-product coverage.
8. Brands and product markets.
9. Verified, estimated, and missing nutrition counts.
10. Allergen and dietary uncertainty.
11. Source/licence breakdown.
12. Duplicate and conflict counts.
13. Schema and migration impact.
14. API/search/storage/performance impact.
15. Accessibility and privacy results.
16. AI uncertainty and confirmation results.
17. Test commands and results.
18. Exact dry-run command.
19. Future apply command, shown but not executed.
20. Backup and rollback procedure.
21. Remaining manual-review queue.
22. Explicit list of production actions not performed.

## Final stop condition

Stop after creating the plan, research package, dry-run outputs, tests, and reports.

Do not:

- import to production;
- alter production data;
- run production migrations;
- update existing aliases or nutrition records;
- change user logs;
- stage or commit.

Ask for explicit approval using this checklist:

- [ ] source and licence plan approved;
- [ ] taxonomy approved;
- [ ] nutrition and serving policy approved;
- [ ] allergen/dietary policy approved;
- [ ] branded-product policy approved;
- [ ] schema changes approved;
- [ ] migration and rollback plan approved;
- [ ] catalogue counts approved;
- [ ] accessibility/privacy plan approved;
- [ ] dry-run reviewed;
- [ ] production backup confirmed;
- [ ] production import explicitly authorized.

Only after all boxes are explicitly approved may you prepare a production import. Even then, show the exact command and wait for confirmation immediately before executing it.
