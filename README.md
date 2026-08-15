# Trace

**The first tracker that grades your diet by strength outcomes, not just the scale.**

Every calorie app answers "did the scale move?" None answers "did the *muscle* move?" Trace reads your meal logs and your workout logs together, and every Sunday tells you one thing no competitor can:

> *"Squat e1RM +4.2%, bench +1.8%, trend weight +0.4 kg over 3 weeks. You're gaining mostly lean mass — hold at 2,850 kcal."*

---

## Repo layout

```
trace/
├── docs/
│   ├── 01-competitor-teardown.md      Cal AI, MacroFactor, Hevy, SnapCalorie, MFP + positioning
│   ├── 02-product-blueprint.md        Feature specs, algorithms, build order, jank fixes
│   ├── 03-gtm-monetization.md         Pricing, paywall, CAC/LTV math, ASO, creative
│   ├── 04-fix-expo-railway-login.md   ← START HERE for the login bug
│   └── 05-food-database.md            ← START HERE for the Pintola/barcode bug
│
├── services/api/                      FastAPI + Postgres
│   ├── app/
│   │   ├── config.py                  Env handling (Railway DATABASE_URL + JWT_SECRET traps)
│   │   ├── security.py                bcrypt pre-hash, JWT issue/verify
│   │   ├── models.py                  SQLModel schema (nutrition + training + adjudication)
│   │   ├── routers/                   auth · foods · meals · recognition · weight · workouts · adjudication
│   │   ├── services/
│   │   │   ├── tdee.py                ★ Adaptive expenditure engine (pure, tested)
│   │   │   ├── adjudication.py        ★ Strength Adjudication Engine (pure, tested)
│   │   │   ├── vision.py              Claude food recognition w/ confidence ranges
│   │   │   └── food_sources.py        OFF + USDA resolution chain
│   │   └── scripts/
│   │       ├── ingest_openfoodfacts.py  Bulk import (~4M packaged products)
│   │       └── seed_dishes.py           ~100 cooked dishes across world cuisines
│   └── tests/test_engines.py          30 tests covering both engines
│
└── apps/mobile/src/lib/api.ts         Expo client (fixes the 5 classic login failures)
```

---

## Quick start

### Backend

```bash
cd services/api
cp .env.example .env

# Generate a JWT secret and paste it into .env — never let this rotate
python -c "import secrets; print(secrets.token_urlsafe(48))"

pip install -r requirements.txt
docker run -d --name trace-db -e POSTGRES_USER=trace -e POSTGRES_PASSWORD=trace \
  -e POSTGRES_DB=trace -p 5432:5432 postgres:16

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# → http://localhost:8000/docs
```

Seed the food catalogue:

```bash
python -m app.scripts.seed_dishes
python -m app.scripts.ingest_openfoodfacts --stream-url --countries india,united-states --limit 50000
```

Run the tests:

```bash
python -m pytest tests/ -v      # 30 passing
```

### Railway

1. New project → Deploy from GitHub → point at `services/api/Dockerfile`
2. Add the **Postgres** plugin
3. Set variables:
   ```
   DATABASE_URL = ${{Postgres.DATABASE_URL}}
   JWT_SECRET   = <the value you generated — set once, never change>
   ENV          = production
   GEMINI_API_KEY = <from aistudio.google.com/apikey>
   OFF_USER_AGENT = Trace/1.0 (you@yourdomain.com)
   ```
4. Healthcheck path: `/health`
5. Verify: `curl https://your-app.up.railway.app/healthz/db`

### Mobile

```bash
cd apps/mobile
cp .env.example .env    # set EXPO_PUBLIC_API_URL=https://your-app.up.railway.app
npx expo start --clear  # --clear is REQUIRED after any env change
```

---

## The two engines

**`services/tdee.py`** — reconstructs real expenditure from demonstrated energy balance instead of trusting a formula:

```
TDEE_observed = mean_intake − (Δtrend_weight_kg × 7700) / days
TDEE          = w·TDEE_observed + (1−w)·TDEE_prior,   w = min(0.85, days/28 × adherence)
```

Guardrails: 10-day washout, ±25% clamp on the prior (out-of-range = under-logging, flagged not believed), ±150 kcal/week max change, BMR×1.1 floor.

**`services/adjudication.py`** — classifies 21 days into five states from trend weight × strength index:

| Δ weight/wk | Δ strength | Verdict | Action |
|---|---|---|---|
| >+0.15% BW | >+0.5% | Lean gain | Hold |
| >+0.35% BW | ~0 | Fat gain | −150 kcal, protein → 1.6 g/kg |
| ~0 | >+1.0% | Recomposition | Hold |
| <−0.15% BW | ≥−0.5% | Clean cut | Hold |
| <−0.3% BW | <−1.5% | Muscle loss risk | +150 kcal, protein → 2.0 g/kg |

Five guardrails, all tested: minimum data, novice discount, program-change detection, logging-adherence gate, and a noise band that refuses to guess. **Returning `INSUFFICIENT_DATA` is always better than a confident wrong verdict.**

---

## Design decisions worth knowing

- **No custom CNN.** Claude vision with a structured tool-call schema beats a fine-tuned ResNet on Food-101, costs 4 fewer months, and handles mixed plates. Spend that time on the correction dataset instead.
- **Confidence ranges, not fake precision.** Every estimate returns low/point/high plus one clarifying question about invisible cooking fat — the largest single error source in photo estimation.
- **Deterministic re-scans.** Perceptual-hash cache + temperature 0, so the same photo always returns the same number. This fixes the #1 complaint about every photo tracker.
- **Nutrition is snapshotted at log time.** Correcting a food's data upstream must never silently rewrite a user's history.
- **`recognition_feedback` is the most valuable table.** Every user correction is a labelled example of exactly the food your users eat. It's the only asset a competitor can't buy.

---

## Attribution

Food data from [Open Food Facts](https://world.openfoodfacts.org) (ODbL) and [USDA FoodData Central](https://fdc.nal.usda.gov) (public domain). Indian composition values cross-checked against IFCT 2017 (ICMR-NIN).
