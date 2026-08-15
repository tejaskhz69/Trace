# The fitness coach + Apple Health integration

---

## The trap you need to know about first

You asked for Apple Health to pull steps and calories burned. Before any of that gets wired up, there's a design decision that determines whether the whole thing helps or actively breaks your app:

> **Never add exercise calories to the user's target.**

This isn't a style preference. It's structural. Your TDEE engine estimates expenditure like this:

```
TDEE_observed = mean_intake − (Δtrend_weight_kg × 7700) / days
```

That number **already contains** every calorie the user burned in the gym, on their walk, and fidgeting at their desk — because all of it showed up in the weight change. Adding HealthKit's `activeEnergyBurned` on top counts the same energy twice. A user who burns 500 kcal in a session and "eats it back" is now running a 500 kcal surplus against a target that already assumed the session happened.

It's worse than double-counting, because the number you'd be doubling is itself inflated: consumer wearables overestimate active energy substantially on non-steady-state activity. You'd be adding a wrong number to a correct one.

This is exactly what MyFitnessPal does, and it's why people eat back phantom calories and stall. MacroFactor deliberately doesn't — same reasoning.

**So Trace pulls the data and never touches the target with it.**

---

## What health data is actually for

Three things, and the first one is a genuinely new feature:

### 1. NEAT drift — the headline

When someone cuts, their non-exercise activity falls without them noticing. They take the lift. They fidget less. They walk slower. This is well-documented and it's the most common reason a diet stalls.

Your adaptive TDEE engine detects the **result** — expenditure fell — about three weeks later. Step count shows the **cause** immediately, and crucially it offers a fix that isn't "eat less":

> *"Your steps are down from about 9,400 to 6,100 a day — roughly 132 kcal/day less burn. That almost certainly explains the stall. Get back to ~9,400 before we cut your calories again. It's the same energy, and it's far easier to stick to."*

No competitor says this. It's the fitness-side equivalent of the strength verdict: it names a cause instead of a symptom, and it hands the user the cheaper lever.

Implemented in `services/activity.py::analyse_neat`. Compares against the **user's own baseline**, never a population norm — "10,000 steps" is a 1960s pedometer marketing figure. A 5,000-step person who drops to 3,000 is drifting just as much as a 12,000-step person who drops to 8,000.

### 2. Faster convergence

Activity stability is a **covariate on confidence**, not on the estimate. Someone whose steps and training are steady produces a clean energy-balance signal, so we can trust the observed TDEE sooner. Someone who did a 20 km hike one weekend and nothing the next needs a longer window before we act on their numbers.

`activity_stability()` returns 0–1 from the coefficient of variation of daily steps, and it multiplies the confidence weight in the TDEE blend. This is the legitimate way to use activity data in the loop: **it changes how much we trust the estimate, never the estimate itself.**

### 3. Readiness

Sleep debt predicts a bad session before it happens. A strength drop after two nights of 5 hours is not a nutrition signal, and the adjudication engine must not treat it as one. `analyse_sleep()` flags it and the coach says so explicitly: *"This is not a nutrition problem, so don't change your calories over it."*

### Bonus: the honesty check

`reconcile_energy()` compares what the watch claims against what the scale proves, and shows the user the gap:

> *"Your watch says you burn about 3,000 kcal/day. Your actual weight change says 2,400. Wearables routinely overestimate by 20–40%, which is exactly why I use your scale rather than your watch to set targets."*

That single card does more to build trust in the algorithm than any amount of onboarding copy.

---

## The coach

`services/coach.py`. Five design rules:

**One recommendation, not a dashboard.** Six observations is a report. A coach says one thing. Candidate insights are ranked and the top one surfaces; the rest sit underneath.

**Always name the cause.** "You're stalled" is useless. "You're stalled and your steps fell 3,300/day" is actionable.

**Diagnose from the cheapest fixable lever first.** The intervention order is:

```
sleep → activity → adherence → protein → calories
```

Cutting calories is the **last** lever, not the first. It has the worst adherence cost and it's usually treating a symptom. There's a test asserting exactly this: a stalled user with collapsed step count gets told to walk, not to eat less.

**Never invent certainty.** Every insight carries its evidence and a confidence score. `data_completeness` tells the user how much we actually had to work with.

**No medical claims.** Trends and training/nutrition adjustments only. No diagnoses, no conditions, no symptom interpretation.

### Where Claude fits

The **deterministic engine decides**; Claude only **rewrites**. `narration_prompt()` builds the input and the system prompt forbids changing any number, inventing any recommendation, or adding medical claims.

That separation is deliberate: the recommendation must be reproducible and testable, and a language model must never be able to invent a calorie change. It's also why the rules are pure functions with 27 tests — if the narration layer fails, you degrade to the structured insight, which is still correct.

---

## Weight logging on workouts

You asked for a weigh-in prompt every time someone trains. Two refinements make it work rather than annoy:

**Post-workout weight is a bad measurement.** You're down 0.5–1.5 kg of sweat. Prompting then trains people to log noise, which corrupts the trend line that everything else depends on. So a completed workout marks the user as *prompt tomorrow morning*:

> *"Nice session. Weigh in first thing tomorrow — right after a workout you're down a kilo of sweat, so it wouldn't be a real reading."*

**Back off for people who are already consistent.** Someone weighing in 13 days out of 14 doesn't need reminding; nagging them is how you lose notification permission. `should_prompt_weigh_in()` handles both.

Also: `bodyMass` is a **read** permission, so a smart scale that writes to Apple Health flows into Trace automatically with no user action at all.

---

## What shipped

```
services/api/app/
├── services/
│   ├── activity.py      NEAT drift · stability · sleep · reconciliation · weigh-in prompts
│   └── coach.py         7 rules · urgency+lever ranking · narration prompt
├── routers/health.py    POST /sync · GET /sync/state · GET /coach · GET /activity/summary
└── models.py            ActivityDay · SleepNight · ExternalWorkout · HealthSyncState · CoachBriefingRecord

apps/mobile/src/lib/health.ts   Unified HealthKit + Health Connect adapter
tests/test_coach.py             27 tests
```

**32 endpoints, 84 backend tests, 0 mobile type errors.**

---

## Setup — the part that will trip you up

**HealthKit does not work in Expo Go.** It's native code. You need a development build:

```bash
npx expo install @kingstinct/react-native-healthkit react-native-nitro-modules
npx expo install react-native-health-connect      # Android
npx expo run:ios                                   # or eas build --profile development
```

The config plugin and all permission strings are already in `app.json`, including the HealthKit entitlement and the nine Android Health Connect permissions.

Two things worth knowing:

- **iOS never tells you whether READ permission was granted.** That's deliberate on Apple's part — a "denied" signal would itself leak health information. So never branch on a granted boolean for reads. Run the query; empty results mean *either* no permission *or* no data, and you genuinely cannot distinguish them.
- **The native modules are imported lazily**, inside each function. Importing at module scope crashes the whole app on launch in any build where the module is missing — a miserable way to discover you forgot to rebuild.

**Sync is push-only.** HealthKit has no server API; all reads happen on-device and the phone pushes deltas. Every upsert is keyed on a natural key (`user+day`, `user+external_id`) because HealthKit re-reports the same workout when a user edits it, changes source priority, or restores a backup. Partial re-syncs use `COALESCE` so they never wipe a field the client didn't send.

Recommended first backfill: **90 days**. Enough for a NEAT baseline and a full adaptive-TDEE window, without a multi-year first sync.

---

## What I'd build next

1. **Background delivery** — `background: true` in the plugin config plus `enableBackgroundDelivery`, so steps sync without the user opening the app. This is what makes NEAT drift detection feel automatic rather than something they have to remember.
2. **The coach card in the UI** — the backend returns it; nothing renders it yet.
3. **Readiness-adjusted training suggestions** — you have sleep and HRV. "You slept 5.2h and your HRV is down 18% — today's a good day to hit your sets at RPE 7 instead of 9."
4. **Cardio into the strength engine** — right now external workouts are context only. A rower's or cyclist's progression is real progress and the adjudication engine can't see it.
5. **Guard the double-counting rule with a test at the API boundary**, so a future contributor can't quietly add `active_energy_kcal` to a target. Right now the rule is enforced by comments and design; it should be enforced by CI.
