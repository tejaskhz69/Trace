# Workout programming — schema design

**Status:** proposal. Nothing here is implemented.
**Written against:** `WORKOUT_DATABASE_UPGRADE_PLAN.md` (untracked, unmodified).
**Baseline this design branches from:**

| | |
|---|---|
| HEAD | `c81c032` |
| Database | `trace` on `127.0.0.1:5432` |
| Alembic revision | `e4f7b0d25c63` |
| `food_items` | 578,773 |
| `food_aliases` | 1,353 |
| `gtin14` populated | 504,850 |
| `name_normalized` populated | 578,772 |
| Backup | `trace_backup_20260823_155514.dump` |

No database was read or written while writing this document beyond the
read-only inspection already reported in Phase 1.

---

## 1. Product scope

### Two layers, and only one of them is new

Trace already has a complete **workout-recording** layer: it knows what you
did. It has no **workout-programming** layer: it cannot tell you what to do.

| | Recording (exists) | Programming (proposed) |
|---|---|---|
| Question answered | "What did I lift?" | "What should I lift today?" |
| Direction of time | Past | Future |
| Tables | `exercises`, `workout_sessions`, `set_logs`, `strength_snapshots` | the nine below |
| Truth source | The user's own taps | A rule engine, later an LLM |
| Failure mode | Lost data | Bad advice |

That second failure mode is why this design keeps prescription in its own
tables rather than adding nullable "planned" columns to `set_logs`. A planned
set that was never performed and a performed set are different kinds of fact,
and conflating them would corrupt every strength calculation downstream —
`strength.py` and `volume.py` both read `set_logs` as ground truth about what a
body actually did.

### The MVP is deterministic template programming

The first release generates programmes from **rules, not a model**: day count
and split type in, a fixed weekly structure out. No LLM call, no network
dependency, no prompt.

This is a deliberate sequencing choice, not timidity. Deterministic generation
exercises every table, every foreign key, every ownership check and the entire
mobile flow, while being fully testable with fixtures and reproducible in CI.
When AI generation is added later it becomes *one more producer* writing into
`planned_sessions` and `prescribed_exercises` — the schema does not change,
only `generated_by` flips from `template` to `ai`.

The MVP is also **beginner-safe** and **educational**, and both are binding
rather than aspirational (§10.7). A new user with no training history gets
bodyweight or standard-dumbbell programming, never a barbell load inferred
from a history that does not exist; `suggested_weight_kg` stays NULL until
there is a basis for it. A prescription shows its rep range, target RIR and
progression rule rather than just a number to hit.

**Manual logging is never gated behind any of this.** A user can log a workout
with no profile, no programme and no planned session, exactly as they can
today. Generated programming is offered, never required.

### Explicitly deferred

Deferred means **the schema anticipates it but the first release does not
build it**. Each is called out again at the table that would carry it.

| Deferred | Why it can wait | Schema impact now |
|---|---|---|
| AI generation | Needs a provider decision, prompt design, and output validation | `planned_sessions.generated_by`, `generation_id`; `ai_generations` table shipped empty |
| Readiness adjustment | Needs the readiness questionnaire UX and a clinical-language review | `readiness_checkins` table + `planned_sessions.readiness_status`, both MVP-created, unused by generation |
| Cardio-aware volume | Depends on `ActivityDay` / HealthKit coverage that varies by user | none |
| Deloading | Needs the fatigue model. Authority is settled: the system recommends, the user confirms (§10.2) | none — `deload_events` is deferred entirely |
| Learned preferences | Requires a signal history that does not exist yet | `training_profiles.disliked_exercise_ids` covers the explicit case only |

`readiness_checkins` is created in the MVP migration despite readiness
adjustment being deferred, because the check-in is worth **capturing** before
it is worth **acting on** — a fatigue model needs history, and history only
accumulates if collection starts early. Nothing reads the table in release one.

### Out of scope entirely

Nutrition. The plan itself says *"Do not automatically treat all cardio
calories as extra food calories. Follow the application's existing calorie and
TDEE rules"* — which is project non-negotiable #1. **No table in this design
references any nutrition table, and no migration step touches one.** The
existing coupling through `ActivityDay` and `adjudication.py` is sufficient
and stays exactly as it is.

---

## 2. Existing reusable components

Everything in this section is **reused unmodified**. No `ALTER TABLE` is
proposed against any of it.

### `Exercise` — `exercises`, 874 rows

```
id, name (indexed), muscle_group, secondary_muscles (JSONB),
equipment (default 'barbell'), is_compound, aliases (JSONB)
```

12 distinct `equipment` values, 9 distinct `muscle_group` values. This is a
usable catalogue and it is **not** re-seeded.

It is, however, missing what programming needs: no movement pattern, no
compound/machine/isolation class, no unilateral flag, no default rep range, no
substitution graph. Those go in `exercise_attributes` and
`exercise_substitutions` as **side tables** rather than new columns —
see §8 for why that choice is load-bearing for migration safety.

### `WorkoutSession` — `workout_sessions`, 5 rows

```
id, user_id → users.id, started_at, ended_at, routine_name, notes
Index ix_session_user_time (user_id, started_at)
```

Stays the record of a *performed* session. `planned_sessions` points **at** it
via a nullable FK; the arrow deliberately runs plan → performance, so a
performed session logged spontaneously (the existing flow, the common case)
never needs a plan to exist.

### `SetLog` — `set_logs`, 8 rows

```
id, session_id, user_id, exercise_id, set_index, weight_kg, reps,
rpe, rir, is_warmup, e1rm, performed_at
```

`rir` already exists and already carries the comment explaining why it is
nullable. **This is the input the plan's progressive-overload section needs**,
and it is already being collected. No change.

### `StrengthSnapshot` — `strength_snapshots`, 0 rows

Weekly rollup, `uq_strength_week (user_id, week_start, exercise_id)`. Empty
because the rollup job has not run against real data yet. Programming reads it
when choosing starting loads; it does not write to it.

### Existing services

| Service | Lines | What programming takes from it |
|---|---|---|
| `strength.py` | 584 | RIR-adjusted e1RM — the load basis for a prescription |
| `volume.py` | 235 | Weekly sets per muscle + verdict — the check on a generated split |
| `units.py` | 235 | Plate and increment snapping — a prescription must be *loadable* |
| `sports.py` | 399 | Cardio classification — needed when cardio-awareness lands |
| `workout_voice.py` | 588 | Voice → sets; unchanged, but a prescription gives it context |

All are pure functions with no I/O, per project convention. Programming adds
`services/programming.py` in the same style.

### Existing endpoints — `/api/workouts`, 12 of them

`GET /exercises`, `GET /catalogue`, `POST /sessions`,
`POST /sessions/{id}/sets`, `GET /sessions/{id}/next-set`,
`POST /sessions/{id}/finish`, `GET /sessions/{id}/summary`,
`GET /sessions/last-performance`, `GET /strength/overview`,
`GET /strength/progress`, `POST /voice`, `POST /voice/commit`.

**None is modified.** Programming endpoints are added alongside. In particular
`POST /sessions/{id}/sets` keeps working with no plan present — the existing
free-logging path must not regress.

### Existing `User` fields relevant to programming

`sex`, `date_of_birth`, `height_cm`, `goal_type`, `program_type`,
`activity_multiplier`, `lifting_experience_months`, `daily_steps`,
`cardio_sessions_per_week`, `lifting_sessions_per_week`, `timezone`.

Roughly half the plan's "user information for programming" list already exists
here. The rest goes to `training_profiles`. `program_type` stays the broad
training reference and `training_profiles.ai_enabled` is a separate, narrower
opt-in for AI generation; the narrower one wins (§10.4).

---

## 3. Proposed tables

Conventions inherited from `models.py` and applied to every table below:

- Primary keys are `str` UUIDs via `default_factory=_uuid`, column type
  `sqlmodel.sql.sqltypes.AutoString()` — matching `users.id` and `exercises.id`
  exactly, as `c2d5f8b03a41` did for `food_aliases`.
- Every timestamp is `TZDateTime` = `DateTime(timezone=True)`. asyncpg refuses
  naive datetimes.
- Calendar days are `sa.Date` with no timezone — a scheduled day is a day.
- Every user-owned table carries `user_id` with `ondelete="CASCADE"`.
- `created_at` / `updated_at` on every mutable row.
- No column is nullable unless the null carries a distinct meaning, which is
  stated where it does.

---

### 3.1 `exercise_attributes` — **MVP**

**Purpose.** The programming metadata `exercises` lacks. Rep ranges, movement
pattern and fatigue cost drive the plan's hypertrophy and prioritisation
sections and have no home today.

**Why a side table and not columns on `exercises`.** Three reasons, in order of
weight: (1) the migration then creates tables only and alters nothing, which is
the single strongest safety property available to us; (2) attributes are
admin-curated reference data on a 874-row catalogue that also holds
user-visible names — different change cadence, different review; (3) a missing
attribute row is a legible state ("not yet classified") rather than a column
full of nulls.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `exercise_id` | AutoString | no | — | **PK and FK** |
| `movement_pattern` | Text | no | — | squat / hinge / push_horizontal / push_vertical / pull_horizontal / pull_vertical / carry / isolation |
| `exercise_class` | Text | no | — | compound / machine / isolation |
| `is_unilateral` | Boolean | no | `false` | |
| `default_rep_min` | SmallInteger | no | — | |
| `default_rep_max` | SmallInteger | no | — | |
| `default_rest_seconds` | SmallInteger | no | `120` | |
| `fatigue_cost` | SmallInteger | no | `3` | 1–5; feeds deload accounting later |
| `created_at` / `updated_at` | TZDateTime | no | now | |

- **PK** `exercise_id` — one attribute row per exercise, enforced by the PK itself.
- **FK** `exercise_id → exercises.id ON DELETE CASCADE`. Attributes are *about*
  the exercise; if it goes, they are meaningless.
- **Unique** — the PK.
- **Checks:** `default_rep_min >= 1`; `default_rep_min <= default_rep_max`;
  `default_rep_max <= 50`; `fatigue_cost BETWEEN 1 AND 5`;
  `default_rest_seconds BETWEEN 15 AND 600`.
- **Indexes:** `ix_exattr_pattern (movement_pattern)`,
  `ix_exattr_class (exercise_class)` — split generation filters on both.
- **Ownership:** none. Global reference data, readable by any authenticated
  user, writable only by seed scripts.
- **Deletion:** cascades with the exercise. Never user-deleted.
- **Privacy:** non-personal.

> The 874 existing exercises will not all have attribute rows on day one.
> Generation must treat an unattributed exercise as **ineligible for
> prescription** rather than guessing defaults — refusing to answer beats
> answering wrong (non-negotiable #3).

---

### 3.2 `exercise_substitutions` — **MVP**

**Purpose.** The plan requires branded-machine substitution ("PRIME hip
thrust" → generic hip thrust) and equipment-driven swaps. A directed, ranked
graph.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | AutoString | no | uuid | PK |
| `from_exercise_id` | AutoString | no | — | FK |
| `to_exercise_id` | AutoString | no | — | FK |
| `reason` | Text | no | — | equipment / branded / limitation / preference |
| `rank` | SmallInteger | no | `1` | 1 = best substitute |
| `created_at` | TZDateTime | no | now | |

- **FKs:** both → `exercises.id ON DELETE CASCADE`.
- **Unique:** `uq_exsub_pair (from_exercise_id, to_exercise_id)`.
- **Checks:** `from_exercise_id <> to_exercise_id`; `rank BETWEEN 1 AND 10`.
- **Indexes:** `ix_exsub_from (from_exercise_id, rank)` — the only access path.
- **Ownership:** none; global. A *user's* dislikes live in
  `training_profiles`, deliberately separate: "these two exercises are
  interchangeable" is a fact about training, "I hate lunges" is a fact about a
  person, and mixing them would leak preference into shared reference data.
- **Deletion:** cascades. **Privacy:** non-personal.

Direction is not assumed symmetric. Barbell → dumbbell bench is a reasonable
substitution; the reverse is a different judgement, and if both hold, both rows
exist.

---

### 3.3 `training_profiles` — **MVP**

**Purpose.** The programming inputs that are not identity. Days available,
minutes per session, equipment on hand, hard exclusions.

**Why not on `users`.** `users` is identity and account state, read on every
authenticated request. Training preferences change often, are edited as a unit
by one screen, and are irrelevant to authentication. Keeping them out also
keeps this design's promise that no existing table is altered.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | AutoString | no | uuid | PK |
| `user_id` | AutoString | no | — | FK, **unique** |
| `days_per_week` | SmallInteger | no | `3` | |
| `available_days` | JSONB | no | `'[]'` | `["mon","wed","fri"]`; empty = no preference |
| `preferred_minutes` | SmallInteger | no | `60` | |
| `equipment` | JSONB | no | `'[]'` | values drawn from `exercises.equipment` |
| `disliked_exercise_ids` | JSONB | no | `'[]'` | explicit user exclusions |
| `limitations` | Text | yes | null | free text — **health-sensitive**, see §11 |
| `ai_enabled` | Boolean | no | `true` | opt-in for AI generation; false disables it whatever `program_type` says (§10.4) |
| `created_at` / `updated_at` | TZDateTime | no | now | |

- **FK:** `user_id → users.id ON DELETE CASCADE`.
- **Unique:** `uq_training_profile_user (user_id)` — one profile per user, in
  the database, not in application code.
- **Checks:** `days_per_week BETWEEN 1 AND 7`;
  `preferred_minutes BETWEEN 15 AND 180`.
- **Indexes:** the unique constraint is the only access path needed.
- **Ownership:** owner-only, read and write. Every query filters
  `user_id == current_user.id`.
- **Deletion:** cascades with the user. Editable, never soft-deleted.
- **Privacy:** personal. `limitations` is free text a user may fill with injury
  or medical detail; it is treated as health-sensitive throughout (§11).

`disliked_exercise_ids` is JSONB rather than a join table because it is always
read whole, never queried across users, and small — the same reasoning
`models.py` already records for `serving_sizes`.

---

### 3.4 `training_programmes` — **MVP**

**Purpose.** One multi-week structure: split type, day count, lifecycle.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | AutoString | no | uuid | PK |
| `user_id` | AutoString | no | — | FK |
| `name` | Text | no | — | e.g. "Upper/Lower — 4 day" |
| `split_type` | Text | no | — | full_body / upper_lower / ppl / … (plan §"Training split generation") |
| `days_per_week` | SmallInteger | no | — | |
| `status` | Text | no | `'active'` | active / paused / archived |
| `generated_by` | Text | no | `'template'` | template / ai / user |
| `started_at` | TZDateTime | no | now | |
| `archived_at` | TZDateTime | yes | null | non-null **iff** archived |
| `created_at` / `updated_at` | TZDateTime | no | now | |

- **FK:** `user_id → users.id ON DELETE CASCADE`.
- **Unique:** a **partial unique index**
  `uq_active_programme_per_user ON training_programmes (user_id) WHERE status = 'active'`.
  This is the one invariant most likely to be violated by a retry or a
  double-tap, and application-level checks lose that race. Postgres does not.
- **Checks:** `days_per_week BETWEEN 1 AND 7`;
  `status IN ('active','paused','archived')`;
  `(status = 'archived') = (archived_at IS NOT NULL)`.
- **Indexes:** `ix_programme_user_status (user_id, status)`.
- **Ownership:** owner-only.
- **Deletion:** **archive, never delete.** A programme is the explanation for
  every planned session under it; deleting it would orphan the reason a user
  did what they did. `DELETE` is not exposed by the API at all.
- **Privacy:** personal, low sensitivity.

---

### 3.5 `programme_days` — **MVP**

**Purpose.** The template rows of a programme — "Day 1: Upper (push emphasis)".
A repeating structure, not calendar dates.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | AutoString | no | uuid | PK |
| `programme_id` | AutoString | no | — | FK |
| `day_index` | SmallInteger | no | — | 0-based position in the week |
| `label` | Text | no | — | "Upper A" |
| `focus` | JSONB | no | `'[]'` | muscle groups, ordered |
| `target_minutes` | SmallInteger | yes | null | null = inherit the profile |
| `created_at` | TZDateTime | no | now | |

- **FK:** `programme_id → training_programmes.id ON DELETE CASCADE`. A day has
  no meaning outside its programme, and programmes are archived rather than
  deleted, so this cascade fires only when a user account is removed.
- **Unique:** `uq_programme_day (programme_id, day_index)`.
- **Checks:** `day_index BETWEEN 0 AND 6`;
  `target_minutes IS NULL OR target_minutes BETWEEN 15 AND 180`.
- **Indexes:** covered by the unique constraint.
- **Ownership:** indirect, through `programme_id`. Every query **joins to
  `training_programmes` and filters on `user_id`** — never trusts a
  client-supplied `programme_id` alone.
- **Deletion:** cascades. **Privacy:** personal, low sensitivity.

---

### 3.6 `planned_sessions` — **MVP**

**Purpose.** One dated instance of a `programme_day`. The join between
intention and reality.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | AutoString | no | uuid | PK |
| `user_id` | AutoString | no | — | FK — denormalised on purpose, see below |
| `programme_day_id` | AutoString | yes | null | FK; null = one-off session |
| `session_id` | AutoString | yes | null | FK → `workout_sessions.id`; null until started |
| `scheduled_for` | Date | no | — | user's local calendar day |
| `status` | Text | no | `'planned'` | planned / active / completed / skipped |
| `readiness_status` | Text | yes | null | deferred; always null in MVP |
| `estimated_minutes` | SmallInteger | yes | null | |
| `generated_by` | Text | no | `'template'` | template / ai / user |
| `generation_id` | AutoString | yes | null | FK → `ai_generations.id`; null unless AI |
| `notes` | JSONB | no | `'[]'` | the plan's `notes[]` array |
| `created_at` / `updated_at` | TZDateTime | no | now | |

- **FKs:**
  - `user_id → users.id ON DELETE CASCADE`
  - `programme_day_id → programme_days.id ON DELETE SET NULL` — **not**
    cascade. If a programme structure is rebuilt, the record that a user
    trained on a given day must survive. It becomes a one-off, not a deletion.
  - `session_id → workout_sessions.id ON DELETE SET NULL`
  - `generation_id → ai_generations.id ON DELETE SET NULL`
- **Unique:** `uq_planned_day (user_id, scheduled_for, programme_day_id)`.
  **Caveat, and it matters:** Postgres treats NULLs as distinct, so this does
  not constrain one-off sessions (`programme_day_id IS NULL`) at all — the same
  trap `c2d5f8b03a41` documented for `food_aliases.lang`. That is the intended
  behaviour here (a user may legitimately plan two ad-hoc sessions in a day),
  but it is called out explicitly so nobody later mistakes it for protection it
  does not give.
- **Checks:** `status IN ('planned','active','completed','skipped')`;
  `estimated_minutes IS NULL OR estimated_minutes BETWEEN 5 AND 300`;
  `(generated_by = 'ai') OR (generation_id IS NULL)` — a non-AI session may not
  cite an AI generation.
- **Indexes:** `ix_planned_user_date (user_id, scheduled_for DESC)` — "today's
  session" and the upcoming list; `ix_planned_session (session_id)` — plan
  lookup from a performed session.
- **`user_id` is denormalised** from `programme_day → programme → user`. This
  is a considered exception: it is the ownership filter on the hottest query in
  the feature, one-off sessions have no programme to derive it from, and the
  join would otherwise be three tables deep on every read. It is written once
  and never updated.
- **Ownership:** owner-only, direct.
- **Deletion:** completed sessions are never deleted. `planned` and `skipped`
  rows may be hard-deleted by the owner — nothing references them.
- **Privacy:** personal, low sensitivity.

---

### 3.7 `prescribed_exercises` — **MVP**

**Purpose.** The plan's AI response JSON, normalised. One row per prescribed
exercise in a planned session.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | AutoString | no | uuid | PK |
| `planned_session_id` | AutoString | no | — | FK |
| `exercise_id` | AutoString | no | — | FK, **RESTRICT** |
| `order_index` | SmallInteger | no | — | deterministic ordering |
| `sets` | SmallInteger | no | — | |
| `rep_min` | SmallInteger | no | — | |
| `rep_max` | SmallInteger | no | — | |
| `target_rir` | SmallInteger | no | `2` | |
| `rest_seconds` | SmallInteger | no | `120` | |
| `suggested_weight_kg` | Float | yes | null | null = no basis in history yet |
| `progression_rule` | Text | no | `'double_progression'` | |
| `substitution_ids` | JSONB | no | `'[]'` | offered alternatives, ordered |
| `status` | Text | no | `'prescribed'` | prescribed / replaced / skipped / done |
| `replaced_with_exercise_id` | AutoString | yes | null | FK, RESTRICT; non-null iff replaced |
| `created_at` / `updated_at` | TZDateTime | no | now | |

- **FKs:**
  - `planned_session_id → planned_sessions.id ON DELETE CASCADE`
  - `exercise_id → exercises.id ON DELETE RESTRICT`
  - `replaced_with_exercise_id → exercises.id ON DELETE RESTRICT`
- **`RESTRICT` is deliberate and differs from every other FK here.** Cascading
  would let a catalogue cleanup silently erase parts of a user's training
  history; `SET NULL` would leave a prescription that prescribes nothing.
  RESTRICT makes the deletion fail loudly and forces a human decision. This is
  the same instinct as the alias importer's refusal to guess a target.
- **Unique:** `uq_prescribed_order (planned_session_id, order_index)`.
- **Checks:** `sets BETWEEN 1 AND 12`; `rep_min >= 1`; `rep_min <= rep_max`;
  `rep_max <= 50`; `target_rir BETWEEN 0 AND 6`;
  `rest_seconds BETWEEN 15 AND 600`;
  `suggested_weight_kg IS NULL OR (suggested_weight_kg > 0 AND suggested_weight_kg <= 1000)`;
  `status IN ('prescribed','replaced','skipped','done')`;
  `(status = 'replaced') = (replaced_with_exercise_id IS NOT NULL)`.
- **Indexes:** `ix_prescribed_session (planned_session_id, order_index)`.
- **Ownership:** indirect via `planned_session_id`; every query joins to
  `planned_sessions` and filters `user_id`.
- **Deletion:** cascades with the planned session. A user "removing" an
  exercise sets `status='skipped'` rather than deleting the row — what was
  prescribed and declined is exactly the signal the deferred preference
  learning will need.
- **Privacy:** personal, low sensitivity.

> `target_rir` is `SmallInteger` while `SetLog.rir` is `Float`. Intentional: a
> prescription is a whole-number instruction ("leave 2 in the tank"), a
> measurement can be 1.5.

---

### 3.8 `readiness_checkins` — **MVP table, deferred consumer**

**Purpose.** The plan's daily readiness questionnaire. Captured from release
one; **not read by anything in release one.**

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | AutoString | no | uuid | PK |
| `user_id` | AutoString | no | — | FK |
| `for_date` | Date | no | — | user's local day |
| `available_minutes` | SmallInteger | yes | null | |
| `energy` | SmallInteger | yes | null | 1–5 |
| `sleep_quality` | SmallInteger | yes | null | 1–5 |
| `soreness` | SmallInteger | yes | null | 1–5 |
| `stress` | SmallInteger | yes | null | 1–5 |
| `pain_flag` | Boolean | no | `false` | |
| `pain_note` | Text | yes | null | **health-sensitive free text** |
| `created_at` / `updated_at` | TZDateTime | no | now | |

- **FK:** `user_id → users.id ON DELETE CASCADE`.
- **Unique:** `uq_readiness_user_date (user_id, for_date)` — one check-in per
  day, upserted.
- **Checks:** each of `energy`, `sleep_quality`, `soreness`, `stress` is
  `NULL OR BETWEEN 1 AND 5`;
  `available_minutes IS NULL OR BETWEEN 5 AND 300`.
- **Indexes:** covered by the unique constraint;
  `ix_readiness_user_date (user_id, for_date DESC)` for history.
- **Every score is nullable.** A partially answered questionnaire is a real
  state and must be distinguishable from a low score. Defaulting an unanswered
  soreness question to any number would fabricate a reading.
- **Ownership:** owner-only.
- **Deletion:** hard-deletable by the owner, independently of account
  deletion — check-ins are optional and user-controlled (§10.5). The retention
  duration and export treatment are still open (§10.8).
- **Privacy:** **health-sensitive.** Pain, sleep and stress are health data in
  a way a bench-press number is not. This classification drives §11, and the
  retention and consent items in §10.8 block any readiness feature shipping.

---

### 3.9 `ai_generations` — **MVP table, deferred consumer**

**Purpose.** The audit trail for AI-produced programming. The plan requires
that *"the backend must validate AI-generated workout output before displaying
or saving it"* — validation without a record of what was rejected is
unauditable.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | AutoString | no | uuid | PK |
| `user_id` | AutoString | no | — | FK |
| `kind` | Text | no | — | programme / session |
| `model` | Text | no | — | e.g. `claude-opus-5` |
| `prompt_digest` | Text | no | — | SHA-256 of the prompt, **not the prompt** |
| `raw_response` | JSONB | yes | null | rejected payloads only, bounded window (§10.6); NULL for accepted |
| `validation_status` | Text | no | — | accepted / rejected |
| `rejection_reason` | Text | yes | null | non-null iff rejected |
| `latency_ms` | Integer | yes | null | |
| `created_at` | TZDateTime | no | now | |

- **FK:** `user_id → users.id ON DELETE CASCADE`.
- **Unique:** none.
- **Checks:** `validation_status IN ('accepted','rejected')`;
  `(validation_status = 'rejected') = (rejection_reason IS NOT NULL)`;
  `kind IN ('programme','session')`.
- **Indexes:** `ix_aigen_user_time (user_id, created_at DESC)`.
- **`prompt_digest`, not the prompt.** The prompt would contain the user's
  limitations, pain notes and full training history. A digest answers "was this
  the same prompt?" — the only question this table needs to answer — without
  creating a second store of health data.
- **Ownership:** owner-only read. Written only by the server.
- **Deletion:** cascades with the user. Retention policy is §10.6; the
  duration it is bounded by is still open (§10.8).
- **Privacy:** sensitive if `raw_response` is populated; low if not.

Shipped in the MVP migration and left empty, so that when AI generation lands
it cannot ship *without* its audit trail — the table is already there and the
insert is the obvious thing to write.

---

## 4. Relationships

```
                              ┌───────────────┐
                              │    users      │
                              └───────┬───────┘
       ┌──────────────┬───────────────┼───────────────┬──────────────┐
       │ 1:1          │ 1:N           │ 1:N           │ 1:N          │ 1:N
       ▼              ▼               ▼               ▼              ▼
┌──────────────┐ ┌──────────┐ ┌───────────────┐ ┌───────────┐ ┌──────────────┐
│training_     │ │training_ │ │workout_       │ │readiness_ │ │ai_           │
│profiles      │ │programmes│ │sessions       │ │checkins   │ │generations   │
└──────────────┘ └────┬─────┘ └───────┬───────┘ └───────────┘ └──────┬───────┘
                      │ 1:N           │ 1:N                          │
                      ▼               ▼                              │
              ┌───────────────┐  ┌──────────┐                        │
              │programme_days │  │ set_logs │                        │
              └───────┬───────┘  └────┬─────┘                        │
                      │ 1:N           │ N:1                          │
                      ▼               │                              │
              ┌────────────────────┐  │                              │
              │ planned_sessions   │◄─┼──────────────────────────────┘
              │                    │  │   generation_id (nullable)
              │  session_id ───────┼──┼──► workout_sessions  (nullable, SET NULL)
              │  programme_day_id ─┼──┘   (nullable, SET NULL)
              └─────────┬──────────┘
                        │ 1:N
                        ▼
              ┌──────────────────────┐
              │prescribed_exercises  │
              └──────────┬───────────┘
                         │ N:1  (RESTRICT)
                         ▼
                  ┌─────────────┐        ┌──────────────────────┐
                  │  exercises  │◄──1:1──│ exercise_attributes  │
                  └──────┬──────┘        └──────────────────────┘
                         │ ▲
                         │ │ N:N (from / to, RESTRICT-free CASCADE)
                    ┌────┴─┴──────────────────┐
                    │ exercise_substitutions  │
                    └─────────────────────────┘

  set_logs ──N:1──► exercises        (existing, unchanged)
  set_logs ──N:1──► workout_sessions (existing, unchanged)
  set_logs ──N:1──► users            (existing, unchanged)
```

**The one arrow worth staring at** is `planned_sessions.session_id →
workout_sessions.id`. It runs plan → performance, nullable, `SET NULL`. That
direction means:

- a spontaneous workout needs no plan (the existing flow, unchanged);
- a plan that was never performed is a first-class state, not a null-filled
  session row;
- deleting a performed session leaves the plan intact as a record of intent.

No arrow anywhere in this diagram reaches a nutrition table.

---

## 5. Invariants

Each states the rule, then **where it is enforced** — a rule enforced only in a
service is a rule that survives until the first background job.

| # | Invariant | Enforced by |
|---|---|---|
| 1 | **At most one active programme per user.** | Partial unique index `uq_active_programme_per_user … WHERE status='active'`. Database, not code. |
| 2 | **Every read and write is ownership-filtered.** Direct tables filter `user_id`; indirect tables join to their owning row and filter there. | Service layer + a test per endpoint (§9). |
| 3 | **No cross-user reads or writes.** A request naming another user's id gets **404, never 403** — a 403 confirms the row exists. | Router; asserted in ownership-isolation tests. |
| 4 | **Planned→performed linkage is one-to-at-most-one, and optional in both directions.** Starting a planned session creates a `workout_sessions` row and sets `session_id`; it never mutates an existing one. | FK + `ix_planned_session`; service transaction. |
| 5 | **Deleting a prescribed exercise from the catalogue is refused.** | `ON DELETE RESTRICT` on `prescribed_exercises.exercise_id` and `replaced_with_exercise_id`. |
| 6 | **Rep, set and RIR ranges are always valid.** `1 ≤ sets ≤ 12`, `1 ≤ rep_min ≤ rep_max ≤ 50`, `0 ≤ target_rir ≤ 6`, `15 ≤ rest_seconds ≤ 600`. | CHECK constraints — a bad AI response cannot be stored even if validation is bypassed. |
| 7 | **Exercise ordering is deterministic.** `uq_prescribed_order` plus `ORDER BY order_index` on every read. No implicit ordering, ever. | Unique constraint + explicit ORDER BY. |
| 8 | **Generation is idempotent per (user, day, programme_day).** Re-requesting today's session returns the existing one; it does not create a second. | `uq_planned_day` + `POST` returning `200` on existing, `201` on created. |
| 9 | **Programmes are archived, never deleted.** No DELETE endpoint exists. Activating a new programme archives the old one in the same transaction. | API surface + CHECK tying `archived_at` to `status`. |
| 10 | **A non-AI session cannot cite an AI generation.** | CHECK `(generated_by='ai') OR (generation_id IS NULL)`. |
| 11 | **An unattributed exercise is never prescribed.** Generation joins `exercise_attributes` inner, not outer. | Service query shape; tested. |

---

## 6. API design

All endpoints sit under the existing `/api/workouts` prefix and use the
existing `current_user` dependency from `routers/auth.py`. **No existing
endpoint changes.**

### Authentication and errors

Bearer JWT on every route. Standard error mapping:

| Status | When |
|---|---|
| 400 | Malformed body |
| 401 | Missing or invalid token |
| 404 | Not found **or not owned** — deliberately indistinguishable |
| 409 | Invariant conflict (e.g. second active programme) |
| 422 | Validation failure (FastAPI/Pydantic) |

### Endpoints

**Training profile**

```
GET   /api/workouts/training-profile      → 200 TrainingProfilePublic | 404
PUT   /api/workouts/training-profile      → 200 (upsert; idempotent)
```
`PUT` rather than `POST`+`PATCH`: one profile per user, replaced as a whole by
one screen. Body: `days_per_week`, `available_days[]`, `preferred_minutes`,
`equipment[]`, `disliked_exercise_ids[]`, `limitations`, `ai_enabled`.

**Programmes**

```
POST  /api/workouts/programmes            → 201 ProgrammePublic | 409
GET   /api/workouts/programmes/active     → 200 | 404
GET   /api/workouts/programmes            → 200 [ProgrammeSummary]  (paginated)
POST  /api/workouts/programmes/{id}/archive → 200 | 404
```
`POST /programmes` takes `{split_type?, days_per_week?}` — omitted fields come
from `training_profiles`. It generates the programme **and** its
`programme_days` in one transaction, archiving any existing active programme in
the same transaction. Returns 409 if a concurrent request already created one
(the partial unique index surfacing as a conflict, translated).

There is **no** `DELETE /programmes/{id}` — invariant 9.

**Planned sessions**

```
POST  /api/workouts/planned-sessions      → 201 created | 200 existing
GET   /api/workouts/planned-sessions/today → 200 | 404
GET   /api/workouts/planned-sessions      → 200 [...] (paginated)
GET   /api/workouts/planned-sessions/{id} → 200 | 404
POST  /api/workouts/planned-sessions/{id}/start → 201 {session_id}
POST  /api/workouts/planned-sessions/{id}/skip  → 200
```
`POST /planned-sessions` body: `{scheduled_for, programme_day_id?}`.
**Idempotent** on `(user_id, scheduled_for, programme_day_id)`: 201 on create,
**200 with the existing row** on repeat. A double-tapping client never produces
two plans. The `programme_day_id IS NULL` caveat from §3.6 applies — one-off
sessions are not deduplicated, by design.

`/start` creates a `workout_sessions` row, sets `session_id`, flips status to
`active`, and returns the session id so the client can hand straight off to the
existing set-logging screen. If already started, it returns the existing
session id — also idempotent.

**Prescriptions**

```
PATCH /api/workouts/prescribed-exercises/{id} → 200 | 404 | 422
```
Body is one of: `{status: 'skipped'}`, or
`{status: 'replaced', replaced_with_exercise_id}`. Replacement is validated
against `exercise_substitutions` **and** against the user's `equipment` —
an arbitrary substitution is rejected 422, because "the user can pick anything"
and "the app suggested it" are different claims.

### Pagination

Keyset, never `OFFSET` — the same rule the nutrition work settled on.
`?before=<iso-date>&limit=<n>` on the two list endpoints, `limit` capped at 100,
ordered by `scheduled_for DESC, id DESC` for a total order.

### Response shapes

`ProgrammePublic` embeds its `days[]`. `PlannedSessionPublic` embeds
`exercises[]` already ordered by `order_index`, each carrying the exercise
name, equipment and the resolved substitution list — so today's-session renders
from one request with no N+1.

---

## 7. Mobile design

Four new screens plus a handoff. All compose existing primitives from
`src/components/instrument.tsx` per the design system: `Panel`, `Rule`,
`Label`, `Gauge`, `StatCell`, `Button`, `Skeleton`. No new component unless
nothing fits, and then it goes in `instrument.tsx`, not inline.

Entry point is the existing **`train` tab**, which currently opens straight
into free logging. It gains a planned-session card above that; free logging
stays reachable in one tap and is never gated behind a programme.

### 7.1 Training-profile setup — `app/(training)/profile-setup.tsx`

Stepped, one question per screen, matching the existing onboarding pattern:
days per week → preferred minutes → equipment (multi-select) → limitations
(optional free text) → confirm. Uppercase tracked micro-labels, one hero number
per step (`type.readout` on the day count).

The limitations step carries a plain, non-clinical note that this is used to
avoid exercises and is not medical advice — wording blocked on §10.8.

### 7.2 Programme overview — `app/(training)/programme.tsx`

Masthead with split name and day count. One `Panel` per `programme_day`,
each a `Label` + focus muscles + target minutes. Footer action: "New
programme", which warns that the current one will be archived — archived, not
deleted, and the copy says so.

### 7.3 Today's planned session — card on `app/(tabs)/train.tsx`

The highest-traffic surface. Shows day label, estimated minutes, exercise count,
and a single primary `Button`: **Start**. `Gauge` shows week progress
(sessions completed / days_per_week).

### 7.4 Prescription view — `app/(training)/session/[id].tsx`

FlashList of prescribed exercises, rows `memo`'d on primitives. Each row:
order index, exercise name, `3 × 6–8 @ RIR 2`, rest, and — where
`suggested_weight_kg` is present — the suggested load with the same `±`
discipline the nutrition side uses for estimates. Long-press opens
substitutions; swipe marks skipped.

**A suggested weight with no basis in history renders as "—", never as a
number.** Same rule as nutrition non-negotiable #2: no confident single value
for an estimate.

### 7.5 Handoff to set logging

`Start` calls `/start`, receives `session_id`, and navigates to the **existing**
logging screen with that id. From that moment the existing flow owns the
session — the same screen, the same `POST /sessions/{id}/sets`, the same voice
path. The prescription is passed as context so `next-set` can pre-fill, but
nothing about logging is rewritten.

This is the design's main risk-control on the mobile side: the new feature
stops at the door of the screen users already rely on.

### 7.6 States

| State | Treatment |
|---|---|
| Loading | `Skeleton`, never a spinner. Screens render the skeleton first and fetch after `InteractionManager.runAfterInteractions`. |
| Empty — no profile | Single `Panel`: "Set up training" → profile setup. |
| Empty — profile, no programme | "Generate a programme" primary button. |
| Empty — programme, nothing today | Rest day. Named as a rest day, not an error. Free logging stays available. |
| Error | Inline `Panel` with a retry action. Never blocks free logging — a programming outage must not stop a user recording a workout. |
| Offline | Today's session and prescriptions are cached and render read-only. Starting a session works offline through the existing local-first logging path; profile and programme mutations are disabled with an explicit "needs connection" note rather than queued — a silently queued programme change that later conflicts is worse than a clear refusal. |

---

## 8. Migration design

**One revision.** `down_revision = "e4f7b0d25c63"` (current head). No branch.

### Why nothing is altered

Every piece of new schema is a new table. `exercise_attributes` exists
specifically so `exercises` needs no `ALTER`. `training_profiles` exists
specifically so `users` needs no `ALTER`. The migration is therefore *purely
additive*, which makes its downgrade exactly reversible and its blast radius
provably zero against existing rows.

### Upgrade order

FK dependencies dictate it. Parents before children:

1. `exercise_attributes` — depends on `exercises` (exists)
2. `exercise_substitutions` — depends on `exercises` (exists)
3. `training_profiles` — depends on `users` (exists)
4. `training_programmes` — depends on `users` (exists)
5. `programme_days` — depends on `training_programmes` (step 4)
6. `ai_generations` — depends on `users` (exists)
7. `readiness_checkins` — depends on `users` (exists)
8. `planned_sessions` — depends on `users`, `programme_days` (5),
   `workout_sessions` (exists), `ai_generations` (6)
9. `prescribed_exercises` — depends on `planned_sessions` (8), `exercises`

`ai_generations` must precede `planned_sessions`; that is the only non-obvious
ordering constraint.

### Indexes

Built **inline and non-concurrently**, following the reasoning already recorded
in `c2d5f8b03a41`: every table is empty at creation, so each build is instant
and locks a table no query has ever read. `CREATE INDEX CONCURRENTLY` here
would be cargo-cult — slower, unable to run in this transaction, and guarding
against contention that cannot exist. (Contrast `e4f7b0d25c63`, where the same
operation on 578,773 `food_items` rows genuinely did need it.)

| Index | Table | Columns |
|---|---|---|
| `ix_exattr_pattern` | exercise_attributes | movement_pattern |
| `ix_exattr_class` | exercise_attributes | exercise_class |
| `ix_exsub_from` | exercise_substitutions | from_exercise_id, rank |
| `uq_training_profile_user` | training_profiles | user_id (UNIQUE) |
| `ix_programme_user_status` | training_programmes | user_id, status |
| `uq_active_programme_per_user` | training_programmes | user_id **WHERE status='active'** (partial UNIQUE) |
| `uq_programme_day` | programme_days | programme_id, day_index (UNIQUE) |
| `ix_planned_user_date` | planned_sessions | user_id, scheduled_for DESC |
| `ix_planned_session` | planned_sessions | session_id |
| `uq_planned_day` | planned_sessions | user_id, scheduled_for, programme_day_id (UNIQUE) |
| `uq_prescribed_order` | prescribed_exercises | planned_session_id, order_index (UNIQUE) |
| `ix_prescribed_session` | prescribed_exercises | planned_session_id, order_index |
| `uq_readiness_user_date` | readiness_checkins | user_id, for_date (UNIQUE) |
| `ix_readiness_user_date` | readiness_checkins | user_id, for_date DESC |
| `ix_aigen_user_time` | ai_generations | user_id, created_at DESC |

The partial unique index is created with raw `op.execute` — Alembic's
`create_index(..., postgresql_where=...)` also works and is preferred if
autogenerate round-trips it cleanly.

### Foreign keys

| Table | Column | References | On delete |
|---|---|---|---|
| exercise_attributes | exercise_id | exercises.id | CASCADE |
| exercise_substitutions | from_exercise_id | exercises.id | CASCADE |
| exercise_substitutions | to_exercise_id | exercises.id | CASCADE |
| training_profiles | user_id | users.id | CASCADE |
| training_programmes | user_id | users.id | CASCADE |
| programme_days | programme_id | training_programmes.id | CASCADE |
| planned_sessions | user_id | users.id | CASCADE |
| planned_sessions | programme_day_id | programme_days.id | SET NULL |
| planned_sessions | session_id | workout_sessions.id | SET NULL |
| planned_sessions | generation_id | ai_generations.id | SET NULL |
| prescribed_exercises | planned_session_id | planned_sessions.id | CASCADE |
| prescribed_exercises | exercise_id | exercises.id | **RESTRICT** |
| prescribed_exercises | replaced_with_exercise_id | exercises.id | **RESTRICT** |
| readiness_checkins | user_id | users.id | CASCADE |
| ai_generations | user_id | users.id | CASCADE |

### Check constraints

All named `ck_<table>_<rule>` so a violation names itself in the error. The
full list is in §3 per table; the migration creates them inline with
`op.create_table`, not as a second pass.

### Downgrade order

Exact reverse — children before parents:

`prescribed_exercises` → `planned_sessions` → `readiness_checkins` →
`ai_generations` → `programme_days` → `training_programmes` →
`training_profiles` → `exercise_substitutions` → `exercise_attributes`

Indexes drop with their tables; no explicit `drop_index` needed except the
partial unique index if created via raw SQL, which drops with the table anyway.

### Confirmations

- **No existing nutrition table is altered.** The migration contains zero
  references to `food_items`, `food_aliases`, `meal_logs`, `recipes`, or any
  other nutrition table.
- **No protected column is touched:** not `gtin14`, `name_normalized`,
  `barcode`, `name`, `names_i18n`, `search_text`, `source_licence`,
  `verification_tier`.
- **No existing workout table is altered:** not `exercises`,
  `workout_sessions`, `set_logs`, `strength_snapshots`.
- **No data backfill.** The migration contains no `INSERT`, no `UPDATE`, no
  `op.execute` carrying DML. All nine tables are created empty. Seeding
  `exercise_attributes` for the 874 existing exercises is a **separate
  script**, separately reviewed, and is not part of this migration.
- **No `create_all`.** Noted because `db.py` still calls it at startup and it
  silently creates missing tables — a known wart tracked separately. The
  migration is the source of truth; `create_all` must not be the thing that
  creates these tables in any environment.

---

## 9. Scratch testing

Reuse the existing harness in `tests/test_migrations.py`: `_scratch_database()`
creates a throwaway database named `trace_migtest_<hex>` and asserts that
prefix before every destructive step. **No test in this plan connects to
`trace`.**

New file: `tests/test_workout_migration.py`.

| # | Test | Asserts |
|---|---|---|
| 1 | **Upgrade** | From `e4f7b0d25c63`, upgrade to head creates exactly the nine tables. |
| 2 | **Downgrade** | Downgrade back to `e4f7b0d25c63` drops exactly those nine and leaves the revision at `e4f7b0d25c63`. |
| 3 | **Round trip** | upgrade → downgrade → upgrade is clean; no residue, no duplicate-object error. |
| 4 | **Indexes and constraints exist** | Query `pg_indexes` / `pg_constraint` for every entry in §8's tables, by name. Named, not counted. |
| 5 | **Partial unique index bites** | Two active programmes for one user → `IntegrityError`. One active + one archived → fine. |
| 6 | **Valid fixtures insert** | A full graph — profile, programme, 4 days, planned session, 5 prescriptions — inserts cleanly. |
| 7 | **Invalid fixtures rejected** | Parametrised over every CHECK: `sets=0`, `sets=13`, `rep_min > rep_max`, `rep_max=51`, `target_rir=7`, `rest_seconds=10`, `days_per_week=8`, `day_index=7`, `energy=6`, `energy=0`, `suggested_weight_kg=0`, bad `status`, `generated_by='template'` with a `generation_id`, `status='replaced'` with null `replaced_with_exercise_id`, `status='archived'` with null `archived_at`. Each raises. |
| 8 | **Ownership isolation** | User B cannot read or write any of user A's rows through any service function; every attempt yields 404, never 403, and never a row. Run per table. |
| 9 | **Programme archival** | Activating a new programme archives the old one in the same transaction; both survive; `archived_at` is set; a rolled-back activation leaves the original active. |
| 10 | **Planned→performed linking** | `/start` creates one `workout_sessions` row and sets `session_id`; calling it twice returns the same session id and creates no second row; deleting the workout session nulls `session_id` and leaves the plan. |
| 11 | **Exercise deletion restricted** | Deleting an exercise referenced by `prescribed_exercises` raises; deleting one referenced only by `exercise_attributes` / `exercise_substitutions` cascades cleanly. Both directions asserted. |
| 12 | **Idempotent generation** | Two `POST /planned-sessions` for the same `(user, date, programme_day)` → 201 then 200, one row. |
| 13 | **Deterministic ordering** | Generating the same programme twice from the same profile produces byte-identical `order_index` sequences. Same property the alias generator was held to. |
| 14 | **Unattributed exercise never prescribed** | An exercise with no `exercise_attributes` row is absent from every generated session. |
| 15 | **Nutrition-table invariance** | Before and after upgrade **and** after downgrade: `food_items` and `food_aliases` row counts and a checksum over the eight protected columns are unchanged. Also assert `information_schema.columns` for both tables is byte-identical across the migration. |

Test 15 is the one that would catch a mistake nobody expected, and it is cheap.
It is the direct descendant of the protected-column fingerprinting used during
the alias import.

Existing tests must keep passing unchanged — the six workout test files
(~1,509 lines) are the regression guard proving the recording layer did not
move.

---

## 10. Decisions

Items 10.1–10.7 are **approved and binding**. They were open when this
document was first written; they are recorded here as settled so that the
implementation has one place to check rather than a conversation to remember.
§10.8 holds what genuinely remains open — all of it privacy and legal
implementation detail, none of it schema-affecting.

### 10.1 Generated workouts are persisted — APPROVED

A generated programme is written to `training_programmes` / `programme_days`,
and a generated session to `planned_sessions` / `prescribed_exercises`. It is
not recomputed on read.

This is what makes a plan something a user can rely on mid-week, makes "what
did the app tell me to do?" answerable after the fact, and makes AI output
auditable at all. The alternative — regenerating on demand — was rejected:
it would make `prescribed_exercises` pointless and collapse the whole schema
below `planned_sessions`.

### 10.2 A deload is recommended, never applied — APPROVED

The system may **recommend** a deload. It may not change the programme until
the user confirms. A recommendation the user ignores leaves the programme
exactly as it was.

`deload_events` remains deferred, but this decision fixes its shape when it
lands: it needs to record who initiated the recommendation *and* the user's
confirmation, because "we suggested it" and "they accepted it" are different
facts and only the second may alter a programme.

### 10.3 An invalid AI `exercise_id` rejects the entire response — APPROVED

If any `exercise_id` in an AI response is malformed, missing, absent from the
catalogue, or references an exercise the requesting user is not entitled to,
**the whole response is rejected.** The system falls back to deterministic
template generation.

The invalid response **must not be silently repaired, dropped, or
substituted.** Not the offending exercise, not the session around it. A model
that hallucinated one identifier may have reasoned badly about the rest, and a
five-exercise plan minus its main lift is not the plan the model designed — it
is a new plan nobody reviewed. Refusing to answer beats answering wrong, which
is project non-negotiable #3.

The rejection is recorded in `ai_generations` with `validation_status =
'rejected'` and a `rejection_reason`, so that a silent fallback is still an
auditable event rather than an invisible one.

### 10.4 `program_type` and `ai_enabled` are separate switches — APPROVED

They are **not** consolidated. Each answers a different question:

| Field | Question it answers | Scope |
|---|---|---|
| `users.program_type` | How does this user train with us overall? | Broad training reference — collaborative / coached / manual |
| `training_profiles.ai_enabled` | May we generate programming with a model? | A specific opt-in for AI generation |

**`ai_enabled = false` disables AI generation regardless of `program_type`.**
The opt-in is the narrower and stricter of the two, and the narrower one wins.
No value of `program_type` re-enables AI generation for a user who declined
it.

**Deterministic template programming remains fully available when AI is
disabled.** Turning AI off costs a user the model, not the feature — they
still get programmes, split generation, progression and the whole mobile flow.
This is what makes the opt-in a real choice rather than a threat.

### 10.5 Readiness check-ins are optional and user-controlled — APPROVED

Check-ins are **optional**: the user is never blocked from training by an
unanswered questionnaire, and every score is nullable so a partial answer
stays distinguishable from a low one. They are **user-controlled**: the user
may view and delete their own readiness history.

They are **privacy-sensitive** — pain, sleep and stress are health data in a
way a bench-press number is not — and treated as such throughout §11.

They are **deferred from the deterministic MVP.** The table ships and the
questionnaire may collect, but nothing in the first release reads it to alter
a programme.

Retention duration and consent wording remain open — see §10.8.

### 10.6 Raw AI responses are not stored indefinitely — APPROVED

| Outcome | What is stored |
|---|---|
| **Accepted** | The validated, structured output and its provenance — the normalised `prescribed_exercises` rows plus `ai_generations.model`, `prompt_digest`, `latency_ms`, `validation_status`. **Not** permanent raw output. |
| **Rejected** | The raw response **may** be retained temporarily, under a bounded retention window, because a rejection nobody can inspect is a bug report with the evidence deleted. |

`ai_generations.raw_response` therefore holds rejected payloads within their
retention window and is otherwise NULL. `prompt_digest` — never the prompt —
answers the only question this table needs to answer, without creating a
second permanent store of health data.

The exact retention duration is open — see §10.8.

### 10.7 The MVP is deterministic, beginner-safe, and educational — APPROVED

Three properties, each binding on the first release:

- **Deterministic.** Rules in, programme out. No model, no network dependency,
  no prompt. The same profile produces the same programme, which is what makes
  it testable in CI and reviewable by a human.
- **Beginner-safe.** A new user with no training history receives **bodyweight
  or standard-dumbbell programming** — never a barbell prescription derived
  from a strength history that does not exist. `suggested_weight_kg` stays
  NULL until there is a basis for it, and the UI renders that as an em dash
  rather than a number.
- **Educational.** A prescription explains itself — the rep range, the target
  RIR and the progression rule are shown, not just a number to hit.

**Manual logging is always available and never gated.** A user can log a
workout with no programme, no planned session and no profile, exactly as they
can today. Generated programming is something the app offers, never something
it requires; `POST /sessions/{id}/sets` keeps working untouched.

### 10.8 STILL UNRESOLVED — privacy and legal

These block features that read or write `readiness_checkins` and
`ai_generations`. Neither is schema-affecting, and both tables ship empty.

1. **Exact retention duration for rejected raw AI responses.** §10.6 fixes
   that the window is bounded; it does not fix the number. Needs a privacy
   decision, and the deletion job that enforces it.
2. **Retention and export treatment of readiness data.** How long check-ins
   are kept, whether they are included in an account export, and whether
   deletion is hard or soft. The current implementation assumes
   cascade-on-account-delete plus owner-initiated hard delete — a placeholder
   until this is answered.
3. **Consent wording for the readiness health fields.** A pain-and-stress
   questionnaire sitting next to a feature that gives training advice may fall
   under a stricter category than food-and-workout logging in some
   jurisdictions. Whether that needs separate consent, a distinct
   privacy-policy clause, or in-context disclosure — and what it must say — is
   a question for a lawyer. The plan already requires *"Do not present
   AI-generated training advice as medical advice."*

**Nothing in this document asserts compliance.**

---

## 11. Security and privacy

### Ownership enforcement

Every query filters on `user_id`, directly or through a join to the owning row.
Client-supplied ids are never trusted as scoping — a `programme_id` in a path
is a claim to be verified, not a filter. Not-found and not-owned both return
404 so the API does not confirm the existence of other users' rows.
Test 8 in §9 exists to make a regression here loud.

### AI output validation

Model output is untrusted input reaching a database. Before anything is stored:
every `exercise_id` is looked up and must exist; every numeric field must pass
the same CHECK ranges the database enforces (validated in the service so the
error is legible, enforced in the database so a bypass still fails); the
response shape is parsed against a strict schema with unknown fields rejected;
and the whole thing is validated **before** display, not after — a rejected
plan is never rendered "pending validation".

Ids are bound as parameters, never interpolated. The CHECK constraints in §3
are the backstop that makes a validation bug a failed insert instead of bad
advice.

### Health-sensitive data

Three fields are health-sensitive: `training_profiles.limitations`,
`readiness_checkins.pain_note`, and the four readiness scores. They are:
never logged; never included in error messages or tracebacks; never sent to an
AI provider until the consent item in §10.8 is resolved; and excluded from any analytics
event.

### Raw-response storage risk

`ai_generations.raw_response` is the highest-risk column in this design, which
is why it is nullable and unused at launch. Whenever it is populated it becomes
a second copy of health data with its own retention clock, its own export
obligation and its own presence in every backup.

Per §10.6 it is bounded on both sides: an **accepted** response never lands
here at all — the validated structured output and its provenance are what
persist — and a **rejected** response may be held only inside a bounded
retention window. `prompt_digest` exists so the common debugging question —
"same prompt?" — is answerable without storing the prompt. The retention
number itself is still open (§10.8), and the deletion job that enforces it
must land with the feature, not after it.

### Logging restrictions

Programming code logs ids and counts, never content. Specifically: no prompt
text, no `raw_response` body, no `limitations`, no `pain_note`, no readiness
scores. This matters more than usual here — the `test_migrations.py`
password-in-traceback issue already on the backlog is the same class of bug:
sensitive values reaching an error path nobody reviewed.

### Backup and deletion implications

These tables land in `pg_dump` output alongside everything else. The existing
rule stands: **backups contain user data and stay outside the repository.**
Once readiness data exists, a backup is a health-data store, and any "delete my
readiness history" guarantee is bounded by backup retention — which needs
stating honestly in whatever policy §10.8 produces rather than being promised
absolutely.

---

## 12. Implementation phases

Seven commits, each independently reviewable and independently revertible.

| # | Commit | Contents | Gate |
|---|---|---|---|
| 1 | **Design document** | This file only. | Approval of §10.1–10.4 |
| 2 | **Models and migration** | Nine SQLModel classes + one Alembic revision. No services, no routes. | Scratch tests §9 pass; `trace` untouched |
| 3 | **Backend services and endpoints** | `services/programming.py` (pure), routers, schemas. | `tsc`-equivalent clean; existing 12 endpoints unchanged |
| 4 | **Backend tests** | `test_workout_migration.py`, `test_programming.py`, `test_programming_api.py`. | All existing tests still pass |
| 5 | **Mobile UI** | Four screens + train-tab card. | `npx tsc --noEmit` = 0; `design-reviewer` on changed files |
| 6 | **Mobile tests** | Jest for the profile flow, session rendering, empty/error states. | Green |
| 7 | **AI programming** *(later)* | Provider integration, prompt, validation, `ai_generations` writes. | §10.8 resolved first |

Commits 2 and 3 are deliberately separate: a migration reviewed on its own is a
migration actually read. Commit 4 follows 3 rather than preceding it because
the endpoints are the spec's surface — but the *pure* service tests are written
first inside commit 4, per project convention that a behaviour change ships with
a test that would fail without it.

Seeding `exercise_attributes` for the 874 existing exercises is **not in this
list**. It is a data task, needs its own review of the classifications, and
follows commit 2.

---

## 13. Rollback

### Before applying anything

A fresh `pg_dump` is required immediately before the migration runs, even
though the migration is purely additive. Current backup on record:
`trace_backup_20260823_155514.dump` (60.4 MB), taken at the nutrition
checkpoint. If any writes occur between then and the migration, take a new one.

Dump command follows the pattern already used: custom format, timestamped
filename **outside the repository**, no `--clean`, no `--create`, credentials
supplied via environment and never printed.

### Downgrade

```
cd services/api
alembic downgrade e4f7b0d25c63
```

### Verification after downgrade

1. `alembic current` reports `e4f7b0d25c63`.
2. All nine tables are absent from `information_schema.tables`.
3. `food_items` = 578,773; `food_aliases` = 1,353.
4. `gtin14` populated = 504,850; `name_normalized` populated = 578,772.
5. `exercises` = 874; `workout_sessions` = 5; `set_logs` = 8.
6. The eight protected `food_items` columns checksum to their pre-migration
   values.
7. `python -m pytest tests/ -q` is green.

### Data-loss implications

**Downgrade is lossless with respect to everything that existed at
`e4f7b0d25c63`** — the migration alters nothing, so reversing it removes only
what it added.

It is **not** lossless with respect to workout-programming data created after
the upgrade. Dropping the nine tables destroys every training profile,
programme, planned session, prescription, readiness check-in and AI generation
record. There is no partial downgrade and no automatic export.

Consequences, stated plainly:

- Downgrading in development, where these tables are empty or synthetic, is
  free.
- Downgrading in production after users have created programmes destroys real
  user data and **must** be preceded by a fresh dump — the pre-migration backup
  will not contain it.
- Nutrition data is unaffected in every case. `food_items` and `food_aliases`
  are never read, written, altered or dropped by this migration or its reverse.
