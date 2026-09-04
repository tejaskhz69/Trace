# Reference matrix

Written **before** any prototype code was changed, per the brief.

## Sources actually inspected

| Source | Status | How |
|---|---|---|
| `prototype/workout-trainer/` (7 files) | inspected | read on disk |
| its `README.md` | inspected | read on disk |
| its `FEATURE_GAP_REPORT.md` | inspected | read on disk |
| `WORKOUT_DATABASE_UPGRADE_PLAN.md` (585 lines) | inspected | read on disk, **not modified** |
| `services/api/WORKOUT_SCHEMA_DESIGN.md` (1,500 lines) | inspected | read on disk, **not modified** |
| **Trace Flight Deck** artifact | **inspected** | fetched from `claude.ai/code/artifact/2ae4dc00-dd1b-4901-904d-df317ce1099a`, 1.57 MB, text extracted — 749 visible lines, 1 `h1`, 3 `h2`, 2 `h3`, 8 `h4` |
| vxstrainer.ai screenshots | **inspected** | ten images pasted inline in the conversation. **Not files on disk** — cannot be cited by path |

### Flight Deck — what it actually contains

Five tabs: **Home · Nutrition · Trainer · Progress · Profile**, settings behind the avatar.
Eleven screens, quoted headings:

1. **Home** — "Remaining today / ON TRACK / 600 KCAL LEFT", macro trio, "Worth watching" micronutrients (sodium over-limit), "Activity today / ABOVE USUAL" with Steps, Sleep, Trained.
2. **Nutrition** — four entry tiles (AI scan, Barcode, Search, My foods), "Today · 3 meals", "Recent / TAP TO REPEAT" with a `verified` tag.
3. **Scan review** — items with `±` bands, the coconut-oil question (Barely any / Home style / Restaurant), "ESTIMATE 381 / 444 kcal / 507".
4. **AI Trainer (coach)** — "Priority lever / SLEEP", Confidence 78%, Data 91%, conversation, "Also worth knowing".
5. **Trainer — gym catalogue** — muscle groups with counts, rows carrying equipment · compound, e1RM and a direction delta, plus "Today · Incline DB Press" set list.
6. **Exercise detail** — muscle chips, **three numbered form cues**, "Estimated 1RM ▲ 4.2% VS LAST WK / 41.8 kg", 6-week line, "Today / SET 3 OF 4", "Log set".
7. **Activities** — "What did you do? / 32 SPORTS" grid, Duration / Avg HR / Est. burn, "Arrived on their own / STRAVA" list, deduplication sentence.
8. **Ride detail** — Distance / Moving / Climb, "Energy / TWO ESTIMATES" (from power 842 vs Strava est. 831), **"Where this goes"** — Activity list *Added*, Weekly training load *Added*, **Today's calorie target *Unchanged***. Discard / Keep ride.
9. **Progress** — "Is it working? / ▲ MOSTLY MUSCLE / +3.1 kg", lean-vs-fat split, weight chart with trend + target range + faint daily dots, "Strength / ALL RISING".
10. **Strength over time** — hero e1RM, "This week vs last" grid (Est. 1RM, Volume, Sets, Reps, Top set, Avg reps), "Week by week", "Recent sessions".
11. **Sleep and burn** — "Sleep / 7H 02M AVG / 7H TARGET", seven day bars, a short-night callout, and **"Where your burn comes from"** — Just being alive 1,680 · Walking around 640 · Training 300 · Digesting food 120.
12. **Profile** — connected sources (Apple Health, Strava, Garmin, Health Connect), goal, units, surface, accent, and a weekly check-in that shows its working then asks: ACCEPT / NOT THIS WEEK.

**What the Flight Deck does NOT contain:** no workout *programming* (it is catalogue + logging), no readiness or recovery check-in, no plateau detection, no programme setup, no manual sleep entry. Those come only from the plan documents and the screenshots.

---

## The matrix

**Y** present · **N** absent · **P** partial.
"Production support" = what `apps/mobile` + `services/api` can do **today**.

### A · Home and navigation

| Reference feature | vxstrainer | Flight Deck | Existing prototype | Production support | Prototype action |
|---|---|---|---|---|---|
| Greeting + date masthead | Y | Y | Y | Y | Keep |
| Split TRAIN / EAT summary cards | Y | N | N | N | **Add** — Trace wording |
| Remaining-calories hero + macro trio | N | Y | N | Y `/health/coach` | **Add**, read-only |
| "Worth watching" micronutrient over-limit | N | Y | N | Y `micronutrients.py` | **Add** one row |
| Activity today (steps · sleep · trained) | N | Y | P sleep only | Y `activity_days` | **Expand** |
| Weekly consistency strip | N | P | P sparkbar | Y `/health/consistency` | **Expand** to home |
| Plateau / fatigue notice on home | N | N | N | N | **Add** — advisory only |
| Quick-action row | Y | P tiles | N | n/a | **Add** — 8 actions |
| Bottom tab navigation | Y | Y 5 tabs | N — flat tab strip | Y 5 tabs | **Add** — see adaptation note |
| Settings behind avatar | N | Y | N | Y | **Adopt** |

### B · Training

| Reference feature | vxstrainer | Flight Deck | Existing prototype | Production support | Prototype action |
|---|---|---|---|---|---|
| Session header with `n/m exercises · min/min` | Y | N | P counts only | N | **Adopt** |
| Ordered exercise list | Y | N | Y | N — needs `f6a9c2e47d85` | Keep |
| Sets / rep range / target RIR | Y RPE | N | Y | N same | Keep |
| Rest timer per exercise | Y "REST 2:00" | N | P shown, static | N | **Add** countdown display |
| Inline set logger on the card | Y | P "Log set" | Y | P free logging exists | Keep |
| "How many more reps?" chip row | Y | N | Y | Y `set_logs.rir` | Keep |
| Warm-up marked "not a working set" | Y | N | P text only | N | **Expand** to rows |
| SWITCH / SKIP per exercise | Y | N | Y | N — `PATCH` exists, unapplied | Keep |
| ADD EXERCISE mid-session | Y | N | N | N | **Add** |
| Session pause / resume | N | N | N | N | **Add** |
| Completion summary | N | P | N | Y `/sessions/{id}/summary` | **Add** |
| Coach prompt bubble | Y | Y chat | N | Y `chat.py`, `coach.py` | **Add** static prompt only |
| Off-programme muscle picker | Y | N | N | N | **Add** as independent-workout entry |
| Exercise demo control | Y | N | N | N | **Add** — original shapes only |
| Three numbered form cues | N | **Y** | P bulleted | N | **Adopt** numbering |
| e1RM hero + multi-week line | N | **Y** | N | Y `/strength/progress` | **Add** to exercise detail |
| Easier / harder variation | N | N | N | N | **Add** |

### C · Recovery and sleep

| Reference feature | vxstrainer | Flight Deck | Existing prototype | Production support | Prototype action |
|---|---|---|---|---|---|
| Sleep average vs target | N | **Y** | N | Y `sleep_nights` | **Add** |
| Seven-day sleep bars | N | **Y** | N | Y | **Add** |
| Short-night explanatory callout | N | **Y** | N | N | **Adopt** |
| Bedtime / wake summary | N | N | N | Y columns exist | **Add** |
| Energy / soreness / stress inputs | N | N | Y | N — table only | Keep |
| Readiness score + band | N | N | Y | N | Keep, **expand** to trend |
| Recommended training intensity | N | N | P sentence | N | **Expand** |
| "Why this recommendation" breakdown | N | P burn breakdown | N | N | **Add** — per-factor contributions |
| Manual sleep entry | N | N | N | **N** — `source` defaults to `healthkit` | **Add**, clearly prototype-only |
| Source label per record | N | Y "Strava"/"Apple Watch" | N | Y `HealthSource` | **Adopt** — required by brief §11 |
| Edit / delete a record | N | Y "Discard" | N | P | **Add** |
| Privacy explanation | N | Y disconnect note | P one line | n/a | **Expand** |

### D · Cardio and cycling

| Reference feature | vxstrainer | Flight Deck | Existing prototype | Production support | Prototype action |
|---|---|---|---|---|---|
| Indoor / outdoor selector | N | N | Y | Y `sports.py` | Keep |
| Distance / moving / climb trio | N | **Y** | Y | Y `ride_tracks` | Keep |
| Average speed | N | P | N | Y derivable | **Add** |
| Two energy estimates, measured marked | N | **Y** | N | P | **Add** |
| Route preview, outdoor only | N | Y | Y drawn | Y `GET /{id}/track` | Keep |
| Indoor shows **no** geographic route | N | n/a | Y | n/a | Keep — enforced by test |
| Recent rides list | N | **Y** | N | Y | **Add** |
| Weekly cardio load | N | Y | N | Y `activity_days` | **Add** |
| **"Where this goes" — target Unchanged** | N | **Y** | P one line | Y `activity.py` | **Adopt verbatim in Trace's words** — this is non-negotiable #1 |
| Deduplication note | N | **Y** | N | Y `external_workouts` | **Add** |
| Start / pause / resume / finish states | N | N | N | N | **Add** as state display |
| Delete activity | N | Y "Discard" | N | P | **Add** |
| Location privacy note | N | P | Y | n/a | Keep |
| Effect on lower-body training | N | N | Y | N — deferred §1 | Keep |

### E · Nutrition

| Reference feature | vxstrainer | Flight Deck | Existing prototype | Production support | Prototype action |
|---|---|---|---|---|---|
| Calorie / macro overview | Y | **Y** | N | Y | **Add**, read-only |
| Food log with running item list | Y | **Y** | N | Y | **Add** |
| Meal grouping with totals | Y | **Y** | N | Y | **Add** |
| Scan-food entry point | Y "PHOTO" | **Y** "AI scan" | N | **Y** shipped | **Add** as a link only |
| `±` band on estimates | N | **Y** | N | **Y** shipped | **Add** |
| `verified` vs estimated tag | N | **Y** | N | **Y** `verification_tier` | **Add** |
| Source attribution line | N | P | N | **Y** shipped this session | **Add** |
| Meal plan with per-meal timing | Y | N | N | N | **Placeholder only** |
| "regenerate to adjust" over-target | Y | N | N | N | Not built — plan is out of scope |
| Cardio calories **not** added to target | n/a | **Y** | P | **Y** invariant #1 | **Adopt** |

### F · Progress and plateau

| Reference feature | vxstrainer | Flight Deck | Existing prototype | Production support | Prototype action |
|---|---|---|---|---|---|
| Weekly consistency | N | Y | Y | Y | Keep |
| Muscle-group volume vs target | N | N | Y | Y `volume.py` | Keep |
| Per-exercise progression with status tag | **Y** | Y | Y | Y | Keep |
| e1RM trend line | N | **Y** | N | Y `strength.py` | **Add** |
| This-week-vs-last grid | N | **Y** | N | Y | **Add** |
| Sets / reps / load history | N | **Y** | N | Y `set_logs` | **Add** |
| Personal records | N | P | N | P derivable | **Add** |
| Eight-week trend | N | Y 6–10 wk | Y | Y | Keep |
| Plateau evidence table | N | N | Y | **N** — `plateau.py` absent | Keep |
| Accept / postpone / dismiss | N | P weekly check-in | Y | N | Keep |
| Fatigue trend | N | N | N | N | **Add** |
| Sleep / cardio overlay on progress | N | P | N | P | **Add** as toggles |
| Programme adherence | N | N | N | N | **Add** |
| "Is it working?" muscle-vs-fat split | N | **Y** | N | **Y** `adjudication.py` | **Add** — the product claim |

### G · Programme and goal setup

| Reference feature | vxstrainer | Flight Deck | Existing prototype | Production support | Prototype action |
|---|---|---|---|---|---|
| Goal selection | Y | Y | N | Y `users.goal_type` | **Add** |
| Target weight + rate → budget + finish date | **Y** | P | N | Y `tdee.py`, `week_budget.py` | **Add** |
| Training phase | N | N | N | Y `program_type` | **Add** |
| Days per week / available days | N | N | N | Y `training_profiles` decl. | **Add** |
| Time per session | Y implied | N | Y chips | Y decl. | Keep |
| Equipment | Y | N | P static | Y decl. | **Add** picker |
| Preferred / disliked exercises | N | N | N | Y `disliked_exercise_ids` | **Add** |
| Cardio frequency | N | N | N | Y `cardio_sessions_per_week` | **Add** |
| Sleep / recovery opt-in | N | N | N | N | **Add** — skippable |
| AI opt-in | N | N | N | Y `ai_enabled` decl. | **Add** — skippable |
| Programme preview + confirm | N | N | N | Y `POST /programmes` | **Add** |

### H · AI

| Reference feature | vxstrainer | Flight Deck | Existing prototype | Production support | Prototype action |
|---|---|---|---|---|---|
| Structured generated session | N | N | Y | N | Keep |
| Mock ids + validation failure | N | N | Y | N | Keep |
| Confirm / edit / reject | N | P ACCEPT / NOT THIS WEEK | Y | N | Keep |
| Confidence + data-coverage meters | N | **Y** 78% / 91% | N | N | **Add** |
| Priority-lever framing | N | **Y** | N | Y `coach.py` ladder | **Adopt** on home |

---

## Navigation adaptation

The two references disagree, and neither matches the brief's seven-item list.

| | Structure |
|---|---|
| vxstrainer screenshots | A single trainer surface; navigation not fully visible |
| Flight Deck | **5 tabs** — Home · Nutrition · Trainer · Progress · Profile, settings behind the avatar |
| Trace production | **5 tabs** — index · log · train · progress · profile |
| Brief | 7 sections — Home · Train · Recover · Cardio · Eat · Progress · Profile |

**Adaptation, and why.** Seven bottom-tab targets is past the point where a thumb can hit them reliably, and both references independently landed on five. The prototype uses **six bottom tabs — Home · Train · Recover · Cardio · Eat · Progress — with Profile and programme setup behind the masthead avatar**, exactly the pattern the Flight Deck uses for settings.

Cardio stays its own tab rather than folding into Train, because the brief requires the prototype to make the workout/cardio boundary legible, and a shared tab is what makes people log a ride as a workout.

Every screen also carries an explicit **kind badge** — `PROGRAMMING`, `LOGGING`, `RECOVERY`, `CARDIO`, `NUTRITION`, `PROGRESS`, `SETUP` — so the six categories the brief asks to distinguish are readable on the screen itself, not just inferable from which tab you came in on.

For production the recommendation is different: keep the existing five tabs and reach Recover and Cardio from Train, since production already ships five and changing the tab bar is the most disruptive change available for the least user benefit.

## What is deliberately not copied

The crimson accent · any wordmark or logo · the third-party coach's product name · "Powered by Strava" and any partner lockup · the 32-sport grid as an asset · verbatim marketing sentences from either source · the streak-and-leaderboard framing · any image or illustration.

Ideas are reimplemented in Trace's own tokens, vocabulary and sentences. Where the Flight Deck's *reasoning* is adopted — most importantly that a ride's energy must leave today's calorie target **unchanged** — it is adopted because it is already project non-negotiable #1, and it is written in new words.
