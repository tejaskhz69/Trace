# AI gym trainer and workout programming

The workout system should function as a complete adaptive gym trainer.

It must not only display exercises or record completed sets. It should help
users decide: which exercises to perform today, which muscle groups to train,
how many exercises, the order, number of sets, repetition ranges, suggested
weight or effort, rest time, warm-up requirements, when to increase or reduce
difficulty, when to change the split, and when to reduce volume because of
fatigue, limited time, or cardio load.

The primary training goals are hypertrophy, progressive overload, consistent
long-term training, appropriate fatigue management, and safe practical
workouts that fit the user's time and equipment.

Do not present AI-generated training advice as medical advice. Include
warnings for pain, injury, medical conditions, pregnancy, and rehabilitation.
Encourage consultation with a qualified trainer or healthcare professional
where appropriate.

## Relationship to the existing systems

This section governs every other section. Three systems already read the same
data and this one must not contradict them.

**`adjudication.py` answers a different question.** It reads the user's three
most-trained lifts, computes Epley e1RM with a 3-week EWMA (α = 0.4), needs
`MIN_SESSIONS = 8`, and returns one of five verdicts about **whether the diet
is working**. The plateau detector in this document answers **whether one lift
is progressing**. Both are legitimate; they must never appear to disagree.

- Both read e1RM from a single shared implementation in
  `services/strength.py`. Neither computes its own.
- While adjudication returns `INSUFFICIENT_DATA`, the plateau detector must
  not surface plateau notices. Flagging one lift as stalled before the system
  can see anything is noise.
- Plateau copy is always scoped to the exercise, never to the programme or the
  diet.

**Exercises are movements; machines are stations.** See
`docs/10-exercise-and-station-model.md`. "PRIME chest press" is not an
exercise — it resolves by alias to `Chest Press Machine`, and the PRIME is a
`Station` of it. Nothing in this document may introduce manufacturer-level
exercise rows or a manufacturer column on `Exercise`.

**Catalogue size is a constraint, not a feature.** Because a verdict needs 8
sessions of a lift, every additional near-duplicate exercise lengthens the
time before any verdict is possible. Exercise selection must draw from a
curated subset, and rotation must be deliberate rather than incidental.

**Never add exercise calories to a calorie target** (invariant #1). Cardio and
training load inform *selection and recovery*, never the food target.

**Adherence-neutral** (invariant #7). A missed session, a skipped exercise or
a reduced-volume week is absorbed, not scored. No red, no streaks, no "you
missed 3 workouts". This applies to training exactly as it applies to food.

## User information for programming

Consider: training goal; current phase; gym days per week; available days;
preferred session duration; cardio frequency, duration and intensity; sports;
training age; experience; age; sex if offered; height and weight if available;
recovery quality; sleep; stress; soreness; energy; pain or injury limits;
available equipment; preferred and disliked exercises; previous performance;
recent muscle-group volume; recent exercise frequency; personal records; gym
schedule.

Do not require sensitive information. Allow every optional field to be skipped.

**Sleep, steps and recent cardio come from HealthKit or Health Connect where
connected. Never ask for data the app already has.**

## Cold start

A new user has no SetLog history, no e1RM, and no readiness baseline. Do not
present calibration guesses as knowledge.

- The first 2–3 sessions are explicitly calibration: conservative loads, wider
  rep ranges, and copy that says so — *"we're learning your numbers"*.
- No plateau evaluation, no progression rules and no deload logic until a
  baseline exists.
- Mirror the nutrition side's honesty: the first prescription is a starting
  point, and it becomes the user's own numbers as they log.

## Training split generation

Generate a split from the user's available days: full body, upper/lower,
push/pull/legs, upper/lower/full, push/pull, body-part split, glute-focused,
strength-and-hypertrophy, hybrid gym-and-cardio, home-and-gym, or custom.

Do not force a fixed split on every user.

- 2 days: full body.
- 3 days: full body or a push/pull/legs rotation.
- 4 days: upper/lower.
- 5 days: upper/lower plus a specialised session.
- 6 days: push/pull/legs, only when recovery supports it.

The recommendation must depend on experience, recovery, cardio, schedule and
goal — not only on the day count.

Use "body-part split" in user-facing copy, never "bro split".

## Cardio-aware programming

Adjust resistance volume and selection for total weekly cardio duration,
intensity, whether it precedes or follows lifting, modality, leg fatigue,
recovery demand, phase, and sport participation.

Avoid demanding leg training immediately before a long run, hard cycling
session or match unless the user chooses it.

When cardio volume is high: reduce redundant lower-body volume, avoid
duplicate exercises, preserve high-value compounds, use fatigue-aware
selection, schedule recovery, and explain the tradeoff.

**Cardio never becomes food calories.** The adaptive TDEE already contains
activity via the weight trend.

## Hypertrophy programming

Prioritise appropriate weekly sets per muscle group, useful frequency, stable
progressible exercises, suitable rep ranges, sufficient rest, practical range
of motion, controlled technique, proximity to failure, fatigue management, and
progressive overload.

**Weekly volume.** Use the public literature range — roughly **10–20 hard sets
per muscle group per week** for trained lifters, fewer for beginners — stated
as a range with wide individual variation, never as a prescription. Do not
reproduce any proprietary volume-landmark framework.

Vary rep ranges by exercise rather than assigning one range to everything:
heavy compounds ≈ 4–8; moderate compound and machine work ≈ 6–12; isolation
≈ 10–20; calves, abs and selected accessories flexible.

These are starting ranges, not rules. Do not claim one range is universally
optimal.

**Cover the strength curve.** Every movement in the catalogue carries a
resistance profile — `lengthened`, `mid` or `shortened`. A well-built week
includes at least one lengthened-biased movement per major muscle group, and
avoids stacking three shortened-biased exercises for the same muscle.

## Progressive overload system

Track progression per exercise using weight, reps, sets, rep quality, RPE,
RIR, tempo where available, range of motion, variation, station, previous
performance, technique notes and personal records.

Use double progression:

- Target 3 sets of 8–12.
- Hold the weight until every set reaches the top of the range at the planned
  RIR.
- Increase by the smallest available increment.
- Return to the bottom of the range.

Never increase weight automatically after a poor-quality or painful set.

Where the user reports missed reps, high RPE, low RIR, poor sleep, high
soreness, low energy, pain or reduced performance, the trainer may reduce
weight, sets, reps, complexity or total volume.

## Plateau detection and progression recovery

The trainer must detect plateaus and respond without blindly prescribing more
weight. A plateau is not one repeated workout or one failed set.

Treat a plateau as possible only when **all** of the following hold:

- The same exercise, or an explicitly equivalent movement, was performed.
- **The station and station profile are unchanged** (see below).
- At least 3 qualifying exposures.
- Spanning approximately 3–4 weeks.
- At least 80% of prescribed sets completed.
- No deload active.
- No pain or safety flag.
- No materially poor readiness signal explaining the result.
- No improvement in any tracked metric.

Track: top-set e1RM, total volume, reps at the same load, RIR at the same
load, completed sets, and rep quality where available. Read these from the
grouped `GET /strength/progress` series, which is already segmented by
`(exercise, station, station_profile)` — do not re-derive segmentation.

### Equipment comparability is a lookup, not a question

`SetLog` carries `station_id` and `station_profile`. If either changed between
exposures, return `not_comparable` automatically, with the reason stated in
plain terms — *"you moved from the PRIME row to the Hammer row"* — and do not
ask the user anything. A PRIME cam setting change is likewise a different
stimulus at the same load and segments the comparison.

### Do not classify as plateaued when

Fewer than 3 qualifying exposures; the exercise, station, setup or range of
motion changed materially; most prescribed sets were missed; the user was
deloading; reps at the same load are improving; e1RM is improving; volume is
improving; readiness, sleep, soreness, stress or recent sport and cardio load
explains it; or the exercise was intentionally replaced.

### Statuses

`insufficient_data`, `progressing`, `not_comparable`, `incomplete_execution`,
`deload_period`, `confounded`, `watch`, `confirmed_plateau`,
`persistent_plateau`, `safety_stop`.

Every assessment includes status, confidence, evidence sessions, baseline and
current performance, the metric that stopped improving, the reason, the
recommended next step, and whether confirmation is required. The user must be
able to see which sessions were considered.

### Response ladder

1. **Verify execution** — sets completed, reps, RIR/RPE, range of motion,
   tempo, station identity, kg/lb confusion, technique or setup change.
2. **Continue double progression** — if reps are rising within the range, hold
   the weight.
3. **Microload** — smallest increment the equipment actually supports. Never
   prescribe a load that cannot be loaded; consult the station's
   `stack_ranges` and `micro_adjust_kg`. For bodyweight or band work with no
   smaller increment, progress reps, tempo, range of motion, pause, leverage
   or an approved variation.
4. **Controlled adjustment, only after the user confirms** — add a set within
   safe volume limits, adjust the rep range, adjust rest, use controlled
   tempo, use an approved equivalent, or reduce fatigue from lower-priority
   work.
5. **Consider a deload** — recommend, never apply automatically; the user
   confirms; record whether system-recommended or user-initiated.
6. **Consider variation** — recommend a reviewed equivalent only when
   appropriate; preserve the original exercise and all history; create a new
   prescription or revision; never overwrite performed SetLog records.

### Never

Add large weight automatically; prescribe a 1RM attempt; change an exercise
after one poor session; treat pain as an ordinary plateau; diagnose; tell the
user to train through sharp, severe, worsening or unusual pain; silently
modify an active programme; erase or rewrite history; use cardio calories to
justify food; blame the user.

For pain or safety concerns, stop normal progression advice and use
conservative wording encouraging professional guidance where warranted.

### Explanation

> "Your dumbbell bench press has stayed at 20 kg for four qualifying sessions
> on the same bench. You're still completing 8–9 reps at about 2 RIR, so this
> looks like a progression plateau rather than a failed session. We can hold
> the weight and aim for 10 reps, try the smallest available increase, add one
> set, or review a temporary variation. What would you like to do?"

Show the evidence, the sessions considered, the options, the tradeoffs,
confirm and cancel controls, and a way to postpone or dismiss.

Derive detection from existing history. Do not require a new table in phase
one. If persistence is later needed, a plateau-event record would hold
`user_id`, `exercise_id`, evidence window, status, recommendation, user
decision, `initiated_by`, `applied_at`, and a cooldown. A dismissed
recommendation must not immediately reappear; the exact cooldown is unresolved.

### Deload changes the calorie target — say so first

A deload reduces expenditure. The weight trend responds, `tdee.py`
recalculates, and the calorie target falls. This is correct and it will look
like a bug. When a deload is accepted, the weekly check-in must say in
advance: *"training volume is down this week, so your burn will be too — your
target may come down slightly. That's expected."*

### Scope

**MVP:** deterministic detector; explainable statuses; `watch` and
`confirmed_plateau`; execution verification; double progression; smallest
increment and microloading; read-only assessment on the exercise screen; no
automatic programme changes; no diagnosis.

**Deferred:** persistent plateau-event history; dismissal cooldown; automatic
revisions; persistent readiness-confounding; automatic deload; advanced
equivalence learning; AI-generated explanations.

## Daily readiness adjustment

**Ask as little as possible.** Nine questions before every session is the
largest tap increase anywhere in the app, on its most habitual screen, and
users answer honestly for about a week.

- **Sleep and recent cardio** come from HealthKit / Health Connect. Never ask.
- **Available time** is the only input that materially changes the session.
  Ask it as chips: 30 / 45 / 60 / 90.
- **Everything else is optional**, collapsed behind a single *"something off
  today?"* affordance — energy, soreness, stress, pain, equipment.
- Ask the fuller set only after a break of 7+ days, or when the previous
  session showed a large performance drop.

Classify the session as normal, reduced-volume, technique-focused, recovery,
cardio-priority, deload recommendation, or seek-professional-advice.

Do not diagnose. If the user reports sharp, severe, worsening or unusual pain,
do not encourage them to train through it.

## Time-based workout generation

Support 15, 20, 30, 45, 60, 75 and 90-minute sessions.

Short: prioritise the important movement patterns, reduce isolation, superset
only where it does not cost safety or performance, avoid redundant warm-up,
and clearly state what was omitted.

Long: add accessories and isolation, add sets only where recovery and weekly
volume support it, and never fill time with low-value work.

Every generated workout shows estimated duration, exercise order, warm-up,
sets, reps, RIR or RPE target, rest, equipment, progression instruction,
substitution options, and optional finishing work.

## Exercise prioritisation

1. Safety and limitations.
2. Planned muscle groups and movement patterns.
3. Exercises serving the current goal.
4. Exercises that can be progressively overloaded.
5. Available equipment.
6. Preferences and previous performance.
7. Time efficiency.
8. Variety, only when useful.

Do not select exercises because they are popular or trending.

**Select from a curated subset, not the whole catalogue.** Rotation must be
deliberate: an exercise a user cannot accumulate 8 sessions on cannot be
assessed, so churning selection quietly disables the strength engine.

**Catalogue size is not what starves plateau detection — rotation is.** The
worry was that a 900-row catalogue would spread a user too thin to ever reach
the exposure threshold. It does not: a six-exercise template trained three
times a week puts three exposures on every movement inside seven days, so
exposures are never the scarce resource. The scarce resource is the calendar —
the detector additionally requires those exposures to span roughly three to
four weeks, which fixes the earliest possible verdict at about three weeks per
movement no matter how often it is trained. That makes generator design, not
catalogue size, the thing that decides whether plateau detection ever fires: a
generator that swaps exercises between weeks resets the clock every time and
keeps every movement permanently below the span requirement. Hold a movement
in the plan for at least four weeks before substituting it, and treat any
proposed rotation rule as a change to the strength engine's reach.

### Substitution is across equipment class, not brand

Brand is not a substitution axis — a PRIME chest press and a Hammer chest
press are the same movement on different stations, and the app already handles
that. Substitute when the *equipment class* is unavailable, preferring a
movement with the same pattern and resistance profile:

- No cable station → dumbbell or machine variant of the same pattern.
- No pendulum squat → hack squat or leg press.
- No specialised machine → the closest free-weight equivalent, with the
  tradeoff explained.

## Recovery and deloading

Track accumulated stress via weekly sets, performance trends, repeated
high-RPE sets, soreness, missed reps, sleep, reported fatigue, cardio and
sport load, and consistency.

Suggest a deload or reduced-volume week when the pattern supports it. Do not
diagnose. A deload may reduce sets, reduce load, raise RIR, reduce exercise
count, or keep technique practice while cutting fatigue.

## Generation architecture

**Most of this is rules, and rules should not call a model.** Split selection,
set counts, rep ranges, rest times, exercise ordering and progression are
stated deterministically in this document. Implement them as code.

- A **deterministic generator** produces the session. It is reproducible,
  free, instant, and testable.
- The **LLM is used only** for the plain-language explanation, and for
  genuinely open-ended requests — *"I've got 20 minutes and my shoulder
  hurts"*.
- Same shape as the food scan: cheap path first, model only where judgement is
  actually required.

### Output contract

```json
{
  "session_name": "Upper Body Hypertrophy",
  "goal": "hypertrophy",
  "estimated_minutes": 55,
  "readiness_status": "normal",
  "exercises": [
    {
      "exercise_id": "verified-id",
      "name": "Incline Dumbbell Press",
      "equipment": "dumbbell",
      "sets": 3,
      "rep_min": 8,
      "rep_max": 12,
      "target_rir": 2,
      "rest_seconds": 120,
      "progression_rule": "Increase weight after 3 sets reach 12 reps at RIR 2",
      "substitutions": ["Incline machine chest press"]
    }
  ],
  "notes": [
    "Stop if you experience sharp or unusual pain.",
    "Adjust load if technique breaks down."
  ]
}
```

### Validation

Hallucinated exercise ids are the dominant failure of model-generated
programmes.

- **Reject the entire response** if any `exercise_id` is not in the catalogue.
  Never silently drop the offending exercise — a plan missing its main lift is
  worse than no plan.
- Retry once, naming the invalid ids.
- On a second failure, fall back to the deterministic generator and say so.
- Validate that prescribed loads are actually loadable on the chosen station.

## Programme provenance

Exercise names and descriptions of how a movement is performed are facts and
are used freely, including eponyms.

Set and rep schemes, progression models, exercise rankings and tier lists from
named coaches and companies — Jeff Nippard, Renaissance Periodization, MI40,
Mountain Dog, Ganbaru and others — are their work product. Generated
programmes are built from first principles and public literature, never
reproduced from a paid programme. Trademarked systems may be named as
attributed methods; they are never implemented as our programming.

## User control

The user must be able to replace or skip an exercise, change available time,
change the target muscle group, adjust sets and reps, mark an exercise painful
or unsuitable, add unavailable equipment, request a simpler or harder workout,
pause or disable AI recommendations, and edit the generated workout before
starting.

The trainer learns from these choices without silently changing the plan.

## Testing requirements

Test: varying gym days; cut, bulk, maintenance and strength goals; low,
medium and high cardio; every session duration; beginner, intermediate and
advanced users; low and high readiness; missing equipment; equipment-class
substitution; exercise replacement; pain reports; missed sessions; progression
maths; deload recommendations; invalid model responses; history and personal
records.

Plateau specifically: insufficient history; exactly 3 qualifying exposures; a
four-week plateau; improving reps at constant load; improving e1RM; improving
volume; missed or incomplete sets; changed exercise; **changed station**;
**changed station profile**; changed setup; deload period; poor readiness;
pain flag; kg/lb confusion; double-progression recommendations; smallest
available increment; bodyweight with no smaller increment; no impossible load;
no large automatic jump; acceptance; refusal; history unchanged; deterministic
output; absence of diagnostic language.

Cross-system: plateau notices suppressed while adjudication is
`INSUFFICIENT_DATA`; deload acceptance producing the calorie-target warning;
station change producing `not_comparable` rather than a plateau.

## Implementation order

Do not implement all of this at once. Inspect what exists first.

1. Extract e1RM into `services/strength.py`, shared by adjudication and
   plateau. Nothing user-visible; unblocks everything.
2. Plateau detector, read-only, statuses only, station-aware.
3. Deterministic session generator — split, sets, reps, rest, order. No LLM.
4. Progression rules — double progression, smallest increment, no automatic
   jumps.
5. Readiness, minimal version — time chips plus HealthKit.
6. LLM explanation layer over the deterministic output.
7. The deferred list.

Steps 1–4 carry most of the value and none of them need a model.
