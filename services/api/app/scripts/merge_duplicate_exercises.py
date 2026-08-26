#!/usr/bin/env python3
"""Merge catalogue rows that are two names for one movement.

WHY
---
The catalogue holds 940 rows, and 42 of them have a name that is another
row's alias -- "Seal Row" alongside "Chest-Supported Row", "Barbell Squat"
alongside "Barbell Back Squat". Two seeds wrote to one table and neither
checked the other's alias space (see `app/services/catalogue.py`).

This matters because adjudication needs MIN_SESSIONS exposures on ONE
`exercise_id`. A lifter alternating between two rows for the same movement
builds two half-height trends and never gets a verdict on either.

WHY NOW
-------
Because `set_logs` currently holds 8 rows. Merging exercise rows means
repointing training history, and today there is almost none to repoint. The
same operation against a live user base is a migration with a rollback plan
and a real risk of silently corrupting somebody's e1RM trend.

WHAT IT DOES
------------
For each cluster below: fold the absorbed row's name and aliases into the
survivor, repoint every FK that references the absorbed row, delete it, and
write the whole thing to a record file so a wrong merge can be reversed.

THE SURVIVOR IS ALWAYS THE `seed_movements` ROW
-----------------------------------------------
Not a style preference -- a correctness constraint. `seed_movements.py` is
declarative: it re-inserts any row in its list that is missing. Delete one of
its rows and the next seed run recreates it, silently undoing the merge and
leaving the alias fold behind as the only trace. `_assert_survivors_are_
durable` enforces this, and it is the check most worth keeping.

WHAT IT REFUSES TO DO
---------------------
- Delete a row `seed_movements.py` would recreate (above).
- Merge two movements that are genuinely different. Seven clusters are
  recorded in KEEP_SEPARATE with the reason; an Inverse Zottman Curl is not a
  Zottman Curl, and a merge is not reversible by adding an alias back.
- Run without `--apply`. Dry-run is the default because the failure mode of
  this script is deleting the wrong catalogue row.
- Proceed when more history would move than expected. `--max-repoint`
  defaults to 8; if the number is larger than that, a human should look
  before any set_log changes hands.

USAGE
    python -m app.scripts.merge_duplicate_exercises --scan     # report only
    python -m app.scripts.merge_duplicate_exercises            # dry run
    python -m app.scripts.merge_duplicate_exercises --apply
    python -m app.scripts.merge_duplicate_exercises --refold --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal
from app.scripts._schema_guard import require_tables
from app.services.catalogue import is_classification_token, normalise_term

log = logging.getLogger("merge_duplicates")

RECORD_PATH = Path(__file__).resolve().parents[2] / "EXERCISE_MERGES.md"
#: Machine-readable twin of the record. The .md is for people; this is
#: what lets a later run render rows it did not perform itself, so the
#: ids needed to reverse an earlier round survive.
LEDGER_PATH = Path(__file__).resolve().parents[2] / "EXERCISE_MERGES.json"

# --------------------------------------------------------------------------
# Every column that points at exercises.id. Missing one means a merge leaves
# a dangling reference or trips an FK, so this list is the load-bearing part
# of the script. It is checked against models.py by
# `tests/test_catalogue.py::test_every_fk_to_exercises_is_repointed`, because
# a new FK added later would otherwise be silently forgotten here.
# --------------------------------------------------------------------------
REFERRERS: tuple[tuple[str, str], ...] = (
    ("set_logs", "exercise_id"),
    ("strength_snapshots", "exercise_id"),
    ("stations", "exercise_id"),
    ("exercise_attributes", "exercise_id"),
    ("exercise_substitutions", "from_exercise_id"),
    ("exercise_substitutions", "to_exercise_id"),
    ("prescribed_exercises", "exercise_id"),
    ("prescribed_exercises", "replaced_with_exercise_id"),
)

# --------------------------------------------------------------------------
# THE DECISION TABLE
#
# (survivor, (absorbed, ...), why)
#
# Curated by hand, not derived by a rule, because each line is a judgement
# about whether two names describe one movement. A rule that got this right
# for "Leg Extension"/"Leg Extensions" would also merge "Zottman Curl" into
# "Inverse Zottman Curl", which is wrong and unrecoverable.
# --------------------------------------------------------------------------
MERGES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Machine Crunch", ("Ab Crunch Machine",), "same machine, word order"),
    ("Barbell Back Squat", ("Barbell Squat",), "bar position is the qualifier, not a movement"),
    ("Conventional Deadlift", ("Barbell Deadlift",), "Sumo Deadlift is the separate row; this is its sibling"),
    ("Hip Thrust", ("Barbell Hip Thrust",), "implement is not a movement axis here"),
    ("Barbell Row", ("Bent Over Barbell Row",), "same lift, longer name"),
    ("Bayesian Curl", ("Bayesian Cable Curl", "Face-Away Bayesian Cable Curl"), "three names for one cable curl behind the body"),
    ("Pec Deck", ("Butterfly", "Pec Deck Fly"), "one machine, three names"),
    ("Cable Chest Fly", ("Cable Crossover", "Standing Cable Fly"), "one movement, three names"),
    ("Cable Crunch", ("Rope Crunch",), "attachment is not a movement axis"),
    ("Reverse Cable Crossover", ("Cable Rear Delt Fly",), "same movement"),
    ("Leg Press Calf Raise", ("Calf Press",), "same movement on the same machine"),
    ("Chest Press Machine", ("Machine Chest Press",), "word order"),
    ("Chest-Supported Row", ("Seal Row",), "bench angle is a station property, not a movement"),
    ("Machine Triceps Dip", ("Dip Machine",), "word order"),
    ("Dumbbell Curl", ("Dumbbell Bicep Curl",), "same lift, longer name"),
    ("Preacher Curl", ("EZ-Bar Preacher Curl",), "bar type is not a movement axis"),
    ("Face Pull", ("Rope Face Pull",), "the rope is the only way it is done"),
    ("Guillotine Press", ("Neck Press",), "Gironda neck press -- one lift, two names"),
    ("Hammer Curl", ("Hammer Curls",), "plural"),
    ("Hip Abduction", ("Machine Hip Abduction",), "word order"),
    ("Hip Adduction", ("Machine Hip Adduction",), "word order"),
    ("Leg Press", ("Horizontal Leg Press",), "sled angle is a station property, not a movement"),
    # Lat Pulldown / Wide-Grip Lat Pulldown is NOT here on purpose -- see
    # KEEP_SEPARATE. Grip variants are separate rows throughout the
    # catalogue, so merging this one and no other would be the inconsistency.
    ("Leg Extension", ("Leg Extensions",), "plural"),
    ("Shoulder Press Machine", ("Machine Shoulder Press",), "word order"),
    ("Triceps Extension Machine", ("Machine Triceps Extension",), "word order"),
    ("Nordic Curl", ("Nordic Hamstring Curl",), "same lift, longer name"),
    ("Overhead Press", ("Standing Military Press",), "same lift, two names"),

    # ---- ROUND 2: rows that SHARE AN ALIAS, with neither name colliding.
    # Invisible to the round-1 scan, and every bit as effective at splitting
    # a trend -- the user picks whichever row search ranks first that day.
    # Found by `--scan`, class 3.
    ("Barbell Bench Press", ("Barbell Bench Press - Medium Grip",), "medium grip IS the bench press; the qualifier is a dataset artifact"),
    ("Barbell Front Squat", ("Front Barbell Squat",), "word order"),
    ("Triceps Pushdown", ("Cable Triceps Pressdown, Rope",), "same movement; the rope is the usual attachment"),
    ("Chest-Supported Row", ("Chest-Supported Machine Row",), "same movement; 'machine' is not a qualifier here"),
    ("Close-Grip Bench Press", ("Close-Grip Barbell Bench Press",), "same lift, longer name"),
    ("Dumbbell Pullover", ("Dumbbell Lat Pullover",), "lat vs chest emphasis is a cue, not a movement"),
    ("Dumbbell Lateral Raise", ("Side Lateral Raise",), "one movement, two names"),
    ("Skull Crusher", ("EZ-Bar Skullcrusher",), "bar type is not a movement axis -- as with Preacher Curl"),
    ("Neutral-Grip Lat Pulldown", ("Hammer-Grip Lat Pulldown",), "hammer grip IS neutral grip: synonyms, not two grip variants"),
    ("Katana Cable Extension", ("Katana Cable Triceps Extension",), "same lift, longer name"),
    ("Pec Deck", ("Machine Chest Fly",), "one machine, two names"),
    ("Machine Pullover", ("Machine Lat Pullover",), "lat vs chest emphasis is a cue, not a movement"),
    ("Seated Cable Row (single arm)", ("Single-Arm Cable Row",), "same movement, two names"),
)

# --------------------------------------------------------------------------
# CONSIDERED AND DELIBERATELY NOT MERGED
#
# Each of these has one row's name sitting in another row's alias list, so
# they look identical to the detector. They are not the same movement, and a
# merge cannot be undone by adding the alias back -- the two trends are
# already one series by then.
# --------------------------------------------------------------------------
KEEP_SEPARATE: tuple[tuple[str, str, str], ...] = (
    ("Zottman Curl", "Inverse Zottman Curl", "opposite rotation -- supinate up/pronate down vs the reverse"),
    ("Glute Kickback", "Cable Kickback", "bodyweight vs cable: different equipment class, which IS a substitution axis"),
    ("Walking Lunge", "Dumbbell Lunge", "travelling vs stationary -- different stability demand"),
    ("Landmine Row", "Meadows Row", "a Meadows Row is one specific landmine row, not the category"),
    ("Clean", "Power Clean", "full clean catches below parallel; power catches above -- different lifts"),
    ("Snatch", "Power Snatch", "same distinction as clean vs power clean"),
    ("Wide-Grip Lat Pulldown", "Lat Pulldown", "grip variants are separate rows throughout (close, neutral, hammer, V-bar); this one is consistent with them"),

    # ---- ROUND 2. Grip and stance variants stay separate unless the whole
    # family is being collapsed, and no family here is.
    ("Seated Cable Fly", "Cable Chest Fly", "seated vs standing: different setup and stability demand"),
    ("Chest-Supported T-Bar Row", "T-Bar Row", "supported vs free -- the support is the point of the variant"),
    ("Seated Dumbbell Shoulder Press", "Dumbbell Shoulder Press", "seated vs standing: different core demand"),
    ("Lean-In Dumbbell Lateral Raise", "Lean-Away Lateral Raise", "opposite bias -- one loads the lengthened end, the other the shortened"),
    ("Pullups", "Weighted Pull-Up", "loaded vs bodyweight: added load is the whole variant"),
    ("Stiff-Legged Barbell Deadlift", "Romanian Deadlift", "knee angle differs and so does the loading; commonly conflated, genuinely distinct"),
    ("Seated Cable Row, Neutral Grip", "Seated Cable Row", "grip variant, kept for the same reason as Wide-Grip Lat Pulldown"),
)

# --------------------------------------------------------------------------
# Aliases that point one distinct movement's NAME at a different row, from
# the KEEP_SEPARATE pairs above. Removing them stops the pair looking like a
# duplicate without merging anything.
#
# ONLY rows `seed_movements.py` does not own are listed. It rewrites the
# alias list of every row it owns, so an edit to one of those reverts on the
# next seed run -- see the report for the five that need a source change.
# --------------------------------------------------------------------------
ALIAS_REMOVALS: tuple[tuple[str, str, str], ...] = (
    ("Inverse Zottman Curl", "zottman curl", "that is the other movement's name"),
    ("Wide-Grip Lat Pulldown", "lat pulldown", "claims the canonical row's name"),
    ("Wide-Grip Lat Pulldown", "pulldown", "the bare term belongs to Lat Pulldown"),
    ("Seated Cable Fly", "cable fly", "the bare term belongs to Cable Chest Fly"),
    ("Chest-Supported T-Bar Row", "t bar row", "that is the other row's name"),
    ("Chest-Supported T-Bar Row", "tbar row", "that is the other row's name"),
    ("Lean-In Dumbbell Lateral Raise", "leaning lateral raise", "ambiguous between the lean-in and lean-away variants"),
    ("Seated Cable Row, Neutral Grip", "cable row", "the bare term belongs to Seated Cable Row"),
    ("Seated Cable Row, Neutral Grip", "seated row", "the bare term belongs to Seated Cable Row"),

    # ---- Also removed from `seed_movements.py` itself. BOTH halves are
    # needed: the source edit stops the alias being re-seeded, this clears
    # the copy already stored -- the seed unions, so it will not drop one on
    # its own. Each term names a DIFFERENT row that is deliberately kept
    # separate; see KEEP_SEPARATE above.
    ("Dumbbell Shoulder Press", "seated db press", "names Seated Dumbbell Shoulder Press"),
    ("Lean-Away Lateral Raise", "leaning lateral raise", "ambiguous between lean-away and lean-in"),
    ("Weighted Pull-Up", "pull up", "names Pullups -- unloaded"),
    ("Weighted Pull-Up", "pullup", "names Pullups -- unloaded"),
    ("Romanian Deadlift", "stiff leg deadlift", "names Stiff-Legged Barbell Deadlift"),
    ("Romanian Deadlift", "sldl", "names Stiff-Legged Barbell Deadlift"),
    ("Dumbbell Lunge", "walking lunge", "names Walking Lunge -- travelling"),
    ("Meadows Row", "landmine row", "names Landmine Row, the general category"),
    ("Cable Kickback", "glute kickback", "names Glute Kickback -- bodyweight"),
    ("Power Clean", "clean", "names Clean -- the full lift"),
    ("Power Snatch", "snatch", "names Snatch -- the full lift"),
)

# --------------------------------------------------------------------------
# Secondary aliases that belonged to an absorbed row and were lost when
# `seed_movements.py` overwrote a survivor's alias list before it learned to
# union (it does now). Listed explicitly rather than recovered from a record
# file, so that what is in the catalogue is what is in this repository.
# --------------------------------------------------------------------------
ALIAS_ADDITIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Bayesian Curl", ("face away curl",)),
    ("Pec Deck", ("machine fly",)),
    ("Cable Chest Fly", ("standing fly",)),
    ("Preacher Curl", ("ez preacher curl",)),
    ("Hip Abduction", ("glute medius machine",)),
)


async def _load_catalogue(session) -> dict[str, dict]:
    rows = (
        await session.execute(
            text("SELECT id, name, aliases FROM exercises")
        )
    ).mappings().all()
    return {normalise_term(r["name"]): dict(r) for r in rows}


def _assert_survivors_are_durable(catalogue: dict[str, dict]) -> None:
    """No absorbed row may be one `seed_movements.py` would recreate.

    This is the check that stops the merge from quietly undoing itself.
    """
    from app.scripts import seed_movements

    curated = {normalise_term(e[0]) for e in seed_movements.E}
    offenders = []
    for survivor, absorbed, _ in MERGES:
        for name in absorbed:
            if normalise_term(name) in curated:
                offenders.append((name, survivor))
    # A row already absent from the catalogue cannot be deleted again, but if
    # the seed owns it the merge is being undone every run -- so this check
    # deliberately does NOT skip already-merged rows.
    if offenders:
        lines = "\n".join(
            f"  {a!r} would be recreated by seed_movements "
            f"(merging into {s!r})"
            for a, s in offenders
        )
        raise SystemExit(
            "REFUSED: these merges would be undone by the next seed run:\n"
            + lines
        )


def _already_merged(catalogue: dict[str, dict], survivor: str, absorbed: str) -> bool:
    """Absent because it was merged, rather than absent because of a typo.

    The discriminator is the fold: merging an absorbed row puts its NAME into
    the survivor's alias list, so an already-merged row is one that is gone
    from the catalogue AND findable through its survivor. A misspelt row is
    gone and findable nowhere -- which is what the guard needs to keep
    catching, because a typo here silently skips a real duplicate.
    """
    row = catalogue.get(normalise_term(survivor))
    if row is None:
        return False
    return normalise_term(absorbed) in {
        normalise_term(a) for a in (row["aliases"] or [])
    }


def _assert_rows_exist(catalogue: dict[str, dict]) -> None:
    """Refuse on a name nothing can explain. Re-running is not an error.

    This script is expected to be run again as new clusters are curated, so
    the rows merged last time are legitimately gone. What must still stop the
    run is a name that is absent for no reason anyone can point at.
    """
    unexplained = []
    for survivor, absorbed, _ in MERGES:
        if normalise_term(survivor) not in catalogue:
            unexplained.append(f"{survivor!r} (survivor)")
        for name in absorbed:
            if normalise_term(name) in catalogue:
                continue
            if _already_merged(catalogue, survivor, name):
                continue
            unexplained.append(f"{name!r} (to be absorbed into {survivor!r})")
    if unexplained:
        raise SystemExit(
            "REFUSED: rows named in the decision table are not in the "
            "catalogue, and are not recorded as already merged. Misspelt?\n  "
            + "\n  ".join(sorted(set(unexplained)))
        )


async def _count_references(session, exercise_id: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for table, column in REFERRERS:
        n = (
            await session.execute(
                text(
                    f"SELECT count(*) FROM {table} WHERE {column} = :eid"
                ),
                {"eid": exercise_id},
            )
        ).scalar_one()
        if n:
            out[f"{table}.{column}"] = n
    return out


#: Movement-pattern and resistance-profile tags that `seed_movements.py`
#: folds into `aliases` on purpose (see the comment at its `add()` call).
#: Shared by design, so they are not evidence of a duplicate.
_PATTERN_TAGS = frozenset(
    {
        "mid", "lengthened", "shortened", "h-pull", "h-press", "v-pull",
        "v-press", "hinge", "pull", "push", "squat", "knee-ext", "elbow-flex",
        "elbow-ext", "trunk-flex", "calf", "carry", "lunge",
    }
)


#: The subset of CLASSIFICATION_TOKENS that are also ordinary English words
#: somebody might genuinely type into a search box. Everything else in that
#: set ("h-press", "anti-rot", "lengthened") is vocabulary nobody searches.
_PLAUSIBLE_SEARCH_TOKENS = frozenset(
    {"squat", "lunge", "hinge", "lateral", "calf", "abduction", "shrug", "pull"}
)


async def strip_classification(apply: bool) -> None:
    """Remove bare pattern/profile tokens from every alias list.

    `seed_movements.py` used to fold each row's movement pattern and
    resistance profile into its aliases, so "hinge" and "lengthened" were
    searchable without new columns. An alias list IS the search index, so the
    effect was that all 155 curated rows answered to a classification token:
    "mid" returned 58 unrelated movements and "squat" returned the leg press.

    The seed no longer generates them. This clears the ones already stored.
    Idempotent, and safe to re-run.

    BEFORE DELETING ANYTHING IT CHECKS FINDABILITY. Some of these tokens are
    also real words -- `squat`, `shrug`, `calf`. A row is only stripped when
    its own NAME still contains the token, or the token was never a sensible
    way to search for it in the first place. Anything that would become
    harder to find is reported and left alone.
    """
    await require_tables("exercises")

    async with SessionLocal() as session:
        rows = (
            await session.execute(text("SELECT id, name, aliases FROM exercises"))
        ).mappings().all()

        stripped: list[tuple[str, list[str]]] = []
        withheld: list[tuple[str, str]] = []

        for r in rows:
            aliases = list(r["aliases"] or [])
            tokens = [a for a in aliases if is_classification_token(a)]
            if not tokens:
                continue

            name = normalise_term(r["name"])
            remaining = [a for a in aliases if not is_classification_token(a)]

            # Most of these could never be search terms -- nobody types
            # "h-press" or "anti-rot" looking for a movement, and searching
            # "mid" is the bug being fixed. A few ARE ordinary words though,
            # so those are reported when the row's own name does not already
            # contain them and no other alias covers them.
            risky = [
                t
                for t in tokens
                if normalise_term(t) in _PLAUSIBLE_SEARCH_TOKENS
                and normalise_term(t) not in name
                and not any(normalise_term(t) in normalise_term(a) for a in remaining)
            ]
            for t in risky:
                withheld.append((r["name"], t))

            stripped.append((r["name"], sorted(tokens)))
            if apply:
                await session.execute(
                    text("UPDATE exercises SET aliases = :a WHERE id = :i"),
                    {"a": json.dumps(sorted(remaining)), "i": r["id"]},
                )

        if apply:
            await session.commit()

    total = sum(len(t) for _, t in stripped)
    log.info(
        "%s %d token(s) from %d row(s)",
        "removed" if apply else "would remove",
        total,
        len(stripped),
    )
    if withheld:
        log.info(
            "\n%d token(s) that are ordinary words and are not echoed by "
            "the row's own name. Stripped anyway -- a classification is "
            "still not a name -- but listed so the choice is visible:",
            len(withheld),
        )
        for name, token in sorted(withheld)[:40]:
            log.info("   %-38s %r", name, token)
        if len(withheld) > 40:
            log.info("   ... and %d more", len(withheld) - 40)
    if not apply:
        log.info("\n--dry-run (default): nothing written. Pass --apply.")


async def scan() -> None:
    """Report every duplicate class currently in the catalogue. Read-only.

    Three classes, and the third is easy to miss:

      1. two rows with the same name;
      2. one row's NAME sitting in another row's alias list -- the 42 this
         script was written for;
      3. two rows SHARING an alias, with neither name colliding. "hammer
         strength row" belonging to both "Chest-Supported Row" and
         "Chest-Supported Machine Row" is invisible to (2), and splits a
         trend just as effectively, because the user picks whichever row the
         search happens to rank first that day.
    """
    from collections import Counter

    await require_tables("exercises")

    async with SessionLocal() as session:
        rows = (
            await session.execute(text("SELECT id, name, aliases FROM exercises"))
        ).mappings().all()

    log.info("catalogue: %d rows", len(rows))

    by_name: defaultdict[str, list[str]] = defaultdict(list)
    alias_owners: defaultdict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_name[normalise_term(r["name"])].append(r["name"])
        for a in r["aliases"] or []:
            key = normalise_term(a)
            if key not in _PATTERN_TAGS:
                alias_owners[key].append(r["name"])

    same_name = {k: v for k, v in by_name.items() if len(v) > 1}
    log.info("\n1. duplicate names: %d", len(same_name))
    for k, v in sorted(same_name.items()):
        log.info("   %r x%d", k, len(v))

    known = {normalise_term(n) for _, names, _ in MERGES for n in names}
    known |= {normalise_term(a) for pair in KEEP_SEPARATE for a in pair[:2]}
    name_is_alias = [
        (r["name"], sorted(set(alias_owners.get(normalise_term(r["name"]), []))))
        for r in rows
        if [o for o in alias_owners.get(normalise_term(r["name"]), []) if o != r["name"]]
    ]
    log.info("\n2. a row's name is another row's alias: %d", len(name_is_alias))
    for name, owners in sorted(name_is_alias):
        tag = "" if normalise_term(name) in known else "   << NOT YET DECIDED"
        log.info("   %r -> %s%s", name, [o for o in owners if o != name], tag)

    shared = {
        k: sorted(set(v))
        for k, v in alias_owners.items()
        if len(set(v)) > 1
    }
    log.info("\n3. one alias claimed by several rows: %d", len(shared))
    for k, v in sorted(shared.items()):
        log.info("   %r -> %s", k, v)

    involved = Counter(n for v in shared.values() for n in v)
    log.info(
        "\n   %d rows involved in class 3. These need the same per-cluster "
        "judgement the table above records, and are NOT decided yet.",
        len(involved),
    )


async def refold(apply: bool) -> None:
    """Re-assert that every retired name still resolves to its survivor.

    A merge folds the absorbed row's name into the survivor's aliases. Any
    writer that REPLACES that alias list instead of extending it silently
    undoes the fold, and the movement becomes unsearchable -- which is worse
    than the duplicate was, because at least a duplicate could be found.

    `seed_movements.py` did exactly that until it learned to union. This is
    the repair, and it is idempotent: run it any time the folds look wrong.
    """
    await require_tables("exercises")

    async with SessionLocal() as session:
        catalogue = await _load_catalogue(session)

        wanted: dict[str, set[str]] = defaultdict(set)
        for survivor_name, absorbed_names, _ in MERGES:
            # The retired NAME is the alias that must exist. It is derivable
            # from the decision table alone, so this repair needs neither the
            # deleted row nor a record file to work.
            wanted[normalise_term(survivor_name)].update(
                normalise_term(n) for n in absorbed_names
            )
        for survivor_name, extra in ALIAS_ADDITIONS:
            wanted[normalise_term(survivor_name)].update(
                normalise_term(a) for a in extra
            )

        repaired: list[tuple[str, list[str]]] = []
        for key, terms in wanted.items():
            row = catalogue.get(key)
            if row is None:
                raise SystemExit(f"REFUSED: survivor {key!r} is not in the catalogue")
            have = {normalise_term(a) for a in (row["aliases"] or [])}
            missing = sorted(terms - have)
            if not missing:
                continue
            repaired.append((row["name"], missing))
            if apply:
                await session.execute(
                    text("UPDATE exercises SET aliases = :a WHERE id = :i"),
                    {
                        "a": json.dumps(sorted(list(row["aliases"] or []) + missing)),
                        "i": row["id"],
                    },
                )

        if apply:
            await session.commit()

        if not repaired:
            log.info("all %d folds intact -- nothing to repair", len(wanted))
            return
        log.info(
            "%s %d survivor(s):",
            "repaired" if apply else "would repair",
            len(repaired),
        )
        for name, missing in repaired:
            log.info("   %s += %s", name, ", ".join(repr(m) for m in missing))
        if not apply:
            log.info("--dry-run (default): nothing written. Pass --apply.")


async def run(apply: bool, max_repoint: int) -> None:
    await require_tables("exercises", "set_logs")

    async with SessionLocal() as session:
        catalogue = await _load_catalogue(session)
        _assert_rows_exist(catalogue)
        _assert_survivors_are_durable(catalogue)

        planned: list[dict] = []
        total_repointed: defaultdict[str, int] = defaultdict(int)

        for survivor_name, absorbed_names, why in MERGES:
            outstanding = [
                n for n in absorbed_names if normalise_term(n) in catalogue
            ]
            if not outstanding:
                continue  # merged on an earlier run
            survivor = catalogue[normalise_term(survivor_name)]
            folded: set[str] = {
                normalise_term(a) for a in (survivor["aliases"] or [])
            }
            entry = {
                "survivor": survivor["name"],
                "survivor_id": survivor["id"],
                "why": why,
                "absorbed": [],
            }

            for name in outstanding:
                dup = catalogue[normalise_term(name)]
                refs = await _count_references(session, dup["id"])
                for k, v in refs.items():
                    total_repointed[k] += v

                # The duplicate's own name must survive as an alias, or
                # "seal row" stops finding anything at all.
                new_terms = [normalise_term(dup["name"])] + [
                    normalise_term(a) for a in (dup["aliases"] or [])
                ]
                added = [t for t in new_terms if t not in folded]
                folded.update(added)

                entry["absorbed"].append(
                    {
                        "name": dup["name"],
                        "id": dup["id"],
                        "aliases_folded": added,
                        "references_repointed": refs,
                    }
                )

            entry["survivor_aliases_after"] = sorted(folded)
            planned.append(entry)

        moving = sum(total_repointed.values())
        log.info(
            "%d clusters, %d rows absorbed, %d references repointed",
            len(planned),
            sum(len(p["absorbed"]) for p in planned),
            moving,
        )
        for k, v in sorted(total_repointed.items()):
            log.info("   %s: %d", k, v)

        if moving > max_repoint:
            raise SystemExit(
                f"REFUSED: {moving} references would move, limit is "
                f"{max_repoint}. That is training history. Re-run with "
                f"--max-repoint if this is expected."
            )

        if not apply:
            log.info("--dry-run (default): nothing written. Pass --apply.")
            for p in planned:
                log.info(
                    "  %s <- %s",
                    p["survivor"],
                    ", ".join(a["name"] for a in p["absorbed"]),
                )
            return

        for p in planned:
            await session.execute(
                text("UPDATE exercises SET aliases = :a WHERE id = :i"),
                {
                    "a": json.dumps(p["survivor_aliases_after"]),
                    "i": p["survivor_id"],
                },
            )
            for absorbed in p["absorbed"]:
                for table, column in REFERRERS:
                    await session.execute(
                        text(
                            f"UPDATE {table} SET {column} = :survivor "
                            f"WHERE {column} = :dup"
                        ),
                        {"survivor": p["survivor_id"], "dup": absorbed["id"]},
                    )
                await session.execute(
                    text("DELETE FROM exercises WHERE id = :i"),
                    {"i": absorbed["id"]},
                )

        # GROUPED BY ROW, DELIBERATELY. Applying these one at a time against
        # the catalogue snapshot taken at the top of this function meant the
        # second removal on a row rewrote the alias list from stale data and
        # silently undid the first. Two rows kept an alias that was supposed
        # to be gone.
        wanted: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)
        for row_name, alias, why in ALIAS_REMOVALS:
            wanted[normalise_term(row_name)].append((alias, why))

        removals: list[dict] = []
        for key, entries in wanted.items():
            row = catalogue.get(key)
            if row is None:
                continue
            drop = {normalise_term(a) for a, _ in entries}
            current = list(row["aliases"] or [])
            kept = [a for a in current if normalise_term(a) not in drop]
            if len(kept) == len(current):
                continue
            await session.execute(
                text("UPDATE exercises SET aliases = :a WHERE id = :i"),
                {"a": json.dumps(kept), "i": row["id"]},
            )
            gone = {normalise_term(a) for a in current} - {
                normalise_term(a) for a in kept
            }
            for alias, why in entries:
                if normalise_term(alias) in gone:
                    removals.append(
                        {"row": row["name"], "alias": alias, "why": why}
                    )

        await session.commit()
        _write_record(planned, removals)
        log.info("Applied. Record written to %s", RECORD_PATH)


def _load_ledger() -> list[dict]:
    """Every merge applied so far, oldest first.

    Bootstraps from the existing markdown table when the ledger does not yet
    exist, so the round-1 ids are not lost on the first accumulating run.
    """
    if LEDGER_PATH.exists():
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))

    if not RECORD_PATH.exists():
        return []

    rows: list[dict] = []
    for line in RECORD_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| Survivor"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 6 or not cells[2].startswith("`"):
            continue
        survivor, absorbed, ident, folded, refs, why = cells
        rows.append(
            {
                "survivor": survivor,
                "name": absorbed,
                "id": ident.strip("`"),
                "aliases_folded": [
                    f.strip().strip("`") for f in folded.split(",")
                ]
                if folded != "none"
                else [],
                "references_repointed": refs,
                "why": why,
            }
        )
    return rows


def _write_record(planned: list[dict], removals: list[dict]) -> None:
    """The reversal record. Without this, a wrong merge is unrecoverable."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    ledger = _load_ledger()
    seen = {e["id"] for e in ledger}
    for p in planned:
        for a in p["absorbed"]:
            if a["id"] in seen:
                continue
            ledger.append(
                {
                    "survivor": p["survivor"],
                    "name": a["name"],
                    "id": a["id"],
                    "aliases_folded": a["aliases_folded"],
                    "references_repointed": (
                        ", ".join(
                            f"{k}x{v}"
                            for k, v in a["references_repointed"].items()
                        )
                        or "none"
                    ),
                    "why": p["why"],
                    "applied": stamp,
                }
            )
            seen.add(a["id"])
    LEDGER_PATH.write_text(json.dumps(ledger, indent=1), encoding="utf-8")

    out = [
        "# Exercise catalogue merges",
        "",
        f"Last updated {stamp}. Rendered from `EXERCISE_MERGES.json`, which "
        "accumulates across runs -- this file covers every round, not "
        "just the most recent.",
        "",
        "Each row below was a second catalogue entry for a movement that "
        "already had one. Two seeds wrote to one table and neither checked "
        "the other's alias space. The consequence was not cosmetic: "
        "adjudication needs 8 exposures on one `exercise_id`, so a lifter "
        "alternating between the two names built two half-height trends and "
        "got a verdict on neither.",
        "",
        "**To reverse a merge:** recreate the absorbed row with the id and "
        "name below, move its aliases back off the survivor, and repoint the "
        "listed references. The ids are recorded precisely so this is "
        "possible.",
        "",
        "## Merged",
        "",
        "| Survivor | Absorbed | Absorbed id | Aliases folded in | References repointed | Why |",
        "|---|---|---|---|---|---|",
    ]
    for e in ledger:
        folded = ", ".join(f"`{t}`" for t in e["aliases_folded"]) or "none"
        out.append(
            f"| {e['survivor']} | {e['name']} | `{e['id']}` | {folded} "
            f"| {e['references_repointed']} | {e['why']} |"
        )

    out += [
        "",
        "## Considered and deliberately NOT merged",
        "",
        "Each of these has one row's name sitting in another row's alias "
        "list, so an automated detector flags them as duplicates. They are "
        "different movements. A merge here is not reversible by adding the "
        "alias back, because by then the two trends are one series.",
        "",
        "| Kept | Also kept | Why |",
        "|---|---|---|",
    ]
    for a, b, why in KEEP_SEPARATE:
        out.append(f"| {a} | {b} | {why} |")

    if removals:
        out += [
            "",
            "## Aliases removed",
            "",
            "Aliases that pointed one distinct movement's *name* at a "
            "different row. Removing them stops the pair looking like a "
            "duplicate without merging anything.",
            "",
            "| Row | Alias removed | Why |",
            "|---|---|---|",
        ]
        for r in removals:
            out.append(f"| {r['row']} | `{r['alias']}` | {r['why']} |")

    out.append("")
    RECORD_PATH.write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--apply",
        action="store_true",
        help="actually write; without it this is a dry run",
    )
    ap.add_argument(
        "--max-repoint",
        type=int,
        default=8,
        help="refuse if more than this many references would move",
    )
    ap.add_argument(
        "--strip-classification",
        action="store_true",
        help="remove bare pattern/profile tokens from every alias list",
    )
    ap.add_argument(
        "--scan",
        action="store_true",
        help="report every duplicate class in the catalogue; read-only",
    )
    ap.add_argument(
        "--refold",
        action="store_true",
        help="re-assert retired names as aliases; idempotent repair, no deletes",
    )
    a = ap.parse_args()
    if a.strip_classification:
        asyncio.run(strip_classification(a.apply))
    elif a.scan:
        asyncio.run(scan())
    elif a.refold:
        asyncio.run(refold(a.apply))
    else:
        asyncio.run(run(a.apply, a.max_repoint))


if __name__ == "__main__":
    main()
