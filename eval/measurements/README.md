# Measurements

The project's first ground-truth numbers. Everything in this directory was
weighed by hand, not taken from a database, a pack estimate, or a memory.

| | |
|---|---|
| **Measured by** | Tejas |
| **Date** | 2026-09-05 |
| **Instrument** | HealthSense kitchen scale, 1 g steps, tare function |
| **Noise floor** | **±1 g, provisional** |

## The instrument, and why ±1 g is not a footnote

```
accuracy:      D'lecta pack declares 7 × 20 g = 140 g
               measured 138 g and 139 g on two separate weighings
               → within ~1% of declared
repeatability: ±1 g at ~139 g (two readings)
```

**Both figures are provisional.** Accuracy was checked against one declared
pack weight, which cannot separate a scale that reads 1 g light from a pack
that is filled 1 g under. Repeatability rests on two readings, not the five
that would give a standard deviation. The full 5× run is outstanding.

Every measurement here inherits ±1 g. That is negligible on a 245 g bowl of
pasta and fatal on a 1 g reading of oil — see `oil_spray.yaml`, where the
first run is wrong by a factor of about three for exactly this reason. It is
kept in the file deliberately as the worked example.

## Files

| File | What it holds |
|---|---|
| `vessels.yaml` | Katori, glass and bowl capacities with measured contents |
| `preparation_factors.yaml` | Penne dry→cooked yield, 2.188× |
| `oil_spray.yaml` | Olive oil spray, 0.15 g per spray, both runs kept |
| `dlecta_mozzarella.yaml` | A label-tier panel that validates clean |
| `fo-009-status.yaml` | Partial unblock, unresolved conflict, re-cook procedure |

## Three findings worth carrying forward

**Volume × density does not work for moundable food.** `katori_A` holds
126 ml level, and took 145 g of curd — an apparent density of 1.15 g/ml when
nothing dairy exceeds ~1.06. The extra is the mound sitting above the rim,
about 15% of the portion. Water fills to level; people serve heaped. Trace
cannot derive a katori weight from one capacity figure, and needs either a
level/heaped distinction or measured weights per food.

**The database's 1 katori = 150 g is wrong for this katori.** It measured
130 g of dal. Every dal logged against that assumption is ~15% high. See the
proposal in the session report; the constant has not been changed.

**A measurement at the instrument's resolution limit is not a measurement.**
Six sprays weighed as "1 g" implies 0.167 g/spray. Forty sprays into a tared
bowl gives 0.15 g/spray at ±8%. Same bottle, same day; the first is a
coin-flip and the second is usable. The fix was not a better scale — it was
increasing the count until the signal cleared the noise.

## What is NOT in here

- `bowl_ikea_steel.water_ml` — not measured. Left `null`. Do not estimate it.
- D'lecta barcode and ingredient list — not legible in the photograph. Left
  `null`. **Do not fill from Open Food Facts**: OFF is the source whose defect
  rate this project is measuring against, and importing from it would make the
  reference row circular.
- `fo-009` cheese — reported two ways from memory, 2–4× apart. Recorded as a
  conflict, not resolved. The row stays blocked.

## How to add to this directory

State the instrument, the date, and the person. Record what was measured, not
what was derived — derivations belong in a `derived:` block so a later reader
can recompute them. Where a measurement is unreliable, keep it and say why;
a discarded bad measurement teaches nobody anything.
