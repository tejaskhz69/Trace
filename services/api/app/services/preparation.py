"""As-sold -> as-prepared conversion for ready-made mixes.

THE PROBLEM NOBODY ELSE SOLVES
------------------------------
Every nutrition label on an Indian ready-mix is per 100 g of DRY MIX. Nobody
eats dry mix. A 200 g pack of MTR/Gits rava idli mix becomes ~620 g of idli
once you add ~415 g of curd. A user who logs "100 g rava idli" against the
dry-mix panel overstates their calories by roughly 3x -- and gets the protein
and fat profile wrong too, because the curd contributed most of both.

Cal AI, MacroFactor and MyFitnessPal all get this wrong. It is a genuine,
demonstrable accuracy win on the exact food category your users eat daily.

THE MODEL
---------
    dry_mix + added_ingredients  ->  [cooking transform]  ->  prepared_food

Three transforms matter:

  1. HYDRATION      water/milk/curd added; mass increases, calories don't
                    (except from the added ingredient's own macros)
  2. EVAPORATION    tawa/griddle items lose 40-50% of batter water
  3. FAT UPTAKE     deep-fried items ABSORB oil -- this is the big one, and
                    it must be applied to the FINISHED weight, not the raw
                    dough, or you overstate by ~20%

Plus one special case: gulab jamun absorbs 1.2-1.9 g of sugar syrup per gram
of fried ball, which is more than half the finished piece's weight.

SOURCES
-------
Manufacturer "makes N per pack" claims (Gits prints these on every pack),
recipe-site quantities, and published food-science measurements for oil uptake:
Sakhale et al. 2011 (J Food Sci Technol) measured 18.34% oil in control samosa;
the deep-fat frying review in Int. J. Food Sci. Technol. gives 13% for french
fries up to 40% for porous items. Gulab jamun syrup absorption of 1.18-2.9 g/g
from Kumar & Mishra's process-optimisation work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Transform(str, Enum):
    steamed = "steamed"        # idli, dhokla, puttu, idiyappam -- minimal loss
    griddled = "griddled"      # dosa, uttapam, appam -- heavy evaporation
    deep_fried = "deep_fried"  # vada, bonda, gulab jamun -- water out, oil in
    simmered = "simmered"      # upma, payasam, sambar -- some evaporation
    no_cook = "no_cook"        # ready-to-eat


@dataclass(frozen=True)
class Nutrients:
    """Absolute grams/kcal for a quantity of food (not per 100 g)."""

    kcal: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0
    sugar_g: float = 0.0
    sodium_mg: float = 0.0

    def __add__(self, other: Nutrients) -> Nutrients:
        return Nutrients(
            *(
                getattr(self, f) + getattr(other, f)
                for f in (
                    "kcal", "protein_g", "carbs_g", "fat_g",
                    "fiber_g", "sugar_g", "sodium_mg",
                )
            )
        )

    def scaled(self, factor: float) -> Nutrients:
        return Nutrients(
            *(getattr(self, f) * factor for f in (
                "kcal", "protein_g", "carbs_g", "fat_g",
                "fiber_g", "sugar_g", "sodium_mg",
            ))
        )

    def per_100g(self, total_grams: float) -> Nutrients:
        if total_grams <= 0:
            return Nutrients()
        return self.scaled(100.0 / total_grams)

    def rounded(self, places: int = 1) -> Nutrients:
        return Nutrients(
            *(round(getattr(self, f), places) for f in (
                "kcal", "protein_g", "carbs_g", "fat_g",
                "fiber_g", "sugar_g", "sodium_mg",
            ))
        )


# ---------------------------------------------------------------------------
# Reference ingredients, per 100 g
# ---------------------------------------------------------------------------

INGREDIENTS: dict[str, Nutrients] = {
    "water": Nutrients(),
    "curd_full_fat": Nutrients(60, 3.1, 4.7, 3.3, 0, 4.7, 46),
    "curd_toned": Nutrients(48, 3.3, 4.9, 1.7, 0, 4.9, 46),
    "milk_full_fat": Nutrients(62, 3.2, 4.8, 3.3, 0, 4.8, 43),
    "milk_toned": Nutrients(50, 3.2, 4.9, 1.5, 0, 4.9, 43),
    "coconut_milk_thick": Nutrients(230, 2.3, 5.5, 24.0, 2.2, 3.3, 15),
    # Cooking fats -- these are what actually move the number
    "oil": Nutrients(884, 0, 0, 100, 0, 0, 0),
    "ghee": Nutrients(900, 0, 0, 100, 0, 0, 0),
    "sugar": Nutrients(387, 0, 100, 0, 0, 100, 1),
    "onion": Nutrients(40, 1.1, 9.3, 0.1, 1.7, 4.2, 4),
    "potato": Nutrients(77, 2.0, 17.5, 0.1, 2.2, 0.8, 6),
    "toor_dal_dry": Nutrients(343, 22.0, 62.8, 1.5, 15.0, 0, 17),
    "mixed_vegetables": Nutrients(45, 2.0, 9.0, 0.3, 3.0, 3.5, 20),
    "tamarind_paste": Nutrients(239, 2.8, 62.5, 0.6, 5.1, 57.4, 28),
}


# ---------------------------------------------------------------------------
# Deep-fry oil uptake, as a fraction of FINISHED weight
# ---------------------------------------------------------------------------

OIL_UPTAKE: dict[str, float] = {
    "medu_vada": 0.18,       # anchored on samosa 18.34% + recipe-derived 18-20%
    "masala_vada": 0.18,
    "bonda": 0.18,
    "bajji": 0.20,
    "pakora": 0.20,
    "samosa": 0.18,          # Sakhale et al. 2011, direct measurement
    "puri": 0.13,            # thin, fast fry, short contact
    "aloo_tikka": 0.28,      # porous matrix
    "brinjal_fry": 0.32,
    "namkeen": 0.30,         # low residual moisture drives high uptake
    "gulab_jamun_ball": 0.10,  # dense low-moisture dough, low-temp fry
    "default_fritter": 0.18,
}

# Water lost during deep frying, as a fraction of the raw dough weight.
FRY_WATER_LOSS = 0.18

# Gulab jamun: grams of sugar syrup absorbed per gram of fried ball.
# 1.18 g/g at 80C, 1.83 g/g at 65C, up to 2.9 g/g at low syrup concentration.
SYRUP_UPTAKE_DEFAULT = 1.5
SYRUP_SUGAR_FRACTION = 0.48  # ~48% sugar w/w in a typical one-string syrup


# ---------------------------------------------------------------------------
# Recipes
# ---------------------------------------------------------------------------


@dataclass
class AddedIngredient:
    ingredient: str
    grams: float
    # Whether the user can realistically change this. Pan oil is the single
    # biggest swing factor in Indian cooking and MUST be user-editable.
    user_adjustable: bool = False
    note: str = ""


@dataclass
class PreparationSpec:
    """How a dry mix becomes food."""

    key: str
    display_name: str
    dry_mix_g: float                     # reference batch size
    added: list[AddedIngredient]
    transform: Transform
    evaporation_fraction: float = 0.0    # of total wet weight
    pieces: int | None = None
    piece_name: str = "piece"
    oil_uptake_key: str | None = None    # for deep_fried
    syrup_uptake: float | None = None    # for gulab jamun
    source_note: str = ""


PREPARATIONS: dict[str, PreparationSpec] = {
    # -- Steamed -----------------------------------------------------------
    "rava_idli": PreparationSpec(
        key="rava_idli",
        display_name="Rava idli (from mix)",
        dry_mix_g=200,
        added=[
            AddedIngredient("curd_full_fat", 415, True,
                            "MTR ratio: 1 measure mix : 1.5 measures sour curd"),
            AddedIngredient("oil", 5, True, "greasing the moulds"),
        ],
        transform=Transform.steamed,
        evaporation_fraction=0.02,
        pieces=12,
        piece_name="idli",
        source_note="Gits 500g pack states 30 idlis; 200g -> 12. Curd is the "
                    "dominant macro contributor -- ~415g curd is ~250 kcal.",
    ),
    "rice_idli": PreparationSpec(
        key="rice_idli",
        display_name="Idli (from instant mix)",
        dry_mix_g=200,
        added=[
            AddedIngredient("water", 320, False),
            AddedIngredient("curd_toned", 160, True),
            AddedIngredient("oil", 4, True, "greasing the moulds"),
        ],
        transform=Transform.steamed,
        evaporation_fraction=0.02,
        pieces=18,
        piece_name="idli",
        source_note="Gits: 200g -> 18 idlis, 500g -> 45, 1kg -> 90. "
                    "~11 g dry mix per idli, ~36 g finished.",
    ),
    "dhokla": PreparationSpec(
        key="dhokla",
        display_name="Khaman dhokla (from mix)",
        dry_mix_g=200,
        added=[
            AddedIngredient("water", 220, False),
            AddedIngredient("oil", 20, True,
                            "tempering poured on AFTER steaming -- fully retained"),
            AddedIngredient("sugar", 15, True, "in the tempering"),
        ],
        transform=Transform.steamed,
        evaporation_fraction=0.03,
        pieces=24,
        piece_name="piece",
        source_note="Gits: 500g -> 60 pieces, 1kg -> 120. Tempering oil is "
                    "never lost -- do not omit it.",
    ),
    # -- Griddled ----------------------------------------------------------
    "dosa": PreparationSpec(
        key="dosa",
        display_name="Dosa (from instant mix)",
        dry_mix_g=200,
        added=[
            AddedIngredient("water", 500, False),
            AddedIngredient("oil", 44, True,
                            "~1 tsp (5.5 g) drizzled per dosa; restaurants use 2-3x"),
        ],
        transform=Transform.griddled,
        evaporation_fraction=0.42,
        pieces=8,
        piece_name="dosa",
        source_note="Gits: 200g -> 8 dosas, 500g -> 20. THE PAN OIL DOMINATES: "
                    "1 tsp is 45 kcal on a ~110 kcal dosa.",
    ),
    "rava_dosa": PreparationSpec(
        key="rava_dosa",
        display_name="Rava dosa (from mix)",
        dry_mix_g=200,
        added=[
            AddedIngredient("water", 570, False),
            AddedIngredient("oil", 36, True, "~0.5-1 tsp per dosa"),
        ],
        transform=Transform.griddled,
        evaporation_fraction=0.50,  # lacy and crisp -> highest loss
        pieces=8,
        piece_name="dosa",
        source_note="Much thinner batter (1:3) than plain dosa, so the highest "
                    "evaporation loss of any batter item.",
    ),
    # -- Deep fried --------------------------------------------------------
    "medu_vada": PreparationSpec(
        key="medu_vada",
        display_name="Medu vada (from mix)",
        dry_mix_g=200,
        added=[AddedIngredient("water", 150, False)],
        transform=Transform.deep_fried,
        pieces=18,
        piece_name="vada",
        oil_uptake_key="medu_vada",
        source_note="Gits: 200g -> 18 vadas. Oil uptake ~18% of FINISHED "
                    "weight (Sakhale et al. 2011 samosa control 18.34%).",
    ),
    "gulab_jamun": PreparationSpec(
        key="gulab_jamun",
        display_name="Gulab jamun (from mix)",
        dry_mix_g=175,
        added=[AddedIngredient("water", 60, False)],
        transform=Transform.deep_fried,
        pieces=20,
        piece_name="jamun",
        oil_uptake_key="gulab_jamun_ball",
        syrup_uptake=SYRUP_UPTAKE_DEFAULT,
        source_note="MTR 175g -> ~20 pieces of ~35g. A finished jamun is "
                    "~40% ball+oil and ~60% absorbed syrup by weight.",
    ),
    # -- Simmered ----------------------------------------------------------
    "upma": PreparationSpec(
        key="upma",
        display_name="Upma (from mix)",
        dry_mix_g=200,
        added=[
            AddedIngredient("water", 700, False),
            AddedIngredient("oil", 20, True,
                            "1.5 tbsp; ghee versions run higher"),
        ],
        transform=Transform.simmered,
        evaporation_fraction=0.06,
        pieces=4,
        piece_name="serving",
        source_note="MTR: 1 cup mix : 2.5 cups boiling water. The oil is ~40% "
                    "of a scratch upma's calories.",
    ),
    "payasam": PreparationSpec(
        key="payasam",
        display_name="Payasam / kheer (from mix)",
        dry_mix_g=180,
        added=[AddedIngredient("milk_full_fat", 1000, True,
                               "toned milk drops this by ~140 kcal per litre")],
        transform=Transform.simmered,
        evaporation_fraction=0.10,
        pieces=6,
        piece_name="bowl",
        source_note="The milk choice swings this dish far more than the mix does.",
    ),
}


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------


@dataclass
class PreparedResult:
    display_name: str
    prepared_weight_g: float
    per_100g: Nutrients
    total: Nutrients
    pieces: int | None
    grams_per_piece: float | None
    per_piece: Nutrients | None
    breakdown: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def prepare(
    spec: PreparationSpec,
    dry_mix_per_100g: Nutrients,
    *,
    dry_mix_g: float | None = None,
    overrides: dict[str, float] | None = None,
) -> PreparedResult:
    """Convert a dry-mix label panel into the finished dish.

    `overrides` lets the user say "I used 2 tbsp of ghee, not 1.5" -- keyed by
    ingredient name, value in grams. This is exposed in the UI because pan oil
    is the single largest source of variance in Indian home cooking.
    """
    batch = dry_mix_g if dry_mix_g is not None else spec.dry_mix_g
    scale = batch / spec.dry_mix_g

    notes: list[str] = []
    breakdown: dict[str, float] = {}

    # 1. Start with the mix itself.
    total = dry_mix_per_100g.scaled(batch / 100.0)
    wet_weight = batch
    breakdown["dry mix"] = round(batch, 1)

    # 2. Add everything that goes in.
    for item in spec.added:
        grams = (overrides or {}).get(item.ingredient)
        grams = grams if grams is not None else item.grams * scale

        ing = INGREDIENTS.get(item.ingredient)
        if ing is None:
            notes.append(f"Unknown ingredient '{item.ingredient}' -- skipped.")
            continue

        total = total + ing.scaled(grams / 100.0)
        wet_weight += grams
        if grams > 0:
            breakdown[item.ingredient] = round(grams, 1)

    # 3. Apply the cooking transform.
    if spec.transform is Transform.deep_fried:
        # Water out first, then oil in. Applying uptake to the raw dough
        # instead of the finished weight overstates calories by ~20%.
        after_water_loss = wet_weight * (1 - FRY_WATER_LOSS)
        uptake = OIL_UPTAKE.get(spec.oil_uptake_key or "default_fritter", 0.18)

        # finished = dough_solids + oil, where oil = uptake * finished
        #  => finished = dough_solids / (1 - uptake)
        finished = after_water_loss / (1 - uptake)
        oil_absorbed = finished - after_water_loss

        total = total + INGREDIENTS["oil"].scaled(oil_absorbed / 100.0)
        breakdown["absorbed frying oil"] = round(oil_absorbed, 1)
        notes.append(
            f"Absorbed {oil_absorbed:.0f} g of frying oil "
            f"({uptake:.0%} of finished weight) = {oil_absorbed * 8.84:.0f} kcal."
        )
        prepared_weight = finished

        # 4. Gulab jamun only: syrup soak.
        if spec.syrup_uptake:
            syrup_g = prepared_weight * spec.syrup_uptake
            sugar_g = syrup_g * SYRUP_SUGAR_FRACTION
            total = total + INGREDIENTS["sugar"].scaled(sugar_g / 100.0)
            prepared_weight += syrup_g
            breakdown["absorbed sugar syrup"] = round(syrup_g, 1)
            notes.append(
                f"Soaked up {syrup_g:.0f} g of syrup ({sugar_g:.0f} g sugar) -- "
                f"more than half the finished weight."
            )
    else:
        prepared_weight = wet_weight * (1 - spec.evaporation_fraction)
        if spec.evaporation_fraction > 0.1:
            notes.append(
                f"Lost {wet_weight * spec.evaporation_fraction:.0f} g of water "
                f"on the pan ({spec.evaporation_fraction:.0%})."
            )

    pieces = int(spec.pieces * scale) if spec.pieces else None
    grams_per_piece = prepared_weight / pieces if pieces else None
    per_piece = total.scaled(1 / pieces) if pieces else None

    if spec.source_note:
        notes.append(spec.source_note)

    return PreparedResult(
        display_name=spec.display_name,
        prepared_weight_g=round(prepared_weight, 1),
        per_100g=total.per_100g(prepared_weight).rounded(),
        total=total.rounded(),
        pieces=pieces,
        grams_per_piece=round(grams_per_piece, 1) if grams_per_piece else None,
        per_piece=per_piece.rounded() if per_piece else None,
        breakdown=breakdown,
        notes=notes,
    )


def dilution_factor(spec: PreparationSpec) -> float:
    """How wrong you'd be logging the dry-mix panel against prepared food.

    Returns prepared_weight / dry_mix_weight. For rava idli this is ~3.1, i.e.
    logging "100 g rava idli" against the dry panel overstates by ~3x.
    """
    wet = spec.dry_mix_g + sum(i.grams for i in spec.added)
    if spec.transform is Transform.deep_fried:
        uptake = OIL_UPTAKE.get(spec.oil_uptake_key or "default_fritter", 0.18)
        finished = (wet * (1 - FRY_WATER_LOSS)) / (1 - uptake)
        if spec.syrup_uptake:
            finished *= 1 + spec.syrup_uptake
        return finished / spec.dry_mix_g
    return (wet * (1 - spec.evaporation_fraction)) / spec.dry_mix_g
