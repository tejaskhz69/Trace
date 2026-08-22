"""The four bets from the nutrition-v2 mockup. These are the spec.

Each class ends with the invariant that makes the feature honest rather than
merely impressive — quadrature over naive summing, no debt across weeks, a
refusal when there is no contrast, and a macro shift that cannot add calories.
"""

from datetime import date, datetime, timedelta

import pytest

from app.services import fuel_link, protein_coach, uncertainty, week_budget
from app.services.fuel_link import LinkVerdict, Session
from app.services.protein_coach import MealProtein
from app.services.uncertainty import LoggedItem, Source

MON = date(2026, 8, 17)
FRI = date(2026, 8, 21)


# ===========================================================================
# BET 1 — uncertainty
# ===========================================================================
class TestDayUncertainty:
    def _day(self):
        return [
            LoggedItem("Idli, sambar", 386, Source.label, 374, 398),
            LoggedItem("Puttu, kadala curry", 462, Source.scan, 433, 491),
            LoggedItem("Whey, banana", 268, Source.label, 262, 274),
            LoggedItem("Mess dinner", 380, Source.quick_add, 296, 464),
        ]

    def test_empty_day(self):
        r = uncertainty.day_uncertainty([])
        assert r.total_kcal == 0
        assert r.band == 0

    def test_total_is_the_plain_sum(self):
        r = uncertainty.day_uncertainty(self._day())
        assert r.total_kcal == pytest.approx(1496)

    def test_band_is_quadrature_not_a_sum(self):
        r = uncertainty.day_uncertainty(self._day())
        naive = 12 + 29 + 6 + 84
        # sqrt(12² + 29² + 6² + 84²) ≈ 89.5
        assert r.band == pytest.approx(89.5, abs=1.0)
        assert r.band < naive
        # Four items each wrong in the same direction at once is not a thing.
        assert r.band < naive * 0.75

    def test_one_bad_item_dominates(self):
        # This is the whole argument for the certainty strip.
        r = uncertainty.day_uncertainty(self._day())
        assert r.worst_item == "Mess dinner"
        assert r.worst_item_band == pytest.approx(84, abs=1)

    def test_low_and_high_bracket_the_total(self):
        r = uncertainty.day_uncertainty(self._day())
        assert r.low < r.total_kcal < r.high
        assert r.high - r.total_kcal == pytest.approx(r.band, abs=0.2)

    def test_low_never_goes_negative(self):
        r = uncertainty.day_uncertainty(
            [LoggedItem("Tiny", 10, Source.quick_add, 0, 200)]
        )
        assert r.low >= 0

    def test_uses_an_explicit_band_over_the_default(self):
        tight = uncertainty.day_uncertainty(
            [LoggedItem("X", 500, Source.quick_add, 495, 505)]
        )
        loose = uncertainty.day_uncertainty([LoggedItem("X", 500, Source.quick_add)])
        assert tight.band < loose.band

    def test_uses_the_wider_side_of_a_skewed_band(self):
        # Collapsing a skewed band to its mean would quietly narrow it.
        r = uncertainty.day_uncertainty(
            [LoggedItem("X", 100, Source.scan, 95, 160)]
        )
        assert r.band == pytest.approx(60, abs=0.5)

    def test_all_barcode_day_is_high_confidence(self):
        items = [LoggedItem(f"P{i}", 400, Source.label) for i in range(4)]
        assert uncertainty.day_uncertainty(items).confidence == "high"

    def test_all_quick_add_day_is_low_confidence(self):
        items = [LoggedItem(f"P{i}", 400, Source.quick_add) for i in range(4)]
        assert uncertainty.day_uncertainty(items).confidence == "low"

    def test_mix_shares_sum_to_one(self):
        r = uncertainty.day_uncertainty(self._day())
        assert sum(m.share for m in r.mix) == pytest.approx(1.0, abs=0.01)
        assert sum(m.uncertainty_share for m in r.mix) == pytest.approx(1.0, abs=0.01)

    def test_mix_leads_with_the_widest_contributor(self):
        r = uncertainty.day_uncertainty(self._day())
        assert r.mix[0].source == "quick_add"

    def test_advice_names_the_item_and_the_payoff(self):
        r = uncertainty.day_uncertainty(self._day())
        assert r.advice is not None
        assert "Mess dinner" in r.advice

    def test_no_advice_when_fixing_it_would_not_help(self):
        # Five identical items: no single one is worth singling out.
        items = [LoggedItem(f"P{i}", 400, Source.scan) for i in range(5)]
        assert uncertainty.day_uncertainty(items).advice is None


class TestSourceClassification:
    def test_barcode_beats_a_prior_scan(self):
        # A scan the user corrected against a barcode IS a label now.
        s = uncertainty.classify_source(
            recognition_id="r1", food_item_id="f1", has_barcode=True
        )
        assert s is Source.label

    def test_scan_when_there_is_no_food_row(self):
        s = uncertainty.classify_source(
            recognition_id="r1", food_item_id=None, has_barcode=False
        )
        assert s is Source.scan

    def test_search_when_matched_but_unbarcoded(self):
        s = uncertainty.classify_source(
            recognition_id=None, food_item_id="f1", has_barcode=False
        )
        assert s is Source.search

    def test_quick_add_when_nothing_backs_it(self):
        s = uncertainty.classify_source(
            recognition_id=None, food_item_id=None, has_barcode=False
        )
        assert s is Source.quick_add


# ===========================================================================
# BET 2 — the weekly budget
# ===========================================================================
class TestWeekBudget:
    def test_week_starts_monday(self):
        start, end = week_budget.week_bounds(FRI)
        assert start == MON
        assert (end - start).days == 6

    def test_week_target_is_seven_days(self):
        w = week_budget.build_week(MON, 2700, {})
        assert w.week_target == pytest.approx(18900)

    def test_spent_and_remaining_track_logged_days(self):
        logged = {MON: 2500, MON + timedelta(days=1): 2900}
        w = week_budget.build_week(MON + timedelta(days=2), 2700, logged)
        assert w.spent == pytest.approx(5400)
        assert w.remaining == pytest.approx(13500)

    def test_per_day_spreads_what_is_left(self):
        logged = {MON: 2290}  # 410 under
        w = week_budget.build_week(MON + timedelta(days=1), 2700, logged)
        assert w.days_left == 6
        assert w.per_day_remaining == pytest.approx(2768, abs=2)

    def test_a_light_day_raises_the_rest(self):
        light = week_budget.build_week(
            MON + timedelta(days=1), 2700, {MON: 2000}
        )
        assert light.per_day_remaining > 2700

    def test_flagging_a_day_moves_calories_into_it(self):
        sat = MON + timedelta(days=5)
        w = week_budget.build_week(MON, 2700, {}, flagged_days={sat})
        satday = next(d for d in w.days if d.day == sat)
        assert satday.shift > 0
        assert satday.planned_kcal > 2700

    def test_the_donors_pay_for_it(self):
        sat = MON + timedelta(days=5)
        w = week_budget.build_week(MON, 2700, {}, flagged_days={sat})
        donors = [d for d in w.days if not d.flagged and not d.is_past]
        assert all(d.planned_kcal < 2700 for d in donors)

    def test_redistribution_is_conservation_not_creation(self):
        sat = MON + timedelta(days=5)
        w = week_budget.build_week(MON, 2700, {}, flagged_days={sat})
        planned = sum(d.planned_kcal for d in w.days)
        assert planned == pytest.approx(w.week_target, abs=1.0)

    def test_no_single_day_is_stripped_too_far(self):
        sat = MON + timedelta(days=5)
        w = week_budget.build_week(MON, 2700, {}, flagged_days={sat})
        floor = 2700 * (1 - week_budget.MAX_DAILY_SHIFT_PCT)
        assert all(d.planned_kcal >= floor - 1 for d in w.days)

    def test_past_days_are_never_rewritten(self):
        # Retroactively changing what Tuesday "should" have been makes every
        # number the user already saw wrong.
        thu = MON + timedelta(days=3)
        w = week_budget.build_week(thu, 2700, {}, flagged_days={MON})
        monday = next(d for d in w.days if d.day == MON)
        assert monday.planned_kcal == monday.baseline_kcal

    def test_says_so_when_the_week_is_unrecoverable(self):
        logged = {MON + timedelta(days=i): 4200 for i in range(4)}
        w = week_budget.build_week(MON + timedelta(days=4), 2700, logged)
        assert w.status == "blown"
        assert "let this one go" in w.detail.lower()

    def test_delta_reports_over_and_under(self):
        w = week_budget.build_week(MON + timedelta(days=1), 2700, {MON: 3000})
        assert next(d for d in w.days if d.day == MON).delta == pytest.approx(300)


class TestNothingCarriesForward:
    """The rule that separates a budget from a debt."""

    def test_settle_is_always_zero(self):
        blown = week_budget.build_week(
            MON + timedelta(days=6), 2700, {MON + timedelta(days=i): 4000 for i in range(6)}
        )
        assert week_budget.settle(blown) == 0.0

    def test_even_a_big_underspend_does_not_roll_over(self):
        under = week_budget.build_week(
            MON + timedelta(days=6), 2700, {MON + timedelta(days=i): 1000 for i in range(6)}
        )
        assert week_budget.settle(under) == 0.0

    def test_the_promise_is_stated_to_the_user(self):
        w = week_budget.build_week(MON, 2700, {})
        assert any("next week" in n.lower() for n in w.notes)


# ===========================================================================
# BET 3 — protein, in food and in rupees
# ===========================================================================
class TestProteinTiming:
    def test_no_meals(self):
        assert protein_coach.analyse_timing([]).shape == "unknown"

    def test_single_sitting_is_called_out(self):
        r = protein_coach.analyse_timing([MealProtein("Dinner", 21, 120)])
        assert r.shape == "single_dose"

    def test_back_loaded_day(self):
        r = protein_coach.analyse_timing(
            [
                MealProtein("Breakfast", 8, 28),
                MealProtein("Lunch", 13.5, 16),
                MealProtein("Snack", 17, 27),
                MealProtein("Dinner", 20.75, 94),
            ],
            target_g=165,
        )
        assert r.shape == "back_loaded"
        assert r.thinnest_meal == "Lunch"

    def test_front_loaded_day(self):
        r = protein_coach.analyse_timing(
            [
                MealProtein("Breakfast", 8, 80),
                MealProtein("Lunch", 13, 30),
                MealProtein("Dinner", 20, 25),
            ]
        )
        assert r.shape == "front_loaded"

    def test_even_day(self):
        r = protein_coach.analyse_timing(
            [
                MealProtein("A", 8, 40),
                MealProtein("B", 13, 40),
                MealProtein("C", 17, 40),
                MealProtein("D", 21, 45),
            ]
        )
        assert r.shape == "even"

    def test_counts_sittings_that_cleared_a_real_dose(self):
        r = protein_coach.analyse_timing(
            [MealProtein("A", 8, 30), MealProtein("B", 13, 8), MealProtein("C", 20, 40)],
            bodyweight_kg=80,
        )
        # 0.3 g/kg of 80 kg = 24 g. Two of three clear it.
        assert r.real_doses == 2

    def test_names_the_gap_in_the_advice(self):
        r = protein_coach.analyse_timing(
            [
                MealProtein("Breakfast", 8, 28),
                MealProtein("Lunch", 13.5, 10),
                MealProtein("Dinner", 21, 90),
            ]
        )
        assert "Lunch" in r.detail


class TestCloseTheGap:
    def test_nothing_to_do(self):
        assert protein_coach.close_the_gap(0).foods == []

    def test_covers_the_shortfall(self):
        g = protein_coach.close_the_gap(30)
        assert g.protein_g >= 30

    def test_prescribes_at_most_three_things(self):
        # Six items is not a prescription.
        assert len(protein_coach.close_the_gap(200).foods) <= 3

    def test_respects_vegetarian(self):
        g = protein_coach.close_the_gap(40, veg_only=True)
        assert all(f.veg for f in g.foods)

    def test_honours_exclusions(self):
        g = protein_coach.close_the_gap(40, exclude={"soya", "eggs"})
        assert all(f.key not in {"soya", "eggs"} for f in g.foods)

    def test_reports_the_price(self):
        g = protein_coach.close_the_gap(30)
        assert g.rupees > 0
        assert "₹" in g.note

    def test_admits_when_it_cannot_reach_the_target(self):
        g = protein_coach.close_the_gap(500)
        assert "short" in g.note.lower()


class TestProteinPerRupee:
    def test_ranked_best_first(self):
        ranked = protein_coach.rank_by_cost()
        vals = [f.g_per_10_rupees for f in ranked]
        assert vals == sorted(vals, reverse=True)

    def test_cheap_staples_beat_supplements(self):
        # The finding that makes this feature worth shipping.
        ranked = {f.key: f.g_per_10_rupees for f in protein_coach.rank_by_cost(limit=99)}
        assert ranked["soya"] > ranked["whey"]
        assert ranked["dal"] > ranked["paneer"]

    def test_a_users_own_price_wins(self):
        default = {f.key: f.g_per_10_rupees for f in protein_coach.rank_by_cost(limit=99)}
        mine = {
            f.key: f.g_per_10_rupees
            for f in protein_coach.rank_by_cost(limit=99, price_overrides={"dal": 6.0})
        }
        assert mine["dal"] > default["dal"]

    def test_an_override_is_marked_as_the_users_own(self):
        ranked = protein_coach.rank_by_cost(limit=99, price_overrides={"dal": 6.0})
        assert next(f for f in ranked if f.key == "dal").price_confidence == "yours"

    def test_staleness_is_measurable_so_the_ui_can_say_so(self):
        # A wrong price is worse than no price: it makes the ranking wrong.
        fresh = protein_coach.price_staleness_months(datetime(2026, 8, 1))
        old = protein_coach.price_staleness_months(datetime(2028, 8, 1))
        assert fresh == 0
        assert old == 24


# ===========================================================================
# BET 4 — the fuel/training link
# ===========================================================================
class TestFuelLink:
    def _pairs(self, carbs_and_volumes):
        carbs: dict[date, float] = {}
        sessions: list[Session] = []
        for i, (c, v) in enumerate(carbs_and_volumes):
            day = MON + timedelta(days=i * 2)
            carbs[day - timedelta(days=1)] = c
            sessions.append(Session(day, v, focus="legs"))
        return carbs, sessions

    def test_refuses_below_the_minimum_pairs(self):
        carbs, sessions = self._pairs([(300, 5000), (200, 4000)])
        r = fuel_link.analyse(carbs, sessions)
        assert r.verdict is LinkVerdict.insufficient_data

    def test_finds_a_real_positive_relationship(self):
        carbs, sessions = self._pairs(
            [(180, 3800), (200, 4000), (240, 4300), (260, 4600),
             (300, 5000), (320, 5200), (340, 5400), (360, 5700)]
        )
        r = fuel_link.analyse(carbs, sessions)
        assert r.verdict is LinkVerdict.positive
        assert r.rho > fuel_link.MIN_RHO
        assert r.uplift_pct > 0

    def test_reports_no_link_when_there_is_none(self):
        carbs, sessions = self._pairs(
            [(180, 5200), (200, 3900), (240, 5100), (260, 4000),
             (300, 4900), (320, 4100), (340, 5000), (360, 4200)]
        )
        r = fuel_link.analyse(carbs, sessions)
        assert r.verdict is LinkVerdict.none_found

    def test_a_negative_finding_is_stated_as_an_answer(self):
        carbs, sessions = self._pairs(
            [(180, 5200), (200, 3900), (240, 5100), (260, 4000),
             (300, 4900), (320, 4100), (340, 5000), (360, 4200)]
        )
        assert "real answer" in fuel_link.analyse(carbs, sessions).detail.lower()

    def test_focus_narrows_the_comparison(self):
        carbs, sessions = self._pairs([(200 + i * 20, 4000 + i * 200) for i in range(8)])
        assert fuel_link.analyse(carbs, sessions, focus="push").pairs == 0

    def test_unmatched_sessions_are_skipped(self):
        r = fuel_link.analyse({}, [Session(MON, 5000)])
        assert r.pairs == 0


class TestRefusesWithoutContrast:
    """The subtle failure mode: a 'pattern' found in data that has none."""

    def test_a_steady_eater_gets_no_claim(self):
        carbs: dict[date, float] = {}
        sessions = []
        for i in range(10):
            day = MON + timedelta(days=i * 2)
            carbs[day - timedelta(days=1)] = 290 + (i % 2)  # 290-291 g, always
            sessions.append(Session(day, 4000 + i * 150))
        r = fuel_link.analyse(carbs, sessions)
        assert r.verdict is LinkVerdict.no_contrast

    def test_and_explains_it_is_not_a_criticism(self):
        carbs: dict[date, float] = {}
        sessions = []
        for i in range(10):
            day = MON + timedelta(days=i * 2)
            carbs[day - timedelta(days=1)] = 290 + (i % 2)
            sessions.append(Session(day, 4000 + i * 150))
        assert "not a bad thing" in fuel_link.analyse(carbs, sessions).detail.lower()


class TestTheShiftNeverAddsCalories:
    """NON-NEGOTIABLE #1, guarded at the one place it could leak in."""

    def _positive(self):
        carbs: dict[date, float] = {}
        sessions = []
        for i, (c, v) in enumerate(
            [(180, 3800), (200, 4000), (240, 4300), (260, 4600),
             (300, 5000), (320, 5200), (340, 5400), (360, 5700)]
        ):
            day = MON + timedelta(days=i * 2)
            carbs[day - timedelta(days=1)] = c
            sessions.append(Session(day, v))
        return fuel_link.analyse(carbs, sessions)

    def test_the_swap_is_calorie_neutral(self):
        shift = fuel_link.suggest_shift(self._positive(), training_tomorrow=True)
        assert shift is not None
        assert shift.kcal_delta == pytest.approx(0.0, abs=1e-6)

    def test_carbs_go_up_and_fat_comes_down(self):
        shift = fuel_link.suggest_shift(self._positive(), training_tomorrow=True)
        assert shift.carbs_delta_g > 0
        assert shift.fat_delta_g < 0

    def test_no_suggestion_without_a_finding(self):
        empty = fuel_link.analyse({}, [])
        assert fuel_link.suggest_shift(empty, training_tomorrow=True) is None

    def test_no_suggestion_on_a_rest_day(self):
        assert fuel_link.suggest_shift(self._positive(), training_tomorrow=False) is None

    def test_it_says_the_target_does_not_change(self):
        shift = fuel_link.suggest_shift(self._positive(), training_tomorrow=True)
        assert "target doesn't change" in shift.detail
