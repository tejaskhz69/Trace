# VXS Trainer — reference screenshots

Eleven screenshots of a competitor, VXS Trainer, captured from their marketing
site and one Instagram story (`vxsxlift`). Version-controlled here so the
design conversation has a fixed referent instead of memory.

**Every file below was opened and looked at, not inferred from its filename.**

## What VXS's visual system actually is

| Element | VXS |
|---|---|
| Ground | near-black, roughly `#0A0A0C` |
| Accent | crimson/pink, roughly `#E8264F` |
| Second accent | mint green `#7EE8A2` for positive actions |
| Verdict colour | **purple** — "strength went up on this lift" |
| Body / labels | monospace, uppercase, wide tracking |
| Headlines | heavy grotesque sans, tight tracking |
| Numerals | large, white, tabular |
| Exercise index | numbered chip in the left gutter |

Their marketing copy is set entirely in monospace, which is unusual and reads
as deliberate. The product UI mixes: mono for labels, sans for names.

---

## The screens, and what each is worth taking

### `vxs-2026-08-28-session-complete-clear.png` — **the important one**
The session summary, clean and legible. This is the direct ancestor of
`design/trace-session-summary-reference.html`.

```
VXS | SESSION COMPLETE
MIN 53   SETS 18   VOL (KG) 10813   AVG RPE 8.8
16 PURPLE SETS TODAY · 5 LIFTS MOVED UP
01 Overhead Shoulder Press  [+ PURPLE SET]   1RM +2.2 KG / 60.5 kg est
02 Dumbbell Lateral Raise   [PURPLE SET]     1RM +0.7 KG
...
06 Cable Crunches           [ON TARGET]      NO CHANGE / 139.9 kg est
· PROGRESSING FASTER THAN EXPECTED
· PROGRESSING AS EXPECTED
```

**Take:** the four-column stat strip; the numbered left gutter; flat rows with
no card boxes; the mono headline that states the session's outcome as a
sentence; right-aligned `1RM +X KG` over `Y kg est`; the legend pinned to the
bottom.

**Do not take:** the crimson, the purple-means-good mapping, the `VXS`
wordmark, or the legend wording.

> **Flag — this needs your decision.** Our reference file is closer to this
> than "layout and information patterns". Specifically:
> - Our legend line **"Progressing faster than expected"** is *verbatim* VXS.
> - Our headline **`7 SETS PROGRESSED TODAY · 2 LIFTS MOVED UP`** is the same
>   construction as their `16 PURPLE SETS TODAY · 5 LIFTS MOVED UP`, with
>   "lifts moved up" carried over word for word.
> - Our stat keys `TIME / SETS / VOL (KG) / AVG RPE` match theirs except
>   `MIN`→`TIME`.
>
> A four-column stat strip is convention and nobody owns it. A legend sentence
> reproduced word for word is not. I would rewrite both legend lines and the
> headline before this ships.

### `vxs-2026-08-24-session-complete.png`
The same screen as an Instagram story, partly occluded by a music overlay.
Kept because it confirms the pattern is what they actually publish, not a
marketing mock. Caption in the user's own words: *"The purple colors indicate
that my strength for that particular workout has gone up."*

### `vxs-2026-08-22-095319.png` — home screen
Two-up card grid: TRAIN (rest/session, `— EX  — MIN  —% CAP`) beside EAT
(calorie ring, meal checkboxes). Below: WEIGHT and PROTEIN as a half-width
pair. **Take:** the paired TRAIN/EAT card at the top — it answers "what am I
doing today" in one glance. **Note:** their empty state uses `—` em-dashes
rather than `0`, which is a good instinct and matches our "grey means we do
not know" rule.

### `vxs-2026-08-22-095423.png` — nutrition log
The screen closest to our Phase 3 work.
```
LOG · TODAY
Today.                    MON · 20 JUL · 18:09
TARGET · 2200 KCAL · 147 G P
1,484 KCAL LEFT                    50 / 147G P
716 EATEN · ON TRACK    23G CARBS  47G FAT
TODAY'S LOG · 3 ITEMS              TAP - TO REMOVE
01 Whole Milk, Whole Egg (me...   24P 11C 22F 17:52   340 KCAL
02 Whole Milk                     6P 10C 7F           124 KCAL
[QUICK ADD] [PLAN] [MANUAL] [HISTORY] [PHOTO]
```
**Take:** leading with **what is left**, not what was eaten; the numbered
gutter on log rows; per-item macros as a compact mono run with each macro in
its own hue; a timestamp per row.
**Competitive note, not a design one:** their copy says *"Drop in the Swiggy
or Zomato screenshot — it reads every item and estimates the macros."* That is
a delivery-receipt import path we do not have, aimed at exactly our market.

### `vxs-2026-08-22-095404.png` — meal plan
`PLAN · DAILY TOTALS` with a four-column macro strip (KCAL/PROT/CARB/FAT),
then an over-target warning row: *"140 kcal over target — regenerate to
adjust."* **Take:** the inline warning row that states the number and the
remedy in one line.

### `vxs-2026-08-22-095451.png` / `095459.png` — active set logging
The set card: KG and REPS as two large tap targets, a green START, then after
the set a **RIR picker** — `HOW MANY MORE REPS COULD YOU HAVE DONE? 0 1 2 3 5+`
with `5 more reps in reserve` underneath, and SUBMIT SET. Collapsed future
sets listed as `SET 2 / SET 3 / SET 4`. Footer `REST 2:00  TARGET RPE 9`, with
SWITCH and SKIP.
**Take:** RIR as a row of discrete chips rather than a slider — it is faster
with sweaty hands and it records an integer, not a fake-precision float. Also
take showing rest and target RPE on the card rather than in a modal.

### `vxs-2026-08-22-095509.png` — form demo
A `Demo` pill on every exercise row opening a video sheet. **Take:** the idea
that form help lives *inside* the set, one tap, not in a separate library.

### `vxs-2026-08-22-095341.png` — goal setup
*"Your goal isn't a wish. It's a budget."* Target weight slider with live
`2,200 kcal INITIAL DAILY BUDGET` and `Aug 31, 2026 PROJECTED FINISH`, plus
per-week / per-month rate in both kg and %BW. **Take:** showing the projected
finish date live as the slider moves — it makes the rate choice concrete.

### `vxs-2026-08-22-095530.png` — muscle picker
`GENERATE & START · 2 GROUPS`. Copy: *"Counts as a day trained for your streak
and the leaderboard, not your program week."* **Take:** the distinction
between a logged day and a program day, stated plainly.

### `vxs-2026-08-22-095518.png`
Not yet examined in detail; kept for completeness.

---

## What we should not copy at all

- **The crimson.** It is their identity. Ours is green/orange/red/grey.
- **Purple-means-good.** In our system purple is not used; "building" is a
  green outline. Their purple encodes the same idea our `--go` does.
- **The wordmark and the mono-everything marketing voice.**
- **Legend and headline sentences.** See the flag above.

## What we do that they do not

Their session screen colours essentially every row. There is no state for *"we
do not have enough data to say"* — the closest is `NO CHANGE`. Our `--dim`
grey, and the rule that four of nine movements sitting colourless is correct,
is the actual difference between the two products. It should not be softened
to look more like this.
