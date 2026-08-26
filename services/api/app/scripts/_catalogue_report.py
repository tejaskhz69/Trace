"""Shared collision reporting for the exercise seeds.

`app/services/catalogue.py` decides what collides; this decides how loudly to
say so. Kept out of the service because the service is pure and this logs.

THE POSTURE HERE IS DELIBERATE. A collision is reported and the offending row
is withheld -- the seed never merges, renames, or deletes to resolve one.
Merging rows rewrites `set_logs.exercise_id`, which is somebody's training
history, and that is not a decision for a bulk import that happened to run
overnight. A cheap refusal that forces a human to look beats clever code that
guesses.
"""

from __future__ import annotations

import logging

from app.services.catalogue import SeedPlan

log = logging.getLogger("seed.catalogue")

#: Beyond this, print a summary instead of every line. A seed against an
#: empty catalogue has no collisions; a wall of them means something
#: structural, and the count is the useful signal.
_MAX_LINES = 25


def report_collisions(plan: SeedPlan, *, logger: logging.Logger | None = None) -> None:
    out = logger or log

    if plan.blocked:
        out.warning(
            "%d incoming row(s) withheld -- the movement already exists "
            "under another name:",
            len(plan.blocked),
        )
        for c in plan.blocked[:_MAX_LINES]:
            out.warning("   %s", c.describe())
        if len(plan.blocked) > _MAX_LINES:
            out.warning("   ... and %d more", len(plan.blocked) - _MAX_LINES)

    if plan.stale_duplicates:
        out.warning(
            "%d existing row(s) duplicate an incoming movement. A seed "
            "cannot fix these -- fixing them means deleting a row and "
            "repointing training history. Run:\n"
            "   python -m app.scripts.merge_duplicate_exercises",
            len(plan.stale_duplicates),
        )
        for c in plan.stale_duplicates[:_MAX_LINES]:
            out.warning("   %s", c.describe())
        if len(plan.stale_duplicates) > _MAX_LINES:
            out.warning(
                "   ... and %d more", len(plan.stale_duplicates) - _MAX_LINES
            )

    if not plan.needs_attention:
        out.info("no name/alias collisions")
