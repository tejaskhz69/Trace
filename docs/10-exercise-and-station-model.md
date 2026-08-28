# Exercises, machines, and why they are separate things

## The problem, stated as a user

> "I'm in Canada. My gym has a PRIME Extreme Row — plate-loaded, adjustable
> cam. No app has it. The ones that let me search for it make it a *different
> exercise* from the Hammer row I used at my last gym, so my progress
> restarts."

Both halves of that are real, and they pull in opposite directions. The user
needs to *find* their machine. The strength engine needs their trend to stay
*continuous*. Most apps pick one and break the other.

## The split

**An exercise is a movement. A station is a machine.**

```
Exercise: Chest-Supported Row          <- one row, one trend, searchable
   ├── Station: PRIME Extreme Row      (plate, cam settings 1/2/3)  — Toronto
   ├── Station: Hammer Iso-Lateral Row (plate)                      — Toronto
   └── Station: "the blue row machine" (pin, 5 kg steps)            — Kochi
```

`SetLog` carries an optional `station_id` and `station_profile`. e1RM trends
per `(exercise, station)`. The catalogue stays one row per movement.

## How the Canadian finds their PRIME

Through **aliases**, not through extra rows. Brand and model names are search
terms on the movement:

| Types | Finds |
|---|---|
| `prime row` | Chest-Supported Row |
| `hammer strength row` | Chest-Supported Row |
| `iso lateral` | Chest Press Machine · Chest-Supported Row · High Row Machine |
| `seal row` | Chest-Supported Row |
| `pw412` | Hack Squat *(Atlantis model code)* |
| `1fe001` | Lat Pulldown *(Panatta model code)* |
| `bayesian` | Bayesian Curl |

**155 movements, 674 aliases.** Search finds the machine; the trend never
splits. Verified against the live database.

Then the machine itself is recorded as a station — brand, model, loading type,
stack ranges, cam setting. Which answers the second half of the complaint:
*"it's not there as plate-loaded"* is fixed by the user telling us once, not
by us guessing.

## No gym setup, ever

Stations are created lazily, from logging. First time you log a movement the
app asks *"which machine?"* — free text, plus whatever other people at your
gym already named. Nobody configures an inventory before their first set.

`Station.is_public` is what makes this scale globally: **once one member of a
gym names the PRIME Extreme Row, every later member of that gym finds it.**
We will never maintain a worldwide hardware database. Users know their own
gyms and we don't.

This also solves India specifically, where most machines are unbranded or
locally fabricated. A dropdown of premium US brands would exclude them
entirely. Free text does not.

## What is deliberately absent: load conversion

There is **no cross-station weight normalisation**, and there never will be.

- Plate-loaded leverage runs roughly **2:1 to 5:1**, is never published, and
  changes through the range of motion.
- Cable stations are frequently **2:1** — PRIME literally names a SKU
  "HLP Selectorized Rack 2:1".
- A 45° leg press delivers about **sin(45°) ≈ 70%** of loaded weight before
  friction, and sled weights run 30–80 kg unlabelled.
- Manufacturers describe printed numbers as *"an estimate of effective
  resistance, not a promise"*.

No public dataset exists. A converter would be invented precision. **Compare
within a station; never across.** The UI should say so where it could be
misread.

## What IS worth capturing per station

- **`loading`** — plate / pin / dial / cable / bodyweight / free weight.
- **`stack_ranges`** — an ordered list, not a single increment. Real stacks
  are non-uniform: 5 kg steps from 15–25, 10 from 25–55, 15 from 55–190, all
  on one machine. A single `increment` field is wrong for a large share of
  equipment.
- **`station_profile`** — PRIME-style cam setting. Setting 1 peaks mid-range,
  2 at the contraction, 3 at the stretch. **Same machine, same load, different
  setting is a different exercise**, so it segments the trend rather than
  polluting it. This is the one brand-specific field that genuinely earns a
  column.
- **`carriage_weight_kg`** — leg press sleds, where known.

## `unit` is declared by the user, and that is sufficient — not a fallback

**Do not add unit inference. It would be a regression, not an improvement.**

This is written down because the ambiguity is real and looks like a bug worth
fixing. It is not.

Four photographs of a Gold's Gym floor, 2026-08-22, three Hammer Strength
selectorised machines standing metres apart:

```
FIXED PULLDOWN   5, 12, 19, 26, 33, 40, ... 138      a 5, then steps of 7
ROW              the same sequence
LATERAL RAISE    5, 10, 15, 20, 25, 32, 39, ... 88+  5s that become 7s
```

The stacks appear dual-marked, in two columns. Read at 4× magnification,
**both columns carry the same sequence** — 5/12/19 on the left, 5/12/19 on the
right. It is one scale printed either side of the selector holes so it can be
read from both sides; the apparent vertical offset is parallax. It is **not**
lb on one side and kg on the other.

And nothing in any frame states a unit. The evidence points both ways: 138 for
a fixed pulldown reads high for kg, but as lb, 138 lb ≈ 63 kg is light for the
top of a stack. A 2.5 add-on plate weakly suggests metric. None of that is
determinative, and **a guess here would be indistinguishable from a
measurement once stored.**

**Why user-declared is sufficient, not merely safe.** The strength engine is
entirely *within-station* and *relative*: e1RM trend on one machine over time.
Every comparison it makes divides one number on a machine by another number on
the same machine, so the unit cancels. Unit affects exactly two things —
display, and cross-gym comparison. We have already refused the second (see
*What is deliberately absent: load conversion*). What remains is a display
label, which is precisely the kind of fact the person standing at the machine
can supply for free and no algorithm can supply reliably.

`Station.unit` is therefore `kg | lb`, CHECK-constrained, declared once per
station. **A future change that infers it from the numbers, from the gym's
country, or from the user's locale is a regression** — it converts a known
unknown into a confident wrong answer, which is the failure mode
`INSUFFICIENT_DATA` and the nullable `movement_pattern` both exist to prevent.

## `movement_pattern` is null for about a third of exercises

Related trap, same shape, recorded here so a client author meets it before
production does.

`ExerciseEducationPublic.movement_pattern` is `str | None`. The eight patterns
describe **compound** lifts; isolation work — a lateral raise, a curl, a calf
raise — satisfies none of them, so the value is null for roughly a third of
the catalogue (45 of 154 curated movements). The field is always *present*;
only its value may be null.

**Render null as absent** — no chip, no row — never as `"undefined"`, an empty
chip, or `"unknown"`. The mobile client's interfaces are hand-maintained
rather than generated from the OpenAPI schema, so TypeScript enforces only
what somebody wrote down: `ExerciseEducation` in `apps/mobile/src/lib/api.ts`
carries the correct `string | null` ahead of its first consumer for exactly
this reason.

## Why not just make machines exercises

`adjudication.py` sets `MIN_SESSIONS = 8`. A verdict needs eight sessions of a
lift. Split one movement into five brand rows and someone training it weekly
waits **forty weeks** for any of them to trend.

The strength engine would get *worse* the more equipment we added. That is the
whole argument.

## Provenance of the catalogue

Exercise names and descriptions of how a movement is performed are facts and
are used freely — including eponyms (Meadows row, JM press, Larsen press,
Spoto press, Zottman curl, Kelso shrug, Bayesian curl, Pendlay row) and the
descriptive cable and stretch-biased variants that became popular 2023–26.

Not used: anyone's **programme content**. Set/rep schemes, progression models,
exercise rankings and tier lists are their authors' work product. Trademarked
systems (FST-7, MI40, Mountain Dog, Ganbaru, Smart Strength, Iso-Lateral) may
be *named* as attributed methods and are never reproduced as programming.

## Seeding

```bash
python -m app.scripts.seed_movements            # 155 movements
python -m app.scripts.seed_movements --dry-run
python -m app.scripts.seed_movements --pattern h-pull
```

Re-running **refreshes** existing rows rather than skipping them — an earlier
version skipped, so adding an alias to the file changed nothing and brand
search silently failed for exactly the machines people own. Identity (the
name) is stable; metadata tracks the file.

---

## Why Trace does not rotate exercises between blocks

Most training apps swap your exercises every four to six weeks. Trace does
not, and this is a deliberate choice with a cost. It will be asked about, so
the reasoning is recorded here rather than in a code comment.

**Variety and "is it working?" pull in opposite directions, and Trace sides
with the verdict.**

Adjudication will not issue a strength verdict until it has `MIN_SESSIONS`
exposures on a *single movement*. That threshold exists because one session
of a lift is noise: effort reports carry about a repetition of error
(Halperin 2022, see `docs/11-constants-and-evidence.md`), and a single e1RM
moves several percent on sleep, bar speed and how honest the RIR call was.
Eight exposures is what makes a trend distinguishable from a good day.

Now rotate the exercise every block. No movement ever accumulates eight
exposures. The strength verdict never fires — not "fires late", *never* —
and the app quietly becomes a workout logger with a nice chart, which is
precisely the product it exists not to be.

So:

- **Exercises are fixed for the life of a programme.** Week 8's Upper A is
  week 1's Upper A.
- **Rotation happens on regeneration**, when the lifter asks for a new
  programme, because that is a moment they have chosen and it restarts the
  exposure count knowingly rather than silently.
- **Variation happens across days and across lifters, not across time.**
  Upper A and Upper B differ; two users on the same template differ. Both
  are seeded deterministically from identifiers that do not change, so
  materialising a session twice returns the same session.

**What this costs, stated honestly.** Some lifters get bored, and boredom is
a real driver of quitting. The trade is deliberate: an app that keeps you
entertained while being unable to tell you whether you are getting stronger
has optimised for the wrong thing. If the exposure requirement ever drops —
for example, if a filter with an explicit uncertainty estimate replaces the
session-count threshold — this decision should be revisited, because the
argument depends entirely on `MIN_SESSIONS` being a session count.

## Cardinality: a column can be populated and still say nothing

Auditing a column by counting NULLs answers "is it populated". That is a
different question from "does it carry information", and the gap between
them has hidden four defects in this catalogue:

| column | state | caught by |
|---|---|---|
| `exercise_class` | NULL on 154/154 | a null check |
| `secondary_muscles` | present but empty arrays | an emptiness check |
| `default_rest_seconds` | **120 on 154/154** | neither |
| `fatigue_cost` | **3 on 154/154** | neither |

The last two are `NOT NULL` and fully populated, and carry exactly zero
information. That is how `_sort_key` came to be ordering a 154-movement
catalogue alphabetically while appearing to sort by class and by fatigue.

**Every column a decision reads must satisfy `count(DISTINCT col) > 1`.**
This is asserted in `TestGeneratorReadColumnsCarryInformation`, and it
applies to fixtures as well as to production — a fixture whose columns all
vary cannot reproduce a catalogue whose columns do not.

## The catalogue's isolation skew is structural, and classifying more rows makes it worse

Candidate counts after the beginner-equipment filter, with everything
classifiable projected in:

```
<isolation>  93        h-push  34      core   17      v-push  11
h-pull       11        lunge   10      squat   9      hinge    8      v-pull 8
```

**Roughly ten isolation movements for every candidate in a compound slot**,
and before the projection it was worse — 22 against 1 to 5.

This is not a gap to be closed by classifying more rows. It is a property of
where the catalogue came from. A scraped exercise database enumerates
accessory movements almost without limit — every grip, angle and implement
variation of a curl is a separate row — while the compound patterns that a
programme is actually built from have a small, fixed number of real members.
There are perhaps a dozen genuine horizontal pulls. There are hundreds of
curls.

**So every classification batch makes the ratio worse, not better.** 82 of
the first 94 rows classified would have gone to isolation. Anyone reading a
thin compound slot as "we need to classify more" is reading it wrong: the
compound slots are thin because those movements do not exist in the source
data, and the fix is authoring them deliberately, not ingesting more.

Recorded here so it is not rediscovered from scratch each time a slot comes
up short.

**Second-order consequence worth stating.** `equipment` is not a reliable
guide to beginner-appropriateness, and the tagging beneath it is not
reliable either. `Band Assisted Pull-Up` — the single most
beginner-appropriate vertical pull in the catalogue — carries
`equipment = 'other'`, while `Weighted Pull-Up` carries `'bodyweight'` and
is therefore admitted by a filter selecting on equipment. A filter over
equipment cannot express "a beginner can perform this"; only a difficulty
attribute can.

## `lunge` is a compound, `core` is not, and that asymmetry is deliberate

`exercise_classify._COMPOUND_PATTERNS` lists eight of the nine movement
patterns. `core` is the one left out, and it is not an oversight.

A lunge is multi-joint — hip and knee, under load, with the same structural
demand as a squat — so it belongs with the compounds and contributes to the
`is_compound` cross-check like any of them.

Core work is neither. A plank is not a compound and it is not an isolation
either; a Pallof press is anti-rotation, where the movement is the *absence*
of movement. Forcing it into the binary is the same conflation this document
records for `exercise_class` and for `is_compound`/`is_isolation`: one
column, two axes.

Where a decision must nonetheless put core somewhere, it is grouped with
**isolation** — accessory volume, late in the session, short rest. That call
is made in exactly two places and they must agree: `derived_class()` for set
count and rest, and migration `a7e2d3b64f19` for the rep range. When they
disagreed, a hanging leg raise was prescribed as three sets with three
minutes of rest — a squat's prescription attached to an ab exercise.
