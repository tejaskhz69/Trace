"""The deterministic generator, as pure functions.

No database, no HTTP. These are the tests that pin the actual programming
decisions -- what a beginner is allowed to be given, how a short session is
shortened, and the fact that the same profile produces byte-identical output
every time. The API tests in test_programming_api.py cover persistence and
ownership; nothing here needs a connection.
"""

from __future__ import annotations

import pytest

from app.services import programming as pg


def _opt(
    ex_id: str,
    *,
    pattern: str | None = "squat",
    klass: str = "compound",
    equipment: str = "dumbbell",
    name: str | None = None,
    rep_min: int = 6,
    rep_max: int = 10,
    rest: int = 120,
    fatigue: int = 3,
    muscle: str = "quads",
    secondary: tuple[str, ...] = ("glutes",),
) -> pg.ExerciseOption:
    return pg.ExerciseOption(
        exercise_id=ex_id,
        name=name or ex_id,
        equipment=equipment,
        muscle_group=muscle,
        secondary_muscles=secondary,
        movement_pattern=pattern,
        # DERIVED. `ck_exattr_isolation_matches_pattern` makes is_isolation
        # exactly the set with no pattern; a helper that let a test set them
        # independently would build options the database cannot hold.
        is_isolation=pattern is None,
        exercise_class=klass,
        default_rep_min=rep_min,
        default_rep_max=rep_max,
        default_rest_seconds=rest,
        fatigue_cost=fatigue,
    )


#: A small catalogue covering every pattern a beginner split asks for.
CATALOGUE = (
    _opt("goblet-squat", pattern="squat", name="Goblet squat"),
    _opt("db-rdl", pattern="hinge", name="Dumbbell RDL"),
    _opt("db-bench", pattern="h-push", name="Dumbbell bench press"),
    _opt("db-row", pattern="h-pull", name="Dumbbell row"),
    _opt("db-press", pattern="v-push", name="Dumbbell shoulder press"),
    _opt("pull-up", pattern="v-pull", name="Pull-up", equipment="bodyweight"),
    _opt("farmer-carry", pattern="carry", name="Farmer carry", klass="compound"),
    _opt(
        "db-curl",
        pattern=None,
        klass="isolation",
        name="Dumbbell curl",
        rep_min=10,
        rep_max=15,
        rest=60,
        muscle="biceps",
        secondary=(),
    ),
    _opt("bb-squat", pattern="squat", name="Barbell squat", equipment="barbell"),
    _opt("leg-press", pattern="squat", name="Leg press", equipment="machine"),
)


class TestSplitGeneration:
    @pytest.mark.parametrize("days", [1, 2, 3])
    def test_beginners_get_full_body_up_to_three_days(self, days):
        """Twice a week, hitting everything twice beats a split. Not a style
        preference -- it is the whole argument for full body at low
        frequency."""
        split, templates = pg.split_for(days)
        assert split == "full_body"
        assert len(templates) == days

    @pytest.mark.parametrize("days", [4, 5, 6, 7])
    def test_four_days_and_up_gets_upper_lower(self, days):
        split, templates = pg.split_for(days)
        assert split == "upper_lower"
        assert len(templates) == days

    @pytest.mark.parametrize("days", range(1, 8))
    def test_every_day_label_in_a_week_is_distinct(self, days):
        """Two days both called "Upper" is ambiguous the moment a user tries
        to say which one they skipped."""
        _, templates = pg.split_for(days)
        labels = [t.label for t in templates]
        assert len(set(labels)) == len(labels), labels

    @pytest.mark.parametrize("days", [0, -1, 8, 99])
    def test_out_of_range_frequency_is_refused(self, days):
        with pytest.raises(ValueError):
            pg.split_for(days)

    def test_generation_is_deterministic(self):
        assert pg.split_for(4) == pg.split_for(4)

    def test_every_template_carries_patterns(self):
        for days in range(1, 8):
            for t in pg.split_for(days)[1]:
                assert t.patterns, t.label
                assert t.focus, t.label

    def test_high_frequency_adds_a_rest_day_note(self):
        assert any("rest day" in n for n in pg.programme_notes(6))
        assert not any("rest day" in n for n in pg.programme_notes(3))

    def test_notes_never_make_a_health_claim(self):
        for days in range(1, 8):
            joined = " ".join(pg.programme_notes(days)).lower()
            for banned in ("injury", "injured", "pain", "doctor", "medical",
                           "diagnos", "treat", "heal", "therapy"):
                assert banned not in joined, (days, banned)


class TestBeginnerEquipment:
    def test_default_is_bodyweight_and_dumbbell(self):
        assert pg.beginner_equipment(None) == pg.BEGINNER_EQUIPMENT
        assert pg.beginner_equipment([]) == pg.BEGINNER_EQUIPMENT

    def test_a_barbell_owner_still_gets_beginner_equipment(self):
        """Owning a barbell does not make someone ready to be prescribed one."""
        assert "barbell" not in pg.beginner_equipment(["barbell", "dumbbell"])

    def test_stated_equipment_narrows_but_never_widens(self):
        assert pg.beginner_equipment(["dumbbell"]) == frozenset({"dumbbell"})

    def test_no_usable_equipment_still_yields_bodyweight(self):
        """Otherwise "I have nothing" would produce an empty programme."""
        assert pg.beginner_equipment(["cable", "machine"]) == frozenset({"bodyweight"})

    def test_junk_input_is_treated_as_no_constraint(self):
        for junk in ("dumbbell", 42, {"a": 1}):
            assert pg.beginner_equipment(junk) == pg.BEGINNER_EQUIPMENT


class TestBudget:
    @pytest.mark.parametrize(
        "minutes,expected", [(15, 3), (30, 3), (45, 3), (60, 5), (90, 7), (180, 8)]
    )
    def test_session_length_bounds_exercise_count(self, minutes, expected):
        assert pg.exercise_budget(minutes) == expected

    def test_never_below_three_or_above_eight(self):
        for minutes in range(15, 181):
            assert 3 <= pg.exercise_budget(minutes) <= 8


class TestEligibility:
    def test_non_beginner_equipment_is_excluded(self):
        kept = pg.eligible(CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT)
        ids = {o.exercise_id for o in kept}
        assert "bb-squat" not in ids
        assert "leg-press" not in ids
        assert "goblet-squat" in ids

    def test_disliked_exercises_are_excluded(self):
        kept = pg.eligible(
            CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT, disliked=["goblet-squat"]
        )
        assert "goblet-squat" not in {o.exercise_id for o in kept}

    def test_ordering_is_total_and_stable(self):
        """The exercise_id tie-break is what makes this a TOTAL order. Without
        it, two otherwise-identical rows would order by whatever the database
        returned, and the same profile would generate two different
        programmes."""
        a = pg.eligible(CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT)
        b = pg.eligible(tuple(reversed(CATALOGUE)), equipment=pg.BEGINNER_EQUIPMENT)
        assert [o.exercise_id for o in a] == [o.exercise_id for o in b]

    def test_compounds_sort_before_isolation(self):
        kept = pg.eligible(CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT)
        classes = [o.exercise_class for o in kept]
        assert classes.index("isolation") == len(classes) - 1

    def test_identical_candidates_still_order_deterministically(self):
        twins = (
            _opt("bbb", name="Same name"),
            _opt("aaa", name="Same name"),
        )
        kept = pg.eligible(twins, equipment=pg.BEGINNER_EQUIPMENT)
        assert [o.exercise_id for o in kept] == ["aaa", "bbb"]


class TestDaySelection:
    def test_one_exercise_per_pattern_before_any_second(self):
        """A session with three chest movements and no pulling is worse than
        one that covers its patterns once each."""
        day = pg.split_for(1)[1][0]
        candidates = pg.eligible(CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT)
        chosen = pg.select_for_day(day, candidates, budget=8)
        patterns = [o.movement_pattern for o in chosen]
        assert len(patterns) == len(set(patterns))

    def test_the_days_own_patterns_come_first(self):
        """A template slot is not always a movement pattern.

        `isolation` asks "is this isolation work", which the eight-pattern
        vocabulary cannot express -- those rows carry a NULL pattern by
        design. So the slot is compared through `_fills_slot`, the same way
        the selector does it, rather than against the pattern column.
        """
        day = pg.split_for(1)[1][0]
        candidates = pg.eligible(CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT)
        chosen = pg.select_for_day(day, candidates, budget=len(day.patterns))

        assert len(chosen) == len(day.patterns)
        for option, slot in zip(chosen, day.patterns):
            assert pg._fills_slot(option, slot), (option.name, slot)

    def test_the_isolation_slot_is_filled_by_a_null_pattern_row(self):
        """Stated on its own because it is the whole point of the slot: a
        NULL pattern is an answer, not a coverage gap."""
        day = pg.split_for(1)[1][0]
        assert pg.ISOLATION_SLOT in day.patterns
        candidates = pg.eligible(CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT)
        chosen = pg.select_for_day(day, candidates, budget=len(day.patterns))

        isolation = [o for o in chosen if o.is_isolation]
        assert isolation, "the isolation slot selected nothing"
        assert all(o.movement_pattern is None for o in isolation)

    def test_no_row_claims_the_string_isolation_as_its_pattern(self):
        """The database CHECK does not permit that value, so a candidate
        holding it could never have come from the real catalogue."""
        assert all(o.movement_pattern != "isolation" for o in CATALOGUE)

    def test_a_short_session_drops_accessories_not_the_main_lift(self):
        day = pg.split_for(1)[1][0]
        candidates = pg.eligible(CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT)
        chosen = pg.select_for_day(day, candidates, budget=3)
        assert len(chosen) == 3
        assert chosen[0].movement_pattern == day.patterns[0]

    def test_selection_is_deterministic(self):
        day = pg.split_for(4)[1][0]
        candidates = pg.eligible(CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT)
        first = pg.select_for_day(day, candidates, budget=5)
        second = pg.select_for_day(day, candidates, budget=5)
        assert first == second

    def test_an_empty_catalogue_yields_nothing_rather_than_raising(self):
        day = pg.split_for(1)[1][0]
        assert pg.select_for_day(day, (), budget=5) == ()


class TestPrescription:
    def _chosen(self):
        day = pg.split_for(1)[1][0]
        candidates = pg.eligible(CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT)
        return pg.select_for_day(day, candidates, budget=8)

    def test_order_index_is_dense_and_sequential(self):
        out = pg.prescribe(self._chosen())
        assert [p.order_index for p in out] == list(range(len(out)))

    def test_every_beginner_set_leaves_three_in_the_tank(self):
        for p in pg.prescribe(self._chosen()):
            assert p.target_rir == pg.BEGINNER_TARGET_RIR == 3

    def test_set_counts_are_conservative(self):
        chosen = self._chosen()
        for option, p in zip(chosen, pg.prescribe(chosen)):
            assert p.sets == pg.SETS_BY_CLASS[option.exercise_class]
            assert 2 <= p.sets <= 3

    def test_rep_range_comes_from_the_exercise_not_a_global_constant(self):
        """A goblet squat and a lateral raise do not belong in the same range."""
        chosen = self._chosen()
        by_id = {p.exercise_id: p for p in pg.prescribe(chosen)}
        if "db-curl" in by_id:
            assert (by_id["db-curl"].rep_min, by_id["db-curl"].rep_max) == (10, 15)
        assert (by_id["goblet-squat"].rep_min, by_id["goblet-squat"].rep_max) == (6, 10)

    def test_every_prescription_is_inside_the_database_check_bounds(self):
        """These mirror the CHECK constraints. A generator that produced an
        out-of-range row would be caught by the database, but only after the
        request had already got that far."""
        for p in pg.prescribe(self._chosen()):
            assert 1 <= p.sets <= 12
            assert 1 <= p.rep_min <= p.rep_max <= 50
            assert 0 <= p.target_rir <= 6
            assert 15 <= p.rest_seconds <= 600
            assert p.order_index >= 0

    def test_progression_is_double_progression(self):
        for p in pg.prescribe(self._chosen()):
            assert p.progression_rule == "double_progression"

    def test_no_prescription_carries_a_suggested_weight(self):
        """With no logged history there is no basis for a number, and
        inventing one is the confident-wrong answer this project refuses."""
        assert not any(
            hasattr(p, "suggested_weight_kg") and getattr(p, "suggested_weight_kg")
            for p in pg.prescribe(self._chosen())
        )

    def test_estimated_minutes_is_sane(self):
        out = pg.prescribe(self._chosen())
        assert 0 < pg.estimated_minutes(out) < 180
        assert pg.estimated_minutes(()) == 0


class TestEducation:
    def test_every_pattern_has_a_cue(self):
        for pattern in pg.PATTERN_PRIORITY:
            assert pattern in pg.FORM_CUES, pattern

    def test_education_reports_primary_and_secondary_muscles(self):
        edu = pg.education_for(CATALOGUE[0])
        assert edu.primary_muscle == "quads"
        assert edu.secondary_muscles == ("glutes",)
        assert edu.movement_pattern == "squat"
        assert edu.form_cue

    def test_an_unknown_pattern_still_gets_a_usable_cue(self):
        edu = pg.education_for(_opt("x", pattern="somersault"))
        assert edu.form_cue == pg._DEFAULT_CUE

    def test_no_cue_makes_a_medical_claim(self):
        """THE ONE THAT MATTERS HERE. These are coaching cues about movement.
        A cue that mentioned injury or pain would be giving medical advice in
        an app that has explicitly promised not to."""
        for pattern, cue in list(pg.FORM_CUES.items()) + [("_default", pg._DEFAULT_CUE)]:
            low = cue.lower()
            for banned in ("injur", "pain", "doctor", "physio", "medical",
                           "diagnos", "treat", "therapy", "heal", "safe from"):
                assert banned not in low, (pattern, banned)


class TestEndToEndDeterminism:
    def test_the_same_profile_generates_the_same_session_twice(self):
        """The property that makes a generated programme reviewable at all."""

        def build():
            _, templates = pg.split_for(4)
            candidates = pg.eligible(
                CATALOGUE, equipment=pg.beginner_equipment(["dumbbell", "bodyweight"])
            )
            return [
                pg.prescribe(
                    pg.select_for_day(t, candidates, pg.exercise_budget(60))
                )
                for t in templates
            ]

        assert build() == build()

    def test_a_different_profile_generates_a_different_session(self):
        """Determinism must not mean "always the same programme"."""
        _, templates = pg.split_for(4)
        candidates = pg.eligible(CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT)
        short = pg.prescribe(
            pg.select_for_day(templates[0], candidates, pg.exercise_budget(20))
        )
        long = pg.prescribe(
            pg.select_for_day(templates[0], candidates, pg.exercise_budget(120))
        )
        assert len(short) < len(long)


class TestNoTemplateSlotSelectsNothing:
    """The bug this exists for was silent, not loud.

    `_LOWER` asks for four slots, one of which is `carry`, and `carry` has
    resolved to zero candidates for as long as it has existed. The symptom
    was a lower-body day with three exercises instead of four -- no error, no
    log line, nothing anywhere saying a slot had gone unfilled.

    So the guard is on the property, not on any one pattern: every slot any
    template names must have at least one curated movement behind it, unless
    it is listed in `KNOWN_EMPTY_PATTERNS` with a written reason.
    """

    @staticmethod
    def _curated() -> list[tuple[str | None, bool]]:
        """(movement_pattern, is_isolation) for every curated movement."""
        from app.scripts.data.movement_attributes import MOVEMENT_ATTRIBUTES
        from app.services.movement import pattern_for

        out = []
        for detail, _profile, _uni in MOVEMENT_ATTRIBUTES.values():
            pattern = pattern_for(detail)
            out.append((pattern, pattern is None))
        return out

    def test_every_slot_is_backed_or_explicitly_known_empty(self):
        """ONE set equality, in both directions, because each direction
        catches a different mistake.

        Left-to-right: a slot quietly empties out and cannot hide inside the
        exemption. Right-to-left: the first curated loaded carry makes this
        fail with "delete carry from KNOWN_EMPTY_PATTERNS", so the exemption
        retires itself instead of outliving its reason.
        """
        assert pg.unfilled_slots(self._curated()) == pg.KNOWN_EMPTY_PATTERNS

    def test_the_exemption_only_names_slots_templates_actually_ask_for(self):
        """An exemption for a slot nothing requests is dead weight that would
        mask a real gap if a template later asked for it."""
        assert pg.KNOWN_EMPTY_PATTERNS <= pg.template_slots()

    def test_the_resolver_agrees_with_the_selector(self):
        """`unfilled_slots` must mean the same thing as `_fills_slot`, or the
        guard measures something the generator does not do."""
        candidates = pg.eligible(CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT)
        classified = [(o.movement_pattern, o.is_isolation) for o in candidates]
        empty = pg.unfilled_slots(classified)

        for slot in pg.template_slots():
            selectable = any(pg._fills_slot(o, slot) for o in candidates)
            assert selectable == (slot not in empty), slot

    def test_isolation_counts_by_the_flag_not_by_a_pattern_named_isolation(self):
        """The slot asks a different question from the pattern slots, and a
        resolver that compared `movement_pattern == "isolation"` would report
        the slot empty while the generator filled it happily."""
        only_isolation = [(None, True)]
        assert pg.ISOLATION_SLOT not in pg.unfilled_slots(only_isolation)

        no_isolation = [("squat", False)]
        assert pg.ISOLATION_SLOT in pg.unfilled_slots(no_isolation)


class TestGeneratorReadColumnsCarryInformation:
    """Cardinality guard: every column selection reads must VARY.

    THE CLASS OF BUG THIS EXISTS FOR, WHICH TOOK FOUR INSTANCES TO NAME.
    Auditing a column by counting NULLs asks "is it populated". That is not
    the same question as "does it carry information", and the gap between
    them has now hidden three separate defects:

        exercise_class          NULL on 154/154   -> caught by a null check
        secondary_muscles       empty arrays      -> needed an emptiness check
        default_rest_seconds    120 on 154/154    -> passed BOTH of those
        fatigue_cost              3 on 154/154    -> passed BOTH of those

    A column with one distinct value is decorative. It is NOT NULL, it is
    fully populated, and it cannot influence any decision -- which is
    exactly how `_sort_key` came to be ordering a 154-movement catalogue
    alphabetically while looking like it sorted by class and fatigue.

    The check is `count(DISTINCT col) > 1`, and it belongs in the fixture
    too: a fixture whose columns all vary cannot reproduce a production
    catalogue whose columns do not. Fixtures supply what production lacks,
    and a fixture uniformly better-formed than production is a wish.
    """

    #: Every field of `ExerciseOption` that participates in a selection or
    #: prescription decision. `exercise_id` is excluded: it is a tie-break
    #: of last resort and is unique by construction.
    DECISION_FIELDS = (
        "name",
        "equipment",
        "muscle_group",
        "movement_pattern",
        "is_isolation",
        "default_rep_min",
        "default_rep_max",
    )

    def test_every_decision_field_varies_across_the_fixture(self):
        for field in self.DECISION_FIELDS:
            values = {getattr(o, field) for o in CATALOGUE}
            assert len(values) > 1, (
                f"{field!r} has one distinct value across the fixture "
                f"({values!r}). A column that cannot vary cannot influence "
                f"a decision, and a test using it proves nothing."
            )

    def test_the_fixture_contains_a_row_for_every_pattern_and_isolation(self):
        """Shape guard: the fixture must be able to fill each slot."""
        patterns = {o.movement_pattern for o in CATALOGUE}
        assert None in patterns, (
            "no isolation row: production allows a NULL movement_pattern, "
            "so the fixture must contain one or the isolation slot is never "
            "exercised"
        )
        for slot in pg.template_slots():
            if slot in pg.KNOWN_EMPTY_PATTERNS or slot == pg.ISOLATION_SLOT:
                continue
            assert any(
                pg._fills_slot(o, slot) for o in CATALOGUE
            ), f"fixture cannot fill the {slot!r} slot"

    def test_fatigue_cost_is_not_a_selection_input(self):
        """It is constant in production, so selection must not depend on it.

        Deliberately asserts the ABSENCE of a dependency. If someone puts
        `fatigue_cost` back into `_sort_key`, this fails and points them at
        the measurement that would make the column real.
        """
        varied = tuple(
            pg.ExerciseOption(
                **{
                    **o.__dict__,
                    "fatigue_cost": 5 if i % 2 else 1,
                }
            )
            for i, o in enumerate(CATALOGUE)
        )
        assert [o.exercise_id for o in pg.eligible(
            varied, equipment=pg.BEGINNER_EQUIPMENT
        )] == [o.exercise_id for o in pg.eligible(
            CATALOGUE, equipment=pg.BEGINNER_EQUIPMENT
        )], "selection changed when only fatigue_cost changed"
