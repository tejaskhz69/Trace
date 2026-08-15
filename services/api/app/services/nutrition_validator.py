"""Plausibility validation for imported nutrition data.

WHY THIS EXISTS
---------------
Public food databases are full of transcription errors, and a wrong entry is
strictly worse than a missing one: a missing entry costs the user 20 seconds
of manual entry, a wrong entry silently corrupts their whole week and produces
a bogus strength verdict.

Real examples found in Open Food Facts / USDA Branded while building the Indian
brand catalogue (Aug 2026):

  * MTR Rava Idli (8901042954516) lists 1.5 g protein/100 g. The product is
    80% semolina; semolina alone is ~12 g protein/100 g. True value ~10-12 g.
    Wrong by a factor of ~7 -- and protein is the exact input the strength
    adjudication engine depends on.
  * Aachi Rice Idli (8904209305541) lists 133 kcal/100 g. A dry idli mix is
    330-360. That is an AS-PREPARED panel filed as if it were as-sold.
  * Gits Sambar Mix: 5,480 mg sodium/100 g (13.7 g salt).
  * Eastern Rice Rava: 46.7 g fibre/100 g. Physically impossible.
  * Bambino Multigrain Vermicelli: sodium "16.29 g" -- a mg/g unit error.
  * Four different Eastern SKUs share one identical macro block: a generic
    panel copy-pasted across products.

Every check below exists because of one of those.

DESIGN
------
Pure functions, no I/O. Returns a verdict plus structured issues; the caller
decides whether to accept, quarantine, or auto-correct. Nothing is silently
mutated -- an auto-correction is always reported so it can be audited.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Atwater factors (kcal per gram)
KCAL_PROTEIN = 4.0
KCAL_CARB = 4.0
KCAL_FAT = 9.0
KCAL_FIBRE = 2.0  # partially fermented; EU uses 2 kcal/g

ATWATER_TOLERANCE = 0.15   # 15% drift before we complain
ATWATER_HARD_LIMIT = 0.35  # beyond this the row is unusable


class Severity(str, Enum):
    info = "info"          # noted, does not block
    warning = "warning"    # accept but downgrade data_quality
    error = "error"        # quarantine: do not serve to users


class Verdict(str, Enum):
    accept = "accept"
    accept_with_corrections = "accept_with_corrections"
    quarantine = "quarantine"


@dataclass
class Issue:
    code: str
    severity: Severity
    message: str
    field: str | None = None
    observed: Any = None
    expected: Any = None


@dataclass
class ValidationResult:
    verdict: Verdict
    issues: list[Issue] = field(default_factory=list)
    corrections: dict[str, float] = field(default_factory=dict)
    quality_score: float = 0.5

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.error]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.warning]

    @property
    def is_servable(self) -> bool:
        return self.verdict is not Verdict.quarantine


# ---------------------------------------------------------------------------
# Category expectation bands
# ---------------------------------------------------------------------------
# (kcal_min, kcal_max, protein_min, protein_max, fat_min)
# fat_min catches the "rice flour has 0.0 g fat" rounding artefact.

CATEGORY_BANDS: dict[str, dict[str, tuple[float, float]]] = {
    # Dry cereal/pulse flours and instant mixes, AS SOLD
    "dry_mix": {"kcal": (300, 430), "protein": (5, 25), "carbs": (45, 90), "fat": (0.3, 25)},
    "flour": {"kcal": (320, 400), "protein": (5, 15), "carbs": (65, 92), "fat": (0.3, 6)},
    "vermicelli": {"kcal": (320, 400), "protein": (7, 15), "carbs": (65, 85), "fat": (0.2, 5)},
    # Spice blends -- wide, because oil-roasted podis are legitimately fatty
    "masala": {"kcal": (250, 560), "protein": (5, 25), "carbs": (10, 65), "fat": (3, 45)},
    # Jaggery/sugar-dominant powders: chukku kappi, sukku malli, panakam mix.
    # These are NOT savoury masalas and must not be judged against that band.
    "sweet_powder": {"kcal": (280, 420), "protein": (0, 10), "carbs": (70, 100), "fat": (0, 6)},
    # Sweet mixes
    "sweet_mix": {"kcal": (350, 500), "protein": (5, 20), "carbs": (50, 80), "fat": (5, 25)},
    # Wet batters
    "batter": {"kcal": (120, 220), "protein": (4, 18), "carbs": (20, 40), "fat": (0.1, 6)},
    # Prepared/cooked dishes
    "prepared": {"kcal": (30, 400), "protein": (0.5, 35), "carbs": (0, 70), "fat": (0, 40)},
}

# Ingredient-class protein floors. If an ingredient making up >=50% of the
# product has a known protein content, the product cannot fall far below it.
# This is what catches the MTR rava idli case.
INGREDIENT_PROTEIN: dict[str, float] = {
    "semolina": 12.0, "sooji": 12.0, "rava": 12.0, "suji": 12.0,
    "wheat": 11.0, "atta": 11.0, "maida": 10.0,
    "rice": 7.0, "rice flour": 6.5,
    "urad": 24.0, "black gram": 24.0,
    "bengal gram": 20.0, "chana": 20.0, "gram flour": 22.0, "besan": 22.0,
    "toor": 22.0, "arhar": 22.0, "moong": 24.0, "green gram": 24.0,
    "ragi": 7.0, "finger millet": 7.0,
    "oats": 13.0,
    "milk solids": 26.0, "khoya": 20.0, "skimmed milk powder": 35.0,
    "soy": 40.0, "soya": 40.0,
    "coconut": 3.3,
    "sugar": 0.0, "jaggery": 0.0, "starch": 0.0, "tapioca": 0.0, "sago": 0.0,
}


def _band(category: str | None) -> dict[str, tuple[float, float]] | None:
    if not category:
        return None
    return CATEGORY_BANDS.get(category)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_macro_sum(n: dict[str, float]) -> list[Issue]:
    """Protein + carbs + fat cannot exceed 100 g per 100 g."""
    total = n.get("protein_g", 0) + n.get("carbs_g", 0) + n.get("fat_g", 0)
    if total > 100.5:
        return [
            Issue(
                "macro_sum_exceeds_100",
                Severity.error,
                f"Macros sum to {total:.1f} g per 100 g, which is impossible.",
                observed=round(total, 1),
                expected="<= 100",
            )
        ]
    if total < 5 and n.get("calories", 0) > 100:
        return [
            Issue(
                "macros_missing",
                Severity.error,
                f"Only {total:.1f} g of macros accounted for, but "
                f"{n.get('calories', 0):.0f} kcal declared. Panel is incomplete.",
                observed=round(total, 1),
            )
        ]
    return []


def check_atwater(n: dict[str, float]) -> list[Issue]:
    """Declared energy must roughly match energy derived from the macros."""
    stated = n.get("calories", 0)
    if stated <= 0:
        return [Issue("no_energy", Severity.error, "No energy value declared.")]

    derived = (
        n.get("protein_g", 0) * KCAL_PROTEIN
        + n.get("carbs_g", 0) * KCAL_CARB
        + n.get("fat_g", 0) * KCAL_FAT
    )
    if derived <= 0:
        return [Issue("no_macros", Severity.error, "No macros declared.")]

    drift = abs(derived - stated) / stated
    if drift > ATWATER_HARD_LIMIT:
        return [
            Issue(
                "atwater_mismatch_severe",
                Severity.error,
                f"Macros imply {derived:.0f} kcal but {stated:.0f} kcal is "
                f"declared ({drift:.0%} drift). One of them is wrong.",
                observed=round(drift, 3),
                expected=f"<{ATWATER_HARD_LIMIT:.0%}",
            )
        ]
    if drift > ATWATER_TOLERANCE:
        return [
            Issue(
                "atwater_mismatch",
                Severity.warning,
                f"Macros imply {derived:.0f} kcal vs {stated:.0f} declared "
                f"({drift:.0%} drift).",
                observed=round(drift, 3),
            )
        ]
    return []


def check_category_band(n: dict[str, float], category: str | None) -> list[Issue]:
    """Compare against what this class of product physically can be.

    Catches Aachi Rice Idli at 133 kcal/100 g -- an as-prepared panel filed as
    a dry mix.
    """
    band = _band(category)
    if band is None:
        return []

    issues: list[Issue] = []
    for key, field_name in (
        ("kcal", "calories"),
        ("protein", "protein_g"),
        ("carbs", "carbs_g"),
        ("fat", "fat_g"),
    ):
        if key not in band:
            continue
        lo, hi = band[key]
        value = n.get(field_name)
        if value is None:
            continue

        if value < lo:
            # A dry mix reading like a cooked dish is the classic mislabel.
            likely_prepared = (
                category in ("dry_mix", "flour", "vermicelli", "sweet_mix")
                and field_name == "calories"
                and value < lo * 0.6
            )
            issues.append(
                Issue(
                    "below_category_band_likely_as_prepared"
                    if likely_prepared
                    else "below_category_band",
                    Severity.error if likely_prepared else Severity.warning,
                    (
                        f"{field_name}={value:g} is far below the {category} range "
                        f"({lo:g}-{hi:g}). This panel is probably AS-PREPARED, not as-sold."
                    )
                    if likely_prepared
                    else f"{field_name}={value:g} is below the {category} range ({lo:g}-{hi:g}).",
                    field=field_name,
                    observed=value,
                    expected=f"{lo:g}-{hi:g}",
                )
            )
        elif value > hi:
            issues.append(
                Issue(
                    "above_category_band",
                    Severity.warning,
                    f"{field_name}={value:g} is above the {category} range ({lo:g}-{hi:g}).",
                    field=field_name,
                    observed=value,
                    expected=f"{lo:g}-{hi:g}",
                )
            )
    return issues


def check_ingredient_consistency(
    n: dict[str, float], ingredients: list[tuple[str, float]] | None
) -> list[Issue]:
    """Cross-check declared protein against the ingredient list.

    ingredients: [(name, percent_of_product), ...]

    THIS IS THE CHECK THAT CATCHES MTR RAVA IDLI. An 80%-semolina product
    cannot contain 1.5 g protein per 100 g: semolina alone contributes
    0.80 x 12 = 9.6 g.
    """
    if not ingredients:
        return []

    expected_protein = 0.0
    matched_pct = 0.0
    for name, pct in ingredients:
        key = name.lower().strip()
        for ing, protein in INGREDIENT_PROTEIN.items():
            if ing in key:
                expected_protein += protein * (pct / 100.0)
                matched_pct += pct
                break

    if matched_pct < 40:
        return []  # not enough of the product identified to judge

    declared = n.get("protein_g", 0)
    # Allow generous slack: processing losses, unmatched minor ingredients.
    floor = expected_protein * 0.6

    if declared < floor:
        return [
            Issue(
                "protein_contradicts_ingredients",
                Severity.error,
                (
                    f"Declared protein {declared:g} g/100 g contradicts the "
                    f"ingredient list ({matched_pct:.0f}% identified implies "
                    f"~{expected_protein:.1f} g). Almost certainly a "
                    f"transcription error."
                ),
                field="protein_g",
                observed=declared,
                expected=f">={floor:.1f}",
            )
        ]
    return []


def check_sodium(n: dict[str, float], is_salted: bool = True) -> list[Issue]:
    """Sodium unit errors and rounding artefacts.

    Catches Bambino's "16.29 g" (should be mg) and the sodium=0 artefact on
    products that unambiguously contain salt.
    """
    issues: list[Issue] = []
    sodium = n.get("sodium_mg")
    if sodium is None:
        return issues

    # A g/mg unit error is the signature failure. If the value is absurd but
    # becomes plausible after dividing by 1000, that is what happened --
    # Bambino's "16.29 g" is really 16.29 mg.
    if sodium > 8_000 and 0 < sodium / 1000 < 5_000:
        issues.append(
            Issue(
                "sodium_unit_error",
                Severity.error,
                f"Sodium {sodium:g} mg/100 g ({sodium / 400:.0f} g salt) is "
                f"impossible, but {sodium / 1000:g} mg is plausible. This is a "
                f"g/mg unit error -- do not import without re-reading the label.",
                field="sodium_mg",
                observed=sodium,
                expected=round(sodium / 1000, 2),
            )
        )
    elif sodium > 5_000:
        issues.append(
            Issue(
                "sodium_implausibly_high",
                Severity.warning,
                f"Sodium {sodium:g} mg/100 g ({sodium / 400:.1f} g salt) is very "
                f"high even for a masala. Verify against the pack.",
                field="sodium_mg",
                observed=sodium,
            )
        )
    elif sodium < 50 and is_salted:
        # Catches both the flat 0 and Aachi Idli Podi's "2.3 mg" on a product
        # whose second ingredient is salt.
        issues.append(
            Issue(
                "sodium_near_zero_on_salted_product",
                Severity.warning if sodium > 0 else Severity.info,
                f"Sodium declared as {sodium:g} mg/100 g on a salted product. "
                f"A masala or savoury mix runs 800-2,500 mg. Treat as unknown "
                f"rather than as a true low-sodium claim.",
                field="sodium_mg",
                observed=sodium,
                expected=">=300",
            )
        )
    return issues


def check_fibre(n: dict[str, float]) -> list[Issue]:
    """Fibre cannot exceed carbohydrate, nor be a large share of the food."""
    fibre = n.get("fiber_g")
    if fibre is None:
        return []
    if fibre > 40:
        return [
            Issue(
                "fibre_impossible",
                Severity.error,
                f"Fibre {fibre:g} g/100 g is impossible outside pure bran.",
                field="fiber_g",
                observed=fibre,
            )
        ]
    carbs = n.get("carbs_g")
    # Note: some labels report carbs EXCLUDING fibre (EU) and some INCLUDING
    # it (US/India). Only flag when it is clearly wrong either way.
    if carbs is not None and fibre > carbs + 5:
        return [
            Issue(
                "fibre_exceeds_carbs",
                Severity.warning,
                f"Fibre ({fibre:g} g) exceeds carbohydrate ({carbs:g} g).",
                field="fiber_g",
                observed=fibre,
            )
        ]
    return []


def check_zero_fat_artefact(
    n: dict[str, float], category: str | None
) -> list[Issue]:
    """Rice/wheat flours are never truly 0.0 g fat.

    Eastern, Nirapara, Double Horse and Brahmins podis all list 0.0. It is a
    rounding artefact. Correcting it matters because 0.5-1.5 g/100 g across a
    100 g serving is 5-14 kcal, and it compounds across a day of logging.
    """
    if category not in ("flour", "vermicelli", "dry_mix"):
        return []
    fat = n.get("fat_g")
    if fat is not None and fat == 0:
        return [
            Issue(
                "zero_fat_artefact",
                Severity.info,
                "Fat declared as 0.0 g on a cereal product. Rice and wheat "
                "flours contain 0.5-1.5 g/100 g; this is label rounding.",
                field="fat_g",
                observed=0,
                expected="~0.5-1.5",
            )
        ]
    return []


def check_saturated_fat(n: dict[str, float]) -> list[Issue]:
    sat = n.get("saturated_fat_g")
    fat = n.get("fat_g")
    if sat is None or fat is None:
        return []
    if sat > fat + 0.2:
        return [
            Issue(
                "saturated_exceeds_total_fat",
                Severity.error,
                f"Saturated fat ({sat:g} g) exceeds total fat ({fat:g} g).",
                field="saturated_fat_g",
                observed=sat,
            )
        ]
    # No edible fat is under ~7% saturated. Coconut and palm oil, which
    # dominate South Indian cooking, are 50-90% saturated.
    if fat > 15 and sat / max(fat, 1e-9) < 0.05:
        return [
            Issue(
                "saturated_fat_implausibly_low",
                Severity.warning,
                f"Saturated fat {sat:g} g is only {sat / fat:.1%} of {fat:g} g "
                f"total fat. No edible oil is under ~7% saturated, and the "
                f"coconut/palm fats common here are 50-90%.",
                field="saturated_fat_g",
                observed=sat,
                expected=f">={fat * 0.07:.1f}",
            )
        ]
    return []


def check_mass_balance(n: dict[str, float], category: str | None) -> list[Issue]:
    """A dry powder is ~90% macros + fibre + ash. If far less is accounted
    for, the panel is partial and the row is not usable.

    Catches the Sakthi entries, where only ~25 g of 100 g is declared -- those
    are community estimates, not label transcriptions.
    """
    # Floors differ by class. Cereal products are almost entirely macros, so a
    # low figure means a partial panel. Spice blends legitimately carry
    # 10-25% salt plus ash and moisture that never appear on the panel, so the
    # same threshold would produce false positives on good data.
    FLOORS = {
        "dry_mix": 60.0,
        "flour": 60.0,
        "vermicelli": 60.0,
        "sweet_mix": 60.0,
        "sweet_powder": 60.0,
        "masala": 45.0,
    }
    floor = FLOORS.get(category or "")
    if floor is None:
        return []

    accounted = (
        n.get("protein_g", 0)
        + n.get("carbs_g", 0)
        + n.get("fat_g", 0)
        + n.get("fiber_g", 0)
    )
    # Carbs on Indian labels usually already include fibre, so don't
    # double-count when that is clearly the case.
    if n.get("fiber_g", 0) and n.get("fiber_g", 0) < n.get("carbs_g", 0):
        accounted -= n.get("fiber_g", 0)

    if accounted < floor:
        return [
            Issue(
                "mass_balance_incomplete",
                Severity.error,
                f"Only {accounted:.0f} g of 100 g is accounted for by macros. "
                f"A {category} should reach at least {floor:.0f} g. This panel "
                f"is partial or estimated, not a label transcription.",
                observed=round(accounted, 1),
                expected=f">={floor:.0f}",
            )
        ]
    return []


def check_sugar(n: dict[str, float]) -> list[Issue]:
    sugar = n.get("sugar_g")
    carbs = n.get("carbs_g")
    if sugar is None or carbs is None:
        return []
    if sugar > carbs + 0.5:
        return [
            Issue(
                "sugar_exceeds_carbs",
                Severity.error,
                f"Sugar ({sugar:g} g) exceeds total carbohydrate ({carbs:g} g).",
                field="sugar_g",
                observed=sugar,
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Duplicate-panel detection
# ---------------------------------------------------------------------------


def panel_fingerprint(n: dict[str, float]) -> str:
    """Hash the macro block so identical panels across SKUs can be spotted.

    Four different Eastern SKUs (idiyappam powder, white puttu podi, appam
    podi, roasted rice powder) all carry the identical 354/8/78/1/0.5/0.2
    block. That is one generic panel reused, not four measurements -- so all
    four should be treated as a category estimate with lower confidence.
    """
    parts = [
        f"{n.get('calories', 0):.1f}",
        f"{n.get('protein_g', 0):.2f}",
        f"{n.get('carbs_g', 0):.2f}",
        f"{n.get('fat_g', 0):.2f}",
        f"{n.get('fiber_g', 0):.2f}",
        f"{n.get('sugar_g', 0):.2f}",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def flag_duplicate_panels(
    products: list[dict[str, Any]], threshold: int = 3
) -> dict[str, list[str]]:
    """Return {fingerprint: [product_ids]} for panels reused >= threshold times.

    Only meaningful within a single brand -- two brands legitimately sharing a
    generic rice-flour panel is expected.
    """
    by_fp: dict[str, list[str]] = {}
    for p in products:
        fp = panel_fingerprint(p.get("nutriments", p))
        by_fp.setdefault(fp, []).append(str(p.get("id") or p.get("barcode") or "?"))
    return {fp: ids for fp, ids in by_fp.items() if len(ids) >= threshold}


# ---------------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------------


def validate(
    nutriments: dict[str, float],
    *,
    category: str | None = None,
    ingredients: list[tuple[str, float]] | None = None,
    is_salted: bool = True,
    source_quality: float = 0.5,
) -> ValidationResult:
    """Run every check and return a verdict.

    `nutriments` is per 100 g and may contain:
      calories, protein_g, carbs_g, fat_g, fiber_g, sugar_g,
      saturated_fat_g, sodium_mg
    """
    issues: list[Issue] = []
    issues += check_macro_sum(nutriments)
    issues += check_atwater(nutriments)
    issues += check_category_band(nutriments, category)
    issues += check_ingredient_consistency(nutriments, ingredients)
    issues += check_sodium(nutriments, is_salted)
    issues += check_fibre(nutriments)
    issues += check_saturated_fat(nutriments)
    issues += check_sugar(nutriments)
    issues += check_zero_fat_artefact(nutriments, category)
    issues += check_mass_balance(nutriments, category)

    errors = [i for i in issues if i.severity is Severity.error]
    warnings = [i for i in issues if i.severity is Severity.warning]

    # Many independent warnings compound into untrustworthiness even when no
    # single check is fatal. Four separate complaints about one panel means
    # the panel is wrong, not that our thresholds are tight.
    if not errors and len(warnings) >= 4:
        issues.append(
            Issue(
                "too_many_warnings",
                Severity.error,
                f"{len(warnings)} independent checks flagged this panel. "
                f"Individually survivable, collectively not credible.",
                observed=len(warnings),
            )
        )
        errors = [i for i in issues if i.severity is Severity.error]

    if errors:
        verdict = Verdict.quarantine
        quality = 0.0
    elif warnings:
        verdict = Verdict.accept_with_corrections
        # Each warning costs 15% of the source's baseline trust.
        quality = round(max(0.15, source_quality * (0.85 ** len(warnings))), 2)
    else:
        verdict = Verdict.accept
        quality = source_quality

    return ValidationResult(
        verdict=verdict, issues=issues, quality_score=quality
    )


def explain(result: ValidationResult) -> str:
    """Human-readable summary for the moderation queue."""
    if result.verdict is Verdict.accept:
        return "Passed all checks."
    lines = [f"Verdict: {result.verdict.value} (quality {result.quality_score})"]
    for i in result.issues:
        lines.append(f"  [{i.severity.value:7}] {i.code}: {i.message}")
    return "\n".join(lines)
