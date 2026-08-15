# Trace vision eval set

25 photos with known calorie truth, used to measure whether the food scan
actually works — and specifically whether it fails the way every other app
fails.

```
eval/
├── manifest.csv   ← the deliverable. 25 rows, pre-planned, truth blank
├── score.py       ← validates the set, then scores a run
└── photos/        ← you shoot these
```

## Why there are no photos in here

Photos off the internet come with `truth_source = estimate`. Scoring a model's
estimate against a scraped guess measures agreement, not accuracy — and it
reports a flattering number while hiding the exact error you're trying to
find. The NIH's 2026 weighed-meal study found photo apps undercount by ~33%,
almost entirely on fat. A guessed fixture set cannot detect that.

They'd also be someone else's copyrighted images sitting permanently in a
commercial repo.

So the photos have to be yours, and the truth has to be weighed.

## The kitchen scale is the whole job

A ₹500 digital scale is the only equipment needed. The routine, once you're
used to it, adds about 60 seconds to a meal:

1. **Weigh each component into the serving dish**, before you plate it.
   Rice 180 g, dal 150 g, 2 roti 84 g. Write it in the `grams` column,
   comma-separated in the order the components appear in `dish`.
2. **Record the cooking fat.** This is the part everyone skips and it is the
   single largest error term. "Tempered with 1 tsp ghee" is 45 kcal that no
   camera can see. If you didn't cook it, ask whoever did.
3. **Photograph the plated meal** the way a user would — one shot, phone held
   naturally, whatever light you're eating in.
4. **Compute `truth_kcal`** from grams × your food database values, plus the
   fat. Put it in the manifest.

If you only do one thing: **weigh ten Indian home meals.** That set is worth
more than fifty guessed photos, and it's the one no competitor has.

## Filename convention

Already written into the manifest — just match it:

```
in-001-dal-tadka-roti-thali.jpg     in- = Indian
fo-001-pasta-cream.jpg              fo- = foreign
ad-001-no-scale-ref.jpg             ad- = adversarial
```

## truth_source tiers

| tier | what it means | scorable |
|---|---|---|
| `label` | packaged food shot beside its own nutrition panel | yes — score to ±2% |
| `weighed` | components on a scale, recipe known | yes — the gold tier |
| `recipe` | known recipe, portions estimated | yes |
| `menu` | chain restaurant with published nutrition | yes |
| `estimate` | you guessed | **no — validator rejects it** |

The only `estimate` row allowed is `ad-004`, the opaque takeaway container,
where the truth is *deliberately* unknowable — the pass condition there is
that the model refuses rather than guessing.

## The four adversarial shots

These matter more than the other 21 combined, because they test the
non-negotiable: *refusing to answer beats answering wrong.*

- `ad-001` no scale reference in frame
- `ad-002` poor lighting
- `ad-003` half-eaten plate — **truth is what was eaten, not what was served**
- `ad-004` opaque takeaway container

Pass condition is behavioural, not numeric: the range widens, confidence
drops, or it refuses. A confident number on any of these is a failure even if
it happens to land close.

## What NOT to shoot

- Overhead shots of one plated item on a white background. Every competitor
  already handles that; it will inflate your score and teach you nothing.
- Anything you can't state a truth number for.
- Anything you'd be uncomfortable having in the repo forever.

## Running it

Before you shoot, and again after you fill the manifest in:

```bash
python score.py --validate
```

It refuses to pass until you have ≥10 weighed rows, ≥12 Indian, ≥8 high
hidden-fat, ≥3 adversarial, and zero guessed truth in the scored set. Those
floors exist because an easy set reports excellent accuracy.

After a run, with results as JSON — one object per photo with `file`, `kcal`,
`kcal_low`, `kcal_high`, `confidence`, optional `refused`:

```bash
python score.py --results results.json
```

You get bias, MAPE, range coverage, a breakdown **by hidden-fat level** —
which is where the real story is — by cuisine, adversarial behaviour, and the
five worst misses.

## The number that matters

Bias, broken down by hidden fat. If your `high` bucket looks like the `low`
bucket, you've solved the thing the entire industry currently gets wrong, and
you should publish it. If `high` sits near −30%, you've reproduced the
incumbents and the oil question isn't working yet.

MAPE is the vanity metric. Bias on hidden fat is the real one.
