"""Protein: when you ate it, how short you are, and the cheapest way to fix it.

THE BET
"47 g short" is a diagnosis. "Dal + curd + eggs = 31 g for ₹50" is a
prescription. Every tracker in the category ships the diagnosis and stops.

Two things here that nothing else does:

1. **TIMING, NOT JUST THE TOTAL.** 165 g eaten as 28/16/27/94 is not the same
   stimulus as 40/40/40/45, and the difference is per-meal leucine threshold —
   below roughly 0.3 g/kg in a sitting, a meal contributes much less to
   synthesis than its gram count suggests. So a back-loaded day gets flagged
   as back-loaded, and the app names the meal that was thin.

2. **COST PER GRAM.** For a student on a mess plan, price is the binding
   constraint, not preference. Ranking foods by protein per ₹10 is the single
   most useful number this app could give that user, and no app in the world
   currently shows it.

WHY THE PRICES ARE A CURATED TABLE AND NOT A FEED
There is no reliable, licensable, per-city grocery price API for India, and a
wrong price is worse than none — it makes the ranking wrong, which is the
whole feature. So this is a small hand-maintained table of typical prices with
an explicit `as_of`, the region it applies to, and a `price_confidence` the UI
can surface. When it goes stale it should be visibly stale, not silently wrong.

Users can override any price; `rank_by_cost` takes an overrides map so a
person's own numbers always beat ours.

PURE FUNCTIONS, NO I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

#: Below this share of the day's protein, a meal counts as "thin".
THIN_MEAL_SHARE = 0.15

#: A single sitting past this share is a spike -- the day is back-loaded.
SPIKE_SHARE = 0.38

#: Grams per kilo of bodyweight that make a sitting count as a real dose.
#: ~0.3 g/kg is the usual figure for hitting the leucine threshold.
DOSE_G_PER_KG = 0.3

#: When the price table was last checked, and where it applies.
PRICES_AS_OF = "2026-08"
PRICES_REGION = "India (metro average)"


@dataclass(frozen=True)
class ProteinFood:
    """A food, sized as people actually buy and eat it."""

    key: str
    name: str
    #: The unit a person thinks in: "1 katori", "2 eggs", "1 scoop".
    portion: str
    protein_g: float
    kcal: float
    #: Typical retail cost of that portion, in rupees.
    rupees: float
    veg: bool = True
    #: Where the price is shakier -- imported or highly brand-dependent.
    price_confidence: str = "typical"
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def g_per_10_rupees(self) -> float:
        if self.rupees <= 0:
            return 0.0
        return round(self.protein_g / self.rupees * 10, 2)

    @property
    def kcal_per_g_protein(self) -> float:
        if self.protein_g <= 0:
            return 0.0
        return round(self.kcal / self.protein_g, 1)


#: The table. Ordered roughly by how commonly it appears in an Indian diet.
PROTEIN_FOODS: tuple[ProteinFood, ...] = (
    ProteinFood("eggs", "Eggs, boiled", "2 eggs", 13.0, 156, 18.0, veg=False,
                tags=("cheap", "complete")),
    ProteinFood("dal", "Dal", "1 katori (150 g)", 7.0, 128, 12.0,
                tags=("cheap", "mess")),
    ProteinFood("curd", "Curd", "1 cup (200 g)", 11.0, 120, 20.0,
                tags=("cheap", "mess")),
    ProteinFood("milk", "Milk", "1 glass (250 ml)", 8.0, 155, 18.0,
                tags=("cheap",)),
    ProteinFood("rajma", "Rajma", "1 katori (150 g)", 9.0, 190, 16.0,
                tags=("cheap", "mess", "potassium")),
    ProteinFood("chana", "Chana", "1 katori (150 g)", 10.0, 200, 15.0,
                tags=("cheap", "mess")),
    ProteinFood("soya", "Soya chunks", "50 g dry", 26.0, 170, 15.0,
                tags=("cheapest", "complete")),
    ProteinFood("paneer", "Paneer", "100 g", 18.0, 265, 55.0),
    ProteinFood("whey", "Whey isolate", "1 scoop (32 g)", 24.0, 120, 60.0,
                price_confidence="brand-dependent", tags=("complete",)),
    ProteinFood("chicken", "Chicken breast", "150 g", 46.0, 250, 90.0, veg=False,
                tags=("complete",)),
    ProteinFood("fish", "Fish", "150 g", 33.0, 220, 85.0, veg=False,
                tags=("complete",)),
    ProteinFood("tofu", "Tofu", "100 g", 12.0, 145, 40.0, tags=("complete",)),
    ProteinFood("peanuts", "Peanuts", "40 g", 10.0, 235, 12.0,
                tags=("cheap", "calorie-dense")),
    ProteinFood("protein_bar", "Protein bar", "1 bar", 20.0, 210, 120.0,
                price_confidence="brand-dependent"),
    ProteinFood("greek_yogurt", "Greek yogurt", "150 g", 15.0, 130, 70.0),
    ProteinFood("sattu", "Sattu", "40 g", 8.0, 155, 10.0,
                tags=("cheapest", "mess")),
)

BY_KEY = {f.key: f for f in PROTEIN_FOODS}


@dataclass
class MealProtein:
    """One logged meal, as far as protein timing cares."""

    name: str
    hour: float  # 0-24, fractional
    protein_g: float


@dataclass
class TimingReport:
    total_g: float
    target_g: float | None
    #: 'even' | 'back_loaded' | 'front_loaded' | 'single_dose' | 'unknown'
    shape: str
    #: The meal with the smallest share, when one is notably thin.
    thinnest_meal: str | None
    #: How many sittings cleared the leucine-threshold dose.
    real_doses: int
    meals: list[MealProtein] = field(default_factory=list)
    headline: str = ""
    detail: str = ""


def analyse_timing(
    meals: list[MealProtein],
    target_g: float | None = None,
    bodyweight_kg: float | None = None,
) -> TimingReport:
    """How the day's protein was spread across sittings."""
    total = sum(m.protein_g for m in meals)
    ordered = sorted(meals, key=lambda m: m.hour)

    dose = (bodyweight_kg or 70.0) * DOSE_G_PER_KG
    real_doses = sum(1 for m in meals if m.protein_g >= dose)

    base = TimingReport(
        total_g=round(total, 1),
        target_g=round(target_g, 1) if target_g else None,
        shape="unknown",
        thinnest_meal=None,
        real_doses=real_doses,
        meals=ordered,
    )

    if not meals or total <= 0:
        base.headline = "No protein logged yet today."
        return base

    if len(meals) == 1:
        base.shape = "single_dose"
        base.headline = "All in one sitting"
        base.detail = (
            "One meal carries the whole day. Splitting the same protein across "
            "three or four sittings does more for recovery than the total alone."
        )
        return base

    shares = [m.protein_g / total for m in ordered]
    biggest = max(range(len(shares)), key=lambda i: shares[i])
    smallest = min(range(len(shares)), key=lambda i: shares[i])

    # Back- or front-loaded is about WHERE the spike is, so it is decided by
    # the position of the biggest share, not by the spread alone.
    late = ordered[biggest].hour >= 18
    early = ordered[biggest].hour <= 10

    if shares[biggest] >= SPIKE_SHARE and late:
        base.shape = "back_loaded"
        base.headline = "Back-loaded"
    elif shares[biggest] >= SPIKE_SHARE and early:
        base.shape = "front_loaded"
        base.headline = "Front-loaded"
    else:
        base.shape = "even"
        base.headline = "Evenly spread"

    if shares[smallest] <= THIN_MEAL_SHARE:
        base.thinnest_meal = ordered[smallest].name

    if base.shape == "back_loaded":
        thin = base.thinnest_meal or "the middle of the day"
        base.detail = (
            f"{thin} is the gap. Four roughly even hits beat one big evening "
            "dose — a sitting below about "
            f"{round(dose)} g contributes much less than its gram count suggests."
        )
    elif base.shape == "front_loaded":
        base.detail = (
            "Most of it lands before lunch, which leaves the evening thin. "
            "Recovery happens overnight, so the last meal is worth loading."
        )
    else:
        base.detail = (
            f"{real_doses} of {len(meals)} sittings cleared a real dose "
            f"(~{round(dose)} g). That's the pattern you want."
        )

    return base


@dataclass
class GapFill:
    foods: list[ProteinFood]
    protein_g: float
    kcal: float
    rupees: float
    note: str = ""


def close_the_gap(
    short_by_g: float,
    *,
    veg_only: bool = False,
    exclude: set[str] | None = None,
    max_items: int = 3,
) -> GapFill:
    """The cheapest realistic combination that covers the shortfall.

    Greedy on protein-per-rupee, which is the right objective here: the user
    asked for protein and the binding constraint is money. It stops at
    `max_items` because a prescription of six things is not a prescription,
    and it does not chase the last gram — landing near the target with three
    foods beats hitting it exactly with five.
    """
    if short_by_g <= 0:
        return GapFill([], 0.0, 0.0, 0.0, note="You're already there.")

    excluded = exclude or set()
    pool = [
        f
        for f in PROTEIN_FOODS
        if f.key not in excluded and (f.veg or not veg_only)
    ]
    pool.sort(key=lambda f: f.g_per_10_rupees, reverse=True)

    chosen: list[ProteinFood] = []
    got = 0.0
    for f in pool:
        if len(chosen) >= max_items or got >= short_by_g:
            break
        chosen.append(f)
        got += f.protein_g

    kcal = sum(f.kcal for f in chosen)
    rupees = sum(f.rupees for f in chosen)

    if got >= short_by_g:
        note = f"{round(got)} g for ₹{round(rupees)}."
    else:
        note = (
            f"{round(got)} g for ₹{round(rupees)} — still "
            f"{round(short_by_g - got)} g short, but that's the cheapest "
            f"{len(chosen)} things you can add."
        )

    return GapFill(
        foods=chosen,
        protein_g=round(got, 1),
        kcal=round(kcal, 1),
        rupees=round(rupees, 1),
        note=note,
    )


def rank_by_cost(
    *,
    veg_only: bool = False,
    limit: int = 8,
    price_overrides: dict[str, float] | None = None,
) -> list[ProteinFood]:
    """Foods ranked by protein per ₹10.

    `price_overrides` lets a user's own prices beat the table's. Somebody who
    knows their mess charges ₹8 for dal should see the ranking that follows
    from that, not from a metro average.
    """
    overrides = price_overrides or {}
    pool = [f for f in PROTEIN_FOODS if f.veg or not veg_only]
    if overrides:
        pool = [
            ProteinFood(
                f.key, f.name, f.portion, f.protein_g, f.kcal,
                overrides.get(f.key, f.rupees), f.veg,
                "yours" if f.key in overrides else f.price_confidence,
                f.tags,
            )
            for f in pool
        ]
    pool.sort(key=lambda f: f.g_per_10_rupees, reverse=True)
    return pool[:limit]


def price_staleness_months(now: datetime | None = None) -> int:
    """How out of date the price table is, so the UI can say so."""
    now = now or datetime.now()
    year, month = (int(x) for x in PRICES_AS_OF.split("-"))
    return max(0, (now.year - year) * 12 + (now.month - month))
