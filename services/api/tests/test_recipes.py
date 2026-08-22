"""Recipe composition. The yield class is the one that matters."""

import pytest

from app.services import recipes
from app.services.recipes import Ingredient, Panel, YieldUnknown

# Real per-100 g panels, so the arithmetic below is checkable by hand.
RICE = Panel(calories=130, protein_g=2.7, carbs_g=28.2, fat_g=0.3, fiber_g=0.4)
CHICKEN = Panel(calories=165, protein_g=31.0, carbs_g=0.0, fat_g=3.6)
OIL = Panel(calories=884, protein_g=0.0, carbs_g=0.0, fat_g=100.0)
DAL = Panel(calories=116, protein_g=9.0, carbs_g=20.0, fat_g=0.4, fiber_g=8.0)
WATER = Panel()


def ing(name, grams, panel, sourced=True):
    return Ingredient(
        name=name,
        grams=grams,
        per_100g=panel,
        food_item_id=f"food-{name}" if sourced else None,
    )


class TestComposition:
    def test_sums_the_ingredients(self):
        c = recipes.compose([ing("rice", 100, RICE), ing("chicken", 100, CHICKEN)])
        assert c.total.calories == pytest.approx(295)
        assert c.total.protein_g == pytest.approx(33.7)

    def test_scales_each_ingredient_by_its_own_weight(self):
        c = recipes.compose([ing("chicken", 250, CHICKEN)])
        assert c.total.calories == pytest.approx(412.5)
        assert c.total.protein_g == pytest.approx(77.5)

    def test_per_serving_divides_the_total(self):
        c = recipes.compose([ing("chicken", 400, CHICKEN)], servings=4)
        assert c.per_serving.calories == pytest.approx(165)
        assert c.per_serving.protein_g == pytest.approx(31.0)

    def test_zero_weight_lines_are_ignored(self):
        c = recipes.compose([ing("rice", 100, RICE), ing("salt", 0, Panel())])
        assert c.ingredient_grams == 100

    def test_an_empty_recipe_does_not_divide_by_zero(self):
        c = recipes.compose([], servings=4)
        assert c.total.calories == 0
        assert c.per_100g is None
        assert "at least one ingredient" in c.warnings[0]

    def test_ingredient_weight_is_the_raw_sum(self):
        c = recipes.compose([ing("dal", 250, DAL), ing("water", 700, WATER)])
        assert c.ingredient_grams == 950

    def test_water_adds_weight_but_no_calories(self):
        dry = recipes.compose([ing("dal", 250, DAL)])
        wet = recipes.compose([ing("dal", 250, DAL), ing("water", 700, WATER)])
        assert wet.total.calories == dry.total.calories


class TestYield:
    """THE CLASS THAT PROTECTS EVERY RECIPE CALORIE IN THE APP.

    A recipe is entered raw and eaten cooked. Dividing the total by the RAW
    ingredient weight produces a per-100 g panel that understates every dish
    that lost water on the hob -- and a dal loses a lot.

    If you are here because this failed: someone has started deriving per-100 g
    from the ingredient sum. Every gram-logged portion of a simmered recipe
    just got cheaper than the food actually is.
    """

    def test_no_cooked_weight_means_no_per_100g(self):
        c = recipes.compose([ing("dal", 250, DAL), ing("water", 700, WATER)])
        assert c.yield_estimated is True
        assert c.per_100g is None

    def test_a_measured_weight_unlocks_per_100g(self):
        c = recipes.compose(
            [ing("dal", 250, DAL), ing("water", 700, WATER)], cooked_weight_g=800
        )
        assert c.yield_estimated is False
        # 250 g dal = 290 kcal, in 800 g finished = 36.25 kcal/100 g
        assert c.per_100g.calories == pytest.approx(36.3, abs=0.1)

    def test_the_raw_sum_would_have_understated_it(self):
        # The bug this class exists to prevent, stated as arithmetic:
        # 290 kcal / 950 g raw = 30.5, versus 36.3 truth. A 16% under-report.
        ings = [ing("dal", 250, DAL), ing("water", 700, WATER)]
        honest = recipes.compose(ings, cooked_weight_g=800).per_100g.calories
        naive = recipes.compose(ings).total.calories / 950 * 100
        assert naive < honest
        assert (honest - naive) / honest > 0.15

    def test_per_serving_is_unaffected_by_the_unknown_weight(self):
        # Calories do not evaporate, so servings stay exact either way.
        ings = [ing("dal", 250, DAL), ing("water", 700, WATER)]
        a = recipes.compose(ings, servings=4)
        b = recipes.compose(ings, servings=4, cooked_weight_g=800)
        assert a.per_serving.calories == b.per_serving.calories

    def test_serving_grams_only_exists_when_the_weight_is_known(self):
        ings = [ing("dal", 250, DAL), ing("water", 700, WATER)]
        assert recipes.compose(ings, servings=4).serving_grams is None
        assert recipes.compose(ings, servings=4, cooked_weight_g=800).serving_grams == 200

    def test_warns_when_the_finished_dish_is_heavier_than_its_ingredients(self):
        c = recipes.compose([ing("rice", 100, RICE)], cooked_weight_g=300)
        assert any("more than the ingredients" in w for w in c.warnings)

    def test_warns_on_implausible_reduction(self):
        c = recipes.compose([ing("rice", 1000, RICE)], cooked_weight_g=100)
        assert any("reduction" in w for w in c.warnings)

    def test_a_normal_cooking_loss_is_not_warned_about(self):
        c = recipes.compose([ing("rice", 100, RICE)], cooked_weight_g=85)
        assert c.warnings == []


class TestPortion:
    def test_one_serving_is_the_default(self):
        c = recipes.compose([ing("chicken", 400, CHICKEN)], servings=4)
        panel, grams, label = recipes.portion(c)
        assert panel.calories == pytest.approx(165)
        assert label == "1 serving"

    def test_multiple_servings_scale(self):
        c = recipes.compose([ing("chicken", 400, CHICKEN)], servings=4)
        panel, _, label = recipes.portion(c, servings=2)
        assert panel.calories == pytest.approx(330)
        assert label == "2 servings"

    def test_half_a_serving(self):
        c = recipes.compose([ing("chicken", 400, CHICKEN)], servings=4)
        panel, _, label = recipes.portion(c, servings=0.5)
        assert panel.calories == pytest.approx(82.5)
        assert label == "0.5 servings"

    def test_a_serving_carries_its_gram_weight_when_known(self):
        c = recipes.compose(
            [ing("dal", 250, DAL), ing("water", 700, WATER)],
            servings=4,
            cooked_weight_g=800,
        )
        _, grams, _ = recipes.portion(c, servings=2)
        assert grams == 400

    def test_grams_work_when_the_weight_was_measured(self):
        c = recipes.compose(
            [ing("dal", 250, DAL), ing("water", 700, WATER)], cooked_weight_g=800
        )
        panel, grams, label = recipes.portion(c, grams=200)
        assert panel.calories == pytest.approx(72.6, abs=0.2)
        assert label == "200 g"

    def test_grams_are_refused_when_the_weight_is_a_guess(self):
        c = recipes.compose([ing("dal", 250, DAL), ing("water", 700, WATER)])
        with pytest.raises(YieldUnknown):
            recipes.portion(c, grams=200)

    def test_the_refusal_says_what_to_do_instead(self):
        c = recipes.compose([ing("dal", 250, DAL)])
        with pytest.raises(YieldUnknown, match="by serving"):
            recipes.portion(c, grams=100)

    def test_servings_win_when_both_are_given(self):
        # Servings is exact; grams is derived. Never resolve the ambiguity in
        # favour of the rougher unit.
        c = recipes.compose([ing("chicken", 400, CHICKEN)], servings=4, cooked_weight_g=320)
        panel, _, label = recipes.portion(c, servings=1, grams=999)
        assert label == "1 serving"
        assert panel.calories == pytest.approx(165)

    def test_portions_of_a_whole_recipe_add_back_up(self):
        c = recipes.compose([ing("chicken", 400, CHICKEN)], servings=4)
        one = recipes.portion(c, servings=1)[0].calories
        assert one * 4 == pytest.approx(c.total.calories, abs=0.5)


class TestPublishGate:
    def two_ingredient(self, **kw):
        return recipes.compose(
            [ing("rice", 200, RICE), ing("chicken", 200, CHICKEN)], **kw
        )

    def test_a_reasonable_recipe_publishes(self):
        c = self.two_ingredient(servings=2, cooked_weight_g=350)
        check = recipes.publish_check(
            "Chicken rice bowl",
            [ing("rice", 200, RICE), ing("chicken", 200, CHICKEN)],
            c,
            steps=["Cook rice", "Grill chicken"],
        )
        assert check.ok is True
        assert check.blockers == []

    def test_one_ingredient_is_a_food_not_a_recipe(self):
        ings = [ing("chicken", 200, CHICKEN)]
        check = recipes.publish_check("Chicken", ings, recipes.compose(ings))
        assert check.ok is False
        assert any("custom food" in b for b in check.blockers)

    def test_an_unnamed_recipe_is_refused(self):
        ings = [ing("rice", 200, RICE), ing("chicken", 200, CHICKEN)]
        check = recipes.publish_check("x", ings, recipes.compose(ings))
        assert check.ok is False
        assert any("name" in b for b in check.blockers)

    def test_zero_calorie_recipes_are_refused(self):
        ings = [ing("water", 500, WATER), ing("ice", 200, WATER)]
        check = recipes.publish_check("Water", ings, recipes.compose(ings))
        assert check.ok is False

    def test_impossible_macros_are_refused(self):
        liar = Panel(calories=100, protein_g=50, carbs_g=50, fat_g=50)
        ings = [ing("a", 100, liar), ing("b", 100, liar)]
        check = recipes.publish_check("Mystery loaf", ings, recipes.compose(ings))
        assert check.ok is False
        assert any("kcal" in b for b in check.blockers)

    def test_a_missing_finished_weight_is_a_caution_not_a_blocker(self):
        # Publishing without it is fine -- others just log by serving.
        ings = [ing("rice", 200, RICE), ing("chicken", 200, CHICKEN)]
        check = recipes.publish_check("Chicken rice", ings, recipes.compose(ings))
        assert check.ok is True
        assert any("finished weight" in c for c in check.cautions)

    def test_a_fried_recipe_with_no_fat_is_flagged(self):
        ings = [ing("potato", 300, RICE), ing("gram flour", 100, DAL)]
        c = recipes.compose(ings, cooked_weight_g=350)
        check = recipes.publish_check("Onion pakora", ings, c)
        assert any("fried" in x for x in check.cautions)

    def test_a_fried_recipe_that_accounts_for_the_oil_is_not_flagged(self):
        ings = [ing("potato", 300, RICE), ing("oil", 40, OIL)]
        c = recipes.compose(ings, cooked_weight_g=320)
        check = recipes.publish_check("Pakora", ings, c)
        assert not any("fried" in x for x in check.cautions)

    def test_mostly_hand_entered_recipes_are_flagged(self):
        ings = [
            ing("rice", 200, RICE, sourced=False),
            ing("chicken", 200, CHICKEN, sourced=False),
        ]
        check = recipes.publish_check("Guesswork bowl", ings, recipes.compose(ings))
        assert any("hand-entered" in c for c in check.cautions)

    def test_cautions_never_block(self):
        ings = [ing("rice", 200, RICE, sourced=False), ing("chicken", 200, CHICKEN, sourced=False)]
        check = recipes.publish_check("Guesswork bowl", ings, recipes.compose(ings))
        assert check.ok is True

    def test_a_private_recipe_is_never_gated(self):
        # There is no private_check(). The gate exists only on publish, on
        # purpose: a note to yourself is nobody's business.
        assert not hasattr(recipes, "private_check")


class TestSourcedFraction:
    def test_all_catalogue_is_one(self):
        c = recipes.compose([ing("rice", 200, RICE), ing("chicken", 200, CHICKEN)])
        assert c.sourced_fraction == 1.0

    def test_all_freehand_is_zero(self):
        c = recipes.compose([ing("rice", 200, RICE, sourced=False)])
        assert c.sourced_fraction == 0.0

    def test_it_is_weighted_by_calories_not_line_count(self):
        # One freehand line carrying most of the calories should dominate a
        # dozen sourced garnishes -- counting lines would hide that.
        c = recipes.compose(
            [ing("oil", 100, OIL, sourced=False), ing("rice", 10, RICE)]
        )
        assert c.sourced_fraction < 0.05

    def test_zero_calorie_recipes_do_not_divide_by_zero(self):
        c = recipes.compose([ing("water", 500, WATER, sourced=False)])
        assert c.sourced_fraction == 1.0


class TestRescale:
    def test_doubling_doubles_every_ingredient(self):
        out = recipes.rescale([ing("rice", 200, RICE), ing("chicken", 150, CHICKEN)], 2, 4)
        assert [i.grams for i in out] == [400, 300]

    def test_halving_halves(self):
        out = recipes.rescale([ing("rice", 200, RICE)], 4, 2)
        assert out[0].grams == 100

    def test_it_keeps_the_nutrition_panels_intact(self):
        out = recipes.rescale([ing("rice", 200, RICE)], 2, 4)
        assert out[0].per_100g == RICE

    def test_a_zero_serving_count_is_a_no_op_rather_than_a_crash(self):
        ings = [ing("rice", 200, RICE)]
        assert recipes.rescale(ings, 0, 4)[0].grams == 200

    def test_rescaling_preserves_calories_per_serving(self):
        ings = [ing("chicken", 400, CHICKEN)]
        before = recipes.compose(ings, servings=4).per_serving.calories
        after = recipes.compose(recipes.rescale(ings, 4, 8), servings=8).per_serving.calories
        assert before == pytest.approx(after)


class TestSuggestServings:
    def test_a_main_meal_is_one_serving(self):
        assert recipes.suggest_servings(480) == 1

    def test_a_family_pot_is_several(self):
        assert recipes.suggest_servings(2400) == 5

    def test_never_zero(self):
        assert recipes.suggest_servings(0) == 1

    def test_capped_so_the_field_stays_sane(self):
        assert recipes.suggest_servings(999_999) == 20
