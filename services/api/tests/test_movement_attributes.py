"""Movement classification: the eight, the nineteen, and what has neither.

The decision these protect: an eight-pattern taxonomy describes COMPOUND
lifts, and roughly a third of the catalogue is isolation work that satisfies
none of them. `movement_pattern` is therefore nullable, and NULL is an
answer rather than a hole. Forcing a lateral raise into `v-push` would put a
false value into a field generation trusts, and generation would then believe
it had covered a pattern it had not.
"""

from __future__ import annotations

import pytest

from app.scripts.data.movement_attributes import MOVEMENT_ATTRIBUTES
from app.services.movement import (
    MOVEMENT_DETAILS,
    MOVEMENT_PATTERNS,
    PATTERN_FOR_DETAIL,
    RESISTANCE_PROFILES,
    is_isolation_detail,
    pattern_for,
)


class TestTheMapping:
    def test_every_detail_maps_somewhere(self):
        """Total over the nineteen. A detail with no entry would raise at
        seed time, but only for a catalogue that happens to use it."""
        assert set(PATTERN_FOR_DETAIL) == set(MOVEMENT_DETAILS)

    def test_every_mapped_pattern_is_in_the_vocabulary(self):
        for detail, pattern in PATTERN_FOR_DETAIL.items():
            assert pattern is None or pattern in MOVEMENT_PATTERNS, detail

    def test_every_pattern_is_reachable(self):
        """A pattern nothing maps to is a value the schema allows and the
        data can never contain."""
        assert set(PATTERN_FOR_DETAIL.values()) - {None} == set(MOVEMENT_PATTERNS)

    @pytest.mark.parametrize(
        "detail,expected",
        [
            ("squat", "squat"),
            ("hinge", "hinge"),
            ("lunge", "lunge"),
            ("h-press", "h-push"),
            ("v-press", "v-push"),
            ("h-pull", "h-pull"),
            ("v-pull", "v-pull"),
            ("trunk-flex", "core"),
            ("anti-ext", "core"),
            ("anti-rot", "core"),
            ("pull", "hinge"),
        ],
    )
    def test_the_compound_mappings(self, detail, expected):
        assert pattern_for(detail) == expected

    def test_olympic_pulls_are_hinges(self):
        """A power clean is hip-dominant and hinge-derived. The explosive
        quality is real but it is not a pattern; putting it here would
        distort the field rather than record it."""
        assert pattern_for("pull") == "hinge"

    @pytest.mark.parametrize(
        "detail",
        [
            "elbow-flex",
            "elbow-ext",
            "lateral",
            "calf",
            "knee-ext",
            "knee-flex",
            "shrug",
            "abduction",
        ],
    )
    def test_isolation_details_have_no_pattern(self, detail):
        """"Which movement pattern does a bicep curl satisfy" has no true
        answer. NULL says so."""
        assert pattern_for(detail) is None
        assert is_isolation_detail(detail)

    def test_a_lateral_raise_is_not_a_vertical_press(self):
        """Named explicitly because it is the tempting wrong answer."""
        assert pattern_for("lateral") != "v-push"
        assert pattern_for("lateral") is None

    def test_isolation_is_exactly_the_set_with_no_pattern(self):
        for detail in MOVEMENT_DETAILS:
            assert is_isolation_detail(detail) == (pattern_for(detail) is None)

    def test_an_unknown_detail_raises_rather_than_returning_none(self):
        """"I do not recognise this" and "this has no pattern" are different
        facts. Collapsing them lets a typo become an isolation row."""
        with pytest.raises(KeyError):
            pattern_for("h-push")  # a PATTERN, not a detail -- easy to confuse
        with pytest.raises(KeyError):
            pattern_for("bench")


class TestTheCuratedData:
    def test_every_catalogue_movement_is_classified(self):
        """The seed and the classification must agree about which movements
        exist. Two files, one fact -- so this is the guard against them
        drifting the way the two seed scripts did."""
        from app.scripts import seed_movements

        catalogue = {e[0] for e in seed_movements.E}
        classified = set(MOVEMENT_ATTRIBUTES)
        assert catalogue - classified == set(), "classified nowhere"
        assert classified - catalogue == set(), "classified but not in the catalogue"

    def test_the_seed_no_longer_carries_classification(self):
        """It was moved out, not copied out. A second copy would drift."""
        from app.scripts import seed_movements

        assert len(seed_movements.E[0]) == 6, seed_movements.E[0]

    def test_every_detail_and_profile_is_in_vocabulary(self):
        for name, (detail, profile, _uni) in MOVEMENT_ATTRIBUTES.items():
            assert detail in MOVEMENT_DETAILS, (name, detail)
            assert profile in RESISTANCE_PROFILES, (name, profile)

    def test_roughly_a_third_has_no_pattern(self):
        """The number that made nullable the right call. If a change pushes
        this to zero, someone has started forcing isolation into patterns."""
        isolation = [
            n for n, (d, _, _) in MOVEMENT_ATTRIBUTES.items() if is_isolation_detail(d)
        ]
        assert 30 <= len(isolation) <= 60, len(isolation)
        assert "Dumbbell Lateral Raise" in isolation

    #: Declared in the vocabulary, with nothing curated behind it yet.
    #:
    #: The catalogue holds four carries -- Farmer's Carry, Farmer's Walk,
    #: Rickshaw Carry, Yoke Walk -- but none is among the 154 curated rows,
    #: so none has an `exercise_attributes` row, and generation inner-joins
    #: that table. Two templates ask for a `carry` slot and currently select
    #: nothing from it.
    #:
    #: This exemption RETIRES ITSELF: the test below fails the moment
    #: somebody curates a carry, which is the prompt to delete this set.
    UNPOPULATED = {"carry"}

    def test_compound_patterns_are_all_populated(self):
        """Every pattern has real movements behind it, so a session-coverage
        question can actually be answered -- except the ones named above."""
        from collections import Counter

        counts = Counter(
            pattern_for(d) for d, _, _ in MOVEMENT_ATTRIBUTES.values()
        )
        for pattern in MOVEMENT_PATTERNS:
            if pattern in self.UNPOPULATED:
                continue
            assert counts[pattern] > 0, f"no movements for {pattern}"

    def test_the_unpopulated_set_is_exactly_right(self):
        """Guards the exemption in both directions.

        If a carry gets curated, this fails and says to delete the
        exemption. If another pattern quietly empties out, this fails too --
        so the exemption cannot grow into a place where gaps hide.
        """
        from collections import Counter

        counts = Counter(
            pattern_for(d) for d, _, _ in MOVEMENT_ATTRIBUTES.values()
        )
        empty = {p for p in MOVEMENT_PATTERNS if counts[p] == 0}
        assert empty == self.UNPOPULATED, (
            f"unpopulated patterns are {sorted(empty)}, "
            f"the exemption lists {sorted(self.UNPOPULATED)}"
        )


class TestTheSchemaAgreesWithTheVocabulary:
    """The CHECK constraints and the Python vocabularies encode one fact."""

    @staticmethod
    def _check(name: str) -> str:
        from app.models import ExerciseAttributes

        for c in ExerciseAttributes.__table__.constraints:
            if getattr(c, "name", None) == name:
                return str(c.sqltext)
        raise AssertionError(f"no constraint named {name}")

    def test_pattern_check_lists_every_pattern(self):
        sql = self._check("ck_exattr_movement_pattern")
        for pattern in MOVEMENT_PATTERNS:
            assert f"'{pattern}'" in sql, pattern
        assert "IS NULL" in sql, "the pattern must be allowed to be NULL"

    def test_detail_check_lists_every_detail(self):
        sql = self._check("ck_exattr_movement_detail")
        for detail in MOVEMENT_DETAILS:
            assert f"'{detail}'" in sql, detail

    def test_profile_check_lists_the_three(self):
        sql = self._check("ck_exattr_resistance_profile")
        for profile in RESISTANCE_PROFILES:
            assert f"'{profile}'" in sql, profile

    def test_isolation_cannot_disagree_with_the_pattern(self):
        """Both derive from one fact. Without this a row could claim to be a
        compound with no pattern, which generation reads as a coverage gap."""
        sql = self._check("ck_exattr_isolation_matches_pattern")
        assert "movement_pattern IS NULL" in sql
        assert "is_isolation" in sql

    def test_classification_does_not_require_a_rep_range(self):
        """These were NOT NULL, which meant nothing could be classified
        without also inventing a prescription for it."""
        from app.models import ExerciseAttributes

        cols = ExerciseAttributes.__table__.columns
        assert cols["default_rep_min"].nullable
        assert cols["default_rep_max"].nullable
        assert cols["movement_detail"].nullable is False
        assert cols["movement_pattern"].nullable is True


class TestProgrammableIsEnforcedNotRemembered:
    """`default_rep_min` and `default_rep_max` became nullable, so an INNER
    JOIN on `exercise_attributes` is no longer proof a movement can be
    prescribed. The guarantee is restored by a view rather than by a comment
    telling the next person to add a predicate.
    """

    def test_the_view_filters_on_both_rep_columns(self):
        from app.models import PROGRAMMABLE_EXERCISES_VIEW

        sql = " ".join(PROGRAMMABLE_EXERCISES_VIEW.split()).lower()
        assert "default_rep_min is not null" in sql
        assert "default_rep_max is not null" in sql
        assert "join exercise_attributes" in sql

    def test_some_migration_defines_the_view_the_harness_runs(self):
        """One fact in two homes: a migration owns the frozen literal that
        built the real database, and `models.py` owns the copy the test
        harness executes after `create_all` (views are not in metadata).
        Something has to check they still match.

        NAMED BY CONTENT, NOT BY REVISION. This used to point at
        `c9e58a2d41bf` by filename, which meant the next migration to touch
        the view -- `e2b6c81d4a37`, adding `exercise_class` -- broke the test
        even though nothing had actually drifted. Searching every migration
        keeps the real property: the harness must run a view that some
        migration actually created. If `models.py` is edited without a
        migration, no file contains it and this still fails.
        """
        import pathlib

        import app.models as models

        versions = (
            pathlib.Path(models.__file__).resolve().parents[1]
            / "alembic"
            / "versions"
        )
        body = " ".join(models.PROGRAMMABLE_EXERCISES_VIEW.split())
        defining = [
            p.name
            for p in versions.glob("*.py")
            if body in " ".join(p.read_text(encoding="utf-8").split())
        ]
        assert defining, (
            "no migration defines the view in models.py -- either the model "
            "was edited without a migration, or the two have drifted"
        )

    def test_the_rep_range_is_all_or_nothing(self):
        """A half-populated range is worse than none: it looks like data."""
        from app.models import ExerciseAttributes

        names = {
            getattr(c, "name", None)
            for c in ExerciseAttributes.__table__.constraints
        }
        assert "ck_exattr_rep_range_paired" in names
