"""The sport catalogue and the burn estimator.

These are the spec. In particular the LAST class in this file is the spec for
non-negotiable #1 -- if someone ever wires this number into a calorie target,
the test that fails should be the one that explains why they must not.
"""

import pytest

from app.services import sports
from app.services.sports import Intensity, SportError


class TestCatalogue:
    def test_has_at_least_the_thirty_two_the_design_promises(self):
        # The Activities screen renders "N SPORTS" from this list. It said 32
        # while the app shipped 9, which is the discrepancy that made the tab
        # feel broken.
        assert len(sports.SPORTS) >= 32

    def test_keys_are_unique(self):
        keys = [s.key for s in sports.SPORTS]
        assert len(keys) == len(set(keys))

    def test_every_sport_has_a_plausible_met(self):
        # Sleeping is 0.95 MET and the highest entry in the whole Compendium
        # is around 23. Anything outside this is a typo.
        for s in sports.SPORTS:
            assert 1.0 <= s.met <= 16.0, s.key

    def test_interpolated_mets_are_declared(self):
        # We may guess, but we may not imply a citation we don't have.
        for key in ("pickleball", "kabaddi", "crossfit", "padel"):
            assert sports.BY_KEY[key].estimated is True

    def test_compendium_values_are_not_flagged_as_estimates(self):
        for key in ("running", "tennis", "cricket", "swimming"):
            assert sports.BY_KEY[key].estimated is False

    def test_groups_are_ordered_and_unique(self):
        g = sports.groups()
        assert g[0] == "Racket"
        assert len(g) == len(set(g))


class TestFind:
    @pytest.mark.parametrize(
        "term,expected",
        [
            ("badminton", "badminton"),
            ("Badminton", "badminton"),
            ("table_tennis", "table_tennis"),
            ("table tennis", "table_tennis"),
            ("Table tennis", "table_tennis"),
        ],
    )
    def test_resolves_keys_and_names(self, term, expected):
        assert sports.find(term).key == expected

    @pytest.mark.parametrize(
        "term,expected",
        [
            ("ping pong", "table_tennis"),
            ("soccer", "football"),
            ("jog", "running"),
            ("went for a ride", "cycling"),
            ("jump rope", "skipping"),
            ("wod", "crossfit"),
        ],
    )
    def test_resolves_what_people_actually_say(self, term, expected):
        # The voice logger hands us free text. "Went for a ride" must not
        # require the user to know we filed it under `cycling`.
        assert sports.find(term).key == expected

    def test_unknown_returns_none_rather_than_guessing(self):
        assert sports.find("underwater basket weaving") is None
        assert sports.find("") is None


class TestEstimateBurn:
    def test_matches_the_met_formula(self):
        # 60 min of 7.5-MET cycling at 80 kg:
        #   7.5 * 3.5 * 80 / 200 = 10.5 kcal/min -> 630 kcal
        est = sports.estimate_burn("cycling", 60, 80)
        assert est.point == 630

    def test_returns_a_range_never_a_bare_number(self):
        est = sports.estimate_burn("badminton", 45, 75)
        assert est.low < est.point < est.high
        assert est.band > 0

    def test_scales_linearly_with_duration(self):
        half = sports.estimate_burn("running", 30, 70).point
        full = sports.estimate_burn("running", 60, 70).point
        assert full == pytest.approx(half * 2, rel=0.01)

    def test_scales_linearly_with_mass(self):
        light = sports.estimate_burn("running", 30, 50).point
        heavy = sports.estimate_burn("running", 30, 100).point
        assert heavy == pytest.approx(light * 2, rel=0.01)

    def test_intensity_moves_the_estimate_in_the_right_direction(self):
        easy = sports.estimate_burn("badminton", 45, 75, Intensity.easy).point
        mod = sports.estimate_burn("badminton", 45, 75, Intensity.moderate).point
        hard = sports.estimate_burn("badminton", 45, 75, Intensity.hard).point
        assert easy < mod < hard

    def test_intensity_accepts_a_plain_string(self):
        assert (
            sports.estimate_burn("badminton", 45, 75, "hard").point
            == sports.estimate_burn("badminton", 45, 75, Intensity.hard).point
        )

    def test_a_missing_weight_widens_the_band_rather_than_hiding_it(self):
        known = sports.estimate_burn("running", 40, 72)
        guessed = sports.estimate_burn("running", 40, None)
        assert guessed.assumed_weight is True
        assert known.assumed_weight is False
        # Two stacked sources of error must read as less certain, not equally
        # certain, on screen.
        assert guessed.band / guessed.point > known.band / known.point

    def test_flags_an_interpolated_met_so_the_ui_can_say_so(self):
        assert sports.estimate_burn("pickleball", 45, 75).met_estimated is True
        assert sports.estimate_burn("tennis", 45, 75).met_estimated is False

    def test_resolves_aliases_too(self):
        assert sports.estimate_burn("soccer", 60, 70).point > 0


class TestRefusesRatherThanGuesses:
    """Non-negotiable #3: refusing to answer beats answering wrong."""

    def test_rejects_an_unknown_sport(self):
        with pytest.raises(SportError):
            sports.estimate_burn("quidditch", 45, 75)

    @pytest.mark.parametrize("bad", [0, -30, 0.5, 601, 100000])
    def test_rejects_impossible_durations(self, bad):
        # A 14-hour session is a timer somebody forgot to stop, and silently
        # banking 6,000 kcal of "activity" would poison the training load.
        with pytest.raises(SportError):
            sports.estimate_burn("badminton", bad, 75)

    def test_rejects_an_unknown_intensity(self):
        with pytest.raises(SportError):
            sports.estimate_burn("badminton", 45, 75, "absolutely brutal")

    def test_accepts_the_boundaries_themselves(self):
        assert sports.estimate_burn("walking", sports.MIN_DURATION_MIN, 70).point >= 0
        assert sports.estimate_burn("walking", sports.MAX_DURATION_MIN, 70).point > 0


class TestNeverFeedsTheCalorieTarget:
    """NON-NEGOTIABLE #1. Read services/activity.py for the full argument.

    If you are here because this test failed, someone has started treating a
    sport session as calories the user may eat back. The adaptive TDEE already
    contains this session -- it showed up in the weight trend. Adding it again
    is double-counting a number that is itself a population average.
    """

    def test_the_ui_copy_says_the_target_is_unchanged(self):
        goes = dict(sports.WHERE_THIS_GOES)
        assert goes["Today's calorie target"] == "Unchanged"

    def test_the_explainer_exists_and_says_do_not_eat_it_back(self):
        assert "eat back" in sports.TARGET_EXPLAINER.lower()

    def test_the_estimator_returns_context_not_an_allowance(self):
        # There is deliberately no `target_adjustment` on BurnEstimate, and
        # there must not be one. This asserts the shape of the contract.
        est = sports.estimate_burn("cycling", 60, 80)
        assert not hasattr(est, "target_adjustment")
        assert not hasattr(est, "extra_calories_allowed")
