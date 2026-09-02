"""Weight units, and the bar you are not carrying.

TWO THINGS THIS SOLVES

1. **kg and lb together.** People think in one and buy plates in the other,
   and gyms in the same city disagree. Showing both removes a conversion the
   user would otherwise do in their head mid-set.

2. **"Just the plates."** Asked for directly: on an incline barbell press the
   user wants to log the 40 kg they loaded, not the 60 kg the system is
   actually moving. That is how most people talk about their lifts.

THE RULE THAT MAKES (2) SAFE
**Storage is always TOTAL weight.** `SetLog.weight_kg` keeps bar + plates,
because every piece of strength maths downstream — e1RM, volume, the weekly
strength index, the adjudication engine's recomposition verdict — is about
the load actually moved. A bar is 20 kg of real resistance.

So "plates only" is a DISPLAY AND INPUT transform, applied at the edge:

    what the user types  →  + bar  →  what we store
    what we store        →  − bar  →  what the user sees

Store plate weight instead and every e1RM in the app silently drops by the
bar, which would show as a strength regression the day someone flips a
display setting. That is the bug this design exists to prevent, and
`test_units.py` has a class guarding it.

BAR WEIGHTS are the honest defaults, not the flattering ones. A standard
Olympic bar is 20 kg / 44 lb. An EZ bar is 7-12 kg depending on make, so it
is `uncertain` and the UI should let the user set theirs. A Smith machine
carriage is the worst case in the building: counterbalancing varies from
about 6 kg to 25 kg between manufacturers and there is no way to know from
here, so we do not guess — `SMITH` is None and the user is asked once.

PURE FUNCTIONS, NO I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

KG_PER_LB = 0.45359237
LB_PER_KG = 1.0 / KG_PER_LB


def kg_to_lb(kg: float) -> float:
    return kg * LB_PER_KG


def lb_to_kg(lb: float) -> float:
    return lb * KG_PER_LB


@dataclass(frozen=True)
class Bar:
    key: str
    name: str
    #: None means "we genuinely don't know" -- ask, don't guess.
    weight_kg: float | None
    #: True when the real weight varies enough between gyms that our default
    #: is a starting point rather than a fact.
    uncertain: bool = False
    note: str = ""


BARS: tuple[Bar, ...] = (
    Bar("olympic", "Olympic bar", 20.0, note="The standard 7 ft bar, 20 kg / 44 lb."),
    Bar("womens", "Women's Olympic bar", 15.0, note="15 kg / 33 lb."),
    Bar("ez", "EZ curl bar", 10.0, uncertain=True,
        note="Ranges 7–12 kg by make. Set yours if it matters."),
    Bar("trap", "Trap / hex bar", 25.0, uncertain=True,
        note="Ranges 20–35 kg. Open-ended bars are heavier."),
    Bar("safety_squat", "Safety squat bar", 25.0, uncertain=True,
        note="Ranges 20–32 kg."),
    Bar("smith", "Smith machine", None, uncertain=True,
        note="Counterbalancing varies from ~6 kg to ~25 kg between machines. "
             "There is no way for us to know yours — weigh it once, or leave "
             "it off and stay consistent."),
    Bar("none", "No bar", 0.0, note="Dumbbells, cables, machines, bodyweight."),
)

BY_KEY = {b.key: b for b in BARS}

#: Which bar an exercise's equipment implies, before the user overrides it.
#:
#: `barbell` maps to the men's Olympic bar because that is what is on the rack
#: in the overwhelming majority of gyms. Everything not on a bar maps to
#: `none`, which makes the plates-only transform a no-op there — a dumbbell
#: press has no bar to subtract, and pretending otherwise would silently
#: mangle the number.
EQUIPMENT_TO_BAR: dict[str, str] = {
    "barbell": "olympic",
    "ezbar": "ez",
    "smith": "smith",
    "dumbbell": "none",
    "cable": "none",
    "machine": "none",
    "bodyweight": "none",
    "kettlebell": "none",
    "band": "none",
    "medicine_ball": "none",
    "exercise_ball": "none",
    "foam_roller": "none",
    "other": "none",
}


def bar_for(equipment: str | None, override_kg: float | None = None) -> Bar:
    """The bar an exercise uses.

    `override_kg` is the user's own measurement and always wins — it is the
    only way a Smith machine ever gets a number.
    """
    if override_kg is not None:
        return Bar("custom", "Your bar", float(override_kg))
    return BY_KEY.get(EQUIPMENT_TO_BAR.get(equipment or "", "none"), BY_KEY["none"])


def has_bar(equipment: str | None) -> bool:
    """Whether "just the plates" means anything for this exercise."""
    return EQUIPMENT_TO_BAR.get(equipment or "", "none") != "none"


class UnknownBarWeight(ValueError):
    """We were asked to subtract a bar whose weight nobody has told us."""


def plates_from_total(
    total_kg: float, equipment: str | None, override_kg: float | None = None
) -> float:
    """Total load → what the user actually loaded on the bar.

    Raises rather than guessing when the bar weight is unknown (Smith
    machines). Silently returning the total would tell someone their plate
    weight is 20 kg higher than it is.
    """
    bar = bar_for(equipment, override_kg)
    if bar.weight_kg is None:
        raise UnknownBarWeight(
            f"{bar.name}: {bar.note} Set it in settings to log plates only."
        )
    # Clamped at zero: a total below the bar means somebody logged a warm-up
    # with an empty bar and a typo, and a negative plate weight is not a
    # thing we should ever render.
    return max(0.0, round(total_kg - bar.weight_kg, 2))


def total_from_plates(
    plates_kg: float, equipment: str | None, override_kg: float | None = None
) -> float:
    """What the user loaded → the total we store.

    THE INVERSE OF THE ABOVE, and the one that protects the strength maths.
    Everything downstream of storage assumes total load.
    """
    bar = bar_for(equipment, override_kg)
    if bar.weight_kg is None:
        raise UnknownBarWeight(
            f"{bar.name}: {bar.note} Set it in settings to log plates only."
        )
    return round(plates_kg + bar.weight_kg, 2)


#: The smallest change most gyms can actually make, per side pair.
#: 2.5 kg total (a 1.25 kg plate each side) is the usual floor; 5 lb pairs
#: give 4.54 kg. Rounding to these stops the UI showing 62.37 kg.
STEP_KG = 2.5
STEP_LB = 5.0


def round_to_step(value: float, step: float) -> float:
    return round(value / step) * step


@dataclass
class WeightDisplay:
    kg: float
    lb: float
    #: Formatted, e.g. "60 kg · 132 lb".
    both: str
    #: Plate-only figures. None when the exercise has no bar, or the bar
    #: weight is unknown.
    plates_kg: float | None
    plates_lb: float | None
    plates_both: str | None
    bar_name: str | None
    bar_kg: float | None
    bar_uncertain: bool = False


def _fmt(value: float, unit: str) -> str:
    """Drop a trailing .0 -- "60 kg" reads better than "60.0 kg"."""
    if abs(value - round(value)) < 0.05:
        return f"{round(value):g} {unit}"
    return f"{value:.1f} {unit}"


def describe(
    total_kg: float,
    equipment: str | None = None,
    override_kg: float | None = None,
) -> WeightDisplay:
    """Everything the UI needs to render one weight."""
    lb = kg_to_lb(total_kg)
    out = WeightDisplay(
        kg=round(total_kg, 2),
        lb=round(lb, 1),
        both=f"{_fmt(total_kg, 'kg')} · {_fmt(lb, 'lb')}",
        plates_kg=None,
        plates_lb=None,
        plates_both=None,
        bar_name=None,
        bar_kg=None,
    )

    if not has_bar(equipment) and override_kg is None:
        return out

    bar = bar_for(equipment, override_kg)
    out.bar_name = bar.name
    out.bar_kg = bar.weight_kg
    out.bar_uncertain = bar.uncertain

    if bar.weight_kg is None:
        # Known-unknown. The UI shows the bar's name and asks for a number
        # rather than rendering a plate figure it cannot stand behind.
        return out

    p_kg = plates_from_total(total_kg, equipment, override_kg)
    p_lb = kg_to_lb(p_kg)
    out.plates_kg = p_kg
    out.plates_lb = round(p_lb, 1)
    out.plates_both = f"{_fmt(p_kg, 'kg')} · {_fmt(p_lb, 'lb')}"
    return out


# ---------------------------------------------------------------------------
# Selectorised stacks
# ---------------------------------------------------------------------------
#
# WHY THIS IS NOT `position * increment`
# Two Hammer Strength machines standing a few metres apart on one Gold's Gym
# floor, photographed 2026-08-22:
#
#   FIXED PULLDOWN / ROW   5, 12, 19, 26, ... 138   (a 5, then steps of 7)
#   LATERAL RAISE          5, 10, 15, 20, 25, 32, 39, ... (5s, then 7s)
#
# Same brand, same gym, same afternoon. "Plate 8" is 54 on one and 46 on the
# other, and on the Lateral Raise the step size CHANGES PARTWAY UP THE STACK,
# so no single increment describes even that one machine. Anything that
# multiplies a pin position by a constant is wrong here, and wrong in the
# direction that tells somebody to select a weight the machine does not have.


def stack_loads(stack_ranges: list[dict[str, float]]) -> list[float]:
    """Expand `Station.stack_ranges` into the numbers printed on the plates.

    Each range is inclusive of both ends. Ranges are walked in the order
    given -- the order they appear on the machine, bottom plate first --
    because a real stack's step size can change partway up and sorting would
    lose that.
    """
    loads: list[float] = []
    for r in stack_ranges:
        start, end, step = float(r["start"]), float(r["end"]), float(r["step"])
        if step <= 0 or end < start:
            continue
        value = start
        while value <= end + 1e-9:
            if not loads or abs(value - loads[-1]) > 1e-9:
                loads.append(round(value, 3))
            value += step
    return loads


def nearest_loadable_on_stack(
    target_kg: float,
    stack_ranges: list[dict[str, float]],
    *,
    add_ons_kg: list[float] | None = None,
) -> float | None:
    """The closest load this specific machine can actually produce.

    `add_ons_kg` are the micro-plates sitting on top of the stack, each
    independently engageable -- the Row carries two 2.5s, the Fixed Pulldown
    a 2.5 and a 5. Every subset is a real selection, so the reachable set is
    every stack value plus every subset sum.

    `None` when the stack is unknown; callers must then fall back to the
    coarse per-equipment step rather than inventing a number.
    """
    loads = stack_loads(stack_ranges)
    if not loads:
        return None

    subsets = {0.0}
    for a in add_ons_kg or []:
        subsets |= {s + float(a) for s in subsets}

    reachable = sorted({round(base + extra, 3) for base in loads for extra in subsets})
    return min(reachable, key=lambda v: (abs(v - target_kg), v))
