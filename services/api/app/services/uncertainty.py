"""How well do we actually know today?

THE BET
Every tracker prints a confident daily total assembled entirely from guesses.
"2,100 kcal" reads like a measurement and is nothing of the sort: it is a
barcode read (nearly exact), a photo estimate (±30%) and a number somebody
typed from memory (±50%), added together and rendered in the same font.

Trace already computes per-item ranges on a photo scan. Propagating them to
the day is close to free, and it does two things nothing else in the category
does:

  1. It is honest. Non-negotiable #2 says an estimate never gets shown as a
     single confident number, and a day total is an estimate.
  2. It makes "log more accurately" ACTIONABLE. Not a nag — a specific item
     with a specific band, which the user can point at and fix. "Scanning the
     380 kcal you typed would halve today's band" is advice; "log carefully"
     is not.

HOW THE BANDS COMBINE, AND WHY NOT BY ADDING THEM
Adding the half-widths assumes every item is wrong in the same direction at
once, which is close to impossible: four items each ±20% do not make a day
±80%. Independent errors combine in QUADRATURE -- the square root of the sum
of squares -- which is what this module does.

The consequence is worth understanding, because it is the whole argument for
the certainty strip: quadrature means ONE BAD ITEM DOMINATES. Four items at
±10 and one at ±84 gives a day band of ±85, not ±94. Tightening the four small
ones changes nothing you can see. Fixing the one big one is the entire win,
and that is why the UI names it.

PURE FUNCTIONS, NO I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

#: Default relative band per source, used when an item carries no explicit
#: low/high of its own.
#:
#: These are the honest widths, not flattering ones:
#:
#:   LABEL      A barcode read off a manufacturer's panel. Regulations allow
#:              roughly 20% tolerance on declared values, and portion error is
#:              near zero because the pack states the serving. Call it 5%.
#:   SEARCH     A database row matched by name. The row is usually right; the
#:              PORTION is the user's estimate, and that is where the error
#:              lives.
#:   SCAN       A photo estimate. The model returns its own band and that is
#:              preferred; this is only the fallback.
#:   QUICK_ADD  A number typed from memory or a restaurant's website. The
#:              widest thing in the app, and deliberately shown as such.
RELATIVE_BAND: dict[str, float] = {
    "label": 0.05,
    "search": 0.18,
    "scan": 0.28,
    "quick_add": 0.35,
}

#: Confidence thresholds on the day band, as a fraction of the day total.
HIGH_CONFIDENCE = 0.06
MEDIUM_CONFIDENCE = 0.12


class Source(str, Enum):
    """Where a logged item's numbers came from.

    Ordered worst-to-best nowhere -- this is a provenance label, not a score.
    The score is the band.
    """

    label = "label"
    search = "search"
    scan = "scan"
    quick_add = "quick_add"


#: Human copy for each source, so the client never invents its own wording.
SOURCE_LABEL: dict[str, str] = {
    "label": "Barcode & label",
    "search": "Searched",
    "scan": "Photo scan",
    "quick_add": "Quick-added",
}


@dataclass
class LoggedItem:
    """One row of the diary, as far as this module cares."""

    name: str
    kcal: float
    source: Source
    #: The model's own band, when it gave one. Preferred over the default.
    kcal_low: float | None = None
    kcal_high: float | None = None

    def half_width(self) -> float:
        """How uncertain this item is, in kcal, either side of its point."""
        if self.kcal_low is not None and self.kcal_high is not None:
            # Use the WIDER side. A skewed band means the model thought one
            # direction was more likely, and collapsing that to a mean would
            # quietly narrow the honest width.
            return max(self.kcal - self.kcal_low, self.kcal_high - self.kcal)
        return abs(self.kcal) * RELATIVE_BAND.get(self.source.value, 0.30)


@dataclass
class SourceSlice:
    source: str
    label: str
    kcal: float
    #: Share of the day's calories, 0-1.
    share: float
    #: Share of the day's UNCERTAINTY (of the summed variance), 0-1.
    uncertainty_share: float


@dataclass
class DayUncertainty:
    total_kcal: float
    band: float
    low: float
    high: float
    #: 'high' | 'medium' | 'low'
    confidence: str
    #: Band as a fraction of the total, for the UI to reason about.
    band_pct: float
    mix: list[SourceSlice] = field(default_factory=list)
    #: The single item whose band contributes most. The actionable one.
    worst_item: str | None = None
    worst_item_band: float | None = None
    headline: str = ""
    advice: str | None = None


def _confidence(band: float, total: float) -> tuple[str, float]:
    if total <= 0:
        return "low", 0.0
    pct = band / total
    if pct <= HIGH_CONFIDENCE:
        return "high", pct
    if pct <= MEDIUM_CONFIDENCE:
        return "medium", pct
    return "low", pct


def day_uncertainty(items: list[LoggedItem]) -> DayUncertainty:
    """Combine a day's logged items into a total and an honest band."""
    if not items:
        return DayUncertainty(
            total_kcal=0.0,
            band=0.0,
            low=0.0,
            high=0.0,
            confidence="low",
            band_pct=0.0,
            headline="Nothing logged yet today.",
        )

    total = sum(i.kcal for i in items)

    # QUADRATURE, not a plain sum. See the module docstring: adding the
    # half-widths would assume every item is wrong in the same direction at
    # the same time.
    variance = sum(i.half_width() ** 2 for i in items)
    band = math.sqrt(variance)

    confidence, pct = _confidence(band, total)

    # ---- the mix, by source --------------------------------------------
    by_source: dict[str, list[LoggedItem]] = {}
    for i in items:
        by_source.setdefault(i.source.value, []).append(i)

    mix: list[SourceSlice] = []
    for src, group in by_source.items():
        kcal = sum(g.kcal for g in group)
        var = sum(g.half_width() ** 2 for g in group)
        mix.append(
            SourceSlice(
                source=src,
                label=SOURCE_LABEL.get(src, src.replace("_", " ").title()),
                kcal=round(kcal, 1),
                share=round(kcal / total, 4) if total else 0.0,
                uncertainty_share=round(var / variance, 4) if variance else 0.0,
            )
        )
    # Widest contributor first: the strip should read in the order that
    # matters, not alphabetically.
    mix.sort(key=lambda m: m.uncertainty_share, reverse=True)

    # ---- the one worth fixing -------------------------------------------
    worst = max(items, key=lambda i: i.half_width())
    worst_band = worst.half_width()

    headline = f"Somewhere between {round(total - band):,} and {round(total + band):,}."

    advice: str | None = None
    # Only advise when fixing the worst item would visibly move the band.
    # Under quadrature, removing it leaves sqrt(variance - w^2) -- if that is
    # barely smaller, saying "fix this" would be advice with no payoff.
    if variance > 0:
        without = math.sqrt(max(0.0, variance - worst_band**2))
        if band > 0 and (band - without) / band >= 0.25:
            pct_drop = round((1 - without / band) * 100)
            advice = (
                f"{worst.name} is your widest guess at ±{round(worst_band)} kcal. "
                f"Scanning it instead would cut today's band by about {pct_drop}%."
            )

    return DayUncertainty(
        total_kcal=round(total, 1),
        band=round(band, 1),
        low=round(max(0.0, total - band), 1),
        high=round(total + band, 1),
        confidence=confidence,
        band_pct=round(pct, 4),
        mix=mix,
        worst_item=worst.name,
        worst_item_band=round(worst_band, 1),
        headline=headline,
        advice=advice,
    )


def classify_source(
    *,
    recognition_id: str | None,
    food_item_id: str | None,
    has_barcode: bool,
) -> Source:
    """Work out where a diary row's numbers came from.

    Order matters. A photo scan the user then corrected against a barcode is
    a LABEL -- the barcode is the better provenance, and the scan that
    preceded it is history rather than the source of the number now stored.
    """
    if food_item_id and has_barcode:
        return Source.label
    if recognition_id:
        return Source.scan
    if food_item_id:
        return Source.search
    return Source.quick_add
