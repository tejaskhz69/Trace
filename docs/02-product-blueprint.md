# Trace — Product & Implementation Blueprint
*How to build the four features that actually matter, in build order*

---

## 0. Build order (why this order)

| # | Feature | Why here | Effort |
|---|---|---|---|
| 1 | **Photo scan with confidence ranges** | Acquisition engine. It's what goes in the ad creative. Without it you have no growth loop. | 2–3 wks |
| 2 | **Fast manual + barcode logging** | Retention floor. Photo scan alone loses users the first time it's wrong and they can't fix it fast. | 2 wks |
| 3 | **Adaptive TDEE engine** | Retention engine. This is what makes month 3 exist. | 2 wks |
| 4 | **Strength Adjudication Engine** | The moat. Needs 3–4 weeks of user data before it can say anything, so it ships third but is *marketed* first. | 3 wks |

Ship 1–3 as the MVP. Feature 4 is the brand — put it in the App Store screenshots from day one even while it's collecting its first month of data.

---

## 1. The Strength Adjudication Engine — *your only real moat*

**The promise:** every Sunday, one sentence that no other app can produce.

> *"Squat e1RM +4.2%, bench +1.8%, trend weight +0.4 kg over 3 weeks. You're gaining mostly lean mass — hold at 2,850 kcal."*

> *"Lifts flat for 2 weeks, trend weight +1.1 kg, protein averaging 0.9 g/kg. That gain isn't muscle. Cut 150 kcal and get protein to 1.6 g/kg."*

### 1.1 The inputs

```
Nutrition (per week):    mean kcal, mean protein g/kg, adherence %, logging days
Body (per week):         trend weight (EWMA), Δtrend weight
Training (per week):     per-lift estimated 1RM, total volume load, sessions, RPE
```

### 1.2 Estimated 1RM — pick one and be consistent

Use **Epley** for reps ≤ 10, and hard-cap at 12 reps (beyond that the formulas are noise):

```
e1RM = weight × (1 + reps / 30)
```

Per lift per week, take the **best single set's e1RM**, then apply a 3-week EWMA (α = 0.4) to kill session-to-session noise from sleep, caffeine, and bar-slip.

Also compute **volume load** = Σ(weight × reps) per muscle group, because a beginner's strength gain shows up in volume before it shows up in e1RM.

### 1.3 The adjudication rule

Classify the last 21 days into one of five states. Thresholds are deliberately conservative — a false "you're gaining fat" is far more damaging than a slow verdict.

| Δ trend weight/wk | Δ strength index | Verdict | Action |
|---|---|---|---|
| > +0.15% BW | > +0.5% | **Lean gain** | Hold. This is the good state. |
| > +0.35% BW | ≈ 0 (±0.5%) | **Fat gain** | −150 kcal/day, protein → 1.6 g/kg |
| ≈ 0 | > +1.0% | **Recomposition** | Hold. Rare and excellent. |
| < −0.15% BW | ≥ −0.5% | **Clean cut** | Hold. Muscle retained. |
| < −0.3% BW | < −1.5% | **Muscle loss risk** | +150 kcal/day, protein → 2.0 g/kg, flag training volume |

Where **strength index** = weighted mean of e1RM % change across the user's 3 most-frequent compound lifts (weights: most-frequent 0.5 / 0.3 / 0.2).

### 1.4 The guardrails that keep it honest

This is where most implementations would embarrass you. Enforce all five:

1. **Minimum data:** ≥ 8 workout sessions and ≥ 14 weight entries in the window, or the verdict is `INSUFFICIENT_DATA` — say so plainly, don't guess.
2. **Novice inflation:** in a user's first 8 weeks of lifting, strength gains are neurological, not muscular. Downweight the strength signal by 0.5 and say so: *"Early strength gains are mostly skill — I'll have a sharper read in a few weeks."*
3. **Program confound:** if the user changed their routine mid-window, e1RM changes are meaningless. Detect via exercise-set overlap < 60% and suppress.
4. **Logging adherence:** if food logging days < 5/week, the calorie side is fiction. Report the strength trend but refuse a calorie verdict.
5. **Never diagnose.** No body-fat-percentage claims, no "you have a slow metabolism." Report the two trends and the recommended nudge. Nothing more.

### 1.5 Why this is defensible

It requires **both data streams logged consistently by the same user**. Cal AI has no workouts. Hevy has no food. MacroFactor has neither photo scan nor lifts. Acquiring a user who logs both is expensive — which means once you have them, they're extremely hard to poach, because switching means abandoning the correlation history. **Retention is the moat, and this feature is the retention.**

---

## 2. Photo scan — build it as a *confidence-aware* pipeline

Your project already specifies a custom CNN. **Don't.** In 2026 a fine-tuned CNN on Food-101 will lose to a well-prompted vision model, cost you 4 months, and require an ML hire. Use Claude vision with a structured pipeline, and spend those 4 months on the correction dataset instead — that's the asset that eventually justifies a custom model, if ever.

### 2.1 The pipeline

```
capture → downscale 768px, WebP q80 → [on-device: barcode check first]
  → Claude Sonnet, structured tool-call output (strict JSON schema)
  → confidence gate: any item < 0.7 → ask ONE disambiguating question
  → user confirms/corrects → log
  → correction written to training_feedback table   ← this is the real asset
```

### 2.2 The three things that make it beat Cal AI

**(a) Return ranges, not fake precision.**
Every item returns `kcal_low / kcal_point / kcal_high`. The UI shows `240 kcal` with a subtle `±60`. Users trust it more, and it's *true*. Cal AI's single confident number is why people notice it drifts when they rescan.

**(b) Ask the one question that halves the error.**
The single biggest error source in photo estimation is invisible cooking fat — a tbsp of oil/ghee/butter is ~120 kcal and leaves no visual signature. SnapCalorie's own docs concede this. So ask:

> *"Dal tadka — 240 kcal (±60). How much ghee/oil?"*  `[None] [1 tsp] [1 tbsp] [Restaurant-style]`

One tap, and your estimate is more accurate than a depth sensor. Same pattern for dressings, sauces, and cooking method (grilled/fried/air-fried).

**(c) Deterministic re-scans.**
Cache by perceptual hash of the image. Same photo → same numbers, always. Temperature 0. This alone fixes the #1 complaint in Cal AI's reviews.

### 2.3 The prompt contract (sketch)

System prompt is **cached** (it's static, ~2k tokens, and you'll send it on every request — 1-hour cache makes it nearly free). Include:

- A cuisine-aware taxonomy with heavy Indian coverage: katori (150g), chapati (40g), idli (35g), dosa (85g), plus Western reference objects.
- **Reference-object scale calibration:** instruct the model to identify a known object (plate rim ~26cm, standard fork, phone) before estimating volume.
- Explicit instruction to enumerate *invisible* ingredients (cooking fat, sugar in sauces, cream) as a separate `hidden_ingredients` array with its own uncertainty.
- Strict output schema via tool-use so you never parse prose.

```json
{
  "items": [{
    "name": "Dal tadka",
    "name_local": "दाल तड़का",
    "portion": {"unit": "katori", "count": 1.0, "grams_est": 150, "grams_range": [120, 190]},
    "kcal": {"point": 240, "low": 180, "high": 320},
    "macros": {"protein_g": 9, "carbs_g": 26, "fat_g": 11},
    "confidence": 0.82,
    "clarifying_question": {
      "text": "How much ghee/oil?",
      "options": ["None", "1 tsp", "1 tbsp", "Restaurant-style"],
      "kcal_deltas": [-60, 0, 45, 110]
    }
  }],
  "hidden_ingredients": ["tempering oil", "cream garnish"],
  "overall_confidence": 0.82
}
```

### 2.4 Unit economics (do this math before you price)

Assumptions: 768px image ≈ 790 image tokens; ~2k cached system prompt (reads at 0.1×); ~400 output tokens.

| Model | Cost / scan | 3 scans/day for a month | 120 scans/mo (heavy user) |
|---|---|---|---|
| Haiku 4.5 ($1 / $5 per MTok) | ~$0.004 | ~$0.36 | ~$0.48 |
| Sonnet 5 ($2 / $10 per MTok) | ~$0.008 | ~$0.72 | ~$0.96 |

**Routing strategy:** Haiku first pass → escalate to Sonnet only when `overall_confidence < 0.75` or the plate has > 3 items. In practice ~25% escalation → blended ~$0.005/scan.

Against a $29.99/yr subscription (= $2.50/mo, ~$2.12 after Apple's 15% small-business rate), a heavy user at blended cost runs **~$0.60/mo in inference → ~72% gross margin**. Healthy. But **free-tier scans are a real cost**: budget 3/day cap, expect ~1/day actual on actives → ~$0.15/user/mo. At 100k free MAU that's $15k/mo. Model it, cap it, and monitor it from week one.

*(Verify current model pricing at [claude.com/pricing](https://claude.com/pricing) before you commit — it moves.)*

### 2.5 The correction loop is the actual product

Every time a user edits an AI estimate, write `(image_hash, ai_output, user_correction, timestamp)`. After 6 months you have a proprietary labeled dataset of exactly the dishes your users eat, which lets you: (a) few-shot the prompt with your own hardest cases, (b) build a re-ranking layer for your most-logged 500 dishes, (c) eventually justify fine-tuning. **This is the only thing in the app a competitor can't buy.** Build it in week one, not week forty.

---

## 3. Adaptive TDEE engine — the MacroFactor algorithm, done transparently

### 3.1 Trend weight (never use raw weight)

Exponentially weighted moving average, α = 0.1 (≈ 20-day half-life, close to what MacroFactor and Hacker's Diet use):

```python
trend[0] = weight[0]
trend[i] = trend[i-1] + alpha * (weight[i] - trend[i-1])
```

Missing days: carry forward, don't interpolate. Show the raw dots faintly and the trend line boldly — this single UI choice prevents most "I gained 2kg overnight" panic churn.

### 3.2 Expenditure estimation (the core loop)

Over a rolling window (14–21 days), reconstruct actual TDEE from energy balance rather than trusting a static formula:

```
TDEE_observed = mean_daily_intake − (Δtrend_weight_kg × 7700 kcal/kg) / days
```

Then blend with the prior (Mifflin–St Jeor or Cunningham × activity factor) using a Kalman-style weight that shifts toward observed data as evidence accumulates:

```python
w = min(0.85, days_of_data / 28)          # confidence in observed
TDEE = w * TDEE_observed + (1 - w) * TDEE_prior
```

**Guardrails:**
- Clamp `TDEE` to ±25% of the prior. If observed falls outside, it's a logging problem, not a metabolism problem — surface it as *"Your numbers don't add up — you may be under-logging on weekends"* rather than silently slashing targets.
- Require ≥ 5 logged days and ≥ 10 weigh-ins in the window before adapting at all.
- Discard the first 10 days entirely (glycogen/water shifts dominate).
- Cap weekly target changes at ±150 kcal so the plan never lurches.

### 3.3 Target setting

```
target = TDEE + goal_rate_kcal_delta

goal_rate: cut  → −0.5% to −1.0% BW/week   (floor: never below BMR × 1.1)
           gain → +0.25% to +0.5% BW/week
```

Protein floor: **1.6 g/kg** for cutting or gaining lifters (2.0 g/kg for aggressive cuts). This is not negotiable in the algorithm — it's what makes the strength verdict in §1 meaningful.

### 3.4 Ship the math, not a black box

MacroFactor's cult loyalty comes from showing its work. Copy that. Your weekly check-in screen shows:

```
Your data, last 14 days
  Avg intake        2,640 kcal    (logged 12/14 days)
  Trend weight      −0.32 kg
  → Your actual burn is about 2,820 kcal/day
     (was 2,750 — I've revised it up)

Recommendation: 2,570 kcal/day  (−70)
  Why: you're losing 0.24%/wk, target is 0.5%/wk

[Accept]  [Adjust]  [Keep current]  [Show the math]
```

That last button — a full breakdown of every number — costs you a day of work and buys you the "this app is honest" review sentiment that no ad budget can.

---

## 4. Free vs. Paid split

Cal AI's free tier is deliberately broken and its reviews reflect it. Hevy's free tier is genuinely great and it still converts fine. Follow Hevy.

| | **Free** | **Trace Pro** ($39.99/yr) |
|---|---|---|
| Photo scan | 3/day | Unlimited |
| Barcode + manual search | Unlimited | Unlimited |
| Workout logging | Unlimited | Unlimited |
| Basic calorie/macro dashboard | ✅ | ✅ |
| Weight + trend graph | ✅ | ✅ |
| **Adaptive calorie targets** | ❌ | ✅ |
| **Strength Adjudication (weekly verdict)** | 1 preview verdict | ✅ Weekly |
| Micronutrients, recipe builder, exports | ❌ | ✅ |
| Voice logging, meal templates | ❌ | ✅ |

**The principle:** free users get a great *tracker*. Paid users get a *coach*. Never paywall barcode scanning (MyFitnessPal did and it's their most-hated decision).

---

## 5. Fixing your animation jank (current priority)

Your prototype's lag is almost certainly one of these five. In diagnostic order:

1. **Work on the JS thread during transitions.** Any `setState` / list re-render fired mid-navigation will drop frames. Move every animation to **Reanimated worklets** (`useAnimatedStyle`, `withTiming`) so it runs on the UI thread and is immune to JS-thread blocking.
2. **The calorie ring re-rendering on every keystroke.** Animate SVG stroke-dashoffset via a Reanimated shared value, `React.memo` the ring, and drive it from a derived value — not from component state.
3. **Unoptimized images in the food list.** Use `expo-image` with `recyclingKey`, explicit `width`/`height`, and WebP thumbnails ≤ 200px. Never let a 4MB camera JPEG render in a list row.
4. **FlatList without `getItemLayout`.** Fixed-height rows + `getItemLayout` + `removeClippedSubviews` + `windowSize={5}`. Or use FlashList.
5. **Navigation animating while data loads.** Render the screen skeleton instantly, fetch after `InteractionManager.runAfterInteractions()`.

Add a CI check: run Reassure or a Maestro flow on a low-end Android profile and fail the build if the food-log flow drops below 55fps.

---

## 6. Data model additions (beyond your existing spec)

Your existing schema covers nutrition. Add the training + adjudication side:

```
Exercise:        id, name, muscle_group, equipment, is_compound, aliases[]
WorkoutSession:  id, user_id, started_at, ended_at, notes, routine_id?
SetLog:          id, session_id, exercise_id, set_index, weight_kg, reps,
                 rpe?, is_warmup, e1rm (computed)
StrengthSnapshot:id, user_id, week_start, exercise_id, best_e1rm,
                 e1rm_ewma, volume_load, session_count
BodyComposition: id, user_id, week_start, trend_weight, tdee_observed,
                 tdee_blended, confidence
Adjudication:    id, user_id, week_start, verdict (enum), strength_index_delta,
                 weight_delta_pct, protein_g_per_kg, recommendation_kcal,
                 explanation, guardrails_triggered[], user_accepted
TrainingFeedback:id, image_hash, ai_output_json, user_correction_json,
                 dish_label, created_at        ← the proprietary dataset
```

New endpoints:

```
POST /api/workouts/sessions            GET /api/workouts/sessions?from=&to=
POST /api/workouts/sessions/:id/sets   GET /api/strength/progress?exercise_id=&days=
GET  /api/adjudication/weekly          POST /api/adjudication/:id/accept
POST /api/foods/recognize              POST /api/foods/recognize/:id/correct
```

---

## 7. What to explicitly NOT build in v1

- ❌ Custom CNN for food recognition (4 months, loses to a good prompt)
- ❌ 1 lakh Indian food items at launch — ship **2,000 high-quality, verified** items covering 90% of logging volume. Data quality beats database size; MyFitnessPal's 20M items are mostly garbage and everyone knows it.
- ❌ Multi-language UI at launch (you chose global-first — English only, but keep `name_hi` / `name_bn` in the food schema so search works in Hinglish)
- ❌ Social feed, challenges, community
- ❌ Meal plans and recipes
- ❌ Wearable integrations beyond Apple Health / Health Connect read
