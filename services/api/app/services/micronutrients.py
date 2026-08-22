"""Daily limits for the nutrients the Home screen watches.

Pure functions, no I/O, like everything else in this package.

WHY ONLY FOUR
The Home screen shows sodium, potassium, sugars and fibre and nothing else.
That is a deliberate product choice, not a limitation: a screen listing
twenty micronutrients is a screen nobody reads. These four are the ones where
a normal day's eating plausibly crosses a line worth knowing about, and where
the number is actionable.

REFERENCE VALUES
Sodium and potassium are the US Dietary Guidelines / NASEM adult figures.
Sugars is the WHO free-sugars ceiling expressed against a 2,000 kcal day.
Fibre scales with intake rather than body size, at the IOM's 14 g per 1,000
kcal -- the same constant `tdee.py` already uses for the fibre target, imported
rather than repeated so the two can never drift apart.

These are POPULATION defaults. They are not personalised, and a user with
hypertension or kidney disease has different numbers. The UI must present them
as general guidance rather than a prescription.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tdee import FIBER_G_PER_1000_KCAL

# Chronic Disease Risk Reduction intake. Not a "safe maximum" -- it is the
# level above which reducing intake is expected to reduce risk.
SODIUM_LIMIT_MG = 2_300.0

# Adequate Intake. Unlike sodium this is a FLOOR to reach, not a ceiling to
# stay under, which is why the UI must not colour a low potassium bar red the
# way it colours a high sodium one.
POTASSIUM_TARGET_MG = 3_400.0

# WHO conditional recommendation: free sugars under 10% of energy, and a
# further benefit below 5%. 10% of 2,000 kcal is 50 g.
SUGARS_PCT_OF_ENERGY = 0.10
KCAL_PER_G_SUGAR = 4.0


@dataclass
class MicroTargets:
    sodium_mg: float
    potassium_mg: float
    sugars_g: float
    fiber_g: float


def daily_targets(*, calorie_target: float | None) -> MicroTargets:
    """Limits for one day.

    `calorie_target` of None means the user has no target yet (they haven't
    onboarded, or have no body-composition row). Sugars and fibre both scale
    with energy intake, so fall back to a 2,000 kcal reference day rather than
    returning nothing -- a missing bar is less useful than an approximate one,
    provided the UI does not claim it is personalised.
    """
    kcal = calorie_target if calorie_target and calorie_target > 0 else 2_000.0
    return MicroTargets(
        sodium_mg=SODIUM_LIMIT_MG,
        potassium_mg=POTASSIUM_TARGET_MG,
        sugars_g=round(kcal * SUGARS_PCT_OF_ENERGY / KCAL_PER_G_SUGAR),
        fiber_g=round(kcal / 1_000.0 * FIBER_G_PER_1000_KCAL),
    )
