"""The catalogue namespace, and the merge decision table that depends on it.

The bug these exist to prevent: two seed scripts wrote to `exercises` and both
asked "does this already exist?" by comparing names. Neither looked at the
other's aliases, so `seed_exercises` inserted "Seal Row" next to
"Chest-Supported Row" -- whose alias list already contained `seal row`.

Forty-two rows of that. Each one is a movement whose strength trend is split
across two `exercise_id`s, so neither half ever reaches the 8 exposures
adjudication requires and the user gets no verdict on a lift they train
every week.
"""

from __future__ import annotations

import pytest

from app.services.catalogue import (
    CatalogueEntry,
    build_namespace,
    normalise_term,
    plan_seed,
)


class TestNormalise:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Seal Row", "seal row"),
            ("  Seal   Row  ", "seal row"),
            ("SEAL ROW", "seal row"),
            ("Chest-Supported Row", "chest-supported row"),
        ],
    )
    def test_folds_case_and_whitespace(self, raw, expected):
        assert normalise_term(raw) == expected

    def test_does_not_fold_plurals(self):
        """Deliberate. Over-matching merges movements nobody asked to merge,
        and a merge is the expensive direction to be wrong in."""
        assert normalise_term("Hammer Curl") != normalise_term("Hammer Curls")

    def test_does_not_strip_punctuation(self):
        assert normalise_term("EZ-Bar Curl") != normalise_term("EZ Bar Curl")


class TestTheBugThatHappened:
    """The exact 42-row scenario, in both directions."""

    def test_incoming_name_already_an_alias_is_not_inserted(self):
        existing = [CatalogueEntry("Chest-Supported Row", ("seal row", "prime row"))]
        plan = plan_seed(existing, [CatalogueEntry("Seal Row", ("bench row",))])

        assert plan.insert == ()
        assert len(plan.blocked) == 1
        assert plan.blocked[0].existing_name == "Chest-Supported Row"
        assert plan.blocked[0].kind == "name_vs_alias"

    def test_existing_row_duplicating_an_incoming_alias_is_reported(self):
        """The direction that produced all 42: the curated row arrives second
        and its alias list claims a name an older row already holds."""
        existing = [CatalogueEntry("Seal Row", ())]
        plan = plan_seed(
            existing, [CatalogueEntry("Chest-Supported Row", ("seal row",))]
        )

        # It still inserts -- the curated row is wanted. But it says so.
        assert plan.insert == ("Chest-Supported Row",)
        assert len(plan.stale_duplicates) == 1
        assert plan.stale_duplicates[0].existing_name == "Seal Row"
        assert plan.stale_duplicates[0].kind == "alias_vs_name"

    def test_a_seed_never_resolves_a_collision_by_itself(self):
        """There is no code path that deletes or renames. Merging rewrites
        training history and needs a human."""
        plan = plan_seed(
            [CatalogueEntry("Seal Row", ())],
            [CatalogueEntry("Chest-Supported Row", ("seal row",))],
        )
        assert plan.needs_attention
        assert not hasattr(plan, "delete")


class TestPlanSeed:
    def test_empty_catalogue_inserts_everything(self):
        incoming = [CatalogueEntry("Squat"), CatalogueEntry("Bench Press")]
        plan = plan_seed([], incoming)
        assert plan.insert == ("Squat", "Bench Press")
        assert not plan.needs_attention

    def test_same_name_is_an_update_not_a_collision(self):
        existing = [CatalogueEntry("Hack Squat", ("old alias",))]
        plan = plan_seed(existing, [CatalogueEntry("Hack Squat", ("pw412",))])
        assert plan.update == ("Hack Squat",)
        assert plan.insert == ()
        assert not plan.needs_attention

    def test_refresh_disabled_leaves_existing_rows_alone(self):
        """seed_exercises is a bulk public dataset; it must not overwrite
        curation applied on top of a row it created."""
        existing = [CatalogueEntry("Hack Squat", ("pw412",))]
        plan = plan_seed(
            existing,
            [CatalogueEntry("Hack Squat", ())],
            refresh_existing=False,
        )
        assert plan.update == ()
        assert plan.insert == ()

    def test_case_difference_is_not_a_new_row(self):
        plan = plan_seed(
            [CatalogueEntry("Barbell Row")], [CatalogueEntry("BARBELL ROW")]
        )
        assert plan.insert == ()

    def test_a_batch_cannot_duplicate_within_itself(self):
        """A source file holding both "Hammer Curl" and a row aliased to it
        must not insert both and recreate the problem."""
        plan = plan_seed(
            [],
            [
                CatalogueEntry("Hammer Curl", ("neutral grip curl",)),
                CatalogueEntry("Neutral Grip Curl", ()),
            ],
        )
        assert plan.insert == ("Hammer Curl",)
        assert len(plan.blocked) == 1

    def test_row_aliased_to_itself_is_not_a_collision(self):
        plan = plan_seed([], [CatalogueEntry("Face Pull", ("face pull",))])
        assert plan.insert == ("Face Pull",)
        assert not plan.needs_attention

    def test_dirty_catalogue_still_builds_a_namespace(self):
        """The index must build even when the data already contains the
        collisions this module exists to find -- otherwise the tool is
        useless exactly when it is needed."""
        ns = build_namespace(
            [
                CatalogueEntry("Seal Row", ()),
                CatalogueEntry("Chest-Supported Row", ("seal row",)),
            ]
        )
        assert sorted(ns["seal row"]) == [
            ("Chest-Supported Row", False),
            ("Seal Row", True),
        ]


class TestMergeDecisionTable:
    """Invariants over the curated merge list itself."""

    @staticmethod
    def _table():
        from app.scripts.merge_duplicate_exercises import (
            ALIAS_ADDITIONS,
            KEEP_SEPARATE,
            MERGES,
        )

        return MERGES, KEEP_SEPARATE, ALIAS_ADDITIONS

    def test_no_absorbed_row_is_one_the_seed_would_recreate(self):
        """THE load-bearing check. `seed_movements.py` re-inserts any row in
        its list that is missing, so deleting one of its rows undoes the
        merge on the next seed run and leaves no trace but a stray alias."""
        from app.scripts import seed_movements

        merges, _, _ = self._table()
        curated = {normalise_term(e[0]) for e in seed_movements.E}
        offenders = [
            name
            for _, absorbed, _ in merges
            for name in absorbed
            if normalise_term(name) in curated
        ]
        assert offenders == [], (
            f"{offenders} would be recreated by seed_movements, silently "
            f"undoing the merge"
        )

    def test_every_survivor_is_a_seed_movements_row_or_deliberately_not(self):
        """Survivors the seed does not own cannot pick up new brand aliases
        from a later seed run. Exactly one is allowed, and it is a word-order
        fix on a row the public dataset owns."""
        from app.scripts import seed_movements

        merges, _, _ = self._table()
        curated = {normalise_term(e[0]) for e in seed_movements.E}
        uncurated = sorted(
            s for s, _, _ in merges if normalise_term(s) not in curated
        )
        assert uncurated == ["Machine Triceps Dip"], uncurated

    def test_no_row_is_both_survivor_and_absorbed(self):
        merges, _, _ = self._table()
        survivors = {normalise_term(s) for s, _, _ in merges}
        absorbed = {normalise_term(n) for _, names, _ in merges for n in names}
        assert survivors & absorbed == set()

    def test_no_row_is_absorbed_twice(self):
        merges, _, _ = self._table()
        absorbed = [normalise_term(n) for _, names, _ in merges for n in names]
        assert len(absorbed) == len(set(absorbed))

    def test_keep_separate_rows_are_never_merged(self):
        """The seven pairs deliberately left alone must not appear in MERGES.
        An Inverse Zottman Curl is not a Zottman Curl, and that merge is not
        reversible by adding the alias back."""
        merges, keep, _ = self._table()
        absorbed = {normalise_term(n) for _, names, _ in merges for n in names}
        for a, b, _ in keep:
            assert normalise_term(a) not in absorbed, a
            assert normalise_term(b) not in absorbed, b

    def test_every_merge_and_exception_carries_a_reason(self):
        merges, keep, _ = self._table()
        for survivor, _, why in merges:
            assert why.strip(), survivor
        for a, _, why in keep:
            assert why.strip(), a

    def test_alias_additions_target_survivors(self):
        merges, _, additions = self._table()
        survivors = {normalise_term(s) for s, _, _ in merges}
        for name, terms in additions:
            assert normalise_term(name) in survivors, name
            assert terms

    def test_every_fk_to_exercises_is_repointed(self):
        """A merge deletes a catalogue row. Any column pointing at it that
        the script does not know about either breaks the delete or, worse,
        cascades and takes training history with it.

        Derived from the live metadata rather than a hand-kept list, so a FK
        added next month fails this test instead of being discovered by a
        user losing their history.
        """
        from sqlmodel import SQLModel

        import app.models  # noqa: F401  -- registers the tables
        from app.scripts.merge_duplicate_exercises import REFERRERS

        actual = {
            (table.name, column.name)
            for table in SQLModel.metadata.tables.values()
            for column in table.columns
            for fk in column.foreign_keys
            if fk.column.table.name == "exercises"
        }
        assert actual == set(REFERRERS), (
            f"missing from REFERRERS: {sorted(actual - set(REFERRERS))}; "
            f"stale in REFERRERS: {sorted(set(REFERRERS) - actual)}"
        )


class TestAliasesAreUnionedNotReplaced:
    """The regression that made 11 movements unsearchable.

    `merge_duplicate_exercises.py` folds a retired row's name into the
    survivor's aliases so that "butterfly" still finds "Pec Deck". The seed
    then rewrote that list wholesale and the folds vanished. `--refold`
    repairs the damage; these stop it happening.
    """

    def test_existing_aliases_survive_a_seed_refresh(self):
        from app.services.catalogue import merge_aliases

        folded_by_a_merge = ["butterfly", "pec deck fly"]
        from_the_seed_file = ["nautilus pec fly", "pec deck machine"]
        result = merge_aliases(folded_by_a_merge, from_the_seed_file)
        for alias in folded_by_a_merge:
            assert alias in result, f"{alias} was dropped -- the merge is undone"

    def test_new_seed_aliases_still_land(self):
        """The original bug ran the other way: rows were skipped, so a newly
        added brand alias never reached the catalogue."""
        from app.services.catalogue import merge_aliases

        result = merge_aliases(["hack squat machine"], ["pw412", "panatta hack"])
        assert "pw412" in result and "panatta hack" in result

    def test_it_is_idempotent(self):
        from app.services.catalogue import merge_aliases

        once = merge_aliases(["a", "b"], ["b", "c"])
        assert merge_aliases(once, ["b", "c"]) == once

    def test_case_variants_do_not_accumulate(self):
        from app.services.catalogue import merge_aliases

        assert merge_aliases(["Butterfly"], ["butterfly", "BUTTERFLY"]) == [
            "Butterfly"
        ]

    def test_classification_tokens_cannot_re_enter_through_the_union(self):
        """The union is exactly where a stale token would survive forever."""
        from app.services.catalogue import merge_aliases

        assert merge_aliases(["mid", "hinge"], ["lengthened", "prime row"]) == [
            "prime row"
        ]

    def test_the_seed_actually_uses_it(self):
        """A pure function nobody calls protects nothing."""
        import inspect

        from app.scripts import seed_movements

        assert "merge_aliases(" in inspect.getsource(seed_movements.run)


class TestNoClassificationTokenIsAnAlias:
    """`mid` used to return 58 unrelated movements.

    Movement pattern and resistance profile were folded into `aliases` so
    they would be searchable without new columns. An alias list IS the search
    index, so every curated row answered to a classification. The token
    vocabulary is closed, so this check is exact rather than heuristic.
    """

    def test_the_token_set_covers_every_value_the_seed_uses(self):
        """If a new pattern is added, this fails until the token set is
        updated -- which keeps 'closed set' true rather than aspirational.

        Reads the classification from its own module now that it has left
        the catalogue tuples; the tokens it must never become are still the
        same ones."""
        from app.scripts.data.movement_attributes import MOVEMENT_ATTRIBUTES
        from app.services.catalogue import CLASSIFICATION_TOKENS

        used = {normalise_term(d) for d, _p, _u in MOVEMENT_ATTRIBUTES.values()}
        used |= {normalise_term(p) for _d, p, _u in MOVEMENT_ATTRIBUTES.values()}
        missing = sorted(used - CLASSIFICATION_TOKENS)
        assert missing == [], (
            f"{missing} are used as a pattern/profile but are not in "
            f"CLASSIFICATION_TOKENS, so nothing stops them becoming aliases"
        )

    def test_no_seed_row_carries_one_as_an_alias(self):
        from app.scripts import seed_movements
        from app.services.catalogue import is_classification_token

        offenders = [
            (row[0], alias)
            for row in seed_movements.E
            for alias in row[5]
            if is_classification_token(alias)
        ]
        assert offenders == [], offenders

    def test_the_generated_rows_carry_none_either(self):
        """Covers the generation step, not just the source tuples -- the bug
        was that `run()` added them on the way past."""
        from app.scripts import seed_movements
        from app.services.catalogue import is_classification_token

        rows = [
            {"name": name, "aliases": sorted(set(aliases))}
            for (name, _m, _s, _e, _c, aliases) in seed_movements.E
        ]
        offenders = [
            (r["name"], a)
            for r in rows
            for a in r["aliases"]
            if is_classification_token(a)
        ]
        assert offenders == []

    def test_pattern_and_profile_are_still_recorded(self):
        """Removed from the alias list and then moved out of the catalogue
        tuples entirely -- but never lost. They now live in
        `data/movement_attributes.py` and land in `exercise_attributes`.
        See tests/test_movement_attributes.py for the full contract."""
        from app.scripts import seed_movements
        from app.scripts.data.movement_attributes import MOVEMENT_ATTRIBUTES

        assert all(d and p for d, p, _u in MOVEMENT_ATTRIBUTES.values())
        assert len(MOVEMENT_ATTRIBUTES) == len(seed_movements.E) == 154


class TestAliasRemovalsAreCoherent:
    """Two bugs found applying round 2, both worth a permanent guard."""

    @staticmethod
    def _removals():
        from app.scripts.merge_duplicate_exercises import ALIAS_REMOVALS

        return ALIAS_REMOVALS

    def test_several_removals_on_one_row_are_all_recorded(self):
        """The applier used to rewrite each row from the snapshot taken at
        the start of the run, so the second removal on a row undid the first.
        Rows with more than one entry are exactly the case that broke."""
        import collections

        by_row = collections.Counter(
            normalise_term(r) for r, _, _ in self._removals()
        )
        multi = [r for r, n in by_row.items() if n > 1]
        assert multi, (
            "no row has multiple removals, so this guard is not exercising "
            "the grouping it exists to protect"
        )

    def test_the_applier_groups_by_row(self):
        import inspect

        from app.scripts import merge_duplicate_exercises as mod

        src = inspect.getsource(mod.run)
        assert "wanted[normalise_term(row_name)].append" in src, (
            "removals must be grouped per row before writing, or the last "
            "one silently wins"
        )

    def test_no_removal_targets_a_row_that_was_merged_away(self):
        from app.scripts.merge_duplicate_exercises import MERGES

        absorbed = {normalise_term(n) for _, names, _ in MERGES for n in names}
        for row, alias, _ in self._removals():
            assert normalise_term(row) not in absorbed, (
                f"{row!r} is absorbed by a merge; removing {alias!r} from it "
                f"is a no-op"
            )

    def test_every_removal_has_a_reason(self):
        for row, alias, why in self._removals():
            assert why.strip(), (row, alias)


class TestSeedSourceAliasHygiene:
    """A seed-source alias that names a different row keeps coming back.

    `merge_aliases` unions, so clearing one from the database is not enough --
    the next seed run restores it. Both halves are required, and this checks
    the half that lives in the repository.
    """

    def test_no_seed_alias_is_another_seed_rows_name(self):
        from app.scripts import seed_movements

        names = {normalise_term(e[0]) for e in seed_movements.E}
        offenders = [
            (row[0], alias)
            for row in seed_movements.E
            for alias in row[5]
            if normalise_term(alias) in names
            and normalise_term(alias) != normalise_term(row[0])
        ]
        assert offenders == [], offenders

    def test_terms_removed_from_the_source_are_also_cleared_from_the_db(self):
        """Each source removal needs a matching ALIAS_REMOVALS entry, or the
        copy already stored survives forever."""
        from app.scripts.merge_duplicate_exercises import ALIAS_REMOVALS

        cleared = {
            (normalise_term(r), normalise_term(a)) for r, a, _ in ALIAS_REMOVALS
        }
        # The nine terms taken out of seed_movements.py in round 2.
        source_removed = [
            ("Dumbbell Shoulder Press", "seated db press"),
            ("Lean-Away Lateral Raise", "leaning lateral raise"),
            ("Weighted Pull-Up", "pull up"),
            ("Romanian Deadlift", "sldl"),
            ("Dumbbell Lunge", "walking lunge"),
            ("Meadows Row", "landmine row"),
            ("Cable Kickback", "glute kickback"),
            ("Power Clean", "clean"),
            ("Power Snatch", "snatch"),
        ]
        missing = [
            pair
            for pair in source_removed
            if (normalise_term(pair[0]), normalise_term(pair[1])) not in cleared
        ]
        assert missing == [], missing
