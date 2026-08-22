"""Does what you ate yesterday show up in today's session?

THE BET
Trace already collects both sides. MacroFactor is two apps away from the
training data, Cal AI has no training at all, and LiftBite logs both and links
neither. "Your best sessions follow your highest-carb days" is an insight only
this app is positioned to produce — and it turns the training log into a
reason to keep logging food, which is the retention problem every nutrition
app has.

WHAT IT ACTUALLY COMPUTES
Rank correlation between the carbohydrate intake on day N-1 and the session
volume on day N, over matched pairs. Rank rather than Pearson because the
relationship is monotonic but not linear, one enormous session would drag a
Pearson coefficient around by itself, and volume distributions are skewed.

WHY IT REFUSES SO OFTEN
Non-negotiable #3. With six sessions you can find a "pattern" in noise
trivially, and a confident wrong claim here is worse than silence because the
user will act on it — they will eat differently on the strength of it. So:

  * fewer than MIN_PAIRS matched days      -> INSUFFICIENT_DATA
  * correlation weaker than MIN_RHO        -> no claim, explicitly
  * carb range too narrow to compare       -> no claim, explicitly

That last one is the subtle one and it is the one most likely to produce a
false positive elsewhere: if someone eats 280-300 g of carbs every single day,
there is no contrast to learn from, and any correlation found is noise
dressed up as a finding.

THIS NEVER CHANGES A CALORIE TARGET. It suggests a MACRO SHIFT at constant
calories — more carbs, less fat, same total. Non-negotiable #1 is about not
inventing calories; this does not invent any.

PURE FUNCTIONS, NO I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

#: Matched (carbs yesterday, volume today) pairs needed before we say anything.
#:
#: Eight is roughly three weeks of training for most people. Below that the
#: confidence interval on a rank correlation is so wide that "positive" and
#: "negative" are both inside it.
MIN_PAIRS = 8

#: Below this, there is no claim to make.
MIN_RHO = 0.45

#: The spread of carb intake needed for the comparison to mean anything,
#: as a fraction of the mean. Someone eating 290 g every day has no contrast.
MIN_CARB_SPREAD = 0.15

#: How far the suggestion moves macros, in grams of carbohydrate.
#: Swapped against fat at constant calories: 45 g carb = 180 kcal = 20 g fat.
SUGGESTED_CARB_SHIFT_G = 45.0
KCAL_PER_G_CARB = 4.0
KCAL_PER_G_FAT = 9.0


class LinkVerdict(str, Enum):
    positive = "positive"
    none_found = "none_found"
    insufficient_data = "insufficient_data"
    no_contrast = "no_contrast"


@dataclass
class Session:
    day: date
    #: Total kg lifted: sum of weight x reps across the session.
    volume_kg: float
    #: Optional, for naming the pattern: 'legs', 'push', 'pull'.
    focus: str | None = None


@dataclass
class FuelLink:
    verdict: LinkVerdict
    pairs: int
    rho: float | None
    #: Mean session volume after a high-carb day vs after a low-carb day.
    high_carb_volume: float | None
    low_carb_volume: float | None
    #: How much better the high-carb sessions were, as a percentage.
    uplift_pct: float | None
    carb_threshold_g: float | None
    headline: str = ""
    detail: str = ""
    notes: list[str] = field(default_factory=list)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation, with average ranks for ties."""
    n = len(xs)
    if n < 3:
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: vals[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    if dx <= 0 or dy <= 0:
        return None
    return num / (dx * dy) ** 0.5


def analyse(
    carbs_by_day: dict[date, float],
    sessions: list[Session],
    focus: str | None = None,
) -> FuelLink:
    """Look for a relationship between yesterday's carbs and today's session.

    `focus` narrows to one training type. Worth doing: leg volume responds to
    glycogen far more than an arm session does, and pooling them dilutes a
    real effect into nothing.
    """
    picked = [s for s in sessions if focus is None or s.focus == focus]

    pairs: list[tuple[float, float]] = []
    for s in picked:
        prev = carbs_by_day.get(s.day - timedelta(days=1))
        if prev is not None and s.volume_kg > 0:
            pairs.append((prev, s.volume_kg))

    base = FuelLink(
        verdict=LinkVerdict.insufficient_data,
        pairs=len(pairs),
        rho=None,
        high_carb_volume=None,
        low_carb_volume=None,
        uplift_pct=None,
        carb_threshold_g=None,
    )

    if len(pairs) < MIN_PAIRS:
        base.headline = "Not enough matched days yet"
        base.detail = (
            f"{len(pairs)} of {MIN_PAIRS} sessions have the day before them "
            "logged. Keep logging on training days and this fills in."
        )
        return base

    carbs = [p[0] for p in pairs]
    vols = [p[1] for p in pairs]

    mean_carbs = sum(carbs) / len(carbs)
    spread = (max(carbs) - min(carbs)) / mean_carbs if mean_carbs else 0.0
    if spread < MIN_CARB_SPREAD:
        base.verdict = LinkVerdict.no_contrast
        base.headline = "Your carbs barely vary"
        base.detail = (
            f"Every day sits near {round(mean_carbs)} g, so there's nothing to "
            "compare. That's not a bad thing — it just means this particular "
            "question can't be answered from your data."
        )
        return base

    rho = _spearman(carbs, vols)
    base.rho = round(rho, 3) if rho is not None else None

    # Split at the median for the human-readable version of the same fact.
    ordered = sorted(carbs)
    mid = len(ordered) // 2
    threshold = (
        ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    )
    hi = [v for c, v in pairs if c >= threshold]
    lo = [v for c, v in pairs if c < threshold]
    base.carb_threshold_g = round(threshold)
    base.high_carb_volume = round(sum(hi) / len(hi)) if hi else None
    base.low_carb_volume = round(sum(lo) / len(lo)) if lo else None
    if base.high_carb_volume and base.low_carb_volume:
        base.uplift_pct = round(
            (base.high_carb_volume / base.low_carb_volume - 1) * 100, 1
        )

    if rho is None or rho < MIN_RHO:
        base.verdict = LinkVerdict.none_found
        base.headline = "No clear link in your data"
        base.detail = (
            "Your session volume doesn't track the day before's carbs. That's a "
            "real answer, not a missing one — plenty of people train fine on a "
            "steady intake."
        )
        return base

    base.verdict = LinkVerdict.positive
    what = f"{focus} sessions" if focus else "sessions"
    base.headline = f"Your best {what} follow your highest-carb days"
    base.detail = (
        f"Across {len(pairs)} sessions, volume was "
        f"{base.uplift_pct:.0f}% higher after a {round(threshold)} g+ carb day."
    )
    base.notes.append(
        "Correlation, not proof — a day you ate more may also have been a day "
        "you slept better. It's a pattern worth testing, not a law."
    )
    return base


@dataclass
class MacroShift:
    carbs_delta_g: float
    fat_delta_g: float
    kcal_delta: float
    headline: str
    detail: str


def suggest_shift(link: FuelLink, training_tomorrow: bool) -> MacroShift | None:
    """Propose a macro swap for a training day, at CONSTANT calories.

    Returns None unless there is a finding to act on. Suggesting a change on
    the strength of a correlation we did not find would be exactly the kind of
    confident nonsense the rest of this file exists to avoid.
    """
    if link.verdict is not LinkVerdict.positive or not training_tomorrow:
        return None

    carbs = SUGGESTED_CARB_SHIFT_G
    fat = -(carbs * KCAL_PER_G_CARB) / KCAL_PER_G_FAT

    return MacroShift(
        carbs_delta_g=round(carbs, 1),
        fat_delta_g=round(fat, 1),
        # Zero by construction, and asserted in the tests: this must never
        # become a back door for adding calories on a training day.
        kcal_delta=round(carbs * KCAL_PER_G_CARB + fat * KCAL_PER_G_FAT, 6),
        headline="Same calories, shifted",
        detail=(
            f"+{round(carbs)} g carbs, {round(fat)} g fat. Your target doesn't "
            "change — only where it comes from. A suggestion; ignore it freely."
        ),
    )
