# Constants and evidence

Trace runs on a few dozen numbers. This document lists them, states where each
one came from, and — where the honest answer is "we chose it" — says so.

It exists because a number in a codebase carries no memory of its own
provenance. `EWMA_ALPHA = 0.4` looks exactly as authoritative as
`EPLEY_DIVISOR = 30.0`, and only one of those has a paper behind it.

## How to read this

Every constant carries one of four labels.

**EVIDENCE** — a specific, named paper supports this value. The citation is
given in full, and a paragraph below the table says what the study actually
measured and in whom. A citation that cannot be named is not a citation.

**CONVENTION** — widely used in the field, with no strong validation for the
specific value. We say who uses it and that validation is absent.

**JUDGEMENT** — we chose it. We say why, and what would change it.

**PLACEHOLDER** — a value is present so the code runs. It is not defended.

A label of JUDGEMENT is not a defect. Most constants in most fitness products
are judgement calls; the difference here is that ours are labelled. The
EVIDENCE rows are only believable because the JUDGEMENT rows are admitted.

**One caveat applies to the whole table.** Evidence supporting a *relationship*
does not license a *value*. A meta-analysis showing that training volume drives
hypertrophy does not tell you to prescribe three sets. Where we have used a
paper for the direction of an effect and chosen the number ourselves, the row
says JUDGEMENT, not EVIDENCE.

---

## The table

| Constant | Value | Category | Source or rationale |
|---|---|---|---|
| `EPLEY_DIVISOR` | 30.0 | **CONVENTION** | Epley 1985, a coaching pamphlet, not peer-reviewed. Validated as a *correlation* by LeSuer 1997. See §1. |
| `REP_CEILING` | 15 | **JUDGEMENT** | No source supports 15. Halperin's breakpoint is in a **different unit** — see §2a before changing it. |
| `TREND_REP_CAP` | 12 | **EVIDENCE** | Halperin 2022: prediction error roughly 8× worse above 12 reps. See §2. |
| `EWMA_ALPHA` | 0.4 | **JUDGEMENT** | Chosen so ~3 weeks dominate. No source. Alternatives in §8. |
| `MIN_SESSIONS` | 8 | **JUDGEMENT** | The *premise* is evidence-backed (§2); the *number* is not. See §7. |
| `MIN_WEIGH_INS` | 14 | **JUDGEMENT** | Two weeks of daily weighing. Not audited. |
| `ON_TARGET_BAND` | 0.03 | **JUDGEMENT** | Chosen to sit above single-set e1RM noise. We have not measured that noise in our own data. |
| `PURPLE_MARGIN` | 0.005 | **JUDGEMENT** | Anti-rounding guard, not a physiological claim. |
| `CONFIRM_BAND` | 0.02 | **JUDGEMENT** | As above. |
| `LAYOFF_RESET_WEEKS` | 4 | **CONVENTION** | Bosquet 2013 supports that cessation costs strength; it does not locate a 4-week threshold. See §4. |
| `KCAL_PER_KG_TISSUE` | 7700.0 | **CONVENTION, KNOWN LIMITS** | Wishnofsky 1958 via Hall 2008. Fails hardest for our own users. See §3. |
| `REST_COMPOUND_S` | 180 | **CONVENTION** | Longer rest is supported; 180 is a round number in that region. |
| `REST_ISOLATION_S` | 90 | **CONVENTION** | As above, shorter end. |
| `REST_LIGHT_BONUS_S` | −30 | **JUDGEMENT** | No source. |
| `SETS_BY_CLASS` | 3 / 3 / 2 | **JUDGEMENT** | Schoenfeld 2017 finds ~10 weekly sets per muscle; per-*session* per-*exercise* counts are ours. See §5. |
| `WEIGHT_STEP_KG` | 2.0–5.0 | **EVIDENCE (engineering)** | Not physiology. These are the plates and stack increments that physically exist. |
| `BEGINNER_TARGET_RIR` | 3 | **JUDGEMENT** | Conservative by choice. |
| `fatigue_cost` | **3 on all 154 rows** | **PLACEHOLDER** | Not merely uncalibrated — *constant*. Its consumer is therefore dead code. See §11. |
| `default_rest_seconds` | **120 on all 154 rows** | **PLACEHOLDER** | Uniform, so the per-class rest constants below never reach a prescription. See §11. |
| rep-range defaults | 6–10 / 8–12 / 10–15 + 5 overrides | **JUDGEMENT** | Set on 153 of 154 rows; Plank deliberately NULL. See §6. |
| RIR → RPE | `RPE = 10 − RIR` | **CONVENTION** | Definitional in the Zourdos/Helms scale, not an empirical result. See §2. |
| `NOVICE_DISCOUNT` / `NOVICE_MONTHS` | 0.5 / 2 | **JUDGEMENT** | Rests on *neural vs muscular* early adaptation, **not** on novices misjudging effort. See §10. |

---

## §1 — Epley, and why not Brzycki or Lombardi

`EPLEY_DIVISOR = 30.0` implements `1RM = w × (1 + reps/30)`.

**The formula's own source is not a study.** It comes from *Boyd Epley Workout*
(1985), a coaching publication from the University of Nebraska strength
programme. It was never peer-reviewed and reports no validation data. Anyone
citing "Epley" as evidence is citing a pamphlet.

What can be cited is the validation done later.

> **LeSuer DA, McCormick JH, Mayhew JL, Wasserstein RL, Arnold MD.** The
> accuracy of prediction equations for estimating 1-RM performance in the bench
> press, squat, and deadlift. *J Strength Cond Res* 1997;11(4):211–213.

**What it measured, and in whom.** Seven prediction equations compared against
directly measured 1RMs in **67 untrained college students (40 men, 27 women)**
enrolled in weight-training classes, after four 45-minute sessions to learn
technique.

**Why the population matters, and here it helps us.** This is close to Trace's
actual user — a beginner in a college gym, not a competitive powerlifter. Much
strength research is done on trained male athletes and generalises poorly
downward. This one does not have that problem.

**What it found, including the part that constrains us.** All equations
correlated highly with measured 1RM (r > 0.95). But correlation is not
agreement: the equations differed meaningfully in absolute accuracy across
lifts, and **all of them significantly underestimated the deadlift 1RM.**

The honest statement is therefore: Epley is a well-correlated estimator whose
absolute error is lift-dependent, and which is known to be biased low on the
deadlift. Trace never displays an e1RM as a measured max and never prescribes a
percentage of it — it is used only to compare a lifter against their own prior
e1RM on the same movement, where a consistent per-lift bias largely cancels.

**Why not Brzycki or Lombardi.** LeSuer compared them all and no single equation
won across all three lifts. Choosing Epley over Brzycki is therefore
**JUDGEMENT, not evidence** — Epley is the most widely implemented, which makes
Trace's numbers comparable with other tools. That is an interoperability
argument, not a scientific one, and it should be labelled as such.

## §2 — The rep ceiling, and the RIR scale

> **Halperin I, Malleron T, Har-Nir I, Androulakis-Korakakis P, Wolf M,
> Fisher J, Steele J.** Accuracy in predicting repetitions to task failure in
> resistance exercise: a scoping review and exploratory meta-analysis. *Sports
> Med* 2022;52(2):377–390. doi:10.1007/s40279-021-01559-x

**What it measured, and in whom.** A scoping review and multilevel
meta-analysis of how accurately people predict their remaining repetitions.
Sixteen publications qualified; **twelve studies with 414 participants** and 262
effect sizes entered the meta-analysis. Participants were healthy adults across
a range of training experience.

**What it found.**

- Participants **underpredicted** repetitions to failure by **0.95 reps**
  (95% CI 0.17–1.73). People have about one more rep in reserve than they think.
- Heterogeneity was extreme: **I² = 97.9%**. The pooled estimate conceals very
  large between-study variation, which should temper any precise use of it.
- Accuracy improved closer to failure (β = −0.025).
- **Accuracy was far worse on high-rep sets: β = 0.06 at ≤12 reps versus
  β = 0.47 above 12 reps** — roughly an eightfold increase in error.
- **Training status had no meaningful influence** (β = −0.006). Experienced
  lifters were not reliably better at this than novices.

**What this licenses, and what it does not.** It licenses the design principle
that a single set's RIR is noisy and must not be allowed to rewrite a verdict —
including for experienced lifters, whom we might otherwise have assumed were
exempt. It locates a breakpoint at **12 repetitions**. It does **not** support
any particular number of sessions before a verdict is issued (see §7).

**The RIR → RPE mapping** (`RPE = 10 − RIR`) is **definitional** within the
Zourdos/Helms RIR-based scale, not an empirical finding. It is a unit
conversion and must never be presented as evidence-backed.

## §2a — Why `REP_CEILING` was not changed to 12

This document's first draft recommended `REP_CEILING = 15 → 12`, and that
recommendation was approved. **It was then withdrawn on a closer reading of the
code, and the reason is a units error worth recording.**

`REP_CEILING` and `TREND_REP_CAP` measure different things:

| | Unit | Gates |
|---|---|---|
| `TREND_REP_CAP = 12` | **raw reps** | `trend_e1rm` — a set above it contributes no point to the trend series at all |
| `REP_CEILING = 15` | **effective reps** (reps + RIR) | the single-set verdict and the suggested-next-load route |

Halperin's breakpoint is at **12 repetitions performed** — raw reps. That is
`TREND_REP_CAP`'s unit, and `TREND_REP_CAP` is already 12. It is *not*
`REP_CEILING`'s unit. A set of 12 reps at RIR 3 is 12 raw and 15 effective:
right on one bound and right on the other, measuring different things.

There is also a second mismatch. Halperin measures the accuracy of **RIR
estimates**. `REP_CEILING` exists because **Epley** drifts optimistic at high
reps. Those are two different degradations that happen to worsen in the same
direction, and one does not license a threshold for the other.

**The interesting consequence, not implemented:** if RIR is unreliable above 12
raw reps, then the "+RIR" term in an effective-rep count is itself unreliable
there — which argues for gating the single-set verdict on **raw reps as well
as** effective reps, rather than for moving 15 to 12. That is a design change,
not a constant change, and it is not made on this document's authority.

`REP_CEILING = 15` therefore stays, still labelled JUDGEMENT, with the
disagreement between the two constants now documented in both docstrings
instead of looking like a duplicate.

## §3 — 7700 kcal per kg

`KCAL_PER_KG_TISSUE = 7700.0` is the metric form of the "3500 kcal per pound"
rule.

> **Wishnofsky M.** Caloric equivalents of gained or lost weight. *Am J Clin
> Nutr* 1958;6(5):542–546.

**What it was.** A 1958 review concluding that the caloric equivalent of a pound
of body weight gained or lost is 3,500 kcal, **assuming adequate protein
intake**. Wishnofsky himself noted the value is much lower during fasting or
refeeding after a fast. Even the original author bounded the claim; sixty-eight
years of citation have sanded the bounds off.

> **Hall KD.** What is the required energy deficit per unit weight loss? *Int J
> Obes* 2008;32(3):573–576. PMID 17848938. doi:10.1038/sj.ijo.0803720

**What it found.** Using a modification of the classic Forbes equation, Hall
showed the energy density of lost tissue is **not a constant** — it depends on
initial body fat, because leaner people lose a greater proportion of lean mass,
which has a much lower energy density than fat. The rule "approximately matches
the predicted energy density of lost weight in obese subjects with an initial
body fat above 30 kg **but overestimates the cumulative energy deficit required
per unit weight loss for people with lower initial body fat.**"

**Where this breaks for Trace specifically — and it is worse for us than for a
general weight-loss app.**

1. **We use the constant in the inverse direction.** `tdee.py` computes
   `TDEE_observed = mean_intake − (Δtrend_kg × 7700) / days`. We are not
   predicting weight from a deficit; we are inferring maintenance from an
   observed weight trend. Any error in 7700 propagates straight into the TDEE
   estimate, scaled by the rate of change.

2. **The error is largest in our own population.** Hall's result is that the
   rule is closest to right for people with high initial body fat and worst for
   lean people. Lifters sit at the lean end of that distribution. Trace's users
   are where the constant is least accurate.

3. **It is weakest at exactly our headline claim.** 7700 assumes mostly-fat
   tissue. Trace's product claim is that we can distinguish muscle gain from fat
   gain. For a lifter *gaining* lean mass the true energy cost per kg is far
   lower than 7700, so the constant is least valid in precisely the case the
   product exists to handle.

**Magnitude, worked.** A lean lifter losing 0.25 kg/week whose true tissue
energy density is nearer 6,500 kcal/kg: we compute a daily deficit of 275 kcal
where the truth is about 232 — understating TDEE by roughly **40 kcal/day**.
Small against a 2,500 kcal target, and **systematic rather than random**, so it
does not average out over time.

**Recommendation: keep the value, change the label and the disclosure.** The
alternative is Hall's full dynamic model, which requires body-composition input
Trace does not reliably have. A wrong constant we understand and have bounded is
safer than a sophisticated model fed guessed inputs. But it must not be
presented as a physical constant, and its direction of error should be stated.

## §4 — Layoff reset

> **Bosquet L, Berryman N, Dupuy O, Mekary S, Arvisais D, Bherer L, Mujika I.**
> Effect of training cessation on muscular performance: a meta-analysis. *Scand
> J Med Sci Sports* 2013;23(3):e140–e149. doi:10.1111/sms.12047

**What it measured.** 103 of 284 screened studies. It found a detrimental effect
of resistance-training cessation on **all** components of muscular performance,
with larger effects in inactive people than in recreational athletes for maximal
force and maximal power.

**What it does not do: locate a threshold.** It establishes that cessation costs
strength and that the cost differs by training status. It does not identify a
number of weeks at which loss becomes meaningful. `LAYOFF_RESET_WEEKS = 4`
therefore stays **CONVENTION** — the direction is evidenced, the boundary is
not. What would change it: a study reporting strength loss as a function of
cessation duration in recreationally trained lifters.

## §5 — Set counts

> **Schoenfeld BJ, Ogborn D, Krieger JW.** Dose–response relationship between
> weekly resistance training volume and increases in muscle mass: a systematic
> review and meta-analysis. *J Sports Sci* 2017;35(11):1073–1082.

**What it measured.** A meta-regression over 34 treatment groups from 15
studies, in people already resistance training.

**What it found.** A graded dose–response between weekly set volume and
hypertrophy (P = 0.002 as a continuous variable; P = 0.03 categorised). Higher
versus lower volume gave an effect-size difference of 0.241, about a **3.9%
difference in gain**. A threshold around **10 weekly sets per muscle group** was
suggested for near-maximal hypertrophy. Heterogeneity was substantial and the
upper bound of the dose–response was unclear.

**Why `SETS_BY_CLASS` is still JUDGEMENT.** The finding concerns **weekly sets
per muscle group**. `SETS_BY_CLASS` is **per exercise, per session**. Converting
between them requires assumptions about weekly frequency and how many exercises
hit a muscle — assumptions that are ours, not Schoenfeld's. The paper also
studies hypertrophy in people already training, whereas these defaults target a
first-time lifter, where the binding constraint is whether they come back in
week two rather than whether growth is maximal. Citing this paper for the value
3 would be exactly the overreach this document exists to prevent.

## §6 — Rep-range defaults

Now set on 153 of 154 classified movements (migration `a7e2d3b64f19`). Every
value is **JUDGEMENT**.

A rep range is a **prescription, not a measurement**. There is no study
establishing the correct rep range for a cable lateral raise. The literature
supports a broad claim — that hypertrophy is similar across a wide loading range
when sets are taken near failure — and that claim underdetermines any specific
range. We will publish the ranges and label them as chosen.

## §7 — MIN_SESSIONS: the row that did not move

This was expected to graduate from JUDGEMENT to EVIDENCE on the strength of the
effort-report imprecision literature. **It does not, and the reason is worth
stating.**

Those papers quantify the imprecision of a **single effort report** — about one
repetition, with enormous between-study variance. `MIN_SESSIONS` answers a
different question: how many *sessions* of evidence are needed before Trace will
assert a strength verdict. Going from per-set measurement error to a required
session count needs an assumed effect size, an assumed error distribution and a
chosen false-positive rate. We have not done that analysis.

The papers therefore support the **premise** — one session cannot rewrite a
verdict — without supporting the **number**. `MIN_SESSIONS = 8` stays JUDGEMENT.

**What would move it:** a power analysis on Trace's own logged data, estimating
session-to-session variance of e1RM per movement and deriving the number of
sessions needed to detect a given change at a stated confidence. That is
computable from data we already collect, and it is the highest-value follow-up
in this document.

## §8 — Kalman and Theil–Sen versus our EWMA

Trace smooths the strength trend with an EWMA at α = 0.4 and the weight trend
with a 7-day rolling mean. Both are **JUDGEMENT**.

A **Kalman filter** would carry an explicit uncertainty estimate alongside the
value — telling us not just the current e1RM but how confident we are in it.
That is a genuine fit for a product whose central discipline is refusing to
answer without enough evidence: `INSUFFICIENT_DATA` could become a threshold on
posterior variance rather than a session count, which would address §7 directly.
The cost is real: process and measurement noise must be specified per movement,
and a misspecified filter is confidently wrong in a way an EWMA is not.

**Theil–Sen** is a median-of-slopes estimator with roughly 29% breakdown — it
ignores outliers rather than smoothing them. For a daily weight series polluted
by salt, hydration and gut content, that is better motivated than a rolling
mean, and it is cheap.

**Recommendation: neither is implemented, and neither should be on this
document's authority.** Theil–Sen for the weight trend is the stronger of the
two and the easier to validate. Both are decisions for the product owner.

## §9 — What this audit covers

**The audit is of what the code contains, not of what anyone proposed.**

Two constants were originally on the list for this document —
`STALE_AFTER_DAYS = 21` and `SESSIONS_AFTER_RETURN = 3` — and neither exists
anywhere in the codebase. Both were proposals from design discussion that were
never implemented. They have been removed from the table rather than listed as
absent, because a table of constants that includes non-constants is not a table
of constants.

The rule this establishes: a row enters this document when a value is in the
code. If `SESSIONS_AFTER_RETURN = 3` is implemented later it enters as
**JUDGEMENT**, like anything else we choose.

The nearest thing that does exist is `LAYOFF_RESET_WEEKS = 4` (§4).

## §10 — NOVICE_DISCOUNT rests on a different claim than expected

Halperin 2022 found training status had **no meaningful influence** on the
accuracy of effort reports (β = −0.006). That raised a question: does
`NOVICE_DISCOUNT = 0.5` exist because we assume novices misjudge effort? If so,
the premise is unsupported.

**It does not.** The guardrail in `adjudication.py` is commented *"novice gains
are neurological, not muscular"*, and halves the strength-index delta for
lifters inside `NOVICE_MONTHS`. The claim is that **early strength gains reflect
neural adaptation rather than hypertrophy** — so a beginner's rising e1RM is
weaker evidence of muscle gain than the same rise in a trained lifter.

That is a real and long-standing claim in the strength literature, and it is a
completely different claim from effort-report accuracy. Halperin neither
supports nor undermines it.

**It remains JUDGEMENT, and the discount factor is the weak part.** Even
granting the neural-adaptation premise, nothing establishes that the correct
discount is *half*. 0.5 is a round number standing in for an effect size nobody
has estimated for us. What would move it: a study reporting the proportion of
early strength gain attributable to neural versus hypertrophic adaptation, over
a window comparable to `NOVICE_MONTHS = 2`.

## §11 — Two columns that are constant, and what that hides

Discovered while generating the first real programmes against the live
database, not by reading code:

```
default_rest_seconds:  120 on all 154 rows
fatigue_cost:            3 on all 154 rows
```

Both are `NOT NULL` and fully populated, which is how they passed an earlier
column-level audit that counted nulls. **A column with no nulls and one distinct
value is populated in the same sense that a stopped clock shows a time.**

The consequences are concrete:

- `REST_COMPOUND_S = 180`, `REST_ISOLATION_S = 90` and `REST_LIGHT_BONUS_S`
  are all real constants that **never reach a prescription**, because the
  generator reads `default_rest_seconds` from the row and every row says 120.
- `_sort_key` in `programming.py` orders candidates by
  `(class_priority, -fatigue_cost, name, exercise_id)`. With `exercise_class`
  NULL on every row and `fatigue_cost` identical on every row, the first two
  terms are constant and **selection is effectively alphabetical by name.**

That second point explains an otherwise baffling result: a 154-movement
catalogue generating four-day programmes out of seven distinct exercises.

Neither column is changed here. They are recorded as PLACEHOLDER so that the
next person to read a rest value in the codebase knows it is not the one being
served.

---

## Sources

Every citation below was resolved against a bibliographic index before being
listed. Where we relied on an abstract rather than a full text, the section
above states only what the abstract states.

- Epley B. *Boyd Epley Workout.* 1985. Not peer-reviewed.
- LeSuer DA, McCormick JH, Mayhew JL, Wasserstein RL, Arnold MD. *J Strength
  Cond Res* 1997;11(4):211–213.
- Halperin I, Malleron T, Har-Nir I, Androulakis-Korakakis P, Wolf M, Fisher J,
  Steele J. *Sports Med* 2022;52(2):377–390. doi:10.1007/s40279-021-01559-x
- Wishnofsky M. *Am J Clin Nutr* 1958;6(5):542–546.
- Hall KD. *Int J Obes* 2008;32(3):573–576. doi:10.1038/sj.ijo.0803720
- Bosquet L, Berryman N, Dupuy O, Mekary S, Arvisais D, Bherer L, Mujika I.
  *Scand J Med Sci Sports* 2013;23(3):e140–e149. doi:10.1111/sms.12047
- Schoenfeld BJ, Ogborn D, Krieger JW. *J Sports Sci* 2017;35(11):1073–1082.

### Not yet audited

These rows are labelled from their code comments and have **not** been checked
against primary literature: `MIN_WEIGH_INS`, `ON_TARGET_BAND`, `PURPLE_MARGIN`,
`CONFIRM_BAND`, `REST_COMPOUND_S`, `REST_ISOLATION_S`, `REST_LIGHT_BONUS_S`,
`BEGINNER_TARGET_RIR`, `NOVICE_DISCOUNT`, `NOVICE_MONTHS`, `fatigue_cost`, and
the adaptive-TDEE estimator itself.

Listing them as unaudited is deliberate. A partially completed audit that hides
its own boundary is worse than one that shows it.
