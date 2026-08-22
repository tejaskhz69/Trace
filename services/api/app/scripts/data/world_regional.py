"""World regional dishes, per 100 g, to extend `seed_dishes.DISHES`.

Companion to `indian_regional.py`, same shape and same rules:

    (name, cuisine, category, kcal, protein_g, carbs_g, fat_g, fiber_g,
     servings, aliases)

WHY THESE AND NOT MORE USDA
USDA's FNDDS is a US dietary-survey instrument. It is excellent on things
Americans eat and thin-to-empty everywhere else: it has no jollof rice, no
goulash, no injera, no bibimbap worth the name, no pierogi beyond a frozen
brand. Those gaps are not obscure -- they are the daily food of several
hundred million people, and an app that returns nothing for them is not a
worldwide app.

Names include the local spelling in `aliases` wherever it differs, because a
Nigerian user searches "jollof", not "rice, West African style".

PROVENANCE AND ITS LIMITS
Composed from national food-composition tables and standard recipes, per 100 g
AS EATEN -- cooked, plated, cooking fat included. These are `recipe`-tier
values, not weighed ones. A restaurant pad see ew and a home one differ by more
than any table admits. Seeded at data_quality 0.85 and never presented as
measured.
"""

from __future__ import annotations

Serving = tuple[str, float, bool]

BOWL: list[Serving] = [("1 bowl", 250, True), ("100 g", 100, False)]
PLATE: list[Serving] = [("1 plate", 300, True), ("100 g", 100, False)]
CUP: list[Serving] = [("1 cup", 150, True), ("100 g", 100, False)]
GLASS: list[Serving] = [("1 glass", 200, True), ("100 ml", 100, False)]


def _p(name: str, grams: float) -> list[Serving]:
    return [(name, grams, True), ("100 g", 100, False)]


WORLD_REGIONAL: list[tuple] = [
    # ==================================================== WEST AFRICA
    ("Jollof rice", "west_african", "rice", 165, 3.5, 26.0, 5.5, 1.4, PLATE,
     ["jollof", "benachin"]),
    ("Egusi soup", "west_african", "soup", 195, 9.0, 6.0, 15.0, 3.0, BOWL,
     ["melon seed soup"]),
    ("Fufu", "west_african", "staple", 155, 1.5, 37.0, 0.3, 1.8, _p("1 ball", 200),
     ["foofoo", "swallow"]),
    ("Pounded yam", "west_african", "staple", 145, 1.8, 34.0, 0.3, 2.2,
     _p("1 portion", 200), ["iyan"]),
    ("Suya", "west_african", "starter", 235, 26.0, 3.5, 13.0, 0.6,
     _p("1 skewer", 100), ["tsire", "spiced beef skewer"]),
    ("Moi moi", "west_african", "snack", 150, 8.0, 13.0, 7.0, 3.5,
     _p("1 portion", 150), ["moin moin", "bean pudding"]),
    ("Waakye", "west_african", "rice", 155, 5.0, 27.0, 3.2, 3.8, PLATE, []),
    ("Banku", "west_african", "staple", 140, 2.5, 30.0, 0.6, 1.5,
     _p("1 ball", 180), []),
    ("Kelewele", "west_african", "snack", 215, 1.5, 32.0, 9.5, 2.4,
     _p("1 portion", 120), ["spiced fried plantain"]),
    ("Thieboudienne", "west_african", "rice", 160, 8.5, 22.0, 4.5, 1.8, PLATE,
     ["ceebu jen", "senegalese fish rice"]),

    # ==================================================== EAST / HORN AFRICA
    ("Injera", "east_african", "bread", 130, 3.8, 26.0, 0.7, 3.2,
     _p("1 injera", 120), ["teff flatbread"]),
    ("Doro wat", "east_african", "curry", 175, 15.0, 6.0, 10.0, 1.6, BOWL,
     ["ethiopian chicken stew"]),
    ("Misir wot", "east_african", "dal", 125, 6.5, 17.0, 3.8, 5.0, BOWL,
     ["ethiopian red lentil stew"]),
    ("Shiro", "east_african", "dal", 145, 7.0, 17.0, 5.5, 4.5, BOWL,
     ["chickpea flour stew"]),
    ("Ugali", "east_african", "staple", 110, 2.5, 24.0, 0.5, 1.2,
     _p("1 portion", 200), ["sima", "nsima", "posho"]),
    ("Nyama choma", "east_african", "starter", 245, 26.0, 0.5, 15.0, 0.0,
     _p("1 portion", 150), ["grilled meat"]),
    ("Sukuma wiki", "east_african", "sabzi", 85, 3.5, 7.0, 5.0, 3.2, CUP,
     ["braised collard greens"]),

    # ==================================================== NORTH AFRICA
    ("Couscous with vegetables", "north_african", "dish", 145, 4.5, 25.0, 3.2,
     2.8, PLATE, ["seksu"]),
    ("Lamb tagine", "north_african", "curry", 165, 14.0, 8.0, 8.5, 1.8, BOWL,
     ["tajine"]),
    ("Harira", "north_african", "soup", 75, 3.8, 10.0, 2.2, 1.8, BOWL,
     ["moroccan soup"]),
    ("Shakshuka", "north_african", "dish", 105, 6.0, 6.0, 6.5, 1.6, PLATE, []),
    ("Koshari", "north_african", "dish", 165, 5.5, 29.0, 3.2, 3.0, PLATE,
     ["koshary", "egyptian rice lentils"]),
    ("Ful medames", "north_african", "dal", 115, 7.0, 15.0, 3.0, 5.5, BOWL,
     ["foul", "fava bean stew"]),

    # ==================================================== MIDDLE EAST
    ("Chicken shawarma plate", "middle_eastern", "dish", 195, 16.0, 14.0, 8.5,
     1.6, PLATE, []),
    ("Mansaf", "middle_eastern", "dish", 185, 12.0, 18.0, 7.5, 0.8, PLATE, []),
    ("Kibbeh", "middle_eastern", "snack", 245, 11.0, 22.0, 13.0, 2.2,
     _p("2 pieces", 90), []),
    ("Fattoush", "middle_eastern", "salad", 95, 2.2, 10.0, 5.5, 2.4, BOWL, []),
    ("Baba ganoush", "middle_eastern", "condiment", 130, 3.0, 9.0, 9.5, 4.0,
     _p("2 tbsp", 40), ["mutabal"]),
    ("Manakish za'atar", "middle_eastern", "bread", 290, 7.0, 38.0, 12.0, 2.6,
     _p("1 piece", 120), ["manaqish"]),
    ("Baklava", "middle_eastern", "sweet", 430, 6.5, 45.0, 25.0, 2.4,
     _p("1 piece", 50), []),
    ("Kebab koobideh", "middle_eastern", "starter", 240, 19.0, 2.0, 17.0, 0.4,
     _p("1 skewer", 120), ["koobideh", "persian kebab"]),
    ("Ghormeh sabzi", "middle_eastern", "curry", 145, 11.0, 6.0, 8.5, 2.6, BOWL,
     ["persian herb stew"]),
    ("Tahchin", "middle_eastern", "rice", 195, 8.0, 26.0, 6.5, 0.8, PLATE, []),

    # ==================================================== EAST ASIA: CHINA
    ("Char siu", "chinese", "starter", 245, 21.0, 12.0, 13.0, 0.2,
     _p("1 portion", 120), ["bbq pork"]),
    ("Wonton soup", "chinese", "soup", 65, 4.5, 7.0, 2.0, 0.5, BOWL, []),
    ("Sweet and sour pork", "chinese", "dish", 225, 12.0, 24.0, 9.5, 0.8, PLATE,
     []),
    ("Congee", "chinese", "breakfast", 55, 1.6, 11.0, 0.4, 0.2, BOWL,
     ["jook", "rice porridge"]),
    ("Xiaolongbao", "chinese", "snack", 200, 9.5, 22.0, 8.0, 0.8,
     _p("4 pieces", 100), ["soup dumplings"]),
    ("Chow mein", "chinese", "noodles", 185, 7.0, 25.0, 6.5, 2.0, PLATE, []),
    ("Dan dan noodles", "chinese", "noodles", 215, 8.5, 26.0, 9.0, 1.8, BOWL, []),
    ("Hot and sour soup", "chinese", "soup", 50, 3.0, 6.0, 1.8, 0.8, BOWL, []),
    ("Peking duck", "chinese", "dish", 290, 19.0, 5.0, 22.0, 0.3,
     _p("1 portion", 120), []),

    # ==================================================== EAST ASIA: JAPAN
    ("Miso soup", "japanese", "soup", 35, 2.5, 3.0, 1.2, 0.6, BOWL, []),
    ("Chicken teriyaki", "japanese", "dish", 190, 18.0, 11.0, 8.0, 0.2, PLATE,
     []),
    ("Gyoza", "japanese", "snack", 215, 8.0, 24.0, 9.5, 1.4,
     _p("5 pieces", 125), ["potstickers"]),
    ("Onigiri", "japanese", "snack", 165, 3.5, 33.0, 1.6, 0.8,
     _p("1 onigiri", 110), ["rice ball"]),
    ("Udon noodle soup", "japanese", "noodles", 95, 3.8, 18.0, 0.8, 1.2, BOWL,
     []),
    ("Tempura (mixed)", "japanese", "starter", 265, 9.0, 24.0, 15.0, 1.4,
     _p("1 portion", 120), []),
    ("Okonomiyaki", "japanese", "dish", 195, 8.5, 20.0, 9.0, 1.8,
     _p("1 piece", 200), []),
    ("Katsu curry", "japanese", "dish", 205, 10.0, 23.0, 8.5, 1.4, PLATE, []),

    # ==================================================== EAST ASIA: KOREA
    ("Kimchi jjigae", "korean", "soup", 75, 5.5, 5.0, 3.8, 1.6, BOWL,
     ["kimchi stew"]),
    ("Tteokbokki", "korean", "snack", 185, 3.5, 38.0, 2.2, 1.2,
     _p("1 portion", 200), ["rice cakes"]),
    ("Japchae", "korean", "noodles", 160, 3.5, 26.0, 5.0, 1.4, PLATE,
     ["glass noodles"]),
    ("Bulgogi", "korean", "dish", 215, 18.0, 8.0, 12.0, 0.5,
     _p("1 portion", 150), []),
    ("Samgyetang", "korean", "soup", 105, 10.0, 6.5, 4.5, 0.3, BOWL,
     ["ginseng chicken soup"]),
    ("Sundubu jjigae", "korean", "soup", 80, 6.0, 4.5, 4.5, 1.0, BOWL,
     ["soft tofu stew"]),

    # ==================================================== SOUTHEAST ASIA
    ("Pad see ew", "thai", "noodles", 200, 8.0, 27.0, 7.0, 1.6, PLATE, []),
    ("Tom yum goong", "thai", "soup", 55, 5.5, 4.5, 1.8, 0.6, BOWL,
     ["tom yum"]),
    ("Massaman curry", "thai", "curry", 175, 9.0, 10.0, 11.5, 1.8, BOWL, []),
    ("Som tam", "thai", "salad", 70, 1.8, 13.0, 1.6, 2.4, BOWL,
     ["green papaya salad"]),
    ("Mango sticky rice", "thai", "sweet", 195, 2.5, 38.0, 4.5, 1.2,
     _p("1 portion", 200), ["khao niao mamuang"]),
    ("Bun cha", "vietnamese", "dish", 155, 11.0, 15.0, 5.5, 1.2, PLATE, []),
    ("Goi cuon", "vietnamese", "snack", 105, 6.0, 15.0, 2.0, 1.0,
     _p("2 rolls", 120), ["summer rolls", "fresh spring rolls"]),
    ("Com tam", "vietnamese", "rice", 185, 10.0, 26.0, 5.0, 0.8, PLATE,
     ["broken rice"]),
    ("Laksa", "malaysian", "noodles", 145, 6.5, 14.0, 7.5, 1.4, BOWL, []),
    ("Nasi lemak", "malaysian", "rice", 215, 5.5, 27.0, 9.5, 1.6, PLATE, []),
    ("Rendang", "indonesian", "curry", 235, 16.0, 6.0, 17.0, 1.4, BOWL,
     ["beef rendang"]),
    ("Satay (chicken)", "indonesian", "starter", 205, 20.0, 7.0, 11.0, 0.8,
     _p("4 skewers", 120), ["sate"]),
    ("Gado gado", "indonesian", "salad", 135, 6.0, 11.0, 8.0, 3.2, PLATE, []),
    ("Adobo", "filipino", "dish", 185, 16.0, 4.0, 11.5, 0.4, PLATE,
     ["chicken adobo"]),
    ("Sinigang", "filipino", "soup", 65, 6.5, 4.5, 2.5, 1.0, BOWL, []),
    ("Pancit", "filipino", "noodles", 170, 6.5, 24.0, 5.0, 1.6, PLATE, []),

    # ==================================================== LATIN AMERICA
    ("Pozole", "mexican", "soup", 90, 7.5, 8.0, 3.2, 1.6, BOWL, []),
    ("Chilaquiles", "mexican", "breakfast", 185, 7.0, 21.0, 8.5, 2.4, PLATE, []),
    ("Tamale", "mexican", "snack", 215, 6.0, 25.0, 10.0, 2.6,
     _p("1 tamale", 120), ["tamales"]),
    ("Enchiladas", "mexican", "dish", 175, 9.0, 18.0, 7.5, 2.2, PLATE, []),
    ("Elote", "mexican", "snack", 145, 4.0, 20.0, 6.0, 2.4,
     _p("1 cob", 180), ["mexican street corn"]),
    ("Empanada (beef)", "argentine", "snack", 265, 9.5, 26.0, 13.5, 1.4,
     _p("1 empanada", 90), ["empanadas"]),
    ("Milanesa", "argentine", "dish", 240, 18.0, 16.0, 12.0, 0.8,
     _p("1 piece", 150), []),
    ("Chimichurri", "argentine", "condiment", 265, 0.8, 3.0, 28.0, 1.2,
     _p("1 tbsp", 15), []),
    ("Pao de queijo", "brazilian", "snack", 305, 6.0, 38.0, 14.0, 0.6,
     _p("2 pieces", 60), ["cheese bread"]),
    ("Acai bowl", "brazilian", "breakfast", 135, 2.0, 22.0, 4.5, 3.0, BOWL, []),
    ("Lomo saltado", "peruvian", "dish", 175, 12.0, 17.0, 6.5, 1.4, PLATE, []),
    ("Aji de gallina", "peruvian", "curry", 165, 11.0, 12.0, 8.0, 1.0, BOWL, []),
    ("Arepa", "venezuelan", "bread", 220, 4.5, 42.0, 3.5, 3.0,
     _p("1 arepa", 120), ["arepas"]),
    ("Ropa vieja", "cuban", "dish", 150, 14.0, 7.0, 7.0, 1.4, PLATE, []),
    ("Gallo pinto", "costa_rican", "rice", 155, 5.5, 26.0, 3.2, 4.0, PLATE, []),

    # ==================================================== EASTERN EUROPE
    ("Goulash", "hungarian", "soup", 105, 9.5, 7.0, 4.5, 1.2, BOWL,
     ["gulyas", "beef goulash"]),
    ("Chicken paprikash", "hungarian", "curry", 155, 13.0, 5.5, 9.0, 0.8, BOWL,
     ["paprikas csirke"]),
    ("Langos", "hungarian", "snack", 315, 7.0, 40.0, 14.0, 1.8,
     _p("1 piece", 130), []),
    ("Pierogi", "polish", "snack", 195, 6.0, 30.0, 5.5, 1.6,
     _p("5 pieces", 150), ["perogies", "varenyky"]),
    ("Bigos", "polish", "dish", 105, 7.5, 6.0, 5.5, 2.6, BOWL,
     ["hunter's stew"]),
    ("Borscht", "ukrainian", "soup", 55, 1.8, 8.0, 1.8, 2.0, BOWL,
     ["borsch", "barszcz"]),
    ("Beef stroganoff", "russian", "dish", 165, 12.0, 6.0, 10.0, 0.6, PLATE, []),
    ("Olivier salad", "russian", "salad", 195, 4.0, 12.0, 14.5, 1.6, BOWL,
     ["russian salad"]),
    ("Sarma", "balkan", "dish", 125, 7.0, 9.0, 6.5, 2.2, PLATE,
     ["stuffed cabbage rolls"]),
    ("Cevapi", "balkan", "starter", 245, 18.0, 3.0, 18.0, 0.4,
     _p("5 pieces", 130), ["cevapcici"]),
    ("Moussaka", "greek", "dish", 155, 8.0, 9.0, 9.5, 2.0, PLATE, []),
    ("Spanakopita", "greek", "snack", 265, 7.5, 22.0, 16.5, 2.0,
     _p("1 piece", 120), []),
    ("Gyros", "greek", "dish", 215, 15.0, 18.0, 9.5, 1.4,
     _p("1 gyros", 250), []),
    ("Tzatziki", "greek", "condiment", 85, 3.5, 4.0, 6.0, 0.4,
     _p("2 tbsp", 40), []),

    # ==================================================== WESTERN EUROPE
    ("Lasagne al forno", "italian", "dish", 145, 8.5, 12.0, 7.0, 1.2, PLATE,
     ["lasagna"]),
    ("Carbonara", "italian", "pasta", 215, 10.0, 24.0, 8.5, 1.2, PLATE,
     ["spaghetti carbonara"]),
    ("Minestrone", "italian", "soup", 55, 2.5, 8.0, 1.6, 2.0, BOWL, []),
    ("Caprese salad", "italian", "salad", 155, 8.5, 3.5, 12.0, 0.8, BOWL, []),
    ("Tiramisu", "italian", "sweet", 285, 5.0, 30.0, 16.0, 0.6,
     _p("1 portion", 120), []),
    ("Gnocchi", "italian", "pasta", 155, 4.0, 30.0, 2.2, 1.8, PLATE, []),
    ("Tortilla espanola", "spanish", "dish", 185, 6.5, 15.0, 11.0, 1.4,
     _p("1 slice", 130), ["spanish omelette"]),
    ("Gazpacho", "spanish", "soup", 45, 1.0, 5.0, 2.5, 1.2, BOWL, []),
    ("Patatas bravas", "spanish", "snack", 175, 2.5, 24.0, 8.0, 2.4,
     _p("1 portion", 180), []),
    ("Croque monsieur", "french", "dish", 265, 13.0, 22.0, 14.0, 1.2,
     _p("1 sandwich", 180), []),
    ("Ratatouille", "french", "sabzi", 75, 1.5, 7.0, 4.8, 2.6, CUP, []),
    ("Quiche lorraine", "french", "dish", 285, 9.5, 20.0, 18.5, 1.0,
     _p("1 slice", 130), []),
    ("Coq au vin", "french", "dish", 165, 15.0, 4.0, 9.0, 0.6, PLATE, []),
    ("Bratwurst", "german", "starter", 300, 14.0, 2.5, 26.0, 0.0,
     _p("1 sausage", 100), []),
    ("Schnitzel", "german", "dish", 245, 17.0, 15.0, 13.0, 0.8,
     _p("1 piece", 150), ["wiener schnitzel"]),
    ("Sauerkraut", "german", "sabzi", 25, 1.2, 4.5, 0.2, 3.0, CUP, []),
    ("Fish and chips", "british", "dish", 235, 11.0, 24.0, 11.0, 2.0, PLATE, []),
    ("Shepherd's pie", "british", "dish", 130, 8.0, 12.0, 5.5, 1.8, PLATE,
     ["cottage pie"]),
    ("Beans on toast", "british", "breakfast", 145, 6.0, 24.0, 2.5, 4.5, PLATE,
     []),
    ("Scone", "british", "bakery", 360, 7.0, 54.0, 13.0, 2.0,
     _p("1 scone", 70), []),
    ("Smorrebrod", "nordic", "dish", 215, 10.0, 22.0, 9.5, 2.2,
     _p("1 piece", 130), ["open sandwich"]),
    ("Gravlax", "nordic", "starter", 185, 22.0, 1.0, 10.5, 0.0,
     _p("1 portion", 80), ["cured salmon"]),
    ("Swedish meatballs", "nordic", "dish", 215, 14.0, 9.0, 14.0, 0.8, PLATE,
     ["kottbullar"]),
    ("Poutine", "canadian", "dish", 210, 6.5, 22.0, 11.0, 2.0, PLATE, []),

    # ==================================================== CENTRAL / SOUTH ASIA
    ("Plov", "central_asian", "rice", 195, 7.0, 26.0, 7.0, 1.4, PLATE,
     ["pilaf", "osh"]),
    ("Manti", "central_asian", "snack", 195, 9.0, 22.0, 8.0, 1.2,
     _p("4 pieces", 140), []),
    ("Lagman", "central_asian", "noodles", 135, 6.5, 18.0, 4.5, 1.4, BOWL, []),
    ("Momo (chicken)", "nepali", "snack", 185, 9.0, 22.0, 6.5, 1.2,
     _p("6 pieces", 150), ["momos"]),
    ("Dal bhat", "nepali", "dish", 135, 5.0, 22.0, 3.0, 3.2, PLATE, []),
    ("Kottu roti", "sri_lankan", "dish", 205, 9.0, 25.0, 8.0, 2.0, PLATE,
     ["kothu"]),
    ("Hoppers", "sri_lankan", "breakfast", 160, 2.8, 32.0, 2.4, 1.2,
     _p("1 hopper", 70), ["appa"]),
    ("Nihari", "pakistani", "curry", 215, 17.0, 6.0, 14.0, 0.8, BOWL, []),
    ("Haleem", "pakistani", "dish", 165, 11.0, 15.0, 6.5, 2.4, BOWL, []),
    ("Seekh kebab", "pakistani", "starter", 245, 18.0, 4.0, 17.5, 0.6,
     _p("2 skewers", 120), []),
]
