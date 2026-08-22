# Paid nutrition APIs — what's worth buying, and what isn't

Short version: **most of what these vendors sell, Trace already has for free
and often better.** One thing they sell has no free equivalent and is worth
paying for. This document says which is which, because the difference is a
recurring bill.

The integration is built and tested. It is switched off until a key exists,
and that is a fully supported state — the app serves 273,000 foods without it.

---

## What we already have, at zero cost

| Source | Rows | Where it wins |
|---|---:|---|
| Open Food Facts | 260,357 | Packaged goods, barcodes, **non-US products**, EU/India coverage |
| USDA FoodData Central | 12,612 | Raw ingredients, lab-measured, public domain |
| Curated (Indian + world regional) | 347 | Puttu, pesarattu, litti chokha — dishes no incumbent carries |
| **Total** | **273,316** | |

That already includes ~180 supermarket private labels: Kirkland 2,545 ·
Great Value 5,407 · Wegmans 3,284 · Hacendado 7,137 · Tesco 7,440.

For reference, LiftBite does not own a food database at all — it licenses
FatSecret's. Trace owns its data outright, which is a durable advantage
neither a subscription nor a competitor can take away.

---

## Vendor by vendor

### Nutritionix — **worth it, for one feature**

~$50/mo business tier; free developer tier is ~200 calls/day, which is plenty
to verify the integration.

**Not worth paying for:** barcodes. Open Food Facts is free and genuinely
better outside the US.

**Worth paying for:**

1. **Natural-language parsing.** *"two rotis and a bowl of dal tadka"* →
   portioned foods with quantities resolved. This is genuinely hard, has no
   free equivalent, and is the same shift the voice workout logger makes on
   the training side: describe what you did instead of filling in a form.
2. **US restaurant chains.** ~1,000 chains with per-item nutrition. No free
   dataset answers *"what did I eat at Chipotle"*.

**This is the one integration that is built.** `POST /api/foods/parse`.

### Nutrola, Bonhappetee, MealStack — **hold off**

Their headline numbers ("900K foods", "17K Indian foods") are largely
**repackaged public data**: USDA, IFCT 2017, and national databases. We
already ingest USDA directly, and the curated Indian set is built from IFCT.
Paying for a wrapper around data we already hold is the wrong trade.

Bonhappetee's regional Indian coverage is the one claim that might justify a
look, but their published API surface is thin enough that I would want a trial
key and a real accuracy comparison against our existing dishes before
committing to a subscription. **I have not verified their API shape**, so I
did not build against it — writing an adapter to a contract I guessed at would
produce something that looks finished and silently returns zeros.

### Free databases worth ingesting before paying anyone

These are the same sources the paid vendors resell, available directly:

- **CIQUAL** (ANSES, France) — ~3,200 foods, excellent French coverage
- **CoFID / McCance & Widdowson** (UK) — the UK reference dataset
- **FRIDA** (Denmark), **Canadian Nutrient File**, **AUSNUT** (Australia)
- **The full Open Food Facts dump** — ~4M products. We have sampled it by
  brand tag; `ingest_openfoodfacts.py --stream-url` takes the whole thing.

That last one is the biggest single win available and costs nothing but hours.

---

## How the integration is built, and why that shape

The adapter is the easy part. These three rules are what keep a $50 line item
from becoming an unbounded one:

**1. Pay once per product, ever.** Every paid response is written into our own
`food_items` table before it is returned. The second person to look up that
food hits Postgres. A few thousand products cover most of what most people
eat, so this is the difference between a fixed cost and one that scales with
traffic.

**2. Never the first resort.** The lookup order is local DB → Open Food Facts
→ USDA → paid. By the time a call reaches the paid tier, three free sources
have already missed — which is exactly the long tail worth paying for. Search
only escalates when fewer than 5 free results came back.

**3. A hard daily ceiling.** `PAID_LOOKUPS_PER_DAY` (default 500) is a
*budget*, not a rate limit. When it is spent, the tier reports a miss rather
than spending more, and the user sees what they would have seen anyway.

> ⚠️ The counter is **in memory, per container**. With N replicas the true
> ceiling is N × the limit. Move it to Redis before scaling out.

Paid rows are validated by `nutrition_validator` like everything else. Paying
for a row is not evidence that it is correct.

---

## Turning it on

```bash
# services/api/.env
NUTRITIONIX_APP_ID=your_app_id
NUTRITIONIX_APP_KEY=your_app_key
PAID_LOOKUPS_PER_DAY=500
```

Then verify against the live API in one command:

```bash
cd services/api
python -m app.scripts.probe_paid
python -m app.scripts.probe_paid --query "two rotis and dal" --raw
```

The probe costs ~3 real calls and separates the failure modes a metered
integration otherwise hides: a bad key, an exhausted budget, a renamed
response field, and a genuine miss all look identical at the call site.

`GET /api/foods/sources/status` reports the same thing at runtime.

---

## The one correctness trap

**Nutritionix reports per SERVING. We store per 100 g.**

Storing its numbers unscaled is wrong by whatever the serving happened to
weigh — a 30 g serving under-reports by 3.3×, silently, with no symptom
except that someone's calorie history is wrong. `to_resolved()` scales by
`serving_weight_grams` and **refuses the row entirely** when that field is
missing, because assuming 100 g would be a fabrication.

There are tests for exactly this in `tests/test_paid_sources.py`.

---

## Recommendation

1. **Now, free:** run the full OFF dump import. Biggest coverage win available.
2. **Now, free:** ingest CIQUAL and CoFID for European coverage.
3. **When there's budget:** Nutritionix, for natural-language logging and US
   restaurant chains — not for barcodes.
4. **Not yet:** Nutrola / Bonhappetee / MealStack. Get trial keys and measure
   them against what we already hold before subscribing to any of them.
