#!/usr/bin/env python3
"""Classify the curated movements into `exercise_attributes`.

WHAT THIS WRITES
One row per curated movement, carrying how it is classified: the nineteen-
value `movement_detail`, the `resistance_profile`, whether it is unilateral,
the derived eight-value `movement_pattern`, and `is_isolation`.

WHAT IT DOES NOT WRITE
Rep ranges, rest and fatigue cost. Those are prescription decisions, not
classification, and they arrive with the session generator. They are nullable
and left NULL rather than filled with a plausible-looking default -- a
number nobody chose is worse than an absent one, because the absent one is
visibly absent.

    A ROW HERE MEANS "CLASSIFIED", NOT "PROGRAMMABLE". Generation must check
    the rep columns are non-null as well as joining this table.

WHERE THE PATTERN COMES FROM
Derived from `movement_detail` by `services/movement.py:pattern_for`, never
stored twice. Roughly 45 of the 154 movements get NULL, because a lateral
raise satisfies no compound pattern and saying it does would put a false
value into a field generation trusts. `is_isolation` is exactly that set, and
a CHECK constraint keeps the two in step.

ONE SOURCE, TWO TABLES
`data/movement_attributes.py` is the only place this data lives. This script
and `seed_movements.py` read one source each and write one table each; there
is no path by which the catalogue and its classification can disagree about
which movements exist. `tests/test_movement_attributes.py` asserts that.

USAGE
    python -m app.scripts.seed_exercise_attributes --dry-run
    python -m app.scripts.seed_exercise_attributes
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import SessionLocal
from ..models import Exercise, ExerciseAttributes
from ..services.catalogue import normalise_term
from ..services.movement import pattern_for
from ._schema_guard import require_tables
from .data.movement_attributes import MOVEMENT_ATTRIBUTES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed.exercise_attributes")


async def run(dry_run: bool) -> None:
    await require_tables("exercises", "exercise_attributes")

    async with SessionLocal() as session:
        rows = (
            await session.execute(select(Exercise.id, Exercise.name))
        ).all()
        by_name = {normalise_term(name): eid for eid, name in rows}

        # A classification for a movement that is not in the catalogue means
        # the two have drifted. Say which, and stop -- inserting would fail
        # on the foreign key anyway, and skipping would hide it.
        missing = [
            name
            for name in MOVEMENT_ATTRIBUTES
            if normalise_term(name) not in by_name
        ]
        if missing:
            raise SystemExit(
                "REFUSED: these movements are classified but not in the "
                "catalogue — run seed_movements first, or reconcile the "
                "names:\n  " + "\n  ".join(sorted(missing))
            )

        existing = {
            eid
            for (eid,) in (
                await session.execute(select(ExerciseAttributes.exercise_id))
            ).all()
        }

        payload = []
        for name, (detail, profile, unilateral) in MOVEMENT_ATTRIBUTES.items():
            pattern = pattern_for(detail)
            payload.append(
                {
                    "exercise_id": by_name[normalise_term(name)],
                    "movement_pattern": pattern,
                    "movement_detail": detail,
                    "resistance_profile": profile,
                    "is_isolation": pattern is None,
                    "is_unilateral": unilateral,
                }
            )

        new_rows = [r for r in payload if r["exercise_id"] not in existing]
        upd_rows = [r for r in payload if r["exercise_id"] in existing]
        isolation = sum(1 for r in payload if r["is_isolation"])

        log.info(
            "%d movements: %d with a pattern, %d isolation (no pattern)",
            len(payload),
            len(payload) - isolation,
            isolation,
        )
        if dry_run:
            log.info("--dry-run: nothing written")
            return

        if new_rows:
            await session.execute(pg_insert(ExerciseAttributes).values(new_rows))
        for r in upd_rows:
            # Classification only. Never touches the rep/rest/fatigue columns,
            # so a prescription decided later is not overwritten by a re-seed.
            await session.execute(
                update(ExerciseAttributes)
                .where(ExerciseAttributes.exercise_id == r["exercise_id"])
                .values(
                    movement_pattern=r["movement_pattern"],
                    movement_detail=r["movement_detail"],
                    resistance_profile=r["resistance_profile"],
                    is_isolation=r["is_isolation"],
                    is_unilateral=r["is_unilateral"],
                )
            )

        await session.commit()
        log.info("Wrote %d new, refreshed %d existing", len(new_rows), len(upd_rows))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(a.dry_run))


if __name__ == "__main__":
    main()
