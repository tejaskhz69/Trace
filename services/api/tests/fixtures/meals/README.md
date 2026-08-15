# Scan evaluation fixtures

Photos and ground truth for `python -m app.scripts.eval_vision`.

The harness scores **interval coverage** — how often the true calorie value
falls inside the `[kcal_low, kcal_high]` band the model returns — not just
point accuracy. The prompt asks for a genuine 80% interval, so coverage should
land near 80%. Below 70% the app is overstating its certainty; above 92% the
ranges are too wide to be useful.

## Layout

```
manifest.csv     one row per photo — this is the real deliverable
images/          the photos themselves
```

Delete the two `example-` rows once you have real data. Any row whose `file`
starts with `example-` is ignored.

## Columns

| column | required | notes |
|---|---|---|
| `file` | yes | filename inside `images/` |
| `cuisine` | yes | `indian-north`, `indian-south`, `italian`, `japanese`, `packaged`… — used for the per-cuisine breakdown, so keep the values consistent |
| `dish` | yes | what a user would type as a hint |
| `truth_kcal` | yes | total for everything visible in the frame |
| `truth_source` | yes | see the tiers below |
| `grams` | no | per component, comma-separated |
| `has_scale_ref` | no | `yes`/`no` — was a plate, fork, hand or katori in frame |
| `hidden_fat` | no | `none`/`low`/`high` — tempered dal and restaurant gravy are `high` |
| `notes` | no | free text |

## Truth tiers

`truth_source` decides whether a row is worth having. The harness **excludes
`estimate` by default** — scoring the model's guess against your guess measures
agreement, not accuracy, and it quietly makes the report look good.

| tier | what it means | trust |
|---|---|---|
| `label` | packaged food shot beside its own nutrition panel | best |
| `weighed` | components on a kitchen scale before eating, known recipe | best for home food |
| `recipe` | known recipe, estimated portions | usable |
| `menu` | chain restaurant with published nutrition | usable |
| `estimate` | you guessed | excluded unless `--include-weak-truth` |

If you do only one thing: **weigh ten Indian home meals before eating them.**
That set is worth more than fifty guessed photos.

## Shooting notes

- One photo per meal, taken the way a real user would — phone, from where
  they're sitting, not styled.
- Include a scale reference (plate rim, fork, hand) in most shots, and
  deliberately omit it in a few. Record which in `has_scale_ref`.
- Keep 3–4 adversarial cases: no scale reference, poor light, half-eaten,
  opaque takeaway container. These test whether the model *widens its range
  and drops confidence* rather than guessing — which is the behaviour the
  product actually promises.
- Don't include anything you'd be uncomfortable having checked into the repo.

## Running

```bash
cd services/api
python -m app.scripts.eval_vision --dry-run     # validate manifest, no API calls
python -m app.scripts.eval_vision               # full run
python -m app.scripts.eval_vision --cuisine indian-north
python -m app.scripts.eval_vision --no-hint     # harder: no dish name given
python -m app.scripts.eval_vision --out results.csv
```

`--dry-run` needs no API key and checks every row resolves to a real file with
a usable truth value. Run it as soon as you've added a few photos.
