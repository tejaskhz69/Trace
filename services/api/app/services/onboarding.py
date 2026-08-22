"""Turn a new user's answers into a starting plan.

WHY THIS EXISTS SEPARATELY FROM tdee.py
---------------------------------------
`tdee.py` is the *adaptive* engine: it reconstructs expenditure from weeks of
demonstrated energy balance. On day one there is no such history, so every
number here is a **prior** -- an educated starting point that the adaptive
loop is expected to overwrite within three weeks. Keeping it in its own module
makes that distinction impossible to miss: nothing in here should ever be used
once `estimate_expenditure()` has real data to chew on.

The two jobs:

  1. Convert the questionnaire into an activity multiplier, rather than
     defaulting everyone to 1.45 and hoping.
  2. Lay out seven concrete days of calories and macros, because "eat 2,450
     kcal" is not a plan a beginner can act on.

NON-NEGOTIABLE #1 STILL HOLDS. The activity multiplier is a *prior on
expenditure*, not a licence to add exercise calories back. A user who does five
cardio sessions a week gets a higher baseline TDEE estimate once, at signup.
They do NOT get extra calories on the days they train -- see `plan_week()`,
where training days are funded by borrowing from rest days, so the weekly total
is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tdee import FIBER_G_PER_1000_KCAL, mifflin_st_jeor

# ---------------------------------------------------------------------------
# Activity multiplier
# ---------------------------------------------------------------------------

# Steps are the single most predictive cheap signal for NEAT, which is where
# most of the between-person variance in TDEE lives -- far more than structured
# exercise does. These brackets are deliberately coarse; pretending to
# distinguish 7,400 from 7,600 steps would be false precision.
_STEP_BRACKETS: tuple[tuple[int, float], ...] = (
    (4000, 1.20),   # desk-bound, drives everywhere
    (7500, 1.32),   # light -- some walking built into the day
    (11000, 1.45),  # moderate -- walks deliberately
    (15000, 1.58),  # high -- on their feet for work
    (10**9, 1.70),  # very high -- manual labour
)

# Each cardio session a week adds a little on top. Capped, because someone
# claiming fourteen sessions is describing intent, not behaviour.
_CARDIO_PER_SESSION = 0.025
_CARDIO_MAX_BONUS = 0.15

# Lifting is included in the multiplier but weighted lightly: an hour of
# resistance training burns far less than lifters believe, and the EPOC
# literature does not support the numbers printed on gym equipment.
_LIFTING_BONUS = 0.03

MULTIPLIER_FLOOR = 1.20
MULTIPLIER_CEILING = 1.90


def activity_multiplier(
    *,
    daily_steps: int,
    cardio_sessions_per_week: int,
    lifting_sessions_per_week: int = 0,
) -> float:
    """A TDEE multiplier over BMR, derived rather than guessed.

    Returns a value in [1.20, 1.90]. This is a prior only; the adaptive engine
    replaces it as soon as there are ~3 weeks of weigh-ins and logs.
    """
    steps = max(0, daily_steps)
    base = next(mult for threshold, mult in _STEP_BRACKETS if steps < threshold)

    cardio = min(
        max(0, cardio_sessions_per_week) * _CARDIO_PER_SESSION, _CARDIO_MAX_BONUS
    )
    lifting = min(max(0, lifting_sessions_per_week), 6) * _LIFTING_BONUS

    return round(
        min(MULTIPLIER_CEILING, max(MULTIPLIER_FLOOR, base + cardio + lifting)), 3
    )


# ---------------------------------------------------------------------------
# Metabolic history
# ---------------------------------------------------------------------------

# Someone at 70 kg who has never been heavier and someone at 70 kg who dieted
# down from 91 kg do not burn the same number of calories. The formerly-heavier
# person is measurably below the prediction -- the reduced-obese literature
# puts it around 10-15% below what body composition alone predicts, and it
# persists for years. Ignoring it is why so many people are told to eat an
# amount that stalls them immediately.
#
# We apply a partial correction rather than the full literature figure: the
# adaptive engine will find the true number within weeks, and starting a user
# too LOW is a worse failure than starting them slightly high -- it costs
# adherence and it costs muscle.
ADAPTATION_PER_PCT_LOST = 0.004   # 0.4% lower TDEE per 1% below peak weight
ADAPTATION_MAX = 0.10             # never dock more than 10%
ADAPTATION_MIN_PCT_LOST = 5.0     # under 5% below peak is noise, not history


@dataclass
class MetabolicHistory:
    pct_below_peak: float
    adaptation_factor: float  # multiply TDEE by this; <= 1.0
    note: str


def metabolic_history(
    *, weight_kg: float, highest_weight_kg: float | None
) -> MetabolicHistory:
    """Discount the TDEE prior for a user who used to be substantially heavier.

    `highest_weight_kg` of None means "not asked / don't know" and is treated
    as no history, NOT as "never been heavier" -- refusing to assume is the
    house rule (CLAUDE.md non-negotiable #3).
    """
    if not highest_weight_kg or highest_weight_kg <= weight_kg:
        return MetabolicHistory(
            pct_below_peak=0.0,
            adaptation_factor=1.0,
            note="No weight-loss history recorded, so no adaptation applied.",
        )

    pct = (highest_weight_kg - weight_kg) / highest_weight_kg * 100.0

    if pct < ADAPTATION_MIN_PCT_LOST:
        return MetabolicHistory(
            pct_below_peak=round(pct, 1),
            adaptation_factor=1.0,
            note=(
                f"You're {pct:.0f}% below your heaviest -- small enough that it "
                f"doesn't change the estimate."
            ),
        )

    factor = 1.0 - min(pct * ADAPTATION_PER_PCT_LOST / 100.0 * 100.0, ADAPTATION_MAX)
    return MetabolicHistory(
        pct_below_peak=round(pct, 1),
        adaptation_factor=round(factor, 4),
        note=(
            f"You're {pct:.0f}% below your heaviest weight of "
            f"{highest_weight_kg:.0f} kg. People who have lost that much tend to "
            f"burn less than their size predicts, so your starting estimate is "
            f"{(1 - factor) * 100:.0f}% lower than the textbook figure. We'll "
            f"correct it from your real data within a few weeks."
        ),
    )


# ---------------------------------------------------------------------------
# The seven-day plan
# ---------------------------------------------------------------------------

# Training days get more carbohydrate and rest days get less, funded entirely
# by moving calories between days -- the weekly total is identical. This is
# presentation and adherence, not metabolic magic, and the docstring says so
# because a future reader will otherwise assume it does something it doesn't.
TRAINING_DAY_SWING = 0.10  # +10% on training days, offset on rest days

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass
class PlannedDay:
    day: str            # "Mon"
    index: int          # 0-6
    day_type: str       # "training" | "rest"
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int


@dataclass
class WeekPlan:
    days: list[PlannedDay]
    weekly_calories: int
    daily_average: int
    training_days: int
    rationale: str
    math: dict = field(default_factory=dict)


def plan_week(
    *,
    calorie_target: float,
    protein_target_g: float,
    fat_target_g: float,
    training_day_indices: tuple[int, ...] | list[int],
) -> WeekPlan:
    """Spread a daily target across seven named days.

    Protein is CONSTANT every day -- it is the one macro where the daily floor
    matters more than the weekly total, because the strength verdict is
    uninterpretable if protein dips (see adjudication). Fat is held constant
    for hormonal and satiety reasons. Carbohydrate absorbs the entire swing,
    which is also where it does the most good: on the days you train.
    """
    training = sorted({i for i in training_day_indices if 0 <= i <= 6})
    n_train = len(training)
    n_rest = 7 - n_train

    weekly = calorie_target * 7

    # With no training days (or all seven), there is nothing to cycle against,
    # so every day is simply the average. Dividing by zero here would be a
    # spectacular way to hand someone an infinite calorie target.
    if n_train == 0 or n_rest == 0:
        train_kcal = rest_kcal = calorie_target
    else:
        train_kcal = calorie_target * (1 + TRAINING_DAY_SWING)
        # Rest days absorb exactly what the training days borrowed.
        rest_kcal = (weekly - train_kcal * n_train) / n_rest

    protein = round(protein_target_g)
    fat = round(fat_target_g)

    days: list[PlannedDay] = []
    for i in range(7):
        is_training = i in training
        kcal = round((train_kcal if is_training else rest_kcal) / 10) * 10
        # Carbs are the remainder, floored at zero -- an aggressive cut with a
        # high protein floor can mathematically leave nothing, and a negative
        # carb target displayed to a user is a bug, not a diet.
        carbs = max(0, round((kcal - protein * 4 - fat * 9) / 4))
        days.append(
            PlannedDay(
                day=DAY_NAMES[i],
                index=i,
                day_type="training" if is_training else "rest",
                calories=int(kcal),
                protein_g=protein,
                carbs_g=int(carbs),
                fat_g=fat,
                fiber_g=int(round(kcal / 1000.0 * FIBER_G_PER_1000_KCAL)),
            )
        )

    actual_weekly = sum(d.calories for d in days)

    if n_train and n_rest:
        rationale = (
            f"{n_train} training days at ~{int(train_kcal):,} kcal and "
            f"{n_rest} rest days at ~{int(rest_kcal):,} kcal. The week still "
            f"totals {actual_weekly:,} kcal -- training days aren't extra "
            f"calories, they're borrowed from your rest days, so the carbs "
            f"land when you can use them."
        )
    else:
        rationale = (
            f"Every day is {int(calorie_target):,} kcal. With no split between "
            f"training and rest days there's nothing to cycle against."
        )

    return WeekPlan(
        days=days,
        weekly_calories=int(actual_weekly),
        daily_average=int(round(actual_weekly / 7)),
        training_days=n_train,
        rationale=rationale,
        math={
            "training_day_kcal": round(train_kcal, 1),
            "rest_day_kcal": round(rest_kcal, 1),
            "swing_pct": TRAINING_DAY_SWING * 100,
            "protein_g_constant": protein,
            "fat_g_constant": fat,
        },
    )


# ---------------------------------------------------------------------------
# The whole thing, end to end
# ---------------------------------------------------------------------------


@dataclass
class OnboardingPlan:
    bmr: float
    activity_multiplier: float
    tdee_prior: float
    history: MetabolicHistory
    calorie_target: int
    protein_target_g: int
    carb_target_g: int
    fat_target_g: int
    fiber_target_g: int
    week: WeekPlan
    goal_rate_pct_per_week: float
    notes: list[str] = field(default_factory=list)


def build_plan(
    *,
    sex: str | None,
    age_years: float,
    height_cm: float,
    weight_kg: float,
    highest_weight_kg: float | None,
    daily_steps: int,
    cardio_sessions_per_week: int,
    lifting_sessions_per_week: int,
    lifting_experience_months: int,
    goal_type: str,
    training_day_indices: tuple[int, ...] | list[int] | None = None,
) -> OnboardingPlan:
    """The full day-one plan, from questionnaire answers to seven named days.

    Deliberately imports `recommend_targets` at call time rather than at module
    scope so the two modules stay independently testable and the direction of
    the dependency stays obvious: onboarding uses tdee, never the reverse.
    """
    from .tdee import recommend_targets

    bmr = mifflin_st_jeor(weight_kg, height_cm, age_years, sex)
    mult = activity_multiplier(
        daily_steps=daily_steps,
        cardio_sessions_per_week=cardio_sessions_per_week,
        lifting_sessions_per_week=lifting_sessions_per_week,
    )
    history = metabolic_history(
        weight_kg=weight_kg, highest_weight_kg=highest_weight_kg
    )
    tdee_prior = bmr * mult * history.adaptation_factor

    # A novice lifter gains muscle fast enough that a slightly bolder surplus
    # is justified; an experienced lifter surplusing at the same rate is mostly
    # buying fat. This is the one place experience changes a number.
    novice = lifting_experience_months < 12
    goal_rate = {
        "lose": -0.7,
        "gain": 0.5 if novice else 0.25,
        "recomp": 0.0,
        "maintain": 0.0,
    }.get(goal_type, 0.0)

    rec = recommend_targets(
        tdee=tdee_prior,
        weight_kg=weight_kg,
        goal_type=goal_type,
        previous_target=None,
        bmr=bmr,
        goal_rate_pct_per_week=goal_rate,
    )

    if training_day_indices is None:
        # Spread the user's stated lifting frequency across the week rather
        # than clustering it, so the default plan is one a human might follow.
        n = max(0, min(6, lifting_sessions_per_week))
        spread = {
            0: (), 1: (2,), 2: (1, 4), 3: (0, 2, 4),
            4: (0, 1, 3, 4), 5: (0, 1, 2, 4, 5), 6: (0, 1, 2, 3, 4, 5),
        }
        training_day_indices = spread[n]

    week = plan_week(
        calorie_target=rec.calorie_target,
        protein_target_g=rec.protein_target_g,
        fat_target_g=rec.fat_target_g,
        training_day_indices=training_day_indices,
    )

    notes = [history.note]
    if novice and goal_type == "gain":
        notes.append(
            "You're under a year of lifting, so you can gain a little faster "
            "without much of it being fat. We'll slow this down as you advance."
        )
    notes.append(
        "These are starting estimates from a formula. Trace replaces them with "
        "your real expenditure once it has about three weeks of weigh-ins and "
        "food logs -- that number is usually different, sometimes by a lot."
    )

    return OnboardingPlan(
        bmr=round(bmr, 1),
        activity_multiplier=mult,
        tdee_prior=round(tdee_prior),
        history=history,
        calorie_target=int(rec.calorie_target),
        protein_target_g=int(rec.protein_target_g),
        carb_target_g=int(rec.carb_target_g),
        fat_target_g=int(rec.fat_target_g),
        fiber_target_g=int(rec.fiber_target_g),
        week=week,
        goal_rate_pct_per_week=goal_rate,
        notes=notes,
    )
