# Workout-trainer prototype

A clickable, self-contained prototype of the Trace training experience, built
for review before anything is implemented in the real app.

**Nothing here is wired to Trace.** No API, no database, no network request, no
key, no stored state. Every number on every screen was invented for this
prototype and is labelled as sample data on screen.

---

## Opening it

Double-click `index.html`, or from the repository root:

```bash
# Any of these. No build, no install, no server required.
start prototype/workout-trainer/index.html          # Windows
open  prototype/workout-trainer/index.html          # macOS
xdg-open prototype/workout-trainer/index.html       # Linux
```

It is a plain page with two local scripts and one local stylesheet. Opening it
from the filesystem is enough — there is nothing for a server to add.

## Running the checks

```bash
node prototype/workout-trainer/check.js
```

**127 checks, all passing.** They drive the page through jsdom — clicking real
buttons and reading the DOM back — so the claims below are verified rather than
asserted. jsdom is **not a new dependency**: it already sits in
`apps/mobile/node_modules` because Jest brings it, and `check.js` resolves it
from there. Nothing is installed, and the run touches no database, no server
and no production file.

## Files

| File | Lines | What it is |
|---|---|---|
| `index.html` | 70 | Shell, fourteen screen containers, tab bar, sheet, dialog |
| `styles.css` | 593 | Instrument-panel styling, tokens mirrored from `apps/mobile/src/theme.ts` |
| `data.js` | 579 | **The only file holding sample values.** If this were ever wired to a real source, this is the file that would be deleted |
| `app.js` | 2,116 | State, router, fourteen screens, all interactions. All in memory |
| `check.js` | 783 | The jsdom checks |
| `REFERENCE_MATRIX.md` | 202 | What was inspected, feature by feature, written before any code changed |
| `FEATURE_GAP_REPORT.md` | — | What the real app would need, feature by feature |
| `README.md` | — | This file |

Nothing outside `prototype/workout-trainer/` was created or modified.

---

## Navigation

Six bottom tabs — **Home · Train · Recover · Cardio · Eat · Progress** — with
Profile and programme setup behind the masthead avatar.

Neither reference used seven tabs. The Flight Deck artifact uses five with
settings behind the avatar; Trace production also ships five. Seven bottom-bar
targets is past the point a thumb hits reliably, so the prototype uses six and
puts the two configuration surfaces behind the avatar, which is the pattern the
artifact already established. `REFERENCE_MATRIX.md` records the adaptation in
full.

Cardio stays its own tab rather than folding into Train, because a shared tab
is exactly what makes people log a ride as a workout.

**Every screen carries a kind badge** — `PROGRAMMING`, `PERFORMED LOG`,
`SLEEP & RECOVERY`, `CARDIO`, `NUTRITION`, `PROGRESS`, `SETUP` — so the six
categories the brief asks to distinguish are readable on the screen itself
rather than inferable from which tab you came in through. A check enforces that
all six appear.

## Screens

**1 · Home.** Greeting, goal and phase, a Train/Eat split, programme with
adherence, readiness, sleep and cardio side by side, weekly consistency, the
muscle-versus-fat progress headline, an advisory plateau notice, and eight
quick actions.

**2 · Train — today's session.** Session state with `n/m` exercises and elapsed
against budget, readiness-adjusted guidance marked *shown, not applied*, target
muscle groups, a live time budget, warm-up rows marked *not working sets*, the
ordered exercise list, add-an-exercise, and the progression rule in full.
Pause, resume and finish.

**3 · Exercise detail.** An original movement diagram, primary and secondary
muscles, movement pattern, equipment, a plain-language explanation, numbered
form cues, common mistakes, what you should feel, easier and harder variations,
an estimated-1RM trend, recent performance, plateau status, and substitutions.

**4 · Session summary.** Exercises, sets, reps and volume, what you did, what
you skipped, and a *where this goes* table whose last row reads **calorie
target — Unchanged**.

**5 · Train anyway.** The off-programme muscle picker, explicitly labelled
*performed log* rather than programming, which builds a session from your
current loads.

**6 · Recovery.** Readiness first, then **why this number** broken down factor
by factor, a seven-day recovery trend, a sleep summary, and the five optional
inputs. "Skip for now" is a first-class action.

**7 · Sleep detail.** Seven nights with a short-night callout, full history with
a per-row source label, manual entry, delete, connection state, and the privacy
position.

**8 · Cardio.** Indoor/outdoor selector, weekly cardio load, the activity with
duration, distance, speed, elevation and energy, a route preview *for outdoor
only*, the **where this goes** table, the effect on today's leg work, recent
activities with per-row sources, and an empty state.

**9 · Cycling detail.** Idle/active/paused/finished display states, the metric
trio, route, energy with its basis stated, where-this-goes, a location privacy
note, a duplicates note, and a confirmed delete.

**10 · Eat.** A read-only mirror: remaining calories, macros, micronutrients
worth watching, four entry points, the day's log with verified-versus-estimated
tags and ± bands, a marked meal-plan placeholder, and the cardio-calories
position.

**11 · Progress.** Consistency, adherence, weekly sets by muscle in four
states, an estimated-1RM trend with optional sleep and cardio overlays,
this-week-vs-last, per-exercise progression, personal records, a fatigue trend,
and the plateau card with its evidence.

**12 · AI review.** A mock draft with mock ids, one of which fails validation,
confidence reported as an em dash, and confirm / edit / reject.

**13 · Programme setup.** Goal, phase, days per week, available days, session
length, equipment, liked and disliked exercises, cardio frequency, two
skippable opt-ins, a live programme preview, and confirmation.

**14 · Profile.** Account, connected sources (all disconnected), an in-page
reduced-motion switch, and what the prototype stores.

## Interactions

Navigate by tab, by quick action, by arrow keys on the tab bar, and back from
every sub-screen · start, pause, resume and finish a session · log a set with
load, reps and reps-in-reserve · a real rest countdown you can skip · advance
automatically · add an exercise to today only · replace via a bottom sheet ·
skip and undo · edit the time budget and watch the session re-fit · expand and
collapse exercise detail · adjust every readiness field · skip the check-in ·
add and delete a sleep night · switch indoor/outdoor · hide and show the route ·
delete an activity behind a confirmation dialog · switch the volume panel
between data, loading, empty and error · overlay sleep or cardio on the
strength trend · pick a plateau option and accept, postpone or dismiss ·
replace the invalid AI exercise, then confirm or reject · configure and confirm
a programme · toggle reduced motion.

All state is in memory and is forgotten on reload.

---

## Sample-data discipline

Every screen carries the banner **"Prototype — sample data only. This screen is
not connected to Trace."** It cannot be dismissed. Every screen head also
carries a `SAMPLE` tag — checked.

**Every record in `data.js` declares a `source`** from a fixed vocabulary:
`demo`, `manually recorded`, `imported`, `estimated`, `unavailable`. That chip
is rendered *next to*, never instead of, the SAMPLE tag — so "what kind of
record is this" and "is this real" stay two separate answers. A check enforces
that no other label ever reaches the screen.

Specifically:

- **No sleep was measured.** Every night is `manually recorded`, `estimated`,
  or `unavailable`. Thursday has no record at all and says so rather than
  showing a zero. Every external source reads **Not connected** on Profile.
- **No route was recorded.** The outdoor line is a drawn polyline, labelled
  *demo route · not recorded*. **An indoor session shows no route at all** —
  on both the cardio and the ride screen — because a map there would be a claim
  about somewhere you never went. Two checks enforce this.
- **The readiness score is arithmetic on answers you typed**, not a
  measurement, and the screen shows the per-factor contributions.
- **No model ran.** Confidence and data coverage are em dashes, not zeroes: a
  confident-looking 0% would be its own kind of wrong.
- **Nutrition is read-only** and distinguishes three different things —
  `verified` (off a label), `estimated` (a photo estimate, with a ± band), and
  sample data, which is a third thing again.
- **Cardio energy never becomes food.** Every relevant screen carries a
  *where this goes* table ending in **calorie target — Unchanged**.
- **No medical or diagnostic claims.** A check walks every screen and requires
  that clinical vocabulary only ever appears negated — "not a diagnosis" is
  allowed, "a diagnosis" is not.

---

## References inspected

Full detail, feature by feature, is in `REFERENCE_MATRIX.md`, which was written
before any code in this round changed.

| Source | Status |
|---|---|
| **Trace Flight Deck** artifact | **Inspected** — fetched from `claude.ai/code/artifact/2ae4dc00-dd1b-4901-904d-df317ce1099a`, 1.57 MB, 749 lines of visible text extracted |
| vxstrainer.ai screenshots | **Inspected** — ten images pasted inline in the conversation |
| `WORKOUT_DATABASE_UPGRADE_PLAN.md` | Inspected, **not modified** |
| `services/api/WORKOUT_SCHEMA_DESIGN.md` | Inspected, **not modified** |
| `C:\Users\Tejas\Downloads\trace-workout-references\` | **Does not exist** — see below |

**The screenshots are still not files on disk.** The folder named in the
earlier brief does not exist, and the ten images live only in the conversation.
They cannot be cited by path and cannot be re-opened later. To take any visual
idea further, save them to `docs/references/` first.

### Ideas adopted

From the **Flight Deck**: the *where this goes* table with the calorie target
marked unchanged; two numbers side by side with the more trustworthy one
marked; three numbered form cues instead of prose; the e1RM hero with a
multi-week line and a this-week-vs-last grid; sleep as seven bars with one
sentence about what to do; the muscle-versus-fat split as the progress
headline; settings behind the avatar; a weekly recommendation that shows its
working and then asks.

From the **screenshots**: logging the set where the exercise already is; the
"how many more reps could you have done?" row; per-exercise switch and skip;
session progress in the header; per-lift status tags with a delta; the
off-programme muscle picker; add-an-exercise mid-session; a per-exercise
demonstration control.

### Deliberately not copied

The crimson accent — Trace has one accent and it is signal green · any wordmark
or logo · the third-party coach's product name and persona · partner lockups ·
verbatim marketing sentences from either source · the 32-sport grid as an asset
· any image or illustration · the streak-and-leaderboard framing · the
"app adjusts automatically" positioning, which conflicts with the
recommend-then-confirm rule this prototype is built around.

Every chart, route line and movement diagram is drawn from primitives in this
repository. No asset was taken from either reference.

---

## Open questions

1. **Where do the screenshots live?** They need to be on disk with a known
   licence before any visual idea goes further.
2. **How long does a dismissed plateau recommendation stay dismissed?**
   §14.7 requires a cooldown and leaves the duration open. The prototype says
   "not on your next session" and does not invent a number.
3. **Does the readiness check-in need its own consent?** §10.8 item 3 — open,
   and flagged as a question for a lawyer.
4. **How long are rejected AI drafts retained?** §10.8 item 1 — bounded, but
   the number is not set.
5. **Is readiness data in an account export, and is deletion hard or soft?**
   §10.8 item 2.
6. **Should cardio reorder exercises, or only annotate them?** The prototype
   only explains the trade-off. Reordering is a programme change and would need
   the same confirm step as everything else.
7. **What produces demonstration content?** The prototype draws original
   diagrams. Video, animation or illustration all carry licensing and
   production costs that have not been scoped.
8. **Are the readiness weights defensible?** They are invented and marked
   illustrative. Anything shipped needs a real basis.
9. **Is the fatigue index worth having at all?** It is on the Progress screen,
   marked illustrative, and nothing in the real app computes it.
10. **Which time budgets are real?** 15 minutes drops four of six exercises,
    which may be worse than saying "not today".

## What still needs backend or database work

See `FEATURE_GAP_REPORT.md`. In summary:

- The nine workout-programming tables exist in `models.py` and in migration
  `f6a9c2e47d85`, **which has not been applied**. The database is at
  `e4f7b0d25c63`.
- `routers/programming.py` exists with eleven endpoints. **No mobile screen
  calls any of them.**
- `services/plateau.py` **does not exist**. §14 is design only.
- Sleep and cycling **storage already exists**. The gap there is manual entry
  and presentation, not schema.
- `exercise_attributes` and `exercise_substitutions` ship **empty**, and 874
  exercises need attributes before most of the Train screen can be real.
