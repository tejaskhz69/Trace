"""What four photographs of one Gold's Gym floor say about the schema.

Taken 2026-08-22. Three Hammer Strength selectorised machines standing within
a few metres of each other, plus a wide shot of the floor:

    FIXED PULLDOWN   5, 12, 19, 26, 33, 40, 47, 54, 61, 68,
                     75, 82, 89, 96, 103, 110, 117, 124, 131, 138
    ROW              the same sequence
    LATERAL RAISE    5, 10, 15, 20, 25, 32, 39, 46, 53, 60, 67, 74, 81, 88...

Add-on micro plates sit on top of the stack on all three: two marked 2.5 on
the Row, one 2.5 and one 5 on the Fixed Pulldown, at least one 2.5 on the
Lateral Raise.

These are the facts the code has to survive. The numbers here are READ FROM
THOSE PHOTOGRAPHS and from nothing else -- no machine outside the four
images gets a stack in this file, because a fabricated stack is worse than an
absent one.
"""

from __future__ import annotations

import pytest

from app.services.units import nearest_loadable_on_stack, stack_loads

# ---------------------------------------------------------------------------
# The two stacks, exactly as photographed
# ---------------------------------------------------------------------------

#: FIXED PULLDOWN and ROW. A 5, then steps of 7 all the way up.
PULLDOWN_PRINTED = [
    5, 12, 19, 26, 33, 40, 47, 54, 61, 68,
    75, 82, 89, 96, 103, 110, 117, 124, 131, 138,
]
PULLDOWN_RANGES = [{"start": 5, "end": 138, "step": 7}]

#: LATERAL RAISE. Steps of 5 that become steps of 7 partway up.
#:
#: The bottom of this stack is out of frame. 88 is legible in the right-hand
#: column and the stack plainly continues below it, so this list is
#: TRUNCATED AT WHAT THE PHOTOGRAPH SHOWS rather than extrapolated to a
#: round number.
LATERAL_PRINTED = [5, 10, 15, 20, 25, 32, 39, 46, 53, 60, 67, 74, 81, 88]
LATERAL_RANGES = [
    {"start": 5, "end": 25, "step": 5},
    {"start": 32, "end": 88, "step": 7},
]


class TestTheSchemaCanHoldWhatIsOnTheFloor:
    def test_the_pulldown_stack_round_trips(self):
        assert stack_loads(PULLDOWN_RANGES) == [float(v) for v in PULLDOWN_PRINTED]

    def test_the_lateral_raise_stack_round_trips(self):
        """The one that matters: its step size changes partway up, so a
        single `increment` column could not describe it at all."""
        assert stack_loads(LATERAL_RANGES) == [float(v) for v in LATERAL_PRINTED]

    def test_plate_eight_is_a_different_weight_on_each_machine(self):
        """Two machines, same brand, same room. This is the whole argument
        for a per-station array rather than a global increment."""
        pulldown = stack_loads(PULLDOWN_RANGES)
        lateral = stack_loads(LATERAL_RANGES)
        assert pulldown[7] == 54
        assert lateral[7] == 46
        assert pulldown[7] != lateral[7]

    def test_the_pulldown_alone_is_position_times_a_constant(self):
        """Stated precisely, because it is the half that makes the naive
        model look like it works. The Pulldown IS 5 + 7i, so any code tested
        only against this machine passes."""
        loads = stack_loads(PULLDOWN_RANGES)
        assert loads == [5.0 + 7.0 * i for i in range(len(loads))]

    def test_the_lateral_raise_is_not_and_that_is_the_point(self):
        """Its step changes from 5 to 7 partway up, so NO single constant
        reproduces it -- not 5, not 7, not an average."""
        loads = stack_loads(LATERAL_RANGES)
        for step in (5.0, 7.0, (loads[-1] - loads[0]) / (len(loads) - 1)):
            naive = [loads[0] + step * i for i in range(len(loads))]
            assert loads != naive, f"step {step} reproduced the stack"

    def test_an_empty_stack_is_not_a_crash(self):
        assert stack_loads([]) == []
        assert nearest_loadable_on_stack(50.0, []) is None

    def test_a_malformed_range_is_skipped_not_guessed_at(self):
        """A zero step would loop forever; a reversed range has no members.
        Neither is worth inventing a stack for."""
        assert stack_loads([{"start": 5, "end": 50, "step": 0}]) == []
        assert stack_loads([{"start": 50, "end": 5, "step": 5}]) == []
        # A good range beside a bad one still yields the good one.
        assert stack_loads(
            [{"start": 5, "end": 15, "step": 5}, {"start": 9, "end": 1, "step": 2}]
        ) == [5.0, 10.0, 15.0]


class TestAddOnMicroPlates:
    """The Row carries two 2.5s; the Fixed Pulldown a 2.5 and a 5. Effective
    load is the stack selection PLUS whichever add-ons are engaged."""

    ROW_ADD_ONS = [2.5, 2.5]
    PULLDOWN_ADD_ONS = [2.5, 5.0]

    def test_the_row_reaches_between_its_stack_positions(self):
        """54 and 61 are adjacent plates. Without add-ons there is nothing
        in between; with two 2.5s, 56.5 and 59 exist."""
        assert nearest_loadable_on_stack(
            56.5, PULLDOWN_RANGES, add_ons_kg=self.ROW_ADD_ONS
        ) == 56.5
        assert nearest_loadable_on_stack(59.0, PULLDOWN_RANGES,
                                         add_ons_kg=self.ROW_ADD_ONS) == 59.0

    def test_two_equal_add_ons_are_not_the_same_as_one_of_twice_the_size(self):
        """Two 2.5s give +2.5 and +5. A 2.5 and a 5 give +2.5, +5 and +7.5.
        A single `micro_adjust_kg` float cannot tell these apart, which is
        the schema gap this test exists to name."""
        row = {
            nearest_loadable_on_stack(t, PULLDOWN_RANGES, add_ons_kg=self.ROW_ADD_ONS)
            for t in (61.5, 61.6)
        }
        pulldown = nearest_loadable_on_stack(
            61.5, PULLDOWN_RANGES, add_ons_kg=self.PULLDOWN_ADD_ONS
        )
        assert pulldown == 61.5              # 54 + 2.5 + 5
        assert 61.5 not in row               # the Row cannot make 61.5

    def test_without_add_ons_the_gap_is_real(self):
        got = nearest_loadable_on_stack(56.5, PULLDOWN_RANGES)
        assert got in (54.0, 61.0)
        assert got != 56.5

    def test_no_add_ons_declared_behaves_like_none_engaged(self):
        assert nearest_loadable_on_stack(
            54.0, PULLDOWN_RANGES, add_ons_kg=[]
        ) == nearest_loadable_on_stack(54.0, PULLDOWN_RANGES)


class TestNothingConvertsLoadAcrossStations:
    """Refused deliberately: plate-loaded leverage runs 2:1 to 5:1, is
    unpublished, and changes through the range of motion."""

    def test_there_is_no_conversion_helper_anywhere_in_units(self):
        import app.services.units as units

        names = [n for n in dir(units) if not n.startswith("_")]
        for suspicious in ("convert_station", "effective_load", "station_ratio",
                           "normalise_load", "normalize_load"):
            assert suspicious not in names

    def test_the_station_model_carries_no_conversion_factor(self):
        from app.models import Station

        cols = set(Station.__table__.columns.keys())
        for suspicious in ("effective_load_ratio", "leverage_ratio",
                           "conversion_factor", "normalisation_factor"):
            assert suspicious not in cols


class TestUnitIsDeclaredNeverInferred:
    """The stacks are marked in two columns. Read at 4x, both columns carry
    THE SAME sequence -- 5/12/19 on the left, 5/12/19 on the right -- so the
    dual marking is one scale printed either side of the selector holes for
    readability, NOT lb on one side and kg on the other.

    Nothing in any of the four photographs states a unit. So the unit is a
    fact only the person standing at the machine has, and the schema treats
    it as declared rather than inferred.
    """

    def test_station_unit_is_a_stored_declaration_with_a_default(self):
        from app.models import Station

        col = Station.__table__.columns["unit"]
        assert col.default is not None or not col.nullable

    def test_only_kg_and_lb_are_accepted(self):
        from app.models import Station

        checks = [
            str(c.sqltext)
            for c in Station.__table__.constraints
            if getattr(c, "name", None) == "ck_station_unit"
        ]
        assert checks, "ck_station_unit is missing"
        assert "'kg'" in checks[0] and "'lb'" in checks[0]

    def test_a_stack_number_is_not_silently_reinterpreted(self):
        """138 is 138 on the machine's own scale. `stack_loads` must not
        apply a conversion of its own."""
        assert stack_loads(PULLDOWN_RANGES)[-1] == 138.0


# ---------------------------------------------------------------------------
# (a) Manufacturer names are not user names
# ---------------------------------------------------------------------------


class TestTheNameplateTermsReachTheRightMovement:
    """What is written on the machine, what people say, and what the
    catalogue calls it are three different strings.

    The nameplates in the photographs read FIXED PULLDOWN and ROW. Nobody
    says "fixed pulldown" out loud -- but somebody standing in front of that
    machine, typing what is printed on it, must still land on Lat Pulldown.
    """

    #: query -> the movement that must own it
    OWNED = {
        "fixed pulldown": "Lat Pulldown",
        "lat pulldown": "Lat Pulldown",
        "hammer strength row": "Chest-Supported Row",
        "hs row": "Chest-Supported Row",
        "hammer lateral raise": "Machine Lateral Raise",
        "lateral raise": "Dumbbell Lateral Raise",
    }

    @staticmethod
    def _namespace() -> dict[str, str]:
        """term -> owning movement name, over the seed source."""
        from app.scripts import seed_movements
        from app.services.catalogue import normalise_term

        owner: dict[str, str] = {}
        for name, _m, _s, _e, _c, aliases in seed_movements.E:
            owner[normalise_term(name)] = name
            for alias in aliases:
                owner.setdefault(normalise_term(alias), name)
        return owner

    @pytest.mark.parametrize("query", sorted(OWNED))
    def test_the_term_resolves_to_exactly_one_movement(self, query):
        from app.services.catalogue import normalise_term

        owner = self._namespace()
        assert normalise_term(query) in owner, f"{query!r} resolves to nothing"

    @pytest.mark.parametrize("query,expected", sorted(OWNED.items()))
    def test_it_resolves_to_the_right_one(self, query, expected):
        from app.services.catalogue import normalise_term

        assert self._namespace()[normalise_term(query)] == expected

    def test_the_bare_term_belongs_to_the_dumbbell_not_the_machine(self):
        """"lateral raise" unqualified means the dumbbell version. The
        machine has to be asked for by name. Asserted because the photographed
        machine is the Hammer Strength one and it would be tempting to give
        it the bare term."""
        from app.services.catalogue import normalise_term

        owner = self._namespace()
        assert owner[normalise_term("lateral raise")] == "Dumbbell Lateral Raise"
        assert owner[normalise_term("machine lateral raise")] == "Machine Lateral Raise"

    def test_no_brand_became_a_catalogue_row(self):
        """Brands are aliases; machines are Station rows. The four photos
        must not have added "Hammer Strength Row" as a movement."""
        from app.scripts import seed_movements

        names = {n.lower() for n, *_ in seed_movements.E}
        for brandish in ("hammer strength row", "fixed pulldown",
                         "hammer strength lateral raise", "hs row"):
            assert brandish not in names, f"{brandish!r} became a catalogue row"


class TestSearchMatchesAtATokenPrefix:
    r"""The rule is Postgres `\m` -- the query must START a word.

    It replaced a two-sided word boundary (`\y..\y`), which looked right on
    "row" but silently dropped every plural in the catalogue: `\yfly\y` does
    not match "Dumbbell Flyes". Measured over all 897 rows, the two-sided
    rule lost 6 rows on "row", 13 on "fly" (half of them), 11 on "curl",
    4 on "dip" -- and 2 even on "pulldown", which is why there is no length
    threshold: long queries were damaged too.
    """

    #: (name, matches "row")
    CASES = [
        ("Barbell Row", True),
        ("Chest-Supported Row", True),
        ("Seated Cable Rows", True),        # plural -- the case \y..\y broke
        ("Row", True),
        ("Backward Medicine Ball Throw", False),   # th(row)
        ("Narrow Stance Squats", False),           # na(rrow)
    ]

    @pytest.mark.parametrize("name,should_match", CASES)
    def test_the_pattern_keeps_plurals_and_rejects_mid_token(self, name, should_match):
        r"""The same rule the query uses, checked in Python so the intent is
        legible without a database. `\m` is Postgres for `\b(?=\w)`."""
        import re

        assert bool(re.search(r"\brow", name, re.IGNORECASE)) is should_match

    def test_there_is_no_length_special_case_left(self):
        """The threshold was a proxy for "short queries produce junk".
        Token-prefix is correct at every length, so the branch earned
        nothing and is gone."""
        import app.routers.workouts as w

        assert not hasattr(w, "SHORT_QUERY_CHARS")

    def test_both_the_name_and_the_alias_side_use_it(self):
        """The alias side was the gap that hid Cyclist Squat: it matched
        "row" through the alias "narrow stance squat" after the name side
        had already excluded it."""
        import app.routers.workouts as w

        token_start = "\\m"  # the two characters a backslash and an m
        assert token_start in str(w._name_match("row"))
        assert token_start in str(w._alias_match("%row%"))
