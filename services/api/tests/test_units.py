"""Units and bar weights. The last class is the one that matters."""

import pytest

from app.services import units
from app.services.units import UnknownBarWeight


class TestConversion:
    def test_kg_to_lb(self):
        assert units.kg_to_lb(100) == pytest.approx(220.462, abs=0.01)

    def test_lb_to_kg(self):
        assert units.lb_to_kg(45) == pytest.approx(20.41, abs=0.01)

    def test_round_trips(self):
        for kg in (2.5, 20, 60, 102.5, 187.5):
            assert units.lb_to_kg(units.kg_to_lb(kg)) == pytest.approx(kg, abs=1e-9)

    def test_a_plate_is_the_number_people_know(self):
        # 20 kg bar is 44 lb; a 20 kg plate is 44 lb. If these drift, the
        # conversion constant is wrong.
        assert round(units.kg_to_lb(20)) == 44
        assert round(units.kg_to_lb(15)) == 33


class TestBars:
    def test_olympic_bar_is_twenty_kilos(self):
        assert units.BY_KEY["olympic"].weight_kg == 20.0

    def test_barbell_exercises_get_the_olympic_bar(self):
        assert units.bar_for("barbell").weight_kg == 20.0

    def test_ez_bar_is_flagged_uncertain(self):
        # 7-12 kg by make. Our default is a starting point, not a fact.
        assert units.BY_KEY["ez"].uncertain is True

    def test_smith_machine_weight_is_unknown_not_guessed(self):
        # Counterbalancing varies ~6-25 kg and cannot be inferred from here.
        assert units.BY_KEY["smith"].weight_kg is None

    def test_non_bar_equipment_has_no_bar(self):
        for eq in ("dumbbell", "cable", "machine", "bodyweight", "kettlebell"):
            assert units.has_bar(eq) is False
            assert units.bar_for(eq).weight_kg == 0.0

    def test_bar_equipment_has_a_bar(self):
        for eq in ("barbell", "ezbar", "smith"):
            assert units.has_bar(eq) is True

    def test_a_user_measurement_always_wins(self):
        assert units.bar_for("smith", override_kg=8.0).weight_kg == 8.0
        assert units.bar_for("barbell", override_kg=15.0).weight_kg == 15.0

    def test_unknown_equipment_is_treated_as_no_bar(self):
        # Safer than assuming a bar and subtracting 20 kg that isn't there.
        assert units.has_bar("something-new") is False


class TestPlatesAndTotal:
    def test_subtracting_the_bar(self):
        assert units.plates_from_total(60, "barbell") == 40.0

    def test_adding_the_bar(self):
        assert units.total_from_plates(40, "barbell") == 60.0

    def test_they_are_exact_inverses(self):
        for total in (20, 42.5, 60, 102.5, 180):
            plates = units.plates_from_total(total, "barbell")
            assert units.total_from_plates(plates, "barbell") == pytest.approx(total)

    def test_no_bar_means_no_transform(self):
        # A dumbbell press has no bar to subtract; pretending otherwise would
        # silently mangle the number.
        assert units.plates_from_total(32.5, "dumbbell") == 32.5
        assert units.total_from_plates(32.5, "dumbbell") == 32.5

    def test_an_empty_bar_is_zero_plates(self):
        assert units.plates_from_total(20, "barbell") == 0.0

    def test_plate_weight_never_goes_negative(self):
        # A total under the bar is a typo, and a negative plate figure is not
        # something we should ever render.
        assert units.plates_from_total(15, "barbell") == 0.0

    def test_refuses_when_the_bar_weight_is_unknown(self):
        with pytest.raises(UnknownBarWeight):
            units.plates_from_total(80, "smith")
        with pytest.raises(UnknownBarWeight):
            units.total_from_plates(60, "smith")

    def test_the_refusal_explains_how_to_fix_it(self):
        with pytest.raises(UnknownBarWeight, match="settings"):
            units.plates_from_total(80, "smith")

    def test_an_override_unblocks_the_smith_machine(self):
        assert units.plates_from_total(80, "smith", override_kg=10) == 70.0


class TestDescribe:
    def test_shows_both_units(self):
        d = units.describe(60, "barbell")
        assert d.kg == 60
        assert d.lb == pytest.approx(132.3, abs=0.1)
        assert "kg" in d.both and "lb" in d.both

    def test_drops_a_pointless_decimal(self):
        assert units.describe(60, "barbell").both.startswith("60 kg")

    def test_keeps_a_meaningful_decimal(self):
        assert "32.5 kg" in units.describe(32.5, "dumbbell").both

    def test_barbell_gets_plate_figures(self):
        d = units.describe(60, "barbell")
        assert d.plates_kg == 40.0
        assert d.plates_lb == pytest.approx(88.2, abs=0.1)
        assert d.bar_name == "Olympic bar"
        assert d.bar_kg == 20.0

    def test_dumbbell_gets_no_plate_figures(self):
        d = units.describe(32.5, "dumbbell")
        assert d.plates_kg is None
        assert d.bar_name is None

    def test_smith_names_the_bar_but_refuses_a_number(self):
        d = units.describe(80, "smith")
        assert d.bar_name == "Smith machine"
        assert d.bar_kg is None
        # Known-unknown: no plate figure we cannot stand behind.
        assert d.plates_kg is None
        assert d.bar_uncertain is True

    def test_an_override_gives_smith_its_plates(self):
        d = units.describe(80, "smith", override_kg=10)
        assert d.plates_kg == 70.0

    def test_ez_bar_is_marked_uncertain_for_the_ui(self):
        assert units.describe(30, "ezbar").bar_uncertain is True


class TestStorageStaysTotal:
    """THE INVARIANT THAT PROTECTS EVERY STRENGTH NUMBER IN THE APP.

    e1RM, volume, the weekly strength index and the recomposition verdict all
    read `SetLog.weight_kg` and all assume TOTAL load — a bar is 20 kg of real
    resistance. "Plates only" is a display and input transform applied at the
    edge, never a storage format.

    If you are here because this failed: someone has started storing plate
    weight. Every e1RM in the app just dropped by the bar, and it will read as
    a strength regression on the day a user flips a display setting.
    """

    def test_input_transform_produces_total_for_storage(self):
        # User types 40 (plates) on a barbell lift; we must store 60.
        assert units.total_from_plates(40, "barbell") == 60.0

    def test_display_transform_does_not_change_what_was_stored(self):
        stored = 60.0
        shown = units.describe(stored, "barbell")
        assert shown.kg == stored
        assert shown.plates_kg == 40.0
        # The stored figure is still the total, and still recoverable.
        assert units.total_from_plates(shown.plates_kg, "barbell") == stored

    def test_a_round_trip_through_the_ui_is_lossless(self):
        for total in (20, 42.5, 60, 100, 182.5):
            plates = units.describe(total, "barbell").plates_kg
            assert units.total_from_plates(plates, "barbell") == pytest.approx(total)

    def test_describe_never_returns_plates_as_the_primary_figure(self):
        # `kg` is the total. A caller reading `.kg` gets storage semantics.
        d = units.describe(100, "barbell")
        assert d.kg == 100
        assert d.plates_kg == 80
        assert d.kg != d.plates_kg


class TestRounding:
    def test_rounds_to_a_loadable_step(self):
        assert units.round_to_step(62.37, units.STEP_KG) == 62.5
        assert units.round_to_step(61.1, units.STEP_KG) == 60.0

    def test_pound_step_is_a_five_pound_pair(self):
        assert units.round_to_step(133.2, units.STEP_LB) == 135.0
