# Exercise catalogue expansion — proposal

**Status:** proposal for review. No code, no seed rows, no migration.
**Supersedes:** the "classify the existing 874" seeding plan, which is withdrawn.

**Baseline**

| | |
|---|---|
| HEAD | `c54f371` |
| Database | `trace` on `127.0.0.1:5432` |
| Alembic revision | `e4f7b0d25c63` — workout migration `f6a9c2e47d85` **not applied** |
| `exercises` | 874 |
| `exercise_attributes` | table does not exist in `trace` |
| `exercise_substitutions` | table does not exist in `trace` |

Everything below rests on a read-only export of `exercises` taken under
`SET TRANSACTION READ ONLY`. Nothing was written.

---

## 1. What the catalogue actually is today

### 1.1 Counts

**874 rows.** Hygiene is better than expected: **0 duplicate ids, 0 exactly
duplicate names, 0 null `muscle_group`, 0 null `equipment`, 0 blank names.**

| Equipment | n | | Muscle group | n |
|---|---:|---|---|---:|
| barbell | 187 | | legs | 246 |
| dumbbell | 149 | | shoulders | 137 |
| cable | 126 | | back | 125 |
| other | 110 | | chest | 98 |
| bodyweight | 100 | | core | 90 |
| machine | 90 | | triceps | 82 |
| kettlebell | 53 | | biceps | 65 |
| band | 20 | | forearms | 26 |
| medicine_ball | 17 | | neck | 5 |
| ezbar | 11 | | | |
| exercise_ball | 8 | | | |
| smith | 3 | | | |

`is_compound`: 538 true / 336 false. `secondary_muscles` empty on **371** rows;
`aliases` empty on **447**.

### 1.2 Which required fields already exist

| Field | Where it lives today | Status |
|---|---|---|
| `name`, `muscle_group`, `secondary_muscles`, `equipment`, `is_compound`, `aliases` | `exercises` | **exists, populated** |
| `movement_pattern`, `exercise_class`, `is_unilateral`, rep/rest/fatigue defaults | `exercise_attributes` | **defined in the model and in migration `f6a9c2e47d85`, but the table does not exist in `trace` and holds no rows anywhere** |
| substitution edges | `exercise_substitutions` | same — defined, unapplied, empty |
| **manufacturer** | — | **does not exist anywhere** |
| **machine family** | — | **does not exist anywhere** |
| **model / model number** | — | **does not exist anywhere** |
| **difficulty** | — | **does not exist anywhere** |
| **provenance / source** | — | **does not exist anywhere** |
| **review status** | — | **does not exist anywhere** |
| **beginner suitability** | — | inferred today from equipment only — see §5 |

So: pattern/class/unilateral are *designed* but unpopulated; manufacturer,
difficulty, provenance and review status are *entirely absent*.

### 1.3 Duplicates and near-duplicates

Exact duplicates: none. Looser matching finds **13 groups worth a human call**:

**Same words, different order (4):**
`Upright Cable Row` / `Cable Upright Row` · `Smith Machine Incline Bench Press` /
`Incline Smith Machine Bench Press` · `Overhead Rope Triceps Extension` /
`Triceps Overhead Extension with Rope` · `High-to-Low Cable Fly` /
`Low-to-High Cable Fly` ← **not a duplicate**, these are genuinely different
movements and the detector is wrong about this one.

**Singular/plural or punctuation variants (9):**
`Standing Calf Raise`/`Raises` · `Cable Shrug`/`Shrugs` · `Donkey Calf
Raise`/`Raises` · `Lying Leg Curl`/`Curls` · `Machine Preacher Curl`/`Curls` ·
`Rack Pull`/`Pulls` · `Concentration Curl`/`Curls` · `Squat with Bands`/`Squats
- With Bands` · `Machine Biceps Curl`/`Machine Bicep Curl`.

That last pair (`Biceps` vs `Bicep`) is a spelling variant, not two exercises.

### 1.4 Branded content already embedded in canonical names

**24 rows carry a manufacturer inside the canonical name** — 23 `Smith`, 1
`Hammer Strength`. This is the anti-pattern §4 exists to stop: the brand is in
the `name` column with no structured field behind it, so it cannot be filtered,
substituted, or hidden from a user whose gym has no Smith machine.

Note `equipment` disagrees with itself here: 20 of the branded rows are filed
under `machine`, only 3 under `smith`.

### 1.5 Coverage gaps — the finding that matters

Movement-pattern coverage, approximated by name matching:

```
equipment          carry   pull_v   push_v   push_h   pull_h    hinge    squat   isol.  UNMATCHED
bodyweight             0        5        0       13        0        3        4      27         48
dumbbell               1        0        4        8       11        4        9      74         38
barbell                0        0        5       15       17       22       33      35         60
cable                  0       15        3       11       17        0        0      52         28
machine                0        0        4       17        9        4       18      26         15
kettlebell             0        0        5        4        4        1        5       0         34
band                   0        0        1        1        1        2        0       3         12
other/misc             3        3        0        6        5        5        4      17        103
```

**338 of 874 rows (39%) match no movement-pattern rule at all.** The `other`
bucket is the worst: 110 rows holding rope climbs, sled work, ring dips, ab
wheels and Atlas stones under one meaningless label.

Restricted to what a beginner may currently be given (bodyweight + dumbbell,
249 rows):

```
carry          1
pull_v         5
push_v         4
hinge          7
pull_h        11
squat         13
push_h        21
isolation    101
UNMATCHED     86
```

**This is the blocker, and it is not a classification problem.** Even with
perfect classification of all 874, a beginner programme would be drawing from
**one** carry, **four** vertical presses and **five** vertical pulls. The
catalogue is isolation-heavy and structurally thin exactly where a beginner
template needs depth. Classifying what exists cannot manufacture the missing
movements — which is why the previous plan was the wrong shape.

---

## 2. Reconciling with the plan and design doc

`WORKOUT_DATABASE_UPGRADE_PLAN.md` asks for branded-machine substitution
("PRIME hip thrust" → generic) and equipment-aware programming.
`WORKOUT_SCHEMA_DESIGN.md` §3.1–3.2 provides `exercise_attributes` and
`exercise_substitutions` for exactly that, and §10.7 fixes the MVP as
deterministic, beginner-safe and educational.

Two things follow that this proposal must honour:

1. **Generic first, branded second.** A branded machine is only ever a *variant
   of* a generic movement. The generic row is the programmable unit.
2. **`exercise_attributes` stays the gate.** Generation joins it inner, so an
   exercise without reviewed attributes is simply not a candidate. Expansion
   does not change that; it fills the table with reviewed rows.

---

## 3. Proposed target catalogue

Numbers below are **targets for a curated set, not data I hold.** They are
sized from the coverage gaps in §1.5.

### 3.1 Tiers

| Tier | What | Records | Attributed? | Prescribable? |
|---|---|---:|---|---|
| **0** | The existing 874 | 874 | No | No — remain unattributed legacy |
| **1** | Curated generic core | **~185 new** | Yes, reviewed | Yes |
| **2** | Generic machine movements | **~55 new** | Yes, reviewed | Yes, when equipment allows |
| **3** | Manufacturer-specific variants | **0 until sourced** | N/A | Never required |

**Target after Tier 1+2: ~1,114 rows, of which ~240 are attributed and
prescribable.** The other 874 stay exactly as they are — untouched, unattributed,
and invisible to the generator. Existing rows are **not** renamed, merged, or
deleted by this plan.

Tier 1 deliberately creates *new canonical rows* rather than retrofitting
attributes onto old ones. Reasons: the old names are inconsistent
(`Squats - With Bands`), 39% match no pattern, and a curated row can carry
provenance and a reviewed classification from birth. Retrofitting is possible
later, per row, as a separate reviewed exercise.

### 3.2 Tier 1 by movement pattern and equipment

Every cell is a target count of curated generic exercises.

| Pattern | bodyweight | dumbbell | barbell | cable | band | kettlebell | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| squat | 8 | 6 | 5 | 0 | 2 | 3 | 24 |
| hinge | 6 | 6 | 5 | 2 | 2 | 4 | 25 |
| push_horizontal | 8 | 6 | 5 | 4 | 2 | 1 | 26 |
| push_vertical | 4 | 5 | 4 | 2 | 2 | 2 | 19 |
| pull_horizontal | 5 | 6 | 4 | 5 | 2 | 1 | 23 |
| pull_vertical | 5 | 2 | 0 | 5 | 2 | 0 | 14 |
| carry | 0 | 4 | 1 | 0 | 0 | 3 | 8 |
| isolation (incl. core) | 12 | 14 | 4 | 12 | 4 | 0 | 46 |
| **Total** | **48** | **49** | **28** | **30** | **16** | **14** | **185** |

The shape is deliberate: **97 of 185 are bodyweight or dumbbell**, and every
pattern including carry and vertical press has real depth there. That is what
makes a beginner programme possible.

### 3.3 By difficulty — a filter that does not exist today

| Difficulty | Target | Meaning |
|---|---:|---|
| beginner | ~95 | Learnable from a written cue; no spotter, no rack, low technique floor |
| intermediate | ~70 | Assumes basic competence in the pattern |
| advanced | ~20 | Skill or heavy loading; never auto-prescribed by the MVP |

### 3.4 By muscle group (Tier 1 target)

legs ~46 · back ~32 · chest ~26 · shoulders ~26 · core ~24 · triceps ~13 ·
biceps ~12 · forearms ~6.

Compared with today's catalogue this rebalances *away* from isolation
(currently 101 of 249 beginner-eligible rows) toward structural movements.

### 3.5 Manufacturer counts

**Zero. Deliberately, and this is the important line in the document.**

I have no sourced manufacturer catalogue, and I will not generate one.
Producing plausible-looking model names — "Hammer Strength ISO-Lateral Row",
"Life Fitness Insignia Leg Press" — would be **fabricated product data
presented as a catalogue**, and a user whose gym has a different model would be
told, by us, that they have equipment they do not have.

Tier 3 therefore ships empty and stays empty until you supply, or point me at,
a real source. The schema in §4 is designed so that Tier 3 can be added later
**without touching Tier 1**, and so that the beginner generator never depends
on it.

The only manufacturer strings in the system today are the 24 legacy names in
§1.4, and those are evidence of the problem rather than a source.

---

## 4. Where manufacturer belongs

### 4.1 Options considered

| Option | Verdict |
|---|---|
| **Columns on `exercises`** | **Rejected.** Every non-machine row carries three permanently-null columns, and it is an `ALTER` on the one table 874 rows already depend on. |
| **In the canonical `name`** | **Rejected.** This is the status quo for 24 rows and is exactly what makes them unfilterable and unsubstitutable. |
| **`exercise_equipment` join table** | Rejected as the primary home — it models *which equipment an exercise needs*, which `equipment` already answers. Useful later for multi-equipment exercises; not the manufacturer question. |
| **`machine_variants` metadata table** | **Recommended.** |

### 4.2 Recommended: `machine_variants`

A branded machine is a *variant of* a generic exercise. That is a one-to-many
relationship from a generic row, which is a table, not a column.

```
machine_variants
  id                  PK
  generic_exercise_id FK -> exercises.id            ON DELETE RESTRICT
  manufacturer        text        e.g. 'Hammer Strength'
  machine_family      text  null  e.g. 'ISO-Lateral'
  model               text  null
  display_name        text        what a user sees in a gym
  provenance          text        REQUIRED — see 5.2
  source_url          text  null
  review_status       text        'unreviewed' | 'approved' | 'rejected'
  created_at, updated_at
  UNIQUE (manufacturer, display_name)
  CHECK  review_status IN (...)
  CHECK  manufacturer <> ''
```

Properties that matter:

- **Purely additive.** `exercises` is not altered. Existing rows are untouched.
- **`RESTRICT`**, matching `prescribed_exercises` — deleting a generic exercise
  that branded variants point at must fail loudly.
- **`provenance` is NOT NULL.** A variant with no source cannot be inserted, so
  fabricated rows are unrepresentable rather than merely discouraged.
- **The generator never reads this table.** Programming selects generic
  exercises; the variant is display sugar and a substitution source.

### 4.3 Attributes gain the missing metadata

A follow-up migration (not an amendment of the committed `f6a9c2e47d85`) adds
to `exercise_attributes`:

```
  difficulty       text  NOT NULL DEFAULT 'intermediate'
                         CHECK IN ('beginner','intermediate','advanced')
  beginner_safe    bool  NOT NULL DEFAULT false
  provenance       text  NOT NULL DEFAULT 'legacy'
  source_url       text  NULL
  review_status    text  NOT NULL DEFAULT 'unreviewed'
                         CHECK IN ('unreviewed','approved','rejected')
  reviewed_at      timestamptz NULL
  reviewed_by      text  NULL
```

`beginner_safe` defaulting to **false** and `review_status` to **unreviewed**
means a row inserted by any future path is non-prescribable until someone says
otherwise. The safe state is the default state.

---

## 5. Provenance, and the two filters

### 5.1 Every proposed record carries

`id` (stable, slug-style, e.g. `gen-db-goblet-squat`) · `canonical_name` ·
`equipment` · `muscle_group` + `secondary_muscles` · `movement_pattern` ·
`exercise_class` · `is_unilateral` · `difficulty` · `beginner_safe` ·
`provenance` · `source_url` · `review_status` · substitution edges.

IDs are slugs, not UUIDs, so a seed file is diffable and a reviewer can see
that `gen-db-goblet-squat` did not silently become a different row.

### 5.2 Provenance vocabulary

| Value | Meaning |
|---|---|
| `curated` | Written for Trace by a named reviewer. The whole of Tier 1. |
| `legacy` | The pre-existing 874. Unreviewed by definition. |
| `manufacturer_supplied` | From a manufacturer's own published material — requires `source_url`. |
| `user_submitted` | Not in scope now; reserved so it cannot later be conflated with curated. |

**No proposed record may claim a provenance it does not have.** A Tier 1 row is
`curated` because a human wrote and reviewed it — not because a rule inferred it.

### 5.3 Beginner safety and equipment availability are SEPARATE filters

This corrects a real shortcut in the shipped code.
`services/programming.beginner_equipment()` currently restricts to
`{bodyweight, dumbbell}` and uses that as a proxy for beginner safety. Those are
two different questions:

- *Is this movement appropriate for a novice?* → `difficulty` / `beginner_safe`
- *Can this person do it in their gym?* → `equipment` ∩ `training_profiles.equipment`

Conflating them means a beginner with a full gym can never be given a simple
cable row, while a dumbbell snatch would sail through. Post-expansion the
selector should apply both filters independently:

```
candidates = attributes
    WHERE review_status = 'approved'
      AND beginner_safe                       -- safety
      AND equipment ∈ user's available set    -- availability
```

Simple cable and generic machine work then becomes available to beginners, and
**no manufacturer-specific record is ever required for a beginner programme** —
Tier 3 is excluded from beginner selection by construction, since a branded
variant is not itself a prescribable exercise.

---

## 6. Quality controls

Run over the proposal artifact before any insert; every check names offending
rows rather than returning a count.

| # | Check | Action |
|---|---|---|
| 1 | Duplicate canonical name (exact, case-folded) | Reject |
| 2 | Duplicate token-bag against Tier 0 **and** within Tier 1 | Review — §1.3 shows the detector produces false positives |
| 3 | Spelling/plural variants (`Bicep`/`Biceps`) | Review |
| 4 | Manufacturer name inside a canonical name | **Reject** — it belongs in `machine_variants` |
| 5 | Missing `muscle_group` | Reject |
| 6 | Missing `equipment` | Reject |
| 7 | Missing `movement_pattern` or `exercise_class` | Reject |
| 8 | Value outside the allowed pattern/class vocabulary | Reject |
| 9 | Rep/rest/fatigue outside the CHECK bounds | Reject |
| 10 | `beginner_safe` true on an `advanced` row | Reject — contradiction |
| 11 | Self-substitution (`from == to`) | Reject — `ck_exsub_not_self` also catches it |
| 12 | Substitution cycle (A→B→A, or longer) | Reject — graph walk, not just pairwise |
| 13 | Substitution to a non-existent or unreviewed exercise | Reject |
| 14 | Substitution crossing movement patterns | Review |
| 15 | `manufacturer_supplied` with no `source_url` | **Reject — unsupported manufacturer claim** |
| 16 | Any manufacturer string not in the supplied source set | **Reject** |

Checks 4, 15 and 16 are the anti-fabrication controls, and they are rejections
rather than warnings on purpose.

---

## 7. Proposed seed-file format

Two files under `services/api/data/`, both hand-reviewable, both diffable:

**`exercises_generic.yaml`** — Tier 1 + 2, one document per exercise:

```yaml
- id: gen-db-goblet-squat
  canonical_name: Goblet Squat
  equipment: dumbbell
  muscle_group: legs
  secondary_muscles: [glutes, core]
  movement_pattern: squat          # long form: ck_exattr_movement_pattern
  exercise_class: compound
  is_unilateral: false
  difficulty: beginner
  beginner_safe: true
  default_rep_min: 6
  default_rep_max: 10
  default_rest_seconds: 150
  fatigue_cost: 5
  provenance: curated
  review_status: approved
  reviewed_by: <name>
  substitutions:
    - to: gen-bw-bodyweight-squat
      reason: equipment
      rank: 1
```

**`machine_variants.yaml`** — Tier 3, empty until sourced:

```yaml
# EMPTY BY DESIGN. Add a row only with a real source; `provenance` and
# `source_url` are required and validated. Do not add a model from memory.
[]
```

YAML rather than JSON for the review pass — comments survive, and a reviewer
can leave a note next to a row they questioned. A deterministic JSON artifact
is generated *from* these for the importer, exactly as the alias work did.

**Movement-pattern vocabulary — one thing needs your decision.** Your brief
listed `push_h` / `push_v` / `pull_h` / `pull_v`. The committed CHECK constraint
`ck_exattr_movement_pattern` in `f6a9c2e47d85` accepts only the long forms
`push_horizontal` / `push_vertical` / `pull_horizontal` / `pull_vertical`. The
seed format above uses the long forms so rows are insertable as-is. Switching to
the short forms is possible but needs a follow-up migration to replace that
constraint. **Say which you want.**

---

## 8. Tests required

**Pure (no database):**
1. Seed file parses; every required field present.
2. IDs unique and stable-slug shaped.
3. Movement pattern and class ∈ allowed vocabularies.
4. Rep/rest/fatigue inside the CHECK bounds — asserted against the constants in
   `models.py`, not re-typed.
5. `beginner_safe` ⟹ `difficulty == 'beginner'`.
6. No manufacturer string in any canonical name.
7. Substitution graph: no self-edge, no cycle, all targets exist.
8. Coverage: every movement pattern has ≥ N beginner-safe bodyweight/dumbbell
   options — the test that would have caught today's "one carry, four vertical
   presses".
9. Deterministic: parsing twice yields identical output.

**Scratch database:**
10. Seeding then generating produces a valid beginner programme.
11. A beginner never receives an `advanced`, `unreviewed` or branded exercise.
12. A beginner with only bodyweight still gets a complete session.
13. Equipment and beginner-safety filters are independently effective — a
    full-gym beginner gets cable work; a full-gym *novice* still gets no
    barbell snatch.
14. `machine_variants` rows never enter generation.
15. Nutrition invariance across the seed migration.

**Regression:** the existing 97 programming tests and 171 workout tests must
pass unchanged.

---

## 9. Rollback

| Stage | Rollback |
|---|---|
| Schema (`machine_variants`, attribute columns) | `alembic downgrade` — additive, so lossless for everything that predates it |
| Tier 1/2 seed rows | All carry `provenance='curated'` and slug ids prefixed `gen-`; deletion is a single scoped `DELETE ... WHERE provenance='curated'`, blocked by `RESTRICT` if any prescription references them |
| Prescriptions referencing seeded rows | `RESTRICT` means rollback **fails loudly** rather than erasing training history — intended |
| Tier 0 (the 874) | Never modified, so nothing to roll back |
| Nutrition | Never touched |

Dump before applying, as with every previous stage. Rollback after users have
built programmes on seeded exercises is **not** clean and should be treated as
forward-fix territory.

---

## 10. Open decisions

1. **Short vs long movement-pattern names** (§7) — long forms work today; short
   forms need a constraint migration.
2. **Manufacturer source.** Tier 3 stays empty until you supply one. What is it?
3. **Retrofit or leave Tier 0?** This plan leaves all 874 unattributed. The
   alternative is a per-row reviewed retrofit, which is a large manual pass.
4. **Target size.** ~185 curated rows is sized to fill the §1.5 gaps. Larger is
   more variety and more review; smaller risks repetitive programmes.
5. **Who reviews?** `reviewed_by` is required and there is currently no named
   reviewer.
6. **Cardio machines** appear in your equipment list but have no place in a
   hypertrophy template — separate `sports.py` concern, or in scope here?
7. **Mobility/warm-up** movements need a prescription shape (no RIR, often
   time-based) that `prescribed_exercises` does not currently express.
