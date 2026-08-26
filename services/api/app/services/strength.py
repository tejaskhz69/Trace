"""Per-set strength adjudication: what did that set actually prove?

THE IDEA THIS FILE IMPLEMENTS
Most trackers store a set and show you a number. That is a diary, not a
measurement. A set only becomes a *measurement of strength* when you know how
close to failure it was -- 75 kg x 10 with five reps left and 75 kg x 10 with
nothing left are wildly different facts about the same lifter.

So every set carries reps-in-reserve (RIR), and every set produces an
estimated one-rep max. That lets us answer, immediately after the set, the
only question the lifter actually cares about:

    did that maintain my strength, or move it?

WHY RIR AND NOT RPE INTERNALLY
They are the same scale inverted (RPE = 10 - RIR), and RIR is the one you can
ask for honestly mid-set: "how many more could you have done" is a question a
beginner can answer. RPE is jargon. We store RIR, and render RPE where the
lifter expects it.

WHAT A "PURPLE SET" IS
A set whose estimated max exceeds your current best estimate -- i.e. it did
not just repeat what you already knew, it raised the number. Naming it gives
the lifter one unambiguous thing to chase per set, and the coaching line below
always tells them the two concrete routes to it: one more rep, or the next
loadable weight.

NOTHING HERE DOES I/O. Every function is pure and covered by tests, because
this is the layer that decides whether the app tells someone they got
stronger, and being wrong about that is the worst thing the product can do.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

# Epley's divisor. Above ~12 reps the estimate drifts optimistic for everyone,
# which is why REP_CEILING exists rather than pretending a 25-rep set measures
# a max.
EPLEY_DIVISOR = 30.0

# Beyond this many effective reps (reps + RIR) the e1RM is a fitness
# measurement, not a strength one. We still store the set; we refuse to let it
# set the reference max.
REP_CEILING = 15

# How far below the reference a set may land and still count as maintaining.
# e1RM from a single set carries a few percent of noise -- bar speed, sleep,
# how honest the RIR call was. Calling a 2% dip a "strength decline" would
# make the app cry wolf every session.
ON_TARGET_BAND = 0.03

# A set has to clear the reference by this much to be called a new best. Zero
# would let rounding noise mint a personal record.
PURPLE_MARGIN = 0.005

# Session-level: how much a week-over-week e1RM change has to move before we
# call it a change at all.
CONFIRM_BAND = 0.02

# Smallest weight you can actually add, by equipment. Telling someone to put
# 1.3 kg on a barbell is telling them nothing; these are the real increments.
WEIGHT_STEP_KG: dict[str, float] = {
    "barbell": 2.5,
    "smith": 2.5,
    "ez_bar": 2.5,
    "dumbbell": 2.0,
    "kettlebell": 4.0,
    "machine": 5.0,
    "cable": 2.5,
    "plate_loaded": 5.0,
    "bodyweight": 0.0,
    "band": 0.0,
}
DEFAULT_WEIGHT_STEP_KG = 2.5

# Rest, in seconds. A compound at low RIR needs real rest; a lateral raise
# does not. These are defaults the lifter can override, not prescriptions.
REST_COMPOUND_S = 180
REST_ISOLATION_S = 90
REST_LIGHT_BONUS_S = -30  # taking it easy (RIR >= 3) shortens the rest


class SetVerdict(str, Enum):
    PURPLE = "PURPLE"          # raised your estimated max
    ON_TARGET = "ON_TARGET"    # maintained it
    UNDER = "UNDER"            # below it
    UNRATED = "UNRATED"        # no reference yet, or no RIR given


class ExerciseTrend(str, Enum):
    CONFIRMED = "CONFIRMED"    # e1RM held or rose against the previous best
    NO_CHANGE = "NO_CHANGE"    # inside the noise band
    DECLINE = "DECLINE"        # fell outside the noise band
    FIRST_TIME = "FIRST_TIME"  # nothing to compare against


# ---------------------------------------------------------------------------
# The estimate
#
# TWO e1RM FUNCTIONS LIVE HERE. DO NOT MERGE THEM.
#
# `e1rm` and `trend_e1rm` share one Epley core (`_epley`) and differ in three
# ways on purpose. They were once separate implementations in separate files,
# which was a real drift risk -- so the FORMULA is now defined once. What is
# not shared is the contract around it, because the two callers are asking
# different questions and 20 of 56 sampled inputs legitimately disagree.
#
#                     e1rm                      trend_e1rm
#   caller            a single logged set       the weekly strength trend
#   RIR               adjusted (reps + RIR)     not accepted
#   1 rep             100 kg x1 -> 103.3        100 kg x1 -> 100
#   rounding          1 dp                      none
#   rep cap           15 effective reps         12 reps
#
# WHY THE 1-REP CASE DIFFERS. If a lifter actually performed one rep at
# 100 kg, their one-rep max IS at least 100 kg -- that is a measurement, not
# an estimate, and Epley returning 103.3 there is a formula artifact. The
# trend must not inherit that artifact, because it feeds the adjudication
# engine's muscle-vs-fat verdict and a phantom 3.3% step on every single at
# the start of a series would read as strength gain that did not happen.
#
# WHY THE RIR ADJUSTMENT DIFFERS. A logged set knows how many reps were left
# in the tank, and a set stopped 3 short of failure is evidence of a
# 3-reps-heavier set. The weekly trend is built from already-reduced weekly
# bests where that information is gone.
#
# WHY THE CAPS DIFFER. `e1rm` counts effective reps (reps + RIR), so its
# ceiling has to sit higher than a raw rep cap to represent the same set.
#
# IF YOU TIDY THESE INTO ONE FUNCTION, one of those two contracts breaks
# silently. Collapsing onto `e1rm`'s semantics shifts the strength index for
# every 1-rep set ever logged; collapsing onto `trend_e1rm`'s throws away the
# RIR adjustment on every set. `tests/test_engines.py` pins the trend
# contract and `tests/test_strength.py` pins the per-set one; if a change
# makes you edit either, the behaviour moved and that is the bug.
# ---------------------------------------------------------------------------

#: Epley is noise beyond roughly 12 raw reps.
TREND_REP_CAP = 12

#: Smoothing factor for the weekly e1RM series. 0.4 keeps roughly the last
#: three weeks dominant without letting one good session set the trend.
EWMA_ALPHA = 0.4


def _epley(weight_kg: float, effective_reps: float) -> float:
    """1RM = w x (1 + reps/30). The formula, with no policy attached.

    Every e1RM in the product resolves to this line. Both public wrappers
    below decide separately what counts as a valid input and what to do with
    the result; neither re-derives the arithmetic.
    """
    return weight_kg * (1 + effective_reps / EPLEY_DIVISOR)


def trend_e1rm(weight_kg: float, reps: int) -> float | None:
    """e1RM for the weekly strength trend. See the block comment above.

    Unrounded, capped at TREND_REP_CAP raw reps, and exact at one rep --
    a single at 100 kg proves a max of at least 100 kg, so the formula does
    not get to add 3.3% to it.

    This is the function the adjudication engine reads, and it is exported
    from `adjudication` as `epley_e1rm` for backwards compatibility.
    """
    if reps < 1 or reps > TREND_REP_CAP or weight_kg <= 0:
        return None
    if reps == 1:
        return weight_kg
    return _epley(weight_kg, reps)


def ewma(values: list[float], alpha: float = EWMA_ALPHA) -> float | None:
    """Exponentially weighted mean, most recent last.

    Moved here unchanged from `adjudication`, so that the strength maths sits
    in one module. `None` for an empty series is a real answer, not a
    failure: there is nothing to smooth.
    """
    if not values:
        return None
    acc = values[0]
    for v in values[1:]:
        acc = acc + alpha * (v - acc)
    return acc


def e1rm(weight_kg: float, reps: int, rir: float | None = None) -> float | None:
    """Estimated one-rep max from a set, adjusted for reps left in the tank.

    A set stopped 3 reps short of failure is evidence of a 3-reps-heavier set,
    so the effective rep count is `reps + rir`. Ignoring RIR -- which is what
    a plain Epley does -- systematically under-rates every set that was not
    taken to failure, and almost no good training is taken to failure.

    Returns None rather than a number when the set cannot measure a max:
    zero/negative load, no reps, or so many effective reps that the formula is
    guessing. `None` is a real answer here; see the INSUFFICIENT_DATA rule.
    """
    if weight_kg <= 0 or reps <= 0:
        return None
    effective = reps + (rir if rir is not None and rir > 0 else 0.0)
    if effective > REP_CEILING:
        return None
    return round(_epley(weight_kg, effective), 1)


def load_pct(weight_kg: float, reference_e1rm: float | None) -> float | None:
    """What fraction of the estimated max this bar weight represents."""
    if not reference_e1rm or reference_e1rm <= 0 or weight_kg <= 0:
        return None
    return round(weight_kg / reference_e1rm * 100, 1)


def rpe_from_rir(rir: float | None) -> float | None:
    """RPE is the scale lifters read; RIR is the one they can answer."""
    if rir is None:
        return None
    return round(max(1.0, min(10.0, 10.0 - rir)), 1)


def weight_step(equipment: str | None) -> float:
    key = (equipment or "").strip().lower().replace("-", "_").replace(" ", "_")
    return WEIGHT_STEP_KG.get(key, DEFAULT_WEIGHT_STEP_KG)


def rest_seconds(*, is_compound: bool, rir: float | None) -> int:
    base = REST_COMPOUND_S if is_compound else REST_ISOLATION_S
    if rir is not None and rir >= 3:
        base += REST_LIGHT_BONUS_S
    return max(45, base)


# ---------------------------------------------------------------------------
# What the set proved
# ---------------------------------------------------------------------------


@dataclass
class PurpleRoute:
    """The two concrete ways to beat the current estimate on this exercise."""

    reps_needed: int | None       # same weight, this many reps
    weight_needed_kg: float | None  # same reps, this much on the bar


@dataclass
class SetAssessment:
    verdict: SetVerdict
    set_e1rm: float | None
    reference_e1rm: float | None
    load_pct: float | None
    rpe: float | None
    route: PurpleRoute
    headline: str
    detail: str


def assess_set(
    *,
    weight_kg: float,
    reps: int,
    rir: float | None,
    reference_e1rm: float | None,
    equipment: str | None = None,
) -> SetAssessment:
    """Judge one set against the lifter's current best estimate.

    `reference_e1rm` is the best estimate we already had for this exercise --
    normally the top e1RM from the last several weeks. Passing None (a first
    session, or an exercise never trained) yields UNRATED, and the copy says
    so instead of inventing a comparison.
    """
    est = e1rm(weight_kg, reps, rir)
    pct = load_pct(weight_kg, reference_e1rm)
    rpe = rpe_from_rir(rir)
    route = purple_route(
        weight_kg=weight_kg,
        reps=reps,
        rir=rir,
        reference_e1rm=reference_e1rm,
        equipment=equipment,
    )

    if reference_e1rm is None or est is None:
        return SetAssessment(
            verdict=SetVerdict.UNRATED,
            set_e1rm=est,
            reference_e1rm=reference_e1rm,
            load_pct=pct,
            rpe=rpe,
            route=route,
            headline="LOGGED",
            detail=_unrated_detail(weight_kg, reps, rir, est, reference_e1rm),
        )

    ratio = est / reference_e1rm
    if ratio > 1 + PURPLE_MARGIN:
        verdict = SetVerdict.PURPLE
    elif ratio >= 1 - ON_TARGET_BAND:
        verdict = SetVerdict.ON_TARGET
    else:
        verdict = SetVerdict.UNDER

    return SetAssessment(
        verdict=verdict,
        set_e1rm=est,
        reference_e1rm=round(reference_e1rm, 1),
        load_pct=pct,
        rpe=rpe,
        route=route,
        headline={
            SetVerdict.PURPLE: "PURPLE SET",
            SetVerdict.ON_TARGET: "ON TARGET",
            SetVerdict.UNDER: "UNDER",
        }[verdict],
        detail=_detail(
            weight_kg=weight_kg,
            reps=reps,
            rir=rir,
            verdict=verdict,
            est=est,
            reference=reference_e1rm,
            route=route,
        ),
    )


def purple_route(
    *,
    weight_kg: float,
    reps: int,
    rir: float | None,
    reference_e1rm: float | None,
    equipment: str | None = None,
) -> PurpleRoute:
    """The smallest rep bump and the smallest load bump that beat the record.

    Both are computed at the SAME effort (same RIR), because "just take it to
    failure" is not progress, it is a different set. Either route may come
    back None: the rep route disappears once it would push past REP_CEILING,
    and the weight route disappears on bodyweight movements.
    """
    if reference_e1rm is None or reference_e1rm <= 0 or weight_kg <= 0:
        return PurpleRoute(None, None)

    target = reference_e1rm * (1 + PURPLE_MARGIN)
    r = rir if rir is not None and rir > 0 else 0.0

    # Reps route: w * (1 + (reps + rir)/30) > target
    reps_needed: int | None = None
    needed_effective = EPLEY_DIVISOR * (target / weight_kg - 1)
    candidate = math.floor(needed_effective - r) + 1
    candidate = max(candidate, reps + 1)
    if candidate <= REP_CEILING - r:
        reps_needed = candidate

    # Weight route: solve for w at the reps actually performed, then round UP
    # to something you can load. Rounding down would hand back a "target"
    # that does not clear the record.
    weight_needed: float | None = None
    step = weight_step(equipment)
    if step > 0:
        exact = target / (1 + (reps + r) / EPLEY_DIVISOR)
        snapped = math.ceil(exact / step) * step
        if snapped <= weight_kg:
            snapped = weight_kg + step
        weight_needed = round(snapped, 1)

    return PurpleRoute(reps_needed, weight_needed)


def _fmt_kg(v: float) -> str:
    return f"{v:g}"


def _effort_phrase(rir: float | None) -> str:
    if rir is None:
        return ""
    if rir <= 0:
        return " to failure"
    if rir == 1:
        return " with 1 rep in reserve"
    return f" with {rir:g} reps in reserve"


def _route_phrase(route: PurpleRoute, weight_kg: float) -> str:
    parts = []
    if route.reps_needed is not None:
        parts.append(f"{route.reps_needed} reps at the same effort")
    if route.weight_needed_kg is not None and route.weight_needed_kg > weight_kg:
        parts.append(f"{_fmt_kg(route.weight_needed_kg)} kg")
    if not parts:
        return ""
    return " — or ".join(parts)


def _detail(
    *,
    weight_kg: float,
    reps: int,
    rir: float | None,
    verdict: SetVerdict,
    est: float,
    reference: float,
    route: PurpleRoute,
) -> str:
    head = f"{_fmt_kg(weight_kg)} kg × {reps}{_effort_phrase(rir)}"
    if verdict is SetVerdict.PURPLE:
        gain = est - reference
        return (
            f"{head} puts your estimated max at {_fmt_kg(est)} kg, "
            f"up {_fmt_kg(round(gain, 1))} kg. That is a new best."
        )
    routes = _route_phrase(route, weight_kg)
    if verdict is SetVerdict.ON_TARGET:
        base = f"{head} maintains your strength."
        return f"{base} {routes} makes it a purple set." if routes else base
    shortfall = reference - est
    base = (
        f"{head} estimates {_fmt_kg(est)} kg, "
        f"{_fmt_kg(round(shortfall, 1))} kg under your best."
    )
    return f"{base} {routes} would clear it." if routes else base


def _unrated_detail(
    weight_kg: float,
    reps: int,
    rir: float | None,
    est: float | None,
    reference: float | None,
) -> str:
    head = f"{_fmt_kg(weight_kg)} kg × {reps}{_effort_phrase(rir)}"
    if est is None and weight_kg > 0 and reps > 0:
        return (
            f"{head} logged. Past {REP_CEILING} effective reps we stop calling "
            f"it a max estimate — that set measured endurance, not strength."
        )
    if reference is None:
        return f"{head} logged. This is your first reference on this lift."
    return f"{head} logged."


# ---------------------------------------------------------------------------
# The session, once it is over
# ---------------------------------------------------------------------------


@dataclass
class LoggedSet:
    exercise_id: str
    exercise_name: str
    weight_kg: float
    reps: int
    rir: float | None = None
    is_warmup: bool = False
    e1rm: float | None = None


@dataclass
class ExerciseResult:
    exercise_id: str
    exercise_name: str
    sets: int
    top_weight_kg: float
    volume_kg: float
    best_e1rm: float | None
    previous_e1rm: float | None
    delta_pct: float | None
    trend: ExerciseTrend
    set_verdicts: list[str] = field(default_factory=list)


@dataclass
class SessionSummary:
    duration_min: int | None
    total_sets: int
    volume_kg: float
    avg_rpe: float | None
    purple_sets: int
    lifts_moved_up: int
    exercises: list[ExerciseResult]
    headline: str


def summarise_session(
    sets: list[LoggedSet],
    *,
    previous_bests: dict[str, float] | None = None,
    duration_min: int | None = None,
) -> SessionSummary:
    """Roll a finished session into the numbers worth showing.

    Warm-ups are counted in volume (you did move the weight) but never rate a
    verdict and never touch the e1RM record, because a warm-up single at 60%
    would otherwise register as a strength decline every single session.
    """
    prev = previous_bests or {}
    by_ex: dict[str, list[LoggedSet]] = {}
    for s in sets:
        by_ex.setdefault(s.exercise_id, []).append(s)

    results: list[ExerciseResult] = []
    rpes: list[float] = []
    purple = 0

    for ex_id, group in by_ex.items():
        working = [s for s in group if not s.is_warmup]
        reference = prev.get(ex_id)
        verdicts: list[str] = []
        best: float | None = None

        for s in working:
            est = s.e1rm if s.e1rm is not None else e1rm(s.weight_kg, s.reps, s.rir)
            if est is not None:
                best = est if best is None else max(best, est)
            a = assess_set(
                weight_kg=s.weight_kg,
                reps=s.reps,
                rir=s.rir,
                reference_e1rm=reference,
            )
            verdicts.append(a.verdict.value)
            if a.verdict is SetVerdict.PURPLE:
                purple += 1
            r = rpe_from_rir(s.rir)
            if r is not None:
                rpes.append(r)

        delta = (
            round((best - reference) / reference * 100, 1)
            if best is not None and reference not in (None, 0)
            else None
        )
        results.append(
            ExerciseResult(
                exercise_id=ex_id,
                exercise_name=group[0].exercise_name,
                sets=len(working),
                top_weight_kg=max((s.weight_kg for s in working), default=0.0),
                volume_kg=round(sum(s.weight_kg * s.reps for s in group), 1),
                best_e1rm=best,
                previous_e1rm=round(reference, 1) if reference else None,
                delta_pct=delta,
                trend=_trend(best, reference),
                set_verdicts=verdicts,
            )
        )

    results.sort(key=lambda r: r.volume_kg, reverse=True)
    moved_up = sum(1 for r in results if r.trend is ExerciseTrend.CONFIRMED)

    return SessionSummary(
        duration_min=duration_min,
        total_sets=sum(r.sets for r in results),
        volume_kg=round(sum(r.volume_kg for r in results), 1),
        avg_rpe=round(sum(rpes) / len(rpes), 1) if rpes else None,
        purple_sets=purple,
        lifts_moved_up=moved_up,
        exercises=results,
        headline=_session_headline(purple, moved_up, results),
    )


def _trend(best: float | None, reference: float | None) -> ExerciseTrend:
    if reference in (None, 0):
        return ExerciseTrend.FIRST_TIME
    if best is None:
        return ExerciseTrend.NO_CHANGE
    ratio = best / reference  # type: ignore[operator]
    if ratio > 1 + CONFIRM_BAND:
        return ExerciseTrend.CONFIRMED
    if ratio < 1 - CONFIRM_BAND:
        return ExerciseTrend.DECLINE
    return ExerciseTrend.NO_CHANGE


def _session_headline(
    purple: int, moved_up: int, results: list[ExerciseResult]
) -> str:
    """One line, and it must not over-claim.

    A single session cannot tell you your training is working -- that is the
    adjudication engine's job over weeks. It can only report what happened in
    the room, so the copy stays descriptive.
    """
    if not results:
        return "No working sets logged."
    if purple:
        return f"{purple} purple set{'s' if purple != 1 else ''} · {moved_up} lift{'s' if moved_up != 1 else ''} moved up"
    declines = sum(1 for r in results if r.trend is ExerciseTrend.DECLINE)
    if declines and declines == len(results):
        return "Everything down on last time — check sleep and food before the next one."
    if moved_up:
        return f"{moved_up} lift{'s' if moved_up != 1 else ''} moved up"
    return "Strength held."


# ---------------------------------------------------------------------------
# The prescription for the NEXT set
# ---------------------------------------------------------------------------


@dataclass
class SetPrescription:
    weight_kg: float | None
    reps: int
    target_rir: int
    rest_s: int
    note: str


def prescribe_next_set(
    *,
    last_weight_kg: float | None,
    last_reps: int | None,
    last_rir: float | None,
    reference_e1rm: float | None,
    is_compound: bool,
    equipment: str | None = None,
    target_rir: int = 2,
) -> SetPrescription:
    """What to put on the bar next, given what happened last time.

    Deliberately conservative. The progression rule is: only add load when the
    previous session cleared the rep target with reps genuinely left over.
    Chasing a number every session is how people run into a wall in six weeks
    and how injuries happen, and the app's job is the long trend.
    """
    step = weight_step(equipment)
    reps = last_reps or 8

    if last_weight_kg is None:
        return SetPrescription(
            weight_kg=None,
            reps=reps,
            target_rir=target_rir,
            rest_s=rest_seconds(is_compound=is_compound, rir=target_rir),
            note="First time on this lift — pick a weight you could do twice more.",
        )

    if last_rir is not None and last_rir > target_rir and step > 0:
        return SetPrescription(
            weight_kg=round(last_weight_kg + step, 1),
            reps=reps,
            target_rir=target_rir,
            rest_s=rest_seconds(is_compound=is_compound, rir=target_rir),
            note=f"You had {last_rir:g} left last time. Add {_fmt_kg(step)} kg.",
        )

    if last_rir is not None and last_rir < target_rir:
        return SetPrescription(
            weight_kg=round(last_weight_kg, 1),
            reps=reps,
            target_rir=target_rir,
            rest_s=rest_seconds(is_compound=is_compound, rir=last_rir),
            note="Same weight. Last one was harder than the target effort.",
        )

    return SetPrescription(
        weight_kg=round(last_weight_kg, 1),
        reps=reps + 1,
        target_rir=target_rir,
        rest_s=rest_seconds(is_compound=is_compound, rir=target_rir),
        note="Same weight, one more rep." if reference_e1rm else "Repeat last session.",
    )
