"""The full nutrient panel — 26 rows, and honest about the gaps.

WHY ONE SCROLLABLE COLUMN AND NOT A TABLE
MacroFactor ships a table. A table is a reference document: you consult it
when you already have a question. This is a column of bars against a common
100%-of-target tick, which you can SCAN — short and over read the same way at
a glance without decoding a colour key, because position on the bar carries
the meaning and colour is only a second signal.

THE PART THAT MATTERS MOST IS `covered`
Public food data is patchy. Open Food Facts has energy and macros for almost
everything and vitamin K for almost nothing, so a naive sum produces "Vitamin
D: 4% of target" for a person eating perfectly well — the food was fine, the
DATABASE was empty. Reporting that as a deficiency would be actively harmful:
it invites someone to supplement against an artefact.

So every row carries `covered`: the share of the day's CALORIES that came from
foods with a value for that nutrient. Below `MIN_COVERAGE` the row reports
`status="unknown"` and refuses to give a percentage. Non-negotiable #3, applied
to a nutrition table.

TARGETS are adult RDA/AI values (NIH ODS, and ICMR-NIN 2020 where it differs
meaningfully for an Indian diet). Sex-specific where the difference is large
enough to matter — iron most of all, where the female RDA is more than double.

PURE FUNCTIONS, NO I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

#: Share of the day's calories that must carry a value before we report a
#: percentage. Below this, the number says more about the database than the
#: diet.
MIN_COVERAGE = 0.5

#: Thresholds against target, for the row's status.
SHORT_BELOW = 0.7
LOW_BELOW = 0.9
OVER_ABOVE = 1.1


class Kind(str, Enum):
    """A target to REACH or a limit to STAY UNDER.

    The distinction is the whole reason a panel like this can be read at a
    glance. 140% of your potassium target is good; 140% of your sodium limit
    is not, and a UI that fills both bars the same way teaches the wrong
    reading of half the rows.
    """

    floor = "floor"
    ceiling = "ceiling"


class Status(str, Enum):
    short = "short"
    low = "low"
    ok = "ok"
    over = "over"
    unknown = "unknown"


@dataclass(frozen=True)
class Nutrient:
    key: str
    name: str
    unit: str
    group: str
    kind: Kind
    #: Target for an adult male / adult female. Equal where sex doesn't matter.
    target_m: float
    target_f: float
    #: True when this scales with energy intake rather than being a fixed RDA.
    scales_with_energy: bool = False


#: kcal reference used when scaling energy-linked targets.
REFERENCE_KCAL = 2000.0

NUTRIENTS: tuple[Nutrient, ...] = (
    # ---- macronutrients --------------------------------------------------
    Nutrient("protein_g", "Protein", "g", "Macronutrients", Kind.floor, 56, 46),
    Nutrient("carbs_g", "Carbs", "g", "Macronutrients", Kind.floor, 275, 275,
             scales_with_energy=True),
    Nutrient("fat_g", "Fat", "g", "Macronutrients", Kind.floor, 78, 78,
             scales_with_energy=True),
    Nutrient("fiber_g", "Fibre", "g", "Macronutrients", Kind.floor, 38, 25),
    Nutrient("sugar_g", "Sugar", "g", "Macronutrients", Kind.ceiling, 50, 50,
             scales_with_energy=True),
    Nutrient("saturated_fat_g", "Sat. fat", "g", "Macronutrients", Kind.ceiling,
             22, 22, scales_with_energy=True),
    Nutrient("trans_fat_g", "Trans fat", "g", "Macronutrients", Kind.ceiling, 2, 2),
    Nutrient("cholesterol_mg", "Cholesterol", "mg", "Macronutrients",
             Kind.ceiling, 300, 300),
    # ---- minerals --------------------------------------------------------
    Nutrient("sodium_mg", "Sodium", "mg", "Minerals", Kind.ceiling, 2300, 2300),
    Nutrient("potassium_mg", "Potassium", "mg", "Minerals", Kind.floor, 3400, 2600),
    Nutrient("calcium_mg", "Calcium", "mg", "Minerals", Kind.floor, 1000, 1000),
    # The female RDA is more than double the male one. Getting this wrong
    # would tell half the users they are fine when they are not.
    Nutrient("iron_mg", "Iron", "mg", "Minerals", Kind.floor, 8, 18),
    Nutrient("magnesium_mg", "Magnesium", "mg", "Minerals", Kind.floor, 400, 310),
    Nutrient("zinc_mg", "Zinc", "mg", "Minerals", Kind.floor, 11, 8),
    Nutrient("phosphorus_mg", "Phosphorus", "mg", "Minerals", Kind.floor, 700, 700),
    Nutrient("selenium_ug", "Selenium", "µg", "Minerals", Kind.floor, 55, 55),
    # ---- vitamins --------------------------------------------------------
    Nutrient("vitamin_a_ug", "Vitamin A", "µg", "Vitamins", Kind.floor, 900, 700),
    Nutrient("vitamin_c_mg", "Vitamin C", "mg", "Vitamins", Kind.floor, 90, 75),
    Nutrient("vitamin_d_ug", "Vitamin D", "µg", "Vitamins", Kind.floor, 15, 15),
    Nutrient("vitamin_e_mg", "Vitamin E", "mg", "Vitamins", Kind.floor, 15, 15),
    Nutrient("vitamin_k_ug", "Vitamin K", "µg", "Vitamins", Kind.floor, 120, 90),
    Nutrient("thiamin_mg", "Thiamin B1", "mg", "Vitamins", Kind.floor, 1.2, 1.1),
    Nutrient("riboflavin_mg", "Riboflavin B2", "mg", "Vitamins", Kind.floor, 1.3, 1.1),
    Nutrient("niacin_mg", "Niacin B3", "mg", "Vitamins", Kind.floor, 16, 14),
    Nutrient("folate_ug", "Folate B9", "µg", "Vitamins", Kind.floor, 400, 400),
    Nutrient("vitamin_b12_ug", "Vitamin B12", "µg", "Vitamins", Kind.floor, 2.4, 2.4),
)

BY_KEY = {n.key: n for n in NUTRIENTS}


def groups() -> list[str]:
    seen: list[str] = []
    for n in NUTRIENTS:
        if n.group not in seen:
            seen.append(n.group)
    return seen


@dataclass
class NutrientRow:
    key: str
    name: str
    unit: str
    group: str
    kind: str
    amount: float | None
    target: float
    #: amount / target. None when coverage is too thin to claim one.
    pct: float | None
    status: str
    #: Share of the day's calories from foods carrying this nutrient, 0-1.
    covered: float


@dataclass
class Panel:
    rows: list[NutrientRow] = field(default_factory=list)
    #: Rows worth surfacing above the full list, worst first.
    notable: list[str] = field(default_factory=list)
    tracked: int = 0
    known: int = 0
    headline: str = ""


def target_for(n: Nutrient, sex: str | None, calorie_target: float | None) -> float:
    """This user's target for one nutrient."""
    base = n.target_f if (sex or "").lower().startswith("f") else n.target_m
    if n.scales_with_energy and calorie_target and calorie_target > 0:
        return round(base * calorie_target / REFERENCE_KCAL, 2)
    return base


def _status(pct: float, kind: Kind) -> Status:
    if kind is Kind.ceiling:
        return Status.over if pct > OVER_ABOVE else Status.ok
    if pct < SHORT_BELOW:
        return Status.short
    if pct < LOW_BELOW:
        return Status.low
    if pct > OVER_ABOVE:
        return Status.over
    return Status.ok


def build_panel(
    totals: dict[str, float],
    coverage: dict[str, float],
    *,
    sex: str | None = None,
    calorie_target: float | None = None,
) -> Panel:
    """Assemble the panel from a day's summed nutrients.

    `totals` is nutrient key -> amount. `coverage` is nutrient key -> share of
    the day's calories that came from foods carrying a value for it.
    """
    rows: list[NutrientRow] = []
    for n in NUTRIENTS:
        target = target_for(n, sex, calorie_target)
        cov = coverage.get(n.key, 0.0)
        amount = totals.get(n.key)

        if amount is None or cov < MIN_COVERAGE or target <= 0:
            # An unknown stays unknown. Reporting "Vitamin D: 4%" from a
            # database that has no vitamin D would invite someone to
            # supplement against an artefact of our ingestion.
            rows.append(
                NutrientRow(
                    key=n.key, name=n.name, unit=n.unit, group=n.group,
                    kind=n.kind.value, amount=round(amount, 2) if amount else None,
                    target=target, pct=None, status=Status.unknown.value,
                    covered=round(cov, 3),
                )
            )
            continue

        pct = amount / target
        rows.append(
            NutrientRow(
                key=n.key, name=n.name, unit=n.unit, group=n.group,
                kind=n.kind.value, amount=round(amount, 2), target=target,
                pct=round(pct, 3), status=_status(pct, n.kind).value,
                covered=round(cov, 3),
            )
        )

    known = [r for r in rows if r.status != Status.unknown.value]

    # ---- what to surface above the list ---------------------------------
    # A ceiling that is over, or a floor that is short, ranked by how far off
    # it is. Twenty-six numbers is a reference table; nobody reads one daily,
    # so the app picks the handful that are actually wrong.
    def severity(r: NutrientRow) -> float:
        if r.pct is None:
            return 0.0
        if r.kind == Kind.ceiling.value:
            return max(0.0, r.pct - 1.0)
        return max(0.0, 1.0 - r.pct)

    notable = sorted(
        (r for r in known if r.status in (Status.short.value, Status.over.value)),
        key=severity,
        reverse=True,
    )

    if not known:
        headline = "Not enough nutrient data on today's foods yet."
    elif not notable:
        headline = f"All {len(known)} nutrients we can see are in range."
    else:
        names = ", ".join(r.name for r in notable[:3])
        headline = f"{len(notable)} worth a look: {names}."

    return Panel(
        rows=rows,
        notable=[r.key for r in notable[:5]],
        tracked=len(rows),
        known=len(known),
        headline=headline,
    )


#: Explanations for the rows most likely to be off, and what to do about them.
#:
#: Written as consequences rather than warnings. "Sodium is high" is a fact
#: nobody acts on; "it moves your scale weight by a kilo overnight, which is
#: why the trend line matters more than this morning's number" connects it to
#: something the user already cares about.
NOTES: dict[str, str] = {
    "sodium_mg": (
        "Mostly pickle, papad and restaurant gravies — two spoons of pickle is "
        "around 900 mg. It doesn't affect fat loss, but it moves scale weight "
        "by a kilo overnight, which is why your trend line matters more than "
        "the morning number."
    ),
    "potassium_mg": (
        "Sodium and potassium work against each other, and most people are "
        "high on one and low on the other. Banana, curd, rajma and coconut "
        "water move this up without touching your calories much."
    ),
    "iron_mg": (
        "Plant iron absorbs poorly on its own. Vitamin C in the same meal — "
        "lemon on your dal, tomato in the sabzi — meaningfully improves it, "
        "and tea with a meal meaningfully hurts it."
    ),
    "vitamin_b12_ug": (
        "Almost absent from plant foods. If you're vegetarian this is the one "
        "worth an actual supplement rather than a food fix."
    ),
    "vitamin_d_ug": (
        "Very little food contains it — this is mostly a sunlight and "
        "supplement question, not a diet one."
    ),
    "fiber_g": (
        "Whole dals, vegetables with skin, and fruit rather than juice. Fibre "
        "also blunts the appetite swing that makes a deficit hard to hold."
    ),
    "sugar_g": (
        "Worth splitting added from natural before acting on it — fruit and "
        "dairy sugar behave differently from what's in chai and biscuits."
    ),
    "saturated_fat_g": (
        "Ghee, coconut oil and full-fat dairy. Not a villain at moderate "
        "intakes, but it adds up faster than people expect in home cooking."
    ),
}


def sodium_potassium_ratio(
    sodium_mg: float | None, potassium_mg: float | None
) -> tuple[float | None, str]:
    """The ratio, and what it means.

    Reported as a ratio rather than two separate bars because that is how the
    evidence is framed — the balance between them predicts blood pressure
    better than either number alone.
    """
    if not sodium_mg or not potassium_mg or potassium_mg <= 0:
        return None, "Not enough data to compare these yet."
    ratio = sodium_mg / potassium_mg
    if ratio <= 1.2:
        note = "Close to 1:1, which is where you want it."
    elif ratio <= 2.0:
        note = "A little sodium-heavy. More fruit and dals would even it out."
    else:
        note = (
            f"{ratio:.1f} to 1 — sodium-heavy. Closer to 1:1 is the goal, and "
            "raising potassium is usually easier than cutting salt."
        )
    return round(ratio, 2), note
