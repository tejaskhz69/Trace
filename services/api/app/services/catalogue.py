"""Catalogue namespace arithmetic -- who already owns a name.

WHY THIS EXISTS
---------------
`seed_exercises.py` and `seed_movements.py` both write to `exercises`, and
both decided "does this already exist?" by comparing names. Neither looked at
the other's aliases. So `seed_exercises` inserted a row called "Seal Row"
even though `seal row` was already an alias of "Chest-Supported Row", and the
catalogue ended up with 42 rows whose name was another row's alias.

That is not cosmetic. Adjudication needs MIN_SESSIONS exposures on ONE
`exercise_id` before it will return a verdict. A user who logs "Seal Row" on
Monday and "Chest-Supported Row" on Thursday is doing one movement and
building two half-height trends, neither of which ever reaches the bar. The
duplicate silently disables the strength engine for that movement.

THE FIX
-------
One namespace, checked by both seeds before they insert. A name is taken if
any existing row uses it as a name *or* as an alias, and an incoming row's
aliases are checked too -- because the collision runs in both directions:

    incoming.name  collides with existing.name   -> update the row in place
    incoming.name  collides with existing.alias  -> the incoming row is a
                                                    duplicate of a row that
                                                    already exists
    incoming.alias collides with existing.name   -> an existing row is a
                                                    duplicate of the incoming
                                                    one (this is the direction
                                                    that produced all 42)

WHAT THIS MODULE WILL NOT DO
----------------------------
It will not delete or merge anything. Collisions are *reported*, and a seed
run that hits one says so and leaves the database alone. Merging rows rewrites
`set_logs.exercise_id`, which is somebody's training history; that decision
belongs to a human running `merge_duplicate_exercises.py`, not to a data
import that happened to run at 3am.

Pure functions, no I/O -- per CLAUDE.md, and so the collision rules can be
tested exhaustively without a database.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "CLASSIFICATION_TOKENS",
    "CatalogueEntry",
    "Collision",
    "SeedPlan",
    "build_namespace",
    "is_classification_token",
    "merge_aliases",
    "normalise_term",
    "plan_seed",
]


def normalise_term(term: str) -> str:
    """Fold a name or alias to its comparison key.

    Case and internal whitespace only. Deliberately NOT stemming or stripping
    equipment words: a normaliser aggressive enough to collide "Hammer Curl"
    with "Hammer Curls" would also collide movements that are genuinely
    different. Under-matching leaves a duplicate for a human to find;
    over-matching merges two exercises nobody asked to merge, and merges are
    the expensive direction to be wrong in.
    """
    return " ".join(term.strip().lower().split())


#: Movement patterns and resistance profiles, as `seed_movements.py` names
#: them. THESE ARE CLASSIFICATIONS, NOT ALIASES, AND MUST NEVER APPEAR IN AN
#: ALIAS LIST.
#:
#: They were folded into `aliases` originally so that "hinge" and "lengthened"
#: were searchable without new columns. The cost was that all 155 curated rows
#: answered to a classification token: searching "mid" returned 58 unrelated
#: movements, and "squat" returned the leg press. An alias list IS the search
#: index for the exercise/station split, and that split only works if finding
#: your machine returns your machine.
#:
#: The set is closed -- it is exactly the vocabulary `seed_movements.E` uses --
#: so the guard against regression can be exact rather than heuristic.
CLASSIFICATION_TOKENS = frozenset(
    {
        # movement patterns (19)
        "squat", "lunge", "hinge", "h-press", "v-press", "h-pull", "v-pull",
        "lateral", "elbow-flex", "elbow-ext", "knee-ext", "knee-flex", "calf",
        "abduction", "shrug", "trunk-flex", "anti-ext", "anti-rot", "pull",
        # resistance profiles (3)
        "mid", "lengthened", "shortened",
    }
)


def is_classification_token(term: str) -> bool:
    """True when `term` is a bare classification, not a name anyone types."""
    return normalise_term(term) in CLASSIFICATION_TOKENS


@dataclass(frozen=True)
class CatalogueEntry:
    """One catalogue row, reduced to the fields the namespace cares about."""

    name: str
    aliases: tuple[str, ...] = ()

    def terms(self) -> tuple[str, ...]:
        """Every string by which this row can be found."""
        return (normalise_term(self.name),) + tuple(
            normalise_term(a) for a in self.aliases
        )


#: Which side of the pair carried the colliding term.
CollisionKind = Literal[
    "name_vs_alias",  # the incoming row already exists under another name
    "alias_vs_name",  # an existing row is a duplicate of the incoming row
]


@dataclass(frozen=True)
class Collision:
    incoming_name: str
    existing_name: str
    term: str
    kind: CollisionKind

    def describe(self) -> str:
        if self.kind == "name_vs_alias":
            return (
                f"{self.incoming_name!r} is already an alias of "
                f"{self.existing_name!r} -- not inserting a second row"
            )
        return (
            f"existing row {self.existing_name!r} is claimed as an alias "
            f"({self.term!r}) of incoming {self.incoming_name!r} -- "
            f"two rows for one movement"
        )


@dataclass(frozen=True)
class SeedPlan:
    """What a seed run should do, decided before it touches the database."""

    insert: tuple[str, ...] = ()
    update: tuple[str, ...] = ()
    #: Incoming rows withheld because the movement already exists.
    blocked: tuple[Collision, ...] = ()
    #: Rows already in the catalogue that duplicate an incoming row. These
    #: need a human and `merge_duplicate_exercises.py`; a seed cannot fix
    #: them, because fixing them means deleting a row.
    stale_duplicates: tuple[Collision, ...] = ()

    @property
    def needs_attention(self) -> bool:
        return bool(self.blocked or self.stale_duplicates)


def build_namespace(
    existing: Iterable[CatalogueEntry],
) -> dict[str, list[tuple[str, bool]]]:
    """term -> [(owning row name, term is that row's own name)].

    A list rather than a single owner, because the catalogue can already
    contain the collisions this module exists to find. Refusing to build the
    index just because the data is dirty would make the tool useless exactly
    when it is needed.
    """
    ns: dict[str, list[tuple[str, bool]]] = {}
    for row in existing:
        canonical = normalise_term(row.name)
        for term in row.terms():
            ns.setdefault(term, []).append((row.name, term == canonical))
    return ns


def plan_seed(
    existing: Sequence[CatalogueEntry],
    incoming: Sequence[CatalogueEntry],
    *,
    refresh_existing: bool = True,
) -> SeedPlan:
    """Partition `incoming` into insert / update / withheld.

    `refresh_existing` is the difference between the two seeds today.
    `seed_movements` rewrites the metadata of rows it owns, so that a newly
    added brand alias actually lands. `seed_exercises` leaves existing rows
    alone -- it is a bulk public dataset and must not overwrite curation.
    """
    ns = build_namespace(existing)
    by_norm_name = {normalise_term(r.name): r.name for r in existing}

    insert: list[str] = []
    update: list[str] = []
    blocked: list[Collision] = []
    stale: list[Collision] = []

    # Rows inserted earlier in THIS run also claim their terms, or a source
    # file containing both "Hammer Curl" and "Hammer Curls" would insert both
    # and recreate the very problem this module exists to stop.
    claimed_this_run: dict[str, str] = {}

    for row in incoming:
        key = normalise_term(row.name)

        if key in by_norm_name:
            # The same row, by identity. Not a conflict.
            if refresh_existing:
                update.append(row.name)
            continue

        owner = _alias_owner(ns, key) or claimed_this_run.get(key)
        if owner is not None:
            blocked.append(
                Collision(
                    incoming_name=row.name,
                    existing_name=owner,
                    term=key,
                    kind="name_vs_alias",
                )
            )
            continue

        # The other direction: does this row's alias list claim a name some
        # existing row already holds? Then the catalogue has a duplicate the
        # seed did not create and must not silently remove.
        for alias in row.aliases:
            akey = normalise_term(alias)
            if akey == key:
                continue
            held_by = by_norm_name.get(akey)
            if held_by is not None:
                stale.append(
                    Collision(
                        incoming_name=row.name,
                        existing_name=held_by,
                        term=akey,
                        kind="alias_vs_name",
                    )
                )

        insert.append(row.name)
        for term in row.terms():
            claimed_this_run.setdefault(term, row.name)

    return SeedPlan(
        insert=tuple(insert),
        update=tuple(update),
        blocked=tuple(blocked),
        stale_duplicates=tuple(stale),
    )


def _alias_owner(
    ns: Mapping[str, list[tuple[str, bool]]], term: str
) -> str | None:
    """The row holding `term` as an alias, if any row holds it at all."""
    for owner_name, is_name in ns.get(term, ()):
        if not is_name:
            return owner_name
    return None


def merge_aliases(
    existing: Iterable[str], incoming: Iterable[str]
) -> list[str]:
    """Union an alias list, never replace it. Sorted, deduplicated on the
    normalised form, classification tokens dropped.

    WHY UNION, AND WHY THIS IS NOT A STYLE CHOICE
    `seed_movements.py` is not the only writer of an alias list.
    `merge_duplicate_exercises.py` folds a retired row's name in here, so
    that "butterfly" still finds "Pec Deck" after the duplicate row is
    deleted. A seed that REPLACES the list wipes those folds -- it did,
    silently, on the first run after a merge, and eleven movements became
    unsearchable. That is worse than the duplicate was: a duplicate can at
    least be found.

    THE COST, STATED PLAINLY: an alias cannot be removed by deleting it from
    the seed file. Deliberate removals go through `ALIAS_REMOVALS` in
    `merge_duplicate_exercises.py`, where each one is recorded with a reason.

    Classification tokens are filtered on the way in rather than trusted,
    because the union is exactly the place a stale one would survive forever.
    """
    seen: dict[str, str] = {}
    for alias in list(existing) + list(incoming):
        key = normalise_term(alias)
        if not key or key in CLASSIFICATION_TOKENS:
            continue
        seen.setdefault(key, alias.strip())
    return sorted(seen.values(), key=normalise_term)
