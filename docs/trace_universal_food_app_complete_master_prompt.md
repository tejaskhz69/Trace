# Trace Universal Food App
## Complete master research, product, database, and implementation prompt

Prepared: 29 August 2026

## Purpose

Trace should become a universal food, nutrition, meal-planning, product, and food-logging application. It should work for people across countries, cultures, languages, diets, budgets, cooking abilities, health goals, household situations, and levels of internet access.

Universal does not mean blindly importing every food name found online. It means building a broad, culturally respectful, safe, accessible, searchable, well-sourced, and maintainable system.

This document combines the following requirements:

- Indian and Asian cuisines;
- all major global cuisines;
- Russian, Eastern European, Balkan, former-Yugoslav, Central European, Nordic, and Mediterranean foods;
- regional Indian dishes including payasam and rasam;
- condiments, chutneys, sauces, pickles, spice blends, pastes, and fermented foods;
- ready-to-eat, heat-and-eat, ready-to-cook, instant, frozen, chilled, canned, retort-pouch, and meal-mix products;
- Indian brands such as MTR and other verified brands;
- global packaged-food brands;
- multilingual and original-script search;
- allergies, dietary patterns, religion, culture, accessibility, budgets, prices, availability, and food waste;
- AI photo, barcode, receipt, and voice logging;
- restaurant food, recipes, pantry, shopping, household, and offline functionality.

## Absolute safety rules

Before production changes:

- inspect the existing Trace application and schema;
- measure the current database and catalogue counts;
- perform all research in read-only mode or against fixtures/scratch databases;
- do not write to the production database;
- do not insert, update, delete, or truncate existing food, nutrition, alias, barcode, or user-log tables;
- do not alter existing migrations without an approved schema plan;
- do not overwrite existing records silently;
- do not invent nutrition, allergens, brands, barcodes, prices, serving sizes, cuisine identities, or licences;
- do not copy restricted recipe collections or images;
- do not expose credentials, tokens, database URLs, API keys, or private user data;
- do not call paid or rate-limited providers from tests;
- do not stage or commit automatically;
- stop before a production import and wait for explicit approval.

## Gate 1: baseline and inspection

Report read-only values for:

- current branch and commit;
- current Git status;
- exact food-item count;
- exact alias count;
- nutrition-row count;
- barcode/GTIN count;
- translation/name count;
- source and licence distribution;
- cuisine/category distribution;
- current database and Alembic revision;
- existing migrations;
- existing import scripts;
- existing food-search behaviour;
- existing barcode behaviour;
- existing AI/photo/receipt/voice integrations;
- existing user-preference and goal models;
- existing privacy and deletion controls;
- current test results.

Inspect whether the schema can represent:

- ingredients;
- raw/cooked forms;
- prepared dishes;
- regional variants;
- condiments;
- spice blends;
- recipes;
- packaged products;
- brands;
- product markets;
- formulations;
- barcodes;
- translations;
- original scripts;
- aliases;
- nutrition observations;
- allergen observations;
- dietary attributes;
- preparation methods;
- serving bases;
- price and availability;
- source/licence provenance;
- review state;
- historical data.

## Universal food taxonomy

### Entity types

- ingredient;
- cooked ingredient;
- grain/cereal;
- pulse/legume;
- fruit;
- vegetable;
- herb/spice;
- flour;
- oil/fat;
- dairy;
- egg;
- meat;
- poultry;
- seafood;
- prepared dish;
- recipe component;
- condiment;
- sauce;
- chutney;
- pickle;
- relish;
- spice blend;
- curry paste;
- fermented food;
- preserved food;
- bread/flatbread;
- noodle/pasta;
- soup/stew;
- snack;
- dessert/sweet;
- beverage;
- alcoholic beverage, if in scope;
- packaged product;
- restaurant menu item;
- recipe;
- meal plan.

### Product/preparation classes

- generic raw;
- generic cooked;
- ready-to-eat;
- heat-and-eat;
- ready-to-cook;
- instant;
- meal mix;
- frozen prepared meal;
- chilled prepared meal;
- shelf-stable retort pouch;
- canned/jarred prepared food;
- dehydrated meal;
- microwave meal;
- air-fryer product;
- breakfast mix;
- dessert mix;
- spice/seasoning mix;
- sauce/paste/pickle product.

Do not call every packaged food ready-to-eat. Store preparation instructions, added ingredients, cooking method, and product class.

## Cuisine and regional coverage

Use hierarchical tags rather than one flat cuisine field. Preserve multiple evidence-backed associations where appropriate. Do not represent shared dishes as exclusively belonging to one country without evidence.

### India

Cover North, South, East, West, Northeast, Himalayan, Kashmiri, Punjabi, Gujarati, Rajasthani, Bengali, Odia, Marathi, Goan, Kerala, Tamil, Telugu, Andhra, Telangana, Karnataka, Chettinad, Konkani, Assamese, and other regional traditions.

Include:

- rice, wheat, millet, and grain dishes;
- idli, dosa, uttapam, appam, paniyaram, vada, upma;
- roti, naan, paratha, bhakri, puri, and regional breads;
- dal, rajma, chana, kadhi, paneer, dairy, fish, meat, egg, and vegetable foods;
- biryani and pulao variants;
- breakfast foods, street foods, snacks, festival foods, sweets, desserts, and beverages;
- chutneys, pickles, podis, masalas, spice pastes, raitas, papads, and sauces;
- regional grains, pulses, flours, oils, and ingredients.

Required named families include:

- payasam: semiya payasam, ada pradhaman, paal payasam, parippu payasam, sakkarai pongal, and other documented variants;
- rasam: tomato, pepper, lemon, pineapple, garlic, Mysore, milagu, jeera, paruppu, and other documented variants;
- sambar;
- bisibele bath;
- pongal;
- lemon, tamarind, coconut, tomato, and curd rice;
- avial, kootu, poriyal, thoran, pachadi, olan, erissery, pulissery, theeyal, kuzhambu, mor kuzhambu, pulusu, and gongura preparations;
- dal makhani, dal tadka, chana masala, rajma, dal baati, panchmel dal;
- sarson ka saag, makki di roti, litti chokha, poha, sabudana khichdi;
- kachori, samosa, pakora, dhokla, fafda, handvo, thepla;
- Bengali sweets and regional dairy desserts;
- halwa, laddoo, barfi, peda, jalebi, rasgulla, sandesh, modak, shrikhand, basundi, kulfi.

Do not make one nutrition record for all payasam or all rasam when ingredients and preparation materially differ. Use a family relationship plus named variants.

### Asia

Cover South Asia, East Asia, Southeast Asia, and Central Asia.

Include Pakistani, Bangladeshi, Sri Lankan, Nepali, Bhutanese, Maldivian, Afghan, Chinese regional, Japanese, Korean, Taiwanese, Mongolian, Thai, Vietnamese, Indonesian, Malaysian, Singaporean, Filipino, Burmese/Myanmar, Cambodian/Khmer, Lao, Bruneian, Uzbek, Kazakh, Kyrgyz, Tajik, and Turkmen foods.

Include tofu, tempeh, soy products, noodles, dumplings, broths, curries, fermented foods, kimchi, pickles, miso, doenjang, gochujang, soy sauces, fish sauces, sambal, chili oils, doubanjiang, hoisin, oyster-style sauces, curry pastes, snacks, desserts, and beverages.

### Europe and Eurasia

Cover:

- Russian;
- Ukrainian;
- Belarusian;
- Polish;
- Czech;
- Slovak;
- Bulgarian;
- Serbian;
- Croatian;
- Bosnian and Herzegovinian;
- Slovenian;
- Montenegrin;
- North Macedonian;
- Romanian;
- Moldovan;
- Hungarian;
- Lithuanian;
- Latvian;
- Estonian;
- German;
- Austrian;
- Swiss;
- French;
- Belgian;
- Dutch;
- British and Irish;
- Italian regional;
- Spanish regional;
- Portuguese;
- Greek;
- Turkish;
- Danish, Swedish, Norwegian, Finnish, Icelandic;
- Maltese and Cypriot;
- Georgian, Armenian, and Azerbaijani;
- Balkan and Central European.

Do not make “Yugoslavian” the only category. Use it as a historical/broader tag and maintain distinct Serbian, Croatian, Bosnian, Slovenian, Montenegrin, and North Macedonian tags where appropriate.

Cover soups, breads, dumplings, porridges, fermented foods, pickles, dairy, pastries, potatoes, grains, preserved fish/meat, sauces, spreads, stews, and desserts.

### Other global regions

Cover Middle Eastern, Persian/Iranian, Levantine, Gulf Arab, Iraqi, Kurdish where supported, Egyptian, Maghrebi, Sudanese, Ethiopian, Eritrean, Somali, West African, Nigerian, Ghanaian, Senegalese, Kenyan, Tanzanian, Southern African, Malagasy, Mexican, Central American, Caribbean, Brazilian, Peruvian, Colombian, Venezuelan, Chilean, Argentine, Uruguayan, Bolivian, Ecuadorian, North American, Australian, Māori, Hawaiian, Melanesian, Micronesian, Polynesian, Fijian, Samoan, Tongan, and Papua New Guinean foods.

## Condiment and pantry expansion

For every region, research:

- sauces;
- chutneys;
- pickles;
- relishes;
- dips;
- oils;
- vinegars;
- mustards;
- hot sauces;
- curry pastes;
- spice blends;
- fermented sauces;
- preserved vegetables;
- jams and preserves;
- dressings;
- broths and stock bases;
- instant seasoning packets.

Store flavour profile, heat level only when sourced, preparation state, common uses, ingredients, allergens, and regional associations. Do not assume two similarly named sauces are nutritionally or culturally identical.

## Indian and global convenience products

Research product-level records separately from generic foods. Candidate Indian brand queue:

- MTR Foods;
- Haldiram’s;
- Gits;
- iD Fresh Food;
- ITC Kitchens of India;
- Bikano;
- Maiyas;
- Priya Foods;
- Deep Foods;
- Bambino;
- Mother’s Recipe;
- Bedekar;
- Eastern;
- Double Horse;
- Anil Foods;
- other verified regional brands.

MTR’s official catalogue separates ready-to-eat and ready-to-cook categories and includes regional items such as rasam rice, bisibelebhath, pongal, sambar, dal makhani, chana masala, palak paneer, and paneer butter masala. Verify each live product, package, market, formulation, and label before import.

Global discovery queue may include regional products from Nestlé, Unilever food brands, Ajinomoto, Nissin, Maruchan, Nongshim, Samyang, Kikkoman, Lee Kum Kee, Patak’s, Sharwood’s, Tilda, Old El Paso, Goya, Amy’s Kitchen, supermarket private labels, and local frozen/retort brands. These are research candidates only, not automatic records.

For every product capture:

- brand;
- product name and variant;
- product class;
- cuisine/region;
- country/market;
- verified GTIN/barcode;
- package size;
- serving count;
- preparation instructions;
- storage condition;
- ingredients;
- allergens;
- printed dietary claims;
- nutrition panel exactly as labelled;
- as-sold/as-prepared basis;
- manufacturer;
- source/product ID;
- licence/terms;
- retrieval date;
- formulation/version date;
- current/discontinued status;
- confidence;
- review state.

Keep a branded product separate from a generic dish and connect them with a relationship such as `product_of`, `prepared_form_of`, or `similar_to`.

## Nutrition and serving standards

Every nutrient value must have:

- source;
- source record ID;
- retrieval date;
- dataset/version;
- measurement type;
- nutrition basis;
- unit;
- confidence;
- verification state.

Classify values as analytical, composition-table, manufacturer-label, recipe-calculated, imported, estimated, or unavailable.

Support per 100 g, per 100 ml, edible portion, per serving, per package, dry matter, raw, cooked, drained, and as-prepared bases. Never mix them silently. Never replace missing values with zero.

Validate:

- nonnegative nutrients;
- plausible energy;
- macro-energy consistency;
- serving-size validity;
- unit validity;
- sodium/salt distinction;
- raw/cooked mismatch;
- duplicate observations;
- label reformulation.

Use FAO/INFOODS, national composition tables, and USDA FoodData Central for generic foods where permitted. Use product labels and permitted product databases for packaged foods. [web:196][web:181][web:210]

## Allergens, diets, and safety

Separate:

- allergy;
- intolerance;
- lifestyle preference;
- religious preference;
- medical restriction;
- ethical preference;
- unknown/not evaluated.

Support must avoid, prefer to avoid, and no preference.

Store:

- contains;
- may contain;
- shared-equipment/facility warning;
- unknown;
- source label wording;
- market-specific rule;
- label date.

At minimum support milk, egg, peanut, tree nuts, fish, crustaceans, molluscs, soy, gluten-containing cereals, sesame, and sulphites, while allowing market-specific allergen lists. Do not infer safety from a food name. Codex allergen-management guidance should inform the source and safety design. [web:237]

## Personalization and use cases

Support:

- weight loss, maintenance, gain, muscle, sport, budget, time-saving, food-waste reduction, or neutral tracking;
- vegetarian, vegan, pescatarian, flexitarian, omnivore;
- halal, kosher, Jain, sattvic, Buddhist vegetarian, no-beef, no-pork, no-alcohol;
- gluten-free and lactose-free preferences;
- family, children with guardian controls, older adults, students, shift workers, travellers, athletes, shared households;
- breakfast, lunch, dinner, snack, fasting, festival, social, office, school, travel, restaurant, and takeaway contexts;
- spice tolerance and disliked foods;
- household profiles with different restrictions and portions.

Never force weight loss or make diagnosis/treatment claims.

## Budget, availability, and food waste

Optionally store:

- currency;
- market and location;
- price and price date;
- package size;
- price per serving;
- local/imported status;
- seasonality;
- retailer/source;
- pantry status;
- storage guidance;
- shelf-life/use-by/best-before distinction;
- leftover potential;
- freezer suitability;
- waste risk.

Add “use what I have,” “under my budget,” “no refrigerator,” “cheapest acceptable substitute,” “use this leftover,” and pantry-based meal planning.

FAO’s food-loss and food-waste database is a possible source lead for future waste features, but not a basis for inventing product-specific sustainability scores. [web:236]

## Units, portions, substitutions, and recipes

Support metric, US customary, imperial, grams, kilograms, millilitres, ounces, pounds, cups, tablespoons, teaspoons, pieces, slices, bowls, plates, handfuls, and local household measures.

Store normalized canonical amounts internally and convert only at display time.

Support raw/cooked, fresh/frozen/dried/canned, chopped/sliced/minced/powder/paste forms.

Substitutions should consider allergen safety, diet, region, availability, budget, cooking function, and nutrition difference. Do not claim equivalence without evidence.

Support recipe import only within licence rules, scaling, batch cooking, yield, freezer portions, leftovers, no-cook plans, meal prep, pantry-only plans, and emergency-budget plans. Do not copy full copyrighted recipes or images without permission.

## Language, culture, and search

Support:

- English and local-language names;
- original scripts;
- transliteration;
- accents and diacritics;
- spelling variants;
- diaspora names;
- country-specific product names;
- voice search;
- phonetic search;
- typo tolerance;
- ingredient search;
- cuisine/region search;
- similar-food search.

Plan for Latin, Cyrillic, Greek, Arabic/Persian, Indic, Chinese, Japanese, Korean, Thai, Vietnamese, Georgian, Armenian, and Hebrew scripts where relevant.

Do not use lossy transliteration as the only canonical name. Preserve source names and distinguish aliases from distinct foods.

## Restaurant food

Create a separate restaurant/menu-item entity with:

- restaurant and location;
- menu item;
- cuisine/region;
- portion estimate/range;
- ingredients and preparation;
- customization;
- nutrition confidence;
- menu version/date;
- source/menu URL;
- allergen uncertainty.

Show estimates as ranges when needed. Do not imply laboratory measurement.

## AI features

Support barcode scanning, product-label scanning, food photos, receipts, voice logging, natural-language entry, recipe extraction, meal decomposition, label translation, and recommendations.

Every AI result must show candidates, confidence, evidence/source, editable portion, uncertainty, confirmation before logging, and a not-found option. A photo is not proof of exact ingredients, allergens, oil, weight, or nutrition.

## Accessibility and offline use

Target WCAG 2.2 mobile guidance. Support screen readers, large text, high contrast, reduced motion, keyboard/switch access, voice input, text-to-speech, low-literacy presentation, dyslexia-friendly text, low bandwidth, offline operation, and older devices. [web:253][web:259]

Never communicate allergen or safety status by colour alone.

Cache recent foods, favourites, common local foods, barcodes, recipes, pantry, translations, essential nutrition, and pending logs. Use conflict resolution and never silently change a user’s offline log.

## Barcode and product identity

Support GTIN-8, GTIN-12, GTIN-13, GTIN-14, UPC/EAN normalization, 2D/QR-linked product pages, package variants, multipacks, market-specific products, formulation versions, batch/lot and expiry only where needed.

GS1 defines GTIN as a trade-item identifier and GS1 Digital Link can connect identifiers to richer product information. [web:243][web:244]

Do not assume the same brand/product family has the same formulation in every country.

## Suggested entities

Use existing models where possible; otherwise consider:

- `food_items`;
- `food_variants`;
- `food_aliases`;
- `food_translations`;
- `cuisine_regions`;
- `food_cuisine_links`;
- `food_preparation_forms`;
- `food_nutrition_observations`;
- `food_allergens`;
- `food_dietary_attributes`;
- `food_products`;
- `brands`;
- `product_markets`;
- `product_labels`;
- `product_formulations`;
- `product_barcodes`;
- `food_relations`;
- `food_substitutions`;
- `food_sources`;
- `food_licences`;
- `food_reviews`;
- `user_corrections`;
- `price_observations`;
- `availability_observations`;
- `seasonality`;
- `storage_guidance`;
- `recipe_yields`;
- `restaurant_menu_items`.

Prefer append-only source/nutrition observations so new labels and revisions do not destroy history.

## Search and recommendation modes

Add filters for cuisine, country, region, language, diet, allergens, preparation time, equipment, packaged/generic, ready-to-eat/ready-to-cook, price, availability, nutrition target, raw/cooked state, season, and pantry status.

Support:

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

Explain why a recommendation was made and show uncertainty.

## Privacy and governance

Treat allergies, medical diets, weight, goals, eating patterns, photos, receipts, location, and shopping behaviour as sensitive.

Add consent, private-by-default settings, export/delete controls, minimal data collection, retention rules, model-improvement consent, source visibility, correction history, no hidden diagnosis, and no sale of sensitive preferences without explicit consent.

Allow users to report missing foods, wrong names, incorrect transliterations, wrong serving sizes, outdated labels, duplicates, missing allergens, product discontinuation, and cultural inaccuracies.

Use review states:

- submitted;
- needs evidence;
- community-supported;
- source-verified;
- nutrition-reviewed;
- culturally reviewed;
- disputed;
- superseded;
- rejected.

## Data source and licence policy

Create a source registry containing source, organization, region, dataset/version, URL/reference, fields used, licence, attribution, redistribution restrictions, derived-data permission, retrieval date, and confidence.

Use:

- FAO/INFOODS and national composition tables for generic nutrition where permitted;
- USDA FoodData Central for suitable generic foods;
- Open Food Facts for permitted packaged-product discovery and label/product data;
- official manufacturer pages for current product labels;
- reliable public sources for cultural identity and regional classification.

Open Food Facts data is community-contributed and may be incomplete. Respect its API documentation, User-Agent requirements, rate limits, bulk-download guidance, attribution, and ODbL obligations. [web:185][web:217]

Do not copy proprietary data merely because it is visible online. Do not scrape aggressively. Do not import product images without licence permission.

## Deterministic research package

Generate outside production:

- `food_catalogue_sources.md`;
- `food_catalogue_licence_matrix.md`;
- `food_catalogue_taxonomy.json`;
- `food_catalogue_coverage_matrix.csv`;
- `food_catalogue_candidates.jsonl`;
- `food_catalogue_products.jsonl`;
- `food_catalogue_rejections.jsonl`;
- `food_catalogue_collisions.json`;
- `food_catalogue_reviews.jsonl`;
- `food_catalogue_import_plan.json`;
- `food_catalogue_summary.md`;
- `food_app_gap_report.md`;
- `food_app_phased_roadmap.md`.

Sort all outputs deterministically. Do not silently omit failed records.

The summary must report exact current counts, accepted additions, projected final count, cuisine/region/entity-type coverage, Indian payasam/rasam coverage, condiment coverage, convenience-product coverage, brands, markets, verified barcodes, verified/estimated/missing nutrition, sources/licences, duplicates, conflicts, missing provenance, manual-review records, expected API/search/storage impact, and remaining coverage gaps.

## Import safety

Any importer must:

- default to dry-run;
- require `--apply` and `--expect-db trace` for production writes;
- reject apply without the expected database before opening a connection;
- verify host, port, current database, and migration revision;
- reject non-loopback hosts unless explicitly allowed;
- import only the approved plan;
- be idempotent;
- preserve existing records;
- stop before writes when conflicts exist;
- never silently overwrite barcodes, nutrition, aliases, source fields, or user logs;
- provide a backup and rollback plan;
- never print secrets.

## Testing

Add tests for:

- taxonomy and cuisine hierarchy;
- multilingual names and transliteration;
- original scripts;
- raw/cooked and dry/cooked distinctions;
- dish/ingredient/product separation;
- condiment identity;
- serving basis and unit conversion;
- recipe scaling;
- nutrition sanity;
- allergen status and uncertainty;
- dietary filters;
- barcode uniqueness;
- product-market variants;
- formulation history;
- duplicate detection;
- alias collisions;
- provenance and licence metadata;
- deterministic generation;
- idempotent import;
- existing-row preservation;
- offline sync conflicts;
- AI confidence and confirmation;
- accessibility;
- no silent overwrite;
- no nutrition-table or alias-table damage.

Use local fixtures and mocked providers. Do not call live providers from tests.

## Phased roadmap

### Phase A: safety and foundations

- inspect schema and baseline;
- source/licence framework;
- allergens;
- dietary attributes;
- serving basis;
- raw/cooked forms;
- duplicate protection;
- generic/branded separation;
- barcode normalization;
- accessibility baseline;
- privacy controls.

### Phase B: core universal catalogue

- Indian regional dishes;
- payasam and rasam families;
- Asian and European coverage;
- global ingredients and condiments;
- multilingual aliases and original scripts;
- ready-to-eat and ready-to-cook classes;
- generic nutrition sources;
- recipe scaling.

### Phase C: practical daily use

- packaged brands and market-specific products;
- restaurant foods;
- pantry and shopping lists;
- budgets and availability;
- substitutions;
- household profiles;
- offline support;
- meal planning;
- leftover and storage support.

### Phase D: advanced intelligence

- AI photo/receipt/voice logging;
- food decomposition;
- label translation;
- personal recommendations;
- food waste reduction;
- sustainability observations;
- community and expert review;
- health-platform integrations;
- exports and interoperability.

## Final report and stop condition

Before any production import, report:

1. Current exact counts.
2. Proposed additions and projected final counts.
3. Coverage by continent, country, cuisine, region, and entity type.
4. Payasam, rasam, Indian regional, condiment, and convenience-food counts.
5. Product counts by brand, market, and product class.
6. Nutrition quality and serving-basis breakdown.
7. Allergen and dietary uncertainty.
8. Source and licence breakdown.
9. Duplicate and collision findings.
10. Translation and original-script coverage.
11. Accessibility and privacy gap report.
12. Search, API, storage, and performance impact.
13. Exact files created or modified.
14. Test results.
15. Dry-run command.
16. Future apply command.
17. Backup and rollback procedure.
18. Remaining gaps and manual-review queue.

Stop after Gate 1. Do not write to production, do not import records, do not alter user data, do not stage, and do not commit until the user explicitly approves the source/licence plan, taxonomy, safety rules, schema impact, counts, import plan, and roadmap.

## Research references

- FAO/INFOODS Asia directory: https://www.fao.org/infoods/infoods/tables-and-databases/asia/en/
- FAO/INFOODS datasets: https://www.fao.org/infoods/infoods/tables-and-databases/faoinfoods-databases/en/
- USDA FoodData Central: https://fdc.nal.usda.gov/
- Open Food Facts API: https://openfoodfacts.github.io/openfoodfacts-server/api/
- Open Food Facts data/licence: https://world.openfoodfacts.org/data
- MTR ready-to-eat: https://www.mtrfoods.com/products/ready-to-eat
- MTR ready-to-cook: https://www.mtrfoods.com/products/ready-to-cook
- Global Nutrition Database for Packaged Foods: https://resolvetosavelives.org/how-we-save-lives/healthier-food/global-nutrition-database/
- Codex allergen-management guidance: https://www.fao.org/fao-who-codexalimentarius/
- GS1 GTIN: https://www.gs1.org/standards/id-keys/gtin
- GS1 Digital Link: https://www.gs1.org/standards/gs1-digital-link
- W3C mobile accessibility: https://www.w3.org/TR/wcag2mobile-22/
- FAO food-based dietary guidelines: https://www.fao.org/nutrition/education/food-dietary-guidelines/home/en/
- FAO food-loss and food-waste database: https://www.fao.org/platform-food-loss-waste/flw-data/en/
