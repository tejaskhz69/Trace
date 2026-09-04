# Feature gap report

What the prototype shows, against what the real application can do **today**.

Every "exists" claim was checked against the working tree on 2026-08-25, not
inferred from the design documents. **No database connection was made** — the
migration state quoted here is the one established earlier in this session and
is restated, not re-queried.

---

## The three facts that shape everything

**1 · The programming backend is written but unreachable.**
`services/api/app/routers/programming.py` exposes eleven endpoints
(`training-profile` ×3, `programmes` ×4, `programmes/{id}/days`,
`planned-sessions` ×2, `prescribed-exercises` PATCH). `app/services/programming.py`
holds the pure logic. All nine tables are declared in `models.py`:
`ExerciseAttributes`, `ExerciseSubstitution`, `TrainingProfile`,
`TrainingProgramme`, `ProgrammeDay`, `PlannedSession`, `PrescribedExercise`,
`ReadinessCheckin`, `AIGeneration`.

**2 · The migration has not been applied.** `f6a9c2e47d85` sits on disk with
`down_revision = "e4f7b0d25c63"`, which is where the database still is. None of
the nine tables exist in `trace`, so every programming endpoint would fail
against the real database today.

**3 · Nothing in the mobile app calls any of it.** Searching `apps/mobile` for
`planned-session`, `training-profile` and `programmes` returns **zero matches**.

**The gap is overwhelmingly mobile, not backend.** And one correction worth
repeating: **sleep and cycling are not missing.** `SleepNight` and `RideTrack`
exist, `routers/rides.py` serves the track endpoints, `routers/health.py`
serves eleven more, and `src/lib/health.ts` and `useHealth.ts` exist on the
client. The gap in those two areas is manual entry and presentation.

---

## Per-feature matrix

**Legend** — Prototype: **B** built · **P** partial · **M** marked placeholder.
The rest: **Y** yes · **N** no · **P** partial.
"Safe next?" means: can it be implemented without a decision nobody has made yet.

### A · Home and navigation

| Feature | Prototype | Production | Backend gap | DB gap | Mobile gap | Permissions | Privacy/legal | Phase | Safe next? |
|---|---|---|---|---|---|---|---|---|---|
| Greeting, goal, phase | B | Y | — | — | — | — | — | shipped | — |
| Train / Eat split | B | N | — | — | new card | — | — | 2 | **Yes** |
| Programme card + adherence | B | N | adherence not computed | needs migration | new card | — | — | 1 | after migration |
| Readiness summary | B | N | no endpoint | table unapplied | new card | — | **Yes** §10.8 | 3 | **No** |
| Sleep summary | B | P stored | — | — | new card | **Yes** sleep scope | **Yes** health data | 3 | **No** |
| Cardio summary | B | P stored | — | — | new card | P Strava OAuth | P third-party terms | 4 | Yes, read-only |
| Nutrition summary | B read-only | **Y** | — | — | reuse existing | — | — | 2 | **Yes** |
| Weekly consistency | B | Y `/health/consistency` | — | — | new card | — | — | 2 | **Yes** |
| Muscle-vs-fat headline | B | **Y** `adjudication.py` | — | — | new card | — | — | 2 | **Yes** |
| Plateau / fatigue notice | B | N | `plateau.py` absent | — | new card | — | P level-4 wording | 4 | **No** |
| Eight quick actions | B | N | — | — | new | — | — | 2 | **Yes** |
| Six-tab navigation | B | Y 5 tabs | — | — | tab-bar change | — | — | — | see note |
| Settings behind avatar | B | Y | — | — | — | — | — | shipped | — |

> **Navigation note.** The prototype uses six tabs to make the categories
> legible for review. **Production should keep its five** and reach Recover and
> Cardio from Train — changing the tab bar is the most disruptive change
> available for the least user benefit.

### B · Training

| Feature | Prototype | Production | Backend gap | DB gap | Mobile gap | Permissions | Privacy/legal | Phase | Safe next? |
|---|---|---|---|---|---|---|---|---|---|
| Session header `n/m · min` | B | N | duration not computed | — | new | — | — | 1 | after migration |
| Ordered exercise list | B | N | — | **migration** | new screen | — | — | 1 | after migration |
| Sets / reps / target RIR | B | N | — | **migration** | new | — | — | 1 | after migration |
| Rest timer | B live countdown | N | — | column exists in migration | new | — | — | 2 | after migration |
| Inline set logger | B | P free logging | — | — | rework | — | — | 2 | **Yes** |
| Reps-in-reserve row | B | **Y** `set_logs.rir` | — | — | new control | — | — | 2 | **Yes** |
| Warm-up marked non-working | B | N | no warm-up model | **new column/table** | new | — | — | 2 | needs a decision |
| Replace / skip | B | N | `PATCH` written | **migration** | new | — | — | 2 | after migration |
| Add exercise mid-session | B | N | no endpoint | — | new | — | — | 3 | needs a decision |
| Pause / resume | B | N | no state field | **new column** | new | — | — | 3 | needs a decision |
| Completion summary | B | Y `/sessions/{id}/summary` | — | — | new screen | — | — | 2 | **Yes** |
| Coach prompt | B static | Y `coach.py`, `chat.py` | — | — | new | — | — | 4 | Yes, read-only |
| Off-programme picker | B | N | no generator for it | — | new screen | — | — | 3 | needs a decision |

### C · Exercise detail and education

| Feature | Prototype | Production | Backend gap | DB gap | Mobile gap | Permissions | Privacy/legal | Phase | Safe next? |
|---|---|---|---|---|---|---|---|---|---|
| Movement diagram | B original SVG | N | — | asset store | new | — | P if licensed art is used | 3 | **Yes** as drawn |
| Primary / secondary muscles | B | **Y** `exercises` | — | — | new | — | — | 1 | **Yes** |
| Movement pattern, unilateral | B | N | — | `exercise_attributes` **empty** | new | — | — | 1 | **seed data first** |
| Beginner explanation | B | **N** | — | **no column anywhere** | new | — | P authorship | 3 | needs a decision |
| Form cues, mistakes, feel | B | **N** | — | **no column anywhere** | new | — | P authorship | 3 | needs a decision |
| Easier / harder variation | B | N | — | `exercise_substitutions` **empty** | new | — | — | 2 | seed data first |
| Substitute | B | N | validated in `PATCH` | **empty** | new | — | — | 2 | seed data first |
| e1RM trend | B | **Y** `/strength/progress` | — | `strength_snapshots` **empty** | new chart | — | — | 2 | run the rollup |
| Recent performance | B | **Y** `set_logs` | — | — | new | — | — | 2 | **Yes** |
| Plateau status | B | N | `plateau.py` absent | none — derivable | new | — | P wording | 4 | **No** |

### D · Sleep and recovery

| Feature | Prototype | Production | Backend gap | DB gap | Mobile gap | Permissions | Privacy/legal | Phase | Safe next? |
|---|---|---|---|---|---|---|---|---|---|
| Sleep duration / quality | B | **Y** `sleep_nights` | — | — | new screen | **Yes** sleep scope | **Yes** | 3 | **No** |
| Bedtime / wake summary | B | **Y** columns exist | — | — | new | Yes | Yes | 3 | **No** |
| Seven-night bars | B | Y | — | — | new chart | Yes | Yes | 3 | **No** |
| Consistency, recent average | B | N | not computed | — | new | Yes | Yes | 3 | **No** |
| **Manual sleep entry** | B | **N** | no write path | **`source` assumes a device** | new | **none** | Yes | 3 | needs a decision |
| Source label per record | B | **Y** `HealthSource` | — | — | new | — | — | 3 | **Yes** |
| Edit / delete a night | B | P | delete endpoint | — | new | — | **Yes** hard vs soft | 3 | **No** |
| Energy / soreness / stress | B | N | no endpoint | `readiness_checkins` **unapplied** | new | — | **Yes** §10.8 | 3 | **No** |
| Readiness score | B | **N** | no calculator, weights invented | — | new | — | **Yes** | 3 | **No** |
| "Why this number" breakdown | B | N | — | — | new | — | Yes | 3 | **No** |
| Recovery trend | B | N | not computed | needs history | new | — | Yes | 4 | **No** |
| Recommended intensity | B advisory | N | deferred by §1 | — | new | — | **Yes** wording | 4 | **No** |
| Privacy explanation | B | N | — | — | copy | — | **Yes** — needs a lawyer | 3 | **No** |

> **Sleep presentation vs sleep storage — the distinction the brief asked for.**
> Storage is **done**: `sleep_nights` has `night_of`, `asleep_hours`,
> `in_bed_hours`, `deep/rem/core`, `awakenings`, `efficiency`, `source`, and
> `/health/sync` writes it. Presentation is **entirely absent** — no mobile
> screen reads it. Manual entry is a third thing again and is **not
> supported**: `source` is a `HealthSource` enum that assumes a device wrote
> the row, so a hand-typed night has nowhere honest to sit. The prototype shows
> the UI; the app cannot store what that UI collects.

### E · Cardio and cycling

| Feature | Prototype | Production | Backend gap | DB gap | Mobile gap | Permissions | Privacy/legal | Phase | Safe next? |
|---|---|---|---|---|---|---|---|---|---|
| Indoor / outdoor selector | B | **Y** `sports.py` | — | — | new | — | — | 4 | **Yes** |
| Duration / distance / climb | B | **Y** `ride_tracks` | — | — | new | — | — | 4 | **Yes** |
| Average speed | B | Y derivable | small calc | — | new | — | — | 4 | **Yes** |
| Energy + basis stated | B | P | basis not recorded | **new column** | new | — | — | 4 | needs a decision |
| **Route preview, outdoor only** | B drawn | **Y** `GET /{id}/track` | — | — | **map renderer** | **Yes** if recorded on device | **Yes** location | 5 | **No** |
| **Indoor draws no route** | B enforced | n/a | — | — | rule to keep | — | — | 4 | **Yes** |
| Recent activities | B | **Y** | — | — | new | P Strava | P terms | 4 | **Yes** |
| Weekly cardio load | B | **Y** `activity_days` | — | — | new | — | — | 4 | **Yes** |
| **Calorie target unchanged** | B | **Y** invariant #1 | — | — | copy | — | — | 2 | **Yes** |
| Deduplication note | B copy | **Y** `external_workouts` | — | — | copy | — | — | 4 | **Yes** |
| Start/pause/resume/finish | B display only | **N** | no recorder | — | new | **Yes** location + background | **Yes** | 5 | **No** |
| Delete activity | B | P | delete endpoint | — | new | — | Yes | 4 | needs a decision |
| Route visibility control | B | N | — | **new column** | new | — | **Yes** | 5 | **No** |

> **Cycling presentation vs GPS tracking — the distinction the brief asked for.**
> `ride_tracks` already stores a `points` JSONB track and `rides.py` serves it,
> so *displaying* a route someone else recorded is a rendering problem.
> **Recording a route on the device is a completely different product**: it
> needs foreground and background location permission, a battery-aware
> recorder, a consent flow, a retention rule and a delete control — none of
> which exists. The prototype does neither: it draws a placeholder and says so.

### F · Nutrition

| Feature | Prototype | Production | Backend gap | DB gap | Mobile gap | Permissions | Privacy/legal | Phase | Safe next? |
|---|---|---|---|---|---|---|---|---|---|
| Calorie / macro overview | B read-only | **Y** shipped | — | — | reuse | — | — | 2 | **Yes** |
| Food log, meal grouping | B read-only | **Y** shipped | — | — | reuse | — | — | 2 | **Yes** |
| Scan entry point | B link only | **Y** shipped | — | — | link | camera (already) | — | 2 | **Yes** |
| ± band on estimates | B | **Y** shipped | — | — | reuse | — | — | 2 | **Yes** |
| Verified vs estimated | B | **Y** `verification_tier` | — | — | reuse | — | — | 2 | **Yes** |
| Source attribution | B | **Y** shipped this session | — | — | reuse | — | **done** | 2 | **Yes** |
| Micronutrients worth watching | B | **Y** `micronutrients.py` | — | — | new card | — | — | 2 | **Yes** |
| Meal plan | **M** placeholder | **N** | no generator | no table | — | — | — | 5 | **No** |
| Cardio kcal not added | B | **Y** invariant #1 | — | — | copy | — | — | — | **Yes** |

> Nutrition is **read-only in the prototype by design**. It reimplements
> nothing, changes no food-database behaviour, and adds no food. The meal plan
> is left as a marked placeholder rather than mocked up, because nothing in
> Trace produces one and a convincing mock-up would be the wrong kind of
> convincing.

### G · Progress and plateau

| Feature | Prototype | Production | Backend gap | DB gap | Mobile gap | Permissions | Privacy/legal | Phase | Safe next? |
|---|---|---|---|---|---|---|---|---|---|
| Weekly consistency | B | **Y** | — | — | reuse | — | — | 2 | **Yes** |
| Muscle-group volume | B | **Y** `volume.py` | — | — | new chart | — | — | 2 | **Yes** |
| Per-exercise progression | B | **Y** | — | — | reuse | — | — | 2 | **Yes** |
| e1RM trend | B | **Y** `strength.py` | — | rollup never run | new chart | — | — | 2 | run the rollup |
| Sets/reps/load history | B | **Y** `set_logs` | — | — | new | — | — | 2 | **Yes** |
| Personal records | B | P derivable | small calc | — | new | — | — | 2 | **Yes** |
| Eight-week trend | B | **Y** | — | — | reuse | — | — | 2 | **Yes** |
| Programme adherence | B | N | not computed | **migration** | new | — | — | 2 | after migration |
| **Fatigue trend** | B illustrative | **N** | **nothing computes this** | — | new | — | — | 5 | **No** |
| Sleep / cardio overlay | B | P data exists | — | — | new chart | Yes for sleep | Yes | 4 | **No** |
| Plateau evidence table | B | **N** | `plateau.py` absent | none needed | new | — | — | 4 | **No** |
| Accept / postpone / dismiss | B | **N** | — | **`plateau_events` deferred** | new | — | — | 5 | **No** |

> **The plateau detector.** §14.8 establishes that detection needs **no new
> table** — `set_logs`, `workout_sessions` and `prescribed_exercises` already
> carry everything, and `strength.e1rm`, `WEIGHT_STEP_KG`, `units.round_to_step`
> and `volume.build_report` cover the arithmetic. So the detector itself is
> buildable now. What is *not* buildable is remembering the user's **decision**:
> a recommendation shown, declined and re-shown next session is a bug, and
> "declined" is not derivable from performed history. That needs
> `plateau_events`, which is deferred, and a cooldown duration nobody has set.

### H · Programme and goal setup

| Feature | Prototype | Production | Backend gap | DB gap | Mobile gap | Permissions | Privacy/legal | Phase | Safe next? |
|---|---|---|---|---|---|---|---|---|---|
| Goal selection | B | **Y** `users.goal_type` | — | — | new screen | — | — | 1 | **Yes** |
| Training phase | B | **Y** `program_type` | — | — | new | — | — | 1 | **Yes** |
| Days / available days | B | Y declared | — | **migration** | new | — | — | 1 | after migration |
| Time per session | B | Y declared | — | **migration** | new | — | — | 1 | after migration |
| Equipment | B | Y declared | — | **migration** | new | — | — | 1 | after migration |
| Preferred / disliked | B | Y `disliked_exercise_ids` | — | **migration** | new | — | — | 1 | after migration |
| Cardio frequency | B | **Y** `cardio_sessions_per_week` | — | — | new | — | — | 1 | **Yes** |
| Recovery opt-in | B skippable | N | — | **migration** | new | — | **Yes** §10.8 | 3 | **No** |
| AI opt-in | B skippable | Y `ai_enabled` declared | — | **migration** | new | — | **Yes** §10.8 | 5 | **No** |
| Preview + confirm | B | **Y** `POST /programmes` | — | **migration** | new | — | — | 1 | after migration |

### I · AI

| Feature | Prototype | Production | Backend gap | DB gap | Mobile gap | Permissions | Privacy/legal | Phase | Safe next? |
|---|---|---|---|---|---|---|---|---|---|
| Structured generated session | B mock | **N** | no producer | `ai_generations` **unapplied** | new | — | **Yes** §10.8 | 5 | **No** |
| Id validation, whole-draft reject | B | **N** | — | validates against `exercises` | new | — | — | 5 | **No** |
| Confirm / edit / reject | B | **N** | — | `validation_status` | new | — | Yes | 5 | **No** |
| Confidence meters | B em dashes | N | — | — | new | — | — | 5 | **No** |

---

## Summary by kind of work

**Migration.** One, already written: `f6a9c2e47d85`. Applying it unlocks most
of Train and all of Setup. Three more are implied later — a manual source for
sleep, an energy-basis column for activities, and `plateau_events`. A home for
exercise coaching text is a fourth, and has no design yet.

**Seed data.** `exercise_attributes` and `exercise_substitutions` ship **empty**.
874 exercises need movement pattern, class, unilateral flag and default rep
range, plus a substitution graph. **This is the largest un-costed item in the
whole plan** and it gates the exercise detail screen, substitutions and
variations.

**Backend.** Duration estimation, time-fitting, warm-up modelling, adherence,
personal records, the plateau detector, readiness endpoints and calculator, and
the AI producer. Plus running the strength rollup, which has never run —
`strength_snapshots` is empty.

**Mobile.** Everything. Fourteen prototype screens map to roughly eight
production screens, none of which exist.

**Permissions.** Two, both already in scope: HealthKit / Health Connect sleep,
and location — the latter **only** if a route is ever recorded on-device rather
than displayed from an import. The prototype requests neither.

**Privacy and legal.** Three unresolved §10.8 items, none schema-affecting:
readiness retention and export treatment, consent wording for the readiness
health fields, and the retention window for rejected AI drafts. A fourth is
implied by this round: whether a recorded route needs its own consent separate
from health data. **Nothing in this document asserts compliance.**

---

## Recommended phasing

| Phase | Content | Gated on |
|---|---|---|
| **1 · Deterministic core** | Apply `f6a9c2e47d85`; seed `exercise_attributes`; setup flow; programme generation; today's session card | migration + seed |
| **2 · Read what exists** | Home dashboard, progress screen, nutrition mirror, session summary, inline set logging, strength rollup | phase 1 |
| **3 · Optional inputs** | Readiness capture, sleep presentation and manual entry, exercise coaching content | **legal sign-off on §10.8** |
| **4 · Signals** | Plateau detector and evidence view, cardio presentation, cardio-aware volume, overlays | phases 2–3 |
| **5 · Deferred** | AI generation and review, route recording, `plateau_events`, meal plan, fatigue index | **provider + retention + location decisions** |

Phase 3 is the first one that cannot start on engineering alone.

---

## The smallest useful first slice

**Apply `f6a9c2e47d85` to a scratch database**, seed `exercise_attributes` for
only the handful of exercises a beginner full-body programme uses, and build
the single "today's planned session" card on the existing `train` tab against
`GET /planned-sessions/today`.

That exercises the migration, the generator, the ownership checks and the
mobile fetch path end to end, while touching no nutrition table, requiring no
permission, and needing no legal sign-off. It is also the slice this
prototype's Home and Train screens describe most concretely.

**A close second, and independent of it:** the read-only Progress screen. Every
number on it — volume, e1RM, progression, records, consistency — comes from
services that already exist and data already being collected. It needs no
migration, no seed, no permission and no legal review. It is the largest
visible gain available for the least risk, and it is the only part of this
prototype that could ship without a decision from anyone.
