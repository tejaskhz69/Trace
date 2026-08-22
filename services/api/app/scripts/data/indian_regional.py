"""Regional Indian dishes, per 100 g, to extend `seed_dishes.DISHES`.

WHY THIS FILE EXISTS SEPARATELY
`seed_dishes.py` carries a global core. This one goes deep on India, because
that is the coverage gap no incumbent fills: USDA's FNDDS has "Biryani with
meat" and nothing for puttu, pesarattu, undhiyu, litti chokha or shukto, and
Open Food Facts only knows packaged goods. A user in Kerala logging breakfast
is the case this project has to win.

SHAPE (identical to seed_dishes.DISHES so the same seeder consumes both):
    (name, cuisine, category, kcal, protein_g, carbs_g, fat_g, fiber_g,
     servings, aliases)

All values are PER 100 g of the dish AS EATEN -- cooked, plated, with its
normal cooking fat already included. That last point is the one that matters:
a dal's calorie count is meaningless without the tempering, and quoting the
uncooked lentil figure is how other apps under-report Indian food by 30%.

PROVENANCE AND ITS LIMITS
Composed from Indian Food Composition Tables (IFCT 2017, NIN Hyderabad) and
USDA equivalents for shared ingredients, combined by standard household
recipes. That makes these `recipe`-tier values, not `weighed` ones: a home
kitchen's dal tadka can differ from any table by ±20% depending on how heavy
the ghee hand is. They are seeded at data_quality 0.85 rather than higher for
exactly that reason, and the AI scan's uncertainty band is what covers the
rest. Do not present any of these as measured.
"""

from __future__ import annotations

Serving = tuple[str, float, bool]

KATORI: list[Serving] = [("1 katori", 150, True), ("100 g", 100, False)]
BOWL: list[Serving] = [("1 bowl", 200, True), ("100 g", 100, False)]
PLATE: list[Serving] = [("1 plate", 250, True), ("100 g", 100, False)]
GLASS: list[Serving] = [("1 glass", 200, True), ("100 ml", 100, False)]
PIECE_50: list[Serving] = [("1 piece", 50, True), ("100 g", 100, False)]
PIECE_80: list[Serving] = [("1 piece", 80, True), ("100 g", 100, False)]


def _p(name: str, grams: float) -> list[Serving]:
    return [(name, grams, True), ("100 g", 100, False)]


INDIAN_REGIONAL: list[tuple] = [
    # ------------------------------------------------ South: Kerala
    ("Puttu", "indian_kerala", "breakfast", 145, 3.2, 30.0, 1.2, 2.4,
     _p("1 cylinder", 120), ["pittu", "steamed rice cake"]),
    ("Kadala curry", "indian_kerala", "curry", 155, 7.0, 18.0, 6.2, 6.8, KATORI,
     ["black chickpea curry", "kadala kari"]),
    ("Appam", "indian_kerala", "breakfast", 165, 3.0, 33.0, 2.2, 1.4,
     _p("1 appam", 70), ["palappam", "hoppers"]),
    ("Kerala fish curry", "indian_kerala", "curry", 130, 14.0, 4.5, 6.5, 1.0, KATORI,
     ["meen curry", "fish moilee"]),
    ("Avial", "indian_kerala", "sabzi", 125, 2.8, 9.5, 8.5, 3.6, KATORI,
     ["mixed vegetable coconut curry"]),
    ("Thoran", "indian_kerala", "sabzi", 110, 3.0, 9.0, 7.0, 4.2, KATORI,
     ["cabbage thoran", "beans thoran"]),
    ("Erissery", "indian_kerala", "curry", 140, 4.0, 16.0, 7.0, 4.5, KATORI, []),
    ("Kerala parotta", "indian_kerala", "bread", 355, 7.5, 48.0, 15.0, 2.2,
     _p("1 parotta", 80), ["malabar parotta", "porotta"]),
    ("Puttu and kadala", "indian_kerala", "dish", 150, 5.0, 24.0, 3.8, 4.6,
     PLATE, ["puttu kadala"]),

    # ------------------------------------------------ South: Tamil Nadu
    ("Rava dosa", "indian_south", "breakfast", 225, 4.0, 29.0, 10.5, 1.4,
     _p("1 dosa", 100), []),
    ("Lemon rice", "indian_south", "rice", 175, 3.2, 27.0, 6.0, 1.4, BOWL,
     ["chitranna"]),
    ("Tamarind rice", "indian_south", "rice", 190, 3.6, 28.0, 7.0, 2.0, BOWL,
     ["puliyodarai", "puliyogare"]),
    ("Chettinad chicken", "indian_south", "curry", 195, 17.0, 5.0, 12.0, 1.4,
     KATORI, []),
    ("Bisi bele bath", "indian_south", "rice", 165, 5.2, 24.0, 5.5, 3.0, BOWL, []),

    # ------------------------------------------------ South: Andhra / Telangana
    ("Pesarattu", "indian_south", "breakfast", 175, 8.0, 25.0, 4.5, 4.0,
     _p("1 pesarattu", 100), ["moong dal dosa"]),
    ("Hyderabadi biryani", "indian_south", "rice", 205, 9.5, 24.0, 8.0, 1.2,
     PLATE, ["dum biryani"]),
    ("Gongura pachadi", "indian_south", "condiment", 145, 3.0, 9.0, 11.0, 4.0,
     _p("2 tbsp", 30), ["sorrel chutney"]),
    ("Andhra chicken curry", "indian_south", "curry", 200, 16.5, 5.5, 13.0, 1.2,
     KATORI, []),

    # ------------------------------------------------ West: Maharashtra
    ("Poha", "indian_west", "breakfast", 155, 2.8, 26.0, 4.8, 1.6, BOWL,
     ["kanda poha", "flattened rice"]),
    ("Misal pav", "indian_west", "dish", 175, 6.5, 21.0, 7.5, 5.0, PLATE, []),
    ("Sabudana khichdi", "indian_west", "breakfast", 215, 3.0, 34.0, 8.0, 1.4,
     BOWL, ["sago khichdi"]),
    ("Puran poli", "indian_west", "sweet", 320, 7.0, 55.0, 8.0, 3.2,
     _p("1 poli", 80), ["holige", "obbattu"]),
    ("Thalipeeth", "indian_west", "breakfast", 245, 7.5, 36.0, 8.0, 5.5,
     _p("1 thalipeeth", 90), []),

    # ------------------------------------------------ West: Gujarat / Rajasthan
    ("Dhokla", "indian_west", "snack", 160, 6.0, 24.0, 4.0, 2.6,
     _p("2 pieces", 80), ["khaman"]),
    ("Undhiyu", "indian_west", "sabzi", 165, 4.5, 16.0, 9.5, 5.5, KATORI, []),
    ("Thepla", "indian_west", "bread", 300, 8.0, 43.0, 10.5, 6.0,
     _p("1 thepla", 45), ["methi thepla"]),
    ("Khandvi", "indian_west", "snack", 145, 5.5, 15.0, 6.5, 1.6,
     _p("4 rolls", 60), []),
    ("Dal baati churma", "indian_north", "dish", 310, 8.0, 42.0, 12.5, 5.0,
     PLATE, ["daal baati"]),
    ("Gatte ki sabzi", "indian_north", "sabzi", 180, 7.0, 18.0, 9.0, 3.0,
     KATORI, ["gatta curry"]),
    ("Ker sangri", "indian_north", "sabzi", 175, 4.0, 14.0, 11.5, 7.0, KATORI, []),

    # ------------------------------------------------ East: Bengal / Odisha
    ("Shukto", "indian_east", "sabzi", 95, 2.5, 10.0, 5.0, 3.4, KATORI, []),
    ("Macher jhol", "indian_east", "curry", 125, 14.5, 4.0, 6.0, 0.8, KATORI,
     ["bengali fish curry"]),
    ("Kosha mangsho", "indian_east", "curry", 240, 17.0, 5.0, 17.0, 0.9, KATORI,
     ["bengali mutton curry"]),
    ("Aloo posto", "indian_east", "sabzi", 165, 3.5, 16.0, 10.0, 2.6, KATORI, []),
    ("Luchi", "indian_east", "bread", 385, 6.5, 45.0, 20.0, 1.8,
     _p("2 luchi", 50), []),
    ("Mishti doi", "indian_east", "sweet", 145, 4.0, 24.0, 3.5, 0.0,
     _p("1 cup", 100), ["sweet yoghurt"]),
    ("Rasgulla", "indian_east", "sweet", 190, 4.5, 38.0, 2.5, 0.0,
     _p("2 pieces", 80), ["roshogolla"]),
    ("Sandesh", "indian_east", "sweet", 265, 9.0, 34.0, 10.0, 0.0,
     _p("2 pieces", 60), []),
    ("Dalma", "indian_east", "dal", 115, 5.0, 16.0, 3.2, 4.2, KATORI, []),
    ("Litti chokha", "indian_east", "dish", 245, 7.5, 36.0, 8.0, 5.5, PLATE,
     ["bihari litti"]),

    # ------------------------------------------------ North / Punjab
    ("Chole bhature", "indian_north", "dish", 285, 7.5, 34.0, 13.5, 4.5, PLATE, []),
    ("Bhatura", "indian_north", "bread", 330, 7.0, 44.0, 14.0, 1.8,
     _p("1 bhatura", 80), []),
    ("Tandoori roti", "indian_north", "bread", 285, 8.5, 55.0, 3.0, 7.5,
     _p("1 roti", 50), []),
    ("Sarson ka saag", "indian_north", "sabzi", 115, 4.0, 8.0, 7.0, 4.5, KATORI,
     ["mustard greens"]),
    ("Makki di roti", "indian_north", "bread", 290, 6.5, 52.0, 6.5, 6.0,
     _p("1 roti", 60), ["corn flatbread"]),
    ("Kadhi pakora", "indian_north", "curry", 135, 4.5, 11.0, 8.0, 1.4, KATORI,
     ["kadhi"]),
    ("Malai kofta", "indian_north", "curry", 275, 7.0, 15.0, 21.0, 2.0, KATORI, []),
    ("Shahi paneer", "indian_north", "curry", 255, 9.0, 11.0, 20.0, 1.5, KATORI, []),
    ("Chicken tikka masala", "indian_north", "curry", 195, 14.5, 7.0, 12.0, 1.2,
     KATORI, []),
    ("Rajma chawal", "indian_north", "dish", 140, 5.0, 22.0, 3.5, 4.0, PLATE, []),
    ("Kheer", "indian_north", "sweet", 145, 3.8, 22.0, 4.5, 0.4,
     _p("1 katori", 150), ["payasam", "rice pudding"]),
    ("Gajar ka halwa", "indian_north", "sweet", 240, 4.0, 30.0, 11.5, 2.2,
     _p("1 katori", 120), ["carrot halwa"]),
    ("Jalebi", "indian_north", "sweet", 380, 3.0, 62.0, 13.5, 0.3,
     _p("2 pieces", 60), []),

    # ------------------------------------------------ Street food
    ("Sev puri", "indian_street", "snack", 245, 5.5, 32.0, 10.5, 3.2,
     _p("1 plate", 100), []),
    ("Dahi puri", "indian_street", "snack", 190, 5.0, 27.0, 7.0, 2.4,
     _p("1 plate", 120), []),
    ("Kachori", "indian_street", "snack", 340, 6.5, 38.0, 18.0, 3.4,
     _p("1 kachori", 55), []),
    ("Aloo tikki", "indian_street", "snack", 195, 3.0, 27.0, 8.5, 2.6,
     _p("2 tikki", 100), []),
    ("Momos (steamed)", "indian_street", "snack", 175, 7.0, 25.0, 5.0, 1.4,
     _p("6 pieces", 150), ["dumplings"]),
    ("Egg bhurji", "indian_street", "dish", 195, 13.0, 4.0, 14.0, 0.8, KATORI,
     ["anda bhurji"]),
    ("Chicken 65", "indian_south", "starter", 245, 18.0, 12.0, 14.5, 0.8,
     _p("1 plate", 150), []),

    # ------------------------------------------------ Drinks
    ("Sweet lassi", "indian_drink", "beverage", 105, 3.0, 17.0, 2.8, 0.0, GLASS,
     ["meethi lassi"]),
    ("Salted buttermilk", "indian_drink", "beverage", 35, 1.8, 3.2, 1.4, 0.0,
     GLASS, ["chaas", "chhaas", "majjige"]),
    ("Masala chai", "indian_drink", "beverage", 65, 1.8, 9.0, 2.4, 0.0,
     _p("1 cup", 150), ["chai", "tea with milk"]),
    ("Filter coffee", "indian_drink", "beverage", 60, 1.8, 8.0, 2.2, 0.0,
     _p("1 cup", 150), ["kaapi", "south indian coffee"]),
    ("Nimbu pani", "indian_drink", "beverage", 40, 0.1, 10.0, 0.0, 0.1, GLASS,
     ["shikanji", "lemonade"]),
    ("Thandai", "indian_drink", "beverage", 135, 4.0, 18.0, 5.5, 0.8, GLASS, []),

    # ------------------------------------------------ Everyday staples
    ("Plain steamed rice", "indian_south", "rice", 130, 2.7, 28.0, 0.3, 0.4, BOWL,
     ["boiled rice", "chawal", "sadam"]),
    ("Moong dal (cooked)", "indian_north", "dal", 105, 7.0, 16.0, 1.2, 4.0,
     KATORI, ["yellow moong"]),
    ("Masoor dal (cooked)", "indian_north", "dal", 115, 7.5, 17.0, 1.8, 4.2,
     KATORI, ["red lentil"]),
    ("Toor dal (cooked)", "indian_north", "dal", 120, 7.2, 18.0, 2.0, 4.4,
     KATORI, ["arhar dal", "pigeon pea"]),
    ("Paneer (raw)", "indian_north", "dairy", 265, 18.0, 3.5, 20.0, 0.0,
     _p("50 g", 50), ["cottage cheese"]),
    ("Curd (dahi)", "indian_north", "dairy", 60, 3.1, 4.7, 3.3, 0.0,
     _p("1 katori", 150), ["yoghurt", "yogurt", "thayir"]),
    ("Idli batter dosa (oil-free)", "indian_south", "breakfast", 155, 3.8, 30.0,
     1.5, 1.6, _p("1 dosa", 85), []),
]
