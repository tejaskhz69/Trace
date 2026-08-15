# Building the food database — why Pintola failed, and how to fix it properly

---

## What actually went wrong

You searched for **Pintola High Protein Oats**, got nothing, then tried the barcode and got nothing.

That product is **already in Open Food Facts**, fully populated:

| | |
|---|---|
| Barcode | `8906136651951` (EAN-13) |
| Name | Pintola High Protein Oats Dark Chocolate, 400 g |
| Serving | 50 g |
| Per 100 g | 25 g protein · 54.6 g carbs · 8 g fat · 9.6 g fibre · 14 g sugar |

There's a 1 kg variant too, at `8906136651968`.

So this is not a "my database is too small" problem. **Your barcode lookup queried your own seeded table, found nothing, and stopped.** The fix is a resolution chain, not a bigger seed file — and no amount of scraping will ever beat "ask the databases that already have it."

---

## The resolution chain

```
scan
 │
 ├─ 1. Local Postgres            ~5 ms      instant, works offline
 ├─ 2. Open Food Facts API       ~300 ms    ~4M products, strong on Indian brands
 ├─ 3. USDA FoodData Central     ~400 ms    ~1.9M US branded, higher data quality
 ├─ 4. AI label OCR              ~2 s       user photographs the nutrition panel
 └─ 5. Manual entry → moderation queue
              │
              └──── every hit is WRITTEN BACK to local Postgres
```

Steps 2 and 3 run **in parallel**, and the higher `data_quality` score wins. That keeps p95 under ~1.5s on a local miss while still hitting your "<1 second scan-to-log" target on the common path.

The write-back is the important part: **the second user to scan that product gets an instant local hit.** Your database grows from real usage instead of from a scraping project you have to maintain forever.

Implemented in `services/api/app/services/food_sources.py` and `routers/foods.py`.

### One detail that will bite you

UPC-A (12 digits, US) and EAN-13 (13 digits, everywhere else) encode the same product differently — EAN-13 is just `0` + UPC. If you store one form and scan the other, you get a false miss. The scaffold checks `{code, code.lstrip("0"), code.zfill(13)}` on every lookup.

---

## The three data sources, honestly

| Source | Size | Covers | Quality | Licence |
|---|---|---|---|---|
| **Open Food Facts** | ~4M products | Packaged goods worldwide, incl. Indian brands (their India DB passed 10k products) | Crowd-sourced — variable. Use `completeness` to filter | ODbL (attribution required) |
| **USDA FoodData Central** | ~1.9M branded + ~8k Foundation/SR Legacy | US packaged + high-quality raw ingredient data | Excellent. Government-curated | Public domain |
| **IFCT 2017** | ~500 foods | Indian raw ingredients, analysed values | Excellent, but tiny and PDF-only | Free to use, cite ICMR-NIN |

**None of them cover cooked dishes.** Nobody puts a barcode on dal. That's what `scripts/seed_dishes.py` is for, and it's where you actually differentiate.

### Getting the bulk data

```bash
# Open Food Facts — full JSONL dump (~9 GB uncompressed)
wget https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz

# Sane first import: India + US + UK, decent completeness only (~250k rows)
python -m app.scripts.ingest_openfoodfacts \
    --dump openfoodfacts-products.jsonl.gz \
    --countries india,united-states,united-kingdom \
    --min-completeness 0.35

# Or stream it without saving 9 GB to disk
python -m app.scripts.ingest_openfoodfacts --stream-url --countries india
```

There's also a Parquet export on Hugging Face (`openfoodfacts/product-database`) that's much faster to query with DuckDB if you want to explore before importing.

**USDA:** free API key at `fdc.nal.usda.gov/api-key-signup.html`, or bulk CSV from their download page.

**Licensing, briefly:** OFF is ODbL — you must attribute Open Food Facts, and if you publicly redistribute a *modified database* you must share it back under the same terms. Using it inside your app with attribution on a credits screen is standard practice. Talk to a lawyer before building a proprietary derived database you sell access to. USDA is public domain, no restrictions.

---

## Cooked dishes — the part that actually differentiates you

`scripts/seed_dishes.py` seeds ~100 dishes across Indian (North, South, street food, sweets), Chinese, Japanese, Korean, Thai, Vietnamese, Indonesian, Middle Eastern, Mediterranean, Italian, French, British, Mexican, Brazilian, Peruvian, and American cuisines — plus global staples and cooking fats.

Three design choices that matter more than the count:

**1. Serving sizes in the unit a native speaker uses.**
Not "100 g of dal." *One katori.* Not "85 g of dosa." *One dosa.* This is the difference between a 2-tap log and a user doing mental arithmetic and giving up:

```
katori 150 g · chapati 40 g · paratha 65 g · idli 35 g · dosa 85 g
ladle 60 g · thali plate 250 g · standard glass 200 ml
```

**2. Aliases and colloquial names.**
`roti = chapati = phulka`. `chowmein = chow mein = hakka noodles`. `golgappa = pani puri = puchka`. Stored in `names_i18n.aliases` and folded into `search_text`, so all spellings resolve.

**3. Cooking fats as first-class entries.**
Ghee and oil are separate loggable items with tsp/tbsp servings, because the photo scanner's clarifying question ("how much ghee?") resolves into a real log line.

---

## Search that tolerates how people actually type

Postgres `pg_trgm`, no Elasticsearch needed:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX ix_food_search_trgm ON food_items USING gin (search_text gin_trgm_ops);
```

```sql
SELECT *, similarity(search_text, :q) AS sim
FROM food_items
WHERE search_text %% :q OR search_text ILIKE :prefix
ORDER BY (search_text ILIKE :prefix) DESC,  -- exact prefix first
         sim DESC,                           -- then fuzzy
         log_count DESC,                     -- then popularity
         data_quality DESC                   -- then trustworthiness
LIMIT 25;
```

This makes `panner tika` find *Paneer Tikka* and `chapathi` find *Chapati*. Ranking by `log_count` means the database gets better at serving your users the more they use it.

---

## Do NOT chase "1 lakh Indian food items"

Your project brief targets 100,000+ Indian items. I'd push back on that hard, and here's the argument:

MyFitnessPal has ~20 million entries. Its Indian data is the single most-complained-about thing about the app, because it's crowd-sourced and unverified — six entries for "roti" with calorie values ranging from 70 to 300, and no way for a user to know which is right. Database size became a liability, not a moat.

**A wrong entry is worse than a missing one.** A missing entry costs the user 20 seconds of manual entry. A wrong entry silently corrupts their whole week, produces a bogus weekly verdict, and destroys trust in the feature you're actually selling.

So:

| Instead of | Do this |
|---|---|
| 100k crowd-sourced Indian items | **2,000 verified dishes** covering ~90% of logging volume |
| Scraping everything upfront | Import OFF/USDA for packaged goods, curate cooked dishes by hand |
| Open user contributions | Contributions default to `moderation_status='pending'` — visible to their author only until approved |

The scaffold enforces this: user-submitted foods are private until moderated, and a macro-vs-calorie sanity check (>30% drift is rejected) blocks the most common typo class before it enters the shared catalogue.

Track **search success rate** — the % of searches that end in a log — not row count. That's the number that actually predicts retention.

---

## What to do this week

1. Wire the barcode chain (`routers/foods.py`) — this alone fixes Pintola.
2. Run `ingest_openfoodfacts.py --countries india,united-states,united-kingdom`.
3. Run `seed_dishes.py`.
4. Add `pg_trgm` and the GIN index.
5. Instrument: log every search that returns zero results, and every barcode miss. **That log is your roadmap** — it tells you exactly which foods to add next, ranked by real demand, instead of guessing.

---

*Sources: [Open Food Facts data exports](https://world.openfoodfacts.org/data) · [Pintola High Protein Oats on OFF](https://in-hi.openfoodfacts.org/product/8906136651951/pintola-high-protein-oats-dark-chocolate) · [USDA FoodData Central](https://fdc.nal.usda.gov/download-datasets.html) · [OFF India 10k milestone](https://blog.openfoodfacts.org/en/news/open-food-facts-india-database-reaches-10k-product-milestone)*
