#!/usr/bin/env python3
"""Seed the catalogue with cooked dishes from around the world.

WHY THIS EXISTS ALONGSIDE THE OFF IMPORT
----------------------------------------
Open Food Facts and USDA Branded are **packaged-goods** databases. They will
find your Pintola oats instantly and will never find "dal tadka", "pad kra pao"
or "birria taco", because nobody puts a barcode on a home-cooked meal.

Cooked dishes are where every competitor is weakest and where photo scanning
sends the most traffic -- so this table is a differentiator, not filler. The
rule that matters: **2,000 verified, correctly-portioned dishes beat 100,000
crowd-sourced guesses.** MyFitnessPal has 20M entries and its Indian data is
famously unusable. Do not repeat that mistake in pursuit of a headline number.

Values are per 100 g as commonly prepared (home-style, moderate oil), sourced
from IFCT 2017 / USDA SR Legacy / published composition tables. Serving sizes
use the unit a native speaker of that cuisine would actually say.

USAGE
    python -m app.scripts.seed_dishes
    python -m app.scripts.seed_dishes --cuisine indian_north
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import SessionLocal, init_db
from ..models import FoodItem, FoodSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed.dishes")

# (name, cuisine, category, kcal, protein, carbs, fat, fiber, servings, aliases)
Serving = tuple[str, float, bool]

KATORI: list[Serving] = [("1 katori", 150, True), ("100 g", 100, False)]
BOWL: list[Serving] = [("1 bowl", 200, True), ("100 g", 100, False)]
PIECE_40: list[Serving] = [("1 piece", 40, True), ("100 g", 100, False)]
PLATE: list[Serving] = [("1 plate", 250, True), ("100 g", 100, False)]
CUP: list[Serving] = [("1 cup", 150, True), ("100 g", 100, False)]
GLASS: list[Serving] = [("1 glass", 200, True), ("100 ml", 100, False)]

DISHES: list[tuple] = [
    # ---------------- North Indian ----------------
    ("Dal tadka", "indian_north", "dal", 160, 6.5, 18.0, 6.5, 4.2, KATORI,
     ["yellow dal", "toor dal tadka", "dal fry"]),
    ("Dal makhani", "indian_north", "dal", 205, 7.0, 17.0, 12.0, 5.0, KATORI,
     ["kali dal", "black dal"]),
    ("Rajma masala", "indian_north", "dal", 145, 6.8, 19.0, 4.5, 6.0, KATORI,
     ["kidney bean curry"]),
    ("Chana masala", "indian_north", "curry", 165, 7.2, 22.0, 5.5, 6.5, KATORI,
     ["chole", "chickpea curry"]),
    ("Paneer butter masala", "indian_north", "curry", 265, 9.5, 10.0, 21.0, 1.8, KATORI,
     ["paneer makhani"]),
    ("Palak paneer", "indian_north", "curry", 190, 9.0, 7.5, 14.0, 2.8, KATORI, []),
    ("Butter chicken", "indian_north", "curry", 240, 14.0, 8.0, 17.0, 1.2, KATORI,
     ["murgh makhani"]),
    ("Chicken curry (home-style)", "indian_north", "curry", 175, 15.0, 5.5, 10.5, 1.0,
     KATORI, ["chicken masala"]),
    ("Mutton rogan josh", "indian_north", "curry", 225, 16.0, 5.0, 16.0, 0.9, KATORI, []),
    ("Aloo gobi", "indian_north", "sabzi", 120, 3.0, 15.0, 5.5, 3.5, KATORI, []),
    ("Bhindi masala", "indian_north", "sabzi", 115, 2.5, 10.0, 7.5, 4.0, KATORI,
     ["okra sabzi"]),
    ("Baingan bharta", "indian_north", "sabzi", 105, 2.2, 9.0, 6.8, 3.8, KATORI, []),
    ("Chapati (whole wheat)", "indian_north", "bread", 275, 9.0, 52.0, 3.5, 8.0,
     [("1 chapati", 40, True), ("100 g", 100, False)], ["roti", "phulka"]),
    ("Paratha (plain)", "indian_north", "bread", 330, 8.0, 45.0, 13.5, 5.5,
     [("1 paratha", 65, True), ("100 g", 100, False)], []),
    ("Aloo paratha", "indian_north", "bread", 285, 6.5, 42.0, 10.5, 4.5,
     [("1 paratha", 110, True), ("100 g", 100, False)], []),
    ("Naan", "indian_north", "bread", 310, 9.0, 52.0, 7.5, 2.5,
     [("1 naan", 90, True), ("100 g", 100, False)], []),
    ("Jeera rice", "indian_north", "rice", 165, 3.2, 30.0, 3.8, 1.0, KATORI, []),
    ("Chicken biryani", "indian_north", "rice", 195, 9.5, 24.0, 7.0, 1.4, PLATE,
     ["biriyani", "biryani"]),
    ("Veg pulao", "indian_north", "rice", 155, 3.5, 27.0, 3.8, 1.8, PLATE, []),
    ("Raita (cucumber)", "indian_north", "side", 60, 3.0, 5.0, 3.0, 0.5, KATORI, []),
    ("Tandoori chicken", "indian_north", "grill", 165, 25.0, 2.5, 6.5, 0.3,
     [("1 leg piece", 120, True), ("100 g", 100, False)], []),
    ("Paneer tikka", "indian_north", "grill", 270, 15.0, 6.0, 21.0, 1.0,
     [("4 pieces", 120, True), ("100 g", 100, False)], ["panner tikka"]),

    # ---------------- South Indian ----------------
    ("Idli", "indian_south", "breakfast", 130, 4.0, 26.0, 0.5, 1.2,
     [("1 idli", 35, True), ("2 idli", 70, False), ("100 g", 100, False)], []),
    ("Plain dosa", "indian_south", "breakfast", 195, 4.5, 30.0, 6.0, 1.5,
     [("1 dosa", 85, True), ("100 g", 100, False)], ["dosai", "dose"]),
    ("Masala dosa", "indian_south", "breakfast", 185, 4.0, 28.0, 6.5, 2.2,
     [("1 dosa", 150, True), ("100 g", 100, False)], []),
    ("Medu vada", "indian_south", "breakfast", 290, 7.5, 30.0, 15.5, 3.5,
     [("1 vada", 45, True), ("100 g", 100, False)], ["urad vada"]),
    ("Upma", "indian_south", "breakfast", 145, 3.5, 22.0, 5.0, 1.8, KATORI, []),
    ("Pongal", "indian_south", "breakfast", 165, 4.5, 24.0, 6.0, 1.5, KATORI, []),
    ("Sambar", "indian_south", "dal", 85, 3.5, 11.0, 3.0, 3.0, KATORI, []),
    ("Rasam", "indian_south", "soup", 40, 1.2, 5.5, 1.5, 1.0, KATORI, []),
    ("Coconut chutney", "indian_south", "side", 195, 3.0, 7.0, 17.0, 4.5,
     [("1 tbsp", 20, True), ("100 g", 100, False)], []),
    ("Curd rice", "indian_south", "rice", 115, 3.5, 18.0, 3.0, 0.6, KATORI,
     ["thayir sadam"]),
    ("Uttapam", "indian_south", "breakfast", 175, 4.5, 28.0, 5.0, 2.0,
     [("1 uttapam", 120, True), ("100 g", 100, False)], []),

    # ---------------- Indian street food ----------------
    ("Pani puri", "indian_street", "snack", 210, 4.0, 32.0, 7.0, 3.0,
     [("6 pieces", 90, True), ("100 g", 100, False)], ["golgappa", "puchka"]),
    ("Vada pav", "indian_street", "snack", 285, 6.5, 38.0, 12.0, 3.2,
     [("1 vada pav", 130, True), ("100 g", 100, False)], []),
    ("Pav bhaji", "indian_street", "snack", 165, 3.8, 20.0, 8.0, 3.5, PLATE, []),
    ("Samosa", "indian_street", "snack", 305, 5.0, 34.0, 16.5, 3.0,
     [("1 samosa", 60, True), ("100 g", 100, False)], []),
    ("Bhel puri", "indian_street", "snack", 220, 5.0, 38.0, 5.5, 3.5, BOWL, []),
    ("Chicken kathi roll", "indian_street", "snack", 225, 11.0, 25.0, 9.0, 2.0,
     [("1 roll", 180, True), ("100 g", 100, False)], ["frankie"]),
    ("Momos (steamed, veg)", "indian_street", "snack", 165, 5.0, 26.0, 4.5, 2.0,
     [("6 pieces", 150, True), ("100 g", 100, False)], ["dumpling"]),

    # ---------------- Indian sweets / drinks ----------------
    ("Gulab jamun", "indian_sweet", "dessert", 340, 4.5, 48.0, 14.5, 0.5,
     [("1 piece", 40, True), ("100 g", 100, False)], []),
    ("Masala chai (with sugar)", "indian_drink", "beverage", 65, 1.8, 9.0, 2.2, 0.0,
     [("1 cup", 150, True), ("100 ml", 100, False)], ["chai", "tea"]),
    ("Mango lassi", "indian_drink", "beverage", 105, 2.8, 18.0, 2.5, 0.4, GLASS, []),
    ("Filter coffee (with milk & sugar)", "indian_drink", "beverage", 70, 2.0, 10.0,
     2.4, 0.0, [("1 cup", 120, True), ("100 ml", 100, False)], []),

    # ---------------- Chinese / East Asian ----------------
    ("Chicken fried rice", "chinese", "rice", 175, 8.0, 24.0, 5.5, 1.2, PLATE, []),
    ("Hakka noodles (veg)", "chinese", "noodles", 190, 5.0, 28.0, 6.5, 2.4, PLATE,
     ["chow mein", "chowmein"]),
    ("Kung pao chicken", "chinese", "curry", 185, 15.0, 9.0, 10.5, 1.5, KATORI, []),
    ("Mapo tofu", "chinese", "curry", 150, 9.5, 6.0, 10.0, 1.2, KATORI, []),
    ("Pork dumplings (steamed)", "chinese", "snack", 210, 9.0, 24.0, 8.5, 1.2,
     [("6 pieces", 150, True), ("100 g", 100, False)], ["jiaozi", "gyoza"]),
    ("Ramen (tonkotsu)", "japanese", "noodles", 130, 6.5, 15.0, 4.8, 1.0,
     [("1 bowl", 500, True), ("100 g", 100, False)], []),
    ("Salmon nigiri", "japanese", "sushi", 145, 8.0, 20.0, 3.2, 0.3,
     [("2 pieces", 80, True), ("100 g", 100, False)], []),
    ("Chicken katsu curry", "japanese", "curry", 195, 10.0, 22.0, 7.5, 1.5, PLATE, []),
    ("Bibimbap", "korean", "rice", 145, 6.5, 19.0, 5.0, 2.2, BOWL, []),
    ("Korean fried chicken", "korean", "grill", 265, 17.0, 18.0, 14.0, 0.6,
     [("4 pieces", 160, True), ("100 g", 100, False)], []),
    ("Pad thai", "thai", "noodles", 180, 7.5, 26.0, 5.5, 1.8, PLATE, []),
    ("Green curry with chicken", "thai", "curry", 130, 9.0, 5.5, 8.5, 1.4, KATORI, []),
    ("Pho bo", "vietnamese", "noodles", 75, 5.5, 9.5, 1.6, 0.6,
     [("1 bowl", 500, True), ("100 g", 100, False)], []),
    ("Banh mi", "vietnamese", "sandwich", 235, 10.0, 30.0, 8.5, 1.8,
     [("1 sandwich", 220, True), ("100 g", 100, False)], []),
    ("Nasi goreng", "indonesian", "rice", 170, 6.0, 25.0, 5.0, 1.2, PLATE, []),

    # ---------------- Middle Eastern / Mediterranean ----------------
    ("Chicken shawarma", "middle_eastern", "grill", 195, 17.0, 8.0, 11.0, 1.0,
     [("1 wrap", 250, True), ("100 g", 100, False)], []),
    ("Falafel", "middle_eastern", "snack", 330, 13.0, 32.0, 17.0, 5.0,
     [("4 pieces", 80, True), ("100 g", 100, False)], []),
    ("Hummus", "middle_eastern", "dip", 175, 7.5, 15.0, 10.0, 6.0,
     [("2 tbsp", 30, True), ("100 g", 100, False)], []),
    ("Greek salad", "mediterranean", "salad", 105, 3.5, 6.0, 7.5, 2.0, BOWL, []),
    ("Chicken souvlaki", "mediterranean", "grill", 175, 22.0, 3.0, 8.0, 0.4,
     [("2 skewers", 150, True), ("100 g", 100, False)], []),
    ("Tabbouleh", "middle_eastern", "salad", 120, 3.0, 15.0, 5.5, 3.5, BOWL, []),

    # ---------------- Italian / European ----------------
    ("Spaghetti bolognese", "italian", "pasta", 155, 8.0, 19.0, 5.0, 1.8, PLATE, []),
    ("Margherita pizza", "italian", "pizza", 265, 11.0, 33.0, 9.5, 2.2,
     [("1 slice", 110, True), ("100 g", 100, False)], []),
    ("Penne arrabbiata", "italian", "pasta", 145, 4.8, 25.0, 3.0, 2.2, PLATE, []),
    ("Chicken alfredo", "italian", "pasta", 215, 11.0, 20.0, 10.5, 1.2, PLATE, []),
    ("Risotto ai funghi", "italian", "rice", 145, 4.0, 22.0, 4.5, 1.0, PLATE, []),
    ("Paella (seafood)", "spanish", "rice", 155, 9.0, 20.0, 4.5, 1.0, PLATE, []),
    ("Croissant", "french", "bakery", 405, 8.0, 46.0, 21.0, 2.5,
     [("1 croissant", 60, True), ("100 g", 100, False)], []),
    ("Full English breakfast", "british", "breakfast", 210, 11.0, 12.0, 13.5, 2.0,
     PLATE, []),

    # ---------------- Latin American ----------------
    ("Chicken burrito", "mexican", "wrap", 195, 10.0, 24.0, 6.5, 3.0,
     [("1 burrito", 350, True), ("100 g", 100, False)], []),
    ("Beef taco", "mexican", "snack", 215, 11.0, 20.0, 10.0, 2.5,
     [("1 taco", 90, True), ("100 g", 100, False)], []),
    ("Guacamole", "mexican", "dip", 155, 2.0, 9.0, 13.5, 6.5,
     [("2 tbsp", 30, True), ("100 g", 100, False)], []),
    ("Chicken quesadilla", "mexican", "snack", 285, 15.0, 24.0, 15.0, 1.8,
     [("1 quesadilla", 180, True), ("100 g", 100, False)], []),
    ("Feijoada", "brazilian", "stew", 165, 11.0, 13.0, 7.5, 4.5, KATORI, []),
    ("Ceviche", "peruvian", "seafood", 90, 15.0, 4.5, 1.5, 0.5, BOWL, []),

    # ---------------- American / global staples ----------------
    ("Cheeseburger", "american", "burger", 260, 14.0, 22.0, 13.0, 1.2,
     [("1 burger", 200, True), ("100 g", 100, False)], []),
    ("Grilled chicken breast", "american", "protein", 165, 31.0, 0.0, 3.6, 0.0,
     [("1 breast", 170, True), ("100 g", 100, False)], []),
    ("Scrambled eggs", "american", "breakfast", 150, 10.0, 1.6, 11.0, 0.0,
     [("2 eggs", 110, True), ("100 g", 100, False)], []),
    ("Oatmeal (cooked, water)", "american", "breakfast", 70, 2.5, 12.0, 1.5, 1.8, BOWL,
     ["porridge", "oats"]),
    ("Greek yoghurt (plain, 2%)", "american", "dairy", 73, 10.0, 4.0, 1.9, 0.0, CUP, []),
    ("Whey protein shake (1 scoop, water)", "supplement", "protein", 400, 80.0, 8.0,
     6.0, 1.0, [("1 scoop", 30, True), ("100 g", 100, False)], ["protein shake"]),
    ("Caesar salad with chicken", "american", "salad", 145, 11.0, 5.0, 9.5, 1.6,
     BOWL, []),
    ("French fries", "american", "side", 310, 3.5, 41.0, 15.0, 3.8,
     [("medium portion", 115, True), ("100 g", 100, False)], ["chips"]),
    ("White rice (cooked)", "global", "rice", 130, 2.7, 28.0, 0.3, 0.4, KATORI, []),
    ("Brown rice (cooked)", "global", "rice", 112, 2.6, 24.0, 0.9, 1.8, KATORI, []),
    ("Banana", "global", "fruit", 89, 1.1, 23.0, 0.3, 2.6,
     [("1 medium", 118, True), ("100 g", 100, False)], []),
    ("Apple", "global", "fruit", 52, 0.3, 14.0, 0.2, 2.4,
     [("1 medium", 180, True), ("100 g", 100, False)], []),
    ("Almonds", "global", "nuts", 579, 21.0, 22.0, 50.0, 12.5,
     [("1 handful", 28, True), ("100 g", 100, False)], ["badam"]),
    ("Peanut butter", "global", "spread", 588, 25.0, 20.0, 50.0, 6.0,
     [("1 tbsp", 16, True), ("100 g", 100, False)], []),
    ("Olive oil", "global", "fat", 884, 0.0, 0.0, 100.0, 0.0,
     [("1 tbsp", 14, True), ("1 tsp", 5, False), ("100 g", 100, False)], []),
    ("Ghee", "global", "fat", 900, 0.0, 0.0, 100.0, 0.0,
     [("1 tbsp", 14, True), ("1 tsp", 5, False), ("100 g", 100, False)], ["clarified butter"]),
]


# Regional Indian coverage lives in its own module -- it is long, it is the
# project's actual differentiator, and keeping it separate means a change to
# the global core can't accidentally clobber it. Appended rather than merged so
# a duplicate name is caught by uq_food_source at write time.
try:
    from .data.indian_regional import INDIAN_REGIONAL

    DISHES = DISHES + INDIAN_REGIONAL
except ImportError:  # pragma: no cover - the file is optional
    pass

try:
    from .data.world_regional import WORLD_REGIONAL

    DISHES = DISHES + WORLD_REGIONAL
except ImportError:  # pragma: no cover - the file is optional
    pass


def _servings(rows: list[Serving]) -> list[dict]:
    return [{"name": n, "grams": g, "is_default": d} for n, g, d in rows]


async def run(cuisine_filter: str | None) -> None:
    await init_db()
    now = datetime.now(timezone.utc)
    payload = []

    for (
        name,
        cuisine,
        category,
        kcal,
        protein,
        carbs,
        fat,
        fiber,
        servings,
        aliases,
    ) in DISHES:
        if cuisine_filter and cuisine != cuisine_filter:
            continue
        search = " ".join([name, cuisine.replace("_", " "), category, *aliases]).lower()
        payload.append(
            {
                "source": FoodSource.curated.value,
                "source_id": f"curated:{name.lower().replace(' ', '_')}",
                "name": name,
                "calories": float(kcal),
                "protein_g": float(protein),
                "carbs_g": float(carbs),
                "fat_g": float(fat),
                "fiber_g": float(fiber),
                "serving_sizes": _servings(servings),
                "cuisine": cuisine,
                "category": category,
                "names_i18n": {"aliases": aliases},
                "is_liquid": category == "beverage",
                # Curated + cross-checked against composition tables: high trust.
                "data_quality": 0.85,
                "is_verified": True,
                "search_text": search,
                "updated_at": now,
            }
        )

    # Defensive de-duplication. Postgres refuses an ON CONFLICT DO UPDATE that
    # would touch the same row twice in one statement, so two entries sharing a
    # name anywhere across the merged lists would abort the whole seed. First
    # occurrence wins, which keeps the global core authoritative over any
    # regional file that re-states the same dish.
    seen: set[str] = set()
    unique = []
    for row in payload:
        if row["source_id"] in seen:
            log.warning("duplicate dish skipped: %s", row["name"])
            continue
        seen.add(row["source_id"])
        unique.append(row)
    payload = unique

    async with SessionLocal() as session:
        stmt = pg_insert(FoodItem).values(payload)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_food_source",
            set_={
                "calories": stmt.excluded.calories,
                "protein_g": stmt.excluded.protein_g,
                "carbs_g": stmt.excluded.carbs_g,
                "fat_g": stmt.excluded.fat_g,
                "fiber_g": stmt.excluded.fiber_g,
                "serving_sizes": stmt.excluded.serving_sizes,
                "search_text": stmt.excluded.search_text,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)
        await session.commit()

    log.info("Seeded %d dishes", len(payload))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cuisine", default=None)
    args = p.parse_args()
    asyncio.run(run(args.cuisine))


if __name__ == "__main__":
    main()
