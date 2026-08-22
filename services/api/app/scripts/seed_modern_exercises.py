#!/usr/bin/env python3
"""Add the modern exercise catalogue on top of whatever is already seeded.

ADDITIVE AND IDEMPOTENT. Upserts on name, so re-running is safe and a row
that already exists keeps its id — which matters, because set logs reference
exercises by id and a re-seed that replaced rows would orphan every set the
user has ever logged against them.

    python -m app.scripts.seed_modern_exercises
    python -m app.scripts.seed_modern_exercises --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from ..db import SessionLocal, init_db
from ..models import Exercise
from .data.modern_exercises import EXERCISES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed.modern")


def _norm(name: str) -> str:
    """Comparison key for "is this already here?".

    Punctuation-insensitive because the two sources disagree about hyphens --
    free-exercise-db has "Chin-Up", this file has "Chin Up" shapes -- and
    seeding a near-duplicate is worse than skipping a row: the user then has
    two entries to pick between and their history splits across both.
    """
    return "".join(c for c in name.lower() if c.isalnum())


async def run(dry_run: bool = False) -> None:
    await init_db()

    async with SessionLocal() as session:
        existing = (await session.execute(select(Exercise))).scalars().all()
        by_norm = {_norm(e.name): e for e in existing}
        log.info("catalogue currently holds %d exercises", len(existing))

        added = 0
        updated = 0
        for ex in EXERCISES:
            key = _norm(ex.name)
            current = by_norm.get(key)

            if current is None:
                if not dry_run:
                    session.add(
                        Exercise(
                            name=ex.name,
                            muscle_group=ex.muscle_group,
                            secondary_muscles=list(ex.secondary),
                            equipment=ex.equipment,
                            is_compound=ex.is_compound,
                            aliases=list(ex.aliases),
                        )
                    )
                added += 1
                continue

            # Already there. Merge in any aliases it lacks rather than
            # overwriting -- the existing row may carry aliases a user's own
            # search history depends on.
            merged = list(dict.fromkeys([*(current.aliases or []), *ex.aliases]))
            if merged != (current.aliases or []):
                if not dry_run:
                    current.aliases = merged
                updated += 1

        if not dry_run:
            await session.commit()

        total = len(existing) + added
        log.info(
            "%s added=%d aliases_merged=%d total=%d",
            "DRY RUN" if dry_run else "DONE",
            added,
            updated,
            total,
        )


def main() -> None:
    p = argparse.ArgumentParser(description="Seed the modern exercise catalogue.")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
