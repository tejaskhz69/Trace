"""User recipes: composing many foods into one loggable thing.

WHY THIS IS NOT JUST "ADD UP THE INGREDIENTS"
---------------------------------------------
A recipe is entered raw and eaten cooked, and those are different weights.
250 g of dal plus 700 g of water simmers down to ~800 g, not 950 g. A pakora
batter *gains* weight from absorbed oil. So the naive per-100 g panel --
total nutrition divided by the sum of the ingredient weights -- is wrong by
whatever the cooking did, and it is wrong in the direction that matters: it
UNDERSTATES the calories in every dish that loses water, which is most of
them.

The way out is to notice that mass changes and energy does not. Water leaving
a pot takes no calories with it. So:

    per SERVING  = total nutrition / servings          <- always exact
    per 100 g    = total nutrition / finished weight   <- needs the weight

Servings is therefore the unit a recipe logs in, and it is exact no matter
what happened in the pan. Per-100 g is only offered when the user has told us
what the finished dish actually weighed. When they haven't, `yield_estimated`
is True and the caller must not offer gram-based logging -- see `portion()`,
which refuses rather than guessing.

That refusal is the same principle as the adjudication engine returning
INSUFFICIENT_DATA: a number we cannot stand behind is worse than no number.

ONE THING THIS DELIBERATELY DOES NOT MODEL
Oil absorbed during deep-frying is real nutrition that no ingredient list
contains -- the oil goes in the pan, not the recipe. `services/preparation.py`
already models fat uptake for ready-made mixes; a recipe that is fried should
list the absorbed oil as an ingredient. `publish_check` warns when a recipe
looks fried and carries no meaningful fat, because that is a recipe whose
calories are understated and which is about to be shown to other people.

PURE FUNCTIONS, NO I/O.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace

# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------

#: The nutrients a recipe carries through composition. Deliberately the same
#: set FoodItem stores per 100 g, so a composed recipe is substitutable for a
#: food anywhere the app already renders one.
NUTRIENT_KEYS: tuple[str, ...] = (
    "calories",
    "protein_g",
    "carbs_g",
    "fat_g",
    "fiber_g",
    "sugar_g",
    "sodium_mg",
    "saturated_fat_g",
)


@dataclass(frozen=True)
class Panel:
    """Nutrition for some quantity of food.

    Used for both per-100 g reference panels and absolute totals; which one it
    is depends on the field holding it. A single type means the scaling
    arithmetic is written once.
    """

    calories: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0
    sugar_g: float = 0.0
    sodium_mg: float = 0.0
    saturated_fat_g: float = 0.0

    def scaled(self, factor: float) -> "Panel":
        return Panel(**{k: getattr(self, k) * factor for k in NUTRIENT_KEYS})

    def plus(self, other: "Panel") -> "Panel":
        return Panel(**{k: getattr(self, k) + getattr(other, k) for k in NUTRIENT_KEYS})

    def rounded(self) -> "Panel":
        return Panel(
            calories=round(self.calories, 1),
            protein_g=round(self.protein_g, 2),
            carbs_g=round(self.carbs_g, 2),
            fat_g=round(self.fat_g, 2),
            fiber_g=round(self.fiber_g, 2),
            sugar_g=round(self.sugar_g, 2),
            sodium_mg=round(self.sodium_mg, 1),
            saturated_fat_g=round(self.saturated_fat_g, 2),
        )

    def as_dict(self) -> dict[str, float]:
        return {k: getattr(self, k) for k in NUTRIENT_KEYS}


@dataclass(frozen=True)
class Ingredient:
    """One line of a recipe.

    `per_100g` comes from the food catalogue. `grams` is the raw quantity the
    recipe calls for. `food_item_id` is None for a free-text line the user
    typed and estimated themselves -- those are allowed, but they are what
    `publish_check` counts when deciding whether a recipe is solid enough to
    put in front of other people.
    """

    name: str
    grams: float
    per_100g: Panel
    food_item_id: str | None = None
    note: str | None = None

    def total(self) -> Panel:
        return self.per_100g.scaled(self.grams / 100.0)


@dataclass(frozen=True)
class Composed:
    """Everything the UI and the log endpoint need for one recipe."""

    total: Panel
    per_serving: Panel
    #: None when the finished weight is unknown AND we refuse to fake it.
    per_100g: Panel | None
    servings: float
    ingredient_grams: float
    #: The finished weight we are working from.
    yield_g: float
    #: True when `yield_g` is the raw ingredient sum rather than a weight the
    #: user actually measured. The finished dish is almost certainly lighter.
    yield_estimated: bool
    serving_grams: float | None
    warnings: list[str] = field(default_factory=list)
    #: Share of the recipe's calories that came from catalogue foods rather
    #: than free-text guesses. Drives the confidence shown on the panel.
    sourced_fraction: float = 1.0


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

#: Below this, "servings" stops meaning anything and the arithmetic starts
#: dividing by something close to zero.
MIN_SERVINGS = 0.25
MAX_SERVINGS = 100.0

#: A finished dish weighing less than a third of its ingredients, or more than
#: its ingredients plus a little, is a typo rather than a cooking loss.
#: Reduction sauces are the honest edge case at the bottom; the top allows a
#: small gain for absorbed oil before we start to disbelieve it.
MIN_YIELD_RATIO = 0.33
MAX_YIELD_RATIO = 1.20


def compose(
    ingredients: list[Ingredient],
    servings: float = 1.0,
    cooked_weight_g: float | None = None,
) -> Composed:
    """Fold a list of ingredients into one panel.

    `cooked_weight_g` is what the finished dish weighed. Pass it and per-100 g
    becomes available; omit it and this returns `per_100g=None` with
    `yield_estimated=True`, because the raw sum is not the cooked weight and
    pretending otherwise understates every dish that simmers.
    """
    servings = _clamp(servings, MIN_SERVINGS, MAX_SERVINGS)
    warnings: list[str] = []

    usable = [i for i in ingredients if i.grams > 0]

    if not usable:
        return Composed(
            total=Panel(),
            per_serving=Panel(),
            per_100g=None,
            servings=servings,
            ingredient_grams=0.0,
            yield_g=0.0,
            yield_estimated=True,
            serving_grams=None,
            warnings=["Add at least one ingredient."],
            sourced_fraction=1.0,
        )

    raw_g = sum(i.grams for i in usable)

    total = Panel()
    for ing in usable:
        total = total.plus(ing.total())

    sourced_kcal = sum(i.total().calories for i in usable if i.food_item_id)
    sourced = (sourced_kcal / total.calories) if total.calories > 0 else 1.0

    # --- the yield decision -------------------------------------------------
    yield_estimated = cooked_weight_g is None
    yield_g = float(cooked_weight_g) if cooked_weight_g is not None else raw_g

    if not yield_estimated and raw_g > 0:
        ratio = yield_g / raw_g
        if ratio > MAX_YIELD_RATIO:
            warnings.append(
                f"The finished weight ({yield_g:.0f} g) is more than the "
                f"ingredients ({raw_g:.0f} g). Cooking rarely adds weight - "
                "check for a missing ingredient or a typo."
            )
        elif ratio < MIN_YIELD_RATIO:
            warnings.append(
                f"The finished weight ({yield_g:.0f} g) is under a third of "
                f"the ingredients ({raw_g:.0f} g). That is a lot of reduction "
                "- check the number."
            )

    per_100g: Panel | None
    if yield_estimated:
        per_100g = None
        warnings.append(
            "Finished weight unknown, so this logs by serving only. Weigh the "
            "cooked dish once to unlock logging by grams."
        )
    else:
        per_100g = total.scaled(100.0 / yield_g).rounded() if yield_g > 0 else None

    if sourced < 1.0 and total.calories > 0:
        pct = round((1 - sourced) * 100)
        warnings.append(f"{pct}% of the calories come from hand-entered lines.")

    return Composed(
        total=total.rounded(),
        per_serving=total.scaled(1.0 / servings).rounded(),
        per_100g=per_100g,
        servings=servings,
        ingredient_grams=round(raw_g, 1),
        yield_g=round(yield_g, 1),
        yield_estimated=yield_estimated,
        serving_grams=round(yield_g / servings, 1) if not yield_estimated else None,
        warnings=warnings,
        sourced_fraction=round(sourced, 3),
    )


class YieldUnknown(ValueError):
    """Asked for a gram portion of a recipe whose finished weight nobody knows."""


def portion(
    composed: Composed,
    servings: float | None = None,
    grams: float | None = None,
) -> tuple[Panel, float, str]:
    """One helping of a composed recipe.

    Returns (nutrition, grams, label). Exactly one of `servings`/`grams` is
    used, servings winning if both are given, because servings is the exact
    unit and grams is the derived one.

    Raises `YieldUnknown` for a gram portion of a recipe with an estimated
    yield. Silently using the raw ingredient weight there would under-report a
    simmered dish by however much water it lost.
    """
    if servings is None and grams is None:
        servings = 1.0

    if servings is not None:
        n = _clamp(servings, MIN_SERVINGS, MAX_SERVINGS)
        grams_out = (
            round(composed.serving_grams * n, 1)
            if composed.serving_grams is not None
            else round(composed.ingredient_grams / composed.servings * n, 1)
        )
        return (
            composed.total.scaled(n / composed.servings).rounded(),
            grams_out,
            _servings_label(n),
        )

    if composed.per_100g is None:
        raise YieldUnknown(
            "This recipe has no measured finished weight, so a gram amount "
            "would be a guess. Log it by serving, or weigh the cooked dish "
            "and add the weight."
        )

    g = max(0.0, float(grams or 0.0))
    return composed.per_100g.scaled(g / 100.0).rounded(), round(g, 1), f"{g:g} g"


def _servings_label(n: float) -> str:
    if abs(n - round(n)) < 0.01:
        whole = round(n)
        return "1 serving" if whole == 1 else f"{whole} servings"
    return f"{n:g} servings"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------

#: A single-ingredient "recipe" is a food, and putting it in the shared recipe
#: list makes that list worse for everyone searching it.
MIN_INGREDIENTS_TO_PUBLISH = 2
MIN_NAME_CHARS = 3

#: Words meaning the dish met hot oil. If no ingredient carries meaningful
#: fat, the recipe's calories are understated by the oil it soaked up -- the
#: most common way a home-entered recipe is wrong.
_FRY_WORDS = re.compile(
    r"\b(fry|fried|frying|deep[- ]fried|pakora|pakoda|bhaji|vada|samosa|puri|"
    r"poori|tempura|fritter|katsu|schnitzel)\b",
    re.IGNORECASE,
)
#: Below this many grams of fat per finished 100 g, a fried dish is
#: implausible. Even a well-drained pakora clears this comfortably.
FRIED_MIN_FAT_PER_100G = 4.0

#: Macros this far from the stated calories mean an ingredient is wrong, not
#: that rounding drifted. Looser than the 30% gate on hand-typed custom foods
#: because a recipe compounds the rounding of every line it contains.
MAX_ATWATER_DRIFT = 0.35


@dataclass(frozen=True)
class PublishCheck:
    ok: bool
    #: Hard stops. Non-empty means the publish is refused.
    blockers: list[str] = field(default_factory=list)
    #: Shown to the author, who may publish anyway.
    cautions: list[str] = field(default_factory=list)


def publish_check(
    name: str,
    ingredients: list[Ingredient],
    composed: Composed,
    steps: list[str] | None = None,
) -> PublishCheck:
    """Whether a recipe is solid enough to show to people who did not cook it.

    The bar is deliberately low -- this gates obvious junk, not quality. A
    PRIVATE recipe has no bar at all; it is the author's own note to
    themselves and none of our business.
    """
    blockers: list[str] = []
    cautions: list[str] = []

    if len(name.strip()) < MIN_NAME_CHARS:
        blockers.append("Give the recipe a name people would recognise.")

    usable = [i for i in ingredients if i.grams > 0]
    if len(usable) < MIN_INGREDIENTS_TO_PUBLISH:
        blockers.append(
            f"A published recipe needs at least {MIN_INGREDIENTS_TO_PUBLISH} "
            "ingredients. One ingredient is a food, not a recipe - add it as a "
            "custom food instead."
        )

    if composed.total.calories <= 0:
        blockers.append("This recipe works out to zero calories. Check the amounts.")

    if composed.servings < 1:
        blockers.append("Set how many servings this makes.")

    # Macros that cannot physically produce the stated calories.
    derived = (
        composed.total.protein_g * 4
        + composed.total.carbs_g * 4
        + composed.total.fat_g * 9
    )
    if composed.total.calories > 0 and derived > 0:
        drift = abs(derived - composed.total.calories) / composed.total.calories
        if drift > MAX_ATWATER_DRIFT:
            blockers.append(
                f"The macros add up to ~{derived:.0f} kcal but the total says "
                f"{composed.total.calories:.0f}. One of the ingredients is off."
            )

    # --- cautions -----------------------------------------------------------
    if composed.yield_estimated:
        cautions.append("No finished weight, so others can only log this by serving.")

    haystack = " ".join([name, *(steps or []), *(i.name for i in usable)])
    if _FRY_WORDS.search(haystack):
        fat_basis = composed.per_100g or composed.total.scaled(
            100.0 / max(composed.ingredient_grams, 1.0)
        )
        if fat_basis.fat_g < FRIED_MIN_FAT_PER_100G:
            cautions.append(
                "This looks fried but carries little fat. Oil absorbed in the "
                "pan is real calories - add the oil the dish soaked up, not the "
                "oil the pan started with."
            )

    if composed.sourced_fraction < 0.5:
        cautions.append(
            "Most of the calories are hand-entered rather than from the food "
            "database, so the totals are rougher than they look."
        )

    if not (steps or []):
        cautions.append("No method written. Others will only see the ingredients.")

    return PublishCheck(ok=not blockers, blockers=blockers, cautions=cautions)


# ---------------------------------------------------------------------------
# Scaling a recipe up or down
# ---------------------------------------------------------------------------


def rescale(
    ingredients: list[Ingredient],
    from_servings: float,
    to_servings: float,
) -> list[Ingredient]:
    """Same dish, different number of people.

    Scales every ingredient linearly. That is right for the ingredients and
    only roughly right for the cooking -- a doubled pot reduces less, because
    it has less surface area per unit of volume -- which is why the caller
    must DROP any measured `cooked_weight_g` when it rescales rather than
    scaling that too. A measured weight belongs to the batch that was weighed.
    """
    if from_servings <= 0 or to_servings <= 0:
        return list(ingredients)
    factor = to_servings / from_servings
    return [replace(i, grams=round(i.grams * factor, 1)) for i in ingredients]


def suggest_servings(total_kcal: float, target_per_serving: float = 500.0) -> int:
    """A starting guess for the servings field, so the user edits rather than types.

    500 kcal is a main-meal portion for most people. This is a default in a
    form field, not a recommendation - it is never shown as advice.
    """
    if total_kcal <= 0:
        return 1
    return max(1, min(20, int(math.ceil(total_kcal / target_per_serving))))
