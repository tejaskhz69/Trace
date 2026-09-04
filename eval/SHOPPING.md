# The list — what to buy, what to shoot

Total: **~₹900**. One grocery run. You already have the scale, which was the
only thing that couldn't be improvised.

Every shot is **two photos**: the food (goes in `photos/`, named exactly as
below) and the nutrition panel (keep it anywhere — it settles arguments a week
later when you can't remember whether the panel was per 100 g or per serving).

---

## Buy — pouches, ~₹550

Heat in hot water. No stove needed. Panel includes the cooking fat, which is
why these are better truth than weighing your own cooking.

| # | Buy | Photo filename |
|---|---|---|
| 1 | MTR dal makhani + rice | `in-001-mtr-dal-makhani-rice.jpg` |
| 2 | MTR paneer butter masala + 2 mess roti | `in-002-mtr-paneer-butter-masala-roti.jpg` |
| 3 | Haldiram chole + rice | `in-003-haldiram-chole-rice.jpg` |
| 4 | MTR palak paneer + 2 roti | `in-004-mtr-palak-paneer-roti.jpg` |
| 5 | MTR rajma masala + rice | `in-005-mtr-rajma-rice.jpg` |
| 6 | MTR bisibele bath | `in-006-mtr-bisibele-bath.jpg` |
| 7 | MTR upma | `in-007-mtr-upma.jpg` |

**Protocol, 90 seconds each:** tare the plate → plate the curry → **write down
the grams** → weigh the rice/roti separately → shoot it normally, phone in
hand, whatever light you're in. Don't style it. Users won't.

## Buy — kettle and shelf, ~₹350

| # | Buy | Photo filename |
|---|---|---|
| 8 | Maggi, whole packet, nothing added | `in-012-maggi-cooked.jpg` |
| 9 | Instant poha or masala oats cup | `in-013-poha-or-oats-instant.jpg` |
| 10 | Cup noodles | `fo-008-instant-noodles-cup.jpg` |
| 11 | Any protein bar — **shoot the panel in the same frame** | `fo-002-protein-bar-with-label.jpg` |
| 12 | Curd cup + mess rice (weigh the rice) | `in-011-curd-rice-assembled.jpg` |
| 13 | Toned milk — weigh the pour | `fo-006-milk-glass.jpg` |
| 14 | Banana + 4 biscuits | `fo-007-banana-and-biscuits.jpg` |
| 15 | Bread ×2, butter, 2 boiled eggs | `fo-001-bread-butter-eggs.jpg` |
| 16 | Convenience-store packaged sandwich | `fo-005-packaged-sandwich.jpg` |

Row 11 is your calibration row — panel in frame means near-perfect truth, and
if the model misses *that* one you have a parsing bug, not an estimation
problem.

## Free — mess, weigh your own plate

| # | What | Photo filename |
|---|---|---|
| 17 | Full thali: rice, sambar, rasam, thoran, papad | `in-008-mess-thali-full.jpg` |
| 18 | Mess dal + rice | `in-009-mess-dal-rice.jpg` |
| 19 | 3 idli + sambar — the low-calorie **control** | `in-010-idli-sambar-mess.jpg` |

**Ask the cook:** *"how much oil goes into one batch of sambar, and how many
people does it serve?"* Two litres across sixty servings is 33 ml a head —
~300 kcal no camera will ever see. Write the answer in `notes`. It is the most
valuable number on this page and no competitor has bothered to ask for it.

## Free — only if you eat out anyway

| # | What | Photo filename |
|---|---|---|
| 20 | Chain burger + fries, note exact items | `fo-003-chain-burger-fries.jpg` |
| 21 | 2 slices chain pizza | `fo-004-chain-pizza-slices.jpg` |

Domino's / McDonald's publish real nutrition. Skip if you're not going.

## Free — adversarial, reuse food you already shot

These are graded on **behaviour**, not accuracy. The pass is a wide range or a
refusal. A model that confidently answers all four is the dangerous one.

| # | What | Photo filename |
|---|---|---|
| 22 | Any pouch dish, nothing in frame for scale | `ad-001-no-scale-ref.jpg` |
| 23 | Mess dinner in dim light | `ad-002-poor-lighting.jpg` |
| 24 | Half-eaten meal — **weigh before AND after**, truth is what you ate | `ad-003-half-eaten.jpg` |
| 25 | Food in an opaque takeaway box | `ad-004-opaque-container.jpg` |

---

## When you're done

    python score.py --validate     # must say "Ready to run"
    python run_eval.py --direct
    python score.py --results results.json

Validation will refuse until 10 label/weighed rows are filled and every photo
is real. That refusal is the point — it's what stops you from shipping a
number that flatters the model.
