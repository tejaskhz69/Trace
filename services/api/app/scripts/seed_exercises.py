#!/usr/bin/env python3
"""Seed the exercise catalogue from the free-exercise-db public domain dataset.

WHY THIS EXISTS
---------------
The strength half of Trace was already built -- `SetLog` stores every set,
`epley_e1rm` turns it into an estimated 1RM, `StrengthSnapshot` rolls it up
weekly, and the adjudication engine reads that trend to decide whether a user
is gaining muscle or losing it. None of it can run without a populated
`exercises` table, and that table had zero rows.

WHERE THE DATA COMES FROM
-------------------------
https://github.com/yuhonas/free-exercise-db -- ~873 movements, released into
the **public domain** (no attribution or licence obligation), with primary and
secondary muscles, equipment, and a compound/isolation flag already tagged.
That is a far better base than a hand-written list: it is broader, it was
curated by people who lift, and it is maintained.

The JSON is cached to `app/scripts/data/exercises.json` on first run so
re-seeding is deterministic and works offline. Images are dropped (we don't
serve them); `instructions` are kept in the cache because form cues are an
obvious later feature, even though no column stores them yet.

WHAT IS EXCLUDED, AND WHY
-------------------------
`stretching` and `cardio` entries are skipped. This table feeds the e1RM
strength engine, and a hamstring stretch has no load to track -- mixing them
in would put un-progressable rows in a screen whose entire job is showing
progression. Cardio belongs to `ExternalWorkout` (the Train tab's cardio
mode), which already models duration and distance properly.

USAGE
    python -m app.scripts.seed_exercises
    python -m app.scripts.seed_exercises --group chest
    python -m app.scripts.seed_exercises --refresh   # re-download the cache
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import pathlib
import urllib.request

from sqlmodel import select

from ..db import SessionLocal, init_db
from ..models import Exercise

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed.exercises")

SOURCE_URL = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
)
CACHE = pathlib.Path(__file__).parent / "data" / "exercises.json"

# These feed a strength-progression screen; a stretch has no load to track.
SKIP_CATEGORIES = {"stretching", "cardio"}

# The dataset splits muscles finer than our nine training groups do.
MUSCLE_TO_GROUP = {
    "abdominals": "core",
    "quadriceps": "legs",
    "hamstrings": "legs",
    "glutes": "legs",
    "calves": "legs",
    "adductors": "legs",
    "abductors": "legs",
    "chest": "chest",
    "lats": "back",
    "middle back": "back",
    "lower back": "back",
    "traps": "back",
    "shoulders": "shoulders",
    "biceps": "biceps",
    "triceps": "triceps",
    "forearms": "forearms",
    "neck": "neck",
}

EQUIPMENT_MAP = {
    "body only": "bodyweight",
    "barbell": "barbell",
    "dumbbell": "dumbbell",
    "cable": "cable",
    "machine": "machine",
    "kettlebells": "kettlebell",
    "bands": "band",
    "e-z curl bar": "ezbar",
    "medicine ball": "medicine_ball",
    "exercise ball": "exercise_ball",
    "foam roll": "foam_roller",
    "other": "other",
}

# The dataset ships no aliases, but search quality lives or dies on them --
# people type "ohp" and "rdl", not "Romanian Deadlift". Keyed on the exact
# dataset name; anything not listed still gets the generated aliases below.
CURATED_ALIASES: dict[str, list[str]] = {
    "Barbell Bench Press - Medium Grip": ["bench", "bench press", "bb bench", "flat bench"],
    "Barbell Squat": ["squat", "back squat", "bb squat"],
    "Barbell Deadlift": ["deadlift", "dl", "conventional deadlift"],
    "Romanian Deadlift": ["rdl", "romanian"],
    "Sumo Deadlift": ["sumo dl"],
    "Stiff-Legged Barbell Deadlift": ["sldl", "stiff leg deadlift"],
    "Front Barbell Squat": ["front squat"],
    "Standing Military Press": ["ohp", "overhead press", "military press"],
    "Dumbbell Shoulder Press": ["db shoulder press", "dumbbell press"],
    "Incline Dumbbell Press": ["incline db press", "incline dumbbell bench"],
    "Dumbbell Bench Press": ["db bench", "flat dumbbell press"],
    "Bent Over Barbell Row": ["bent over row", "bb row", "barbell row"],
    "Wide-Grip Lat Pulldown": ["lat pulldown", "pulldown", "lat pull"],
    "Pullups": ["pull up", "pullup", "pull-up"],
    "Chin-Up": ["chin up", "chinup"],
    "Barbell Curl": ["bicep curl", "bb curl"],
    "Dumbbell Bicep Curl": ["db curl", "dumbbell curl"],
    "Hammer Curls": ["hammer curl"],
    "Triceps Pushdown": ["pushdown", "tricep pushdown", "rope pushdown"],
    "Close-Grip Barbell Bench Press": ["cgbp", "close grip bench"],
    "Leg Press": ["leg press machine"],
    "Barbell Hip Thrust": ["hip thrust"],
    "Side Lateral Raise": ["lateral raise", "lat raise", "side raise"],
    "Face Pull": ["facepull"],
    "Barbell Shrug": ["shrug"],
}

# Words worth dropping when generating a short alias from a long name.
_NOISE = {"-", "with", "the", "a", "and", "on", "for"}


def _download(refresh: bool = False) -> list[dict]:
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text(encoding="utf-8"))

    log.info("Downloading exercise dataset from %s", SOURCE_URL)
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as r:
        data = json.load(r)

    # Drop images (never served) but keep instructions -- form cues are an
    # obvious later feature and re-downloading to get them would be silly.
    slim = [
        {k: v for k, v in row.items() if k != "images"}
        for row in data
    ]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(slim, indent=1), encoding="utf-8")
    log.info("Cached %d exercises to %s", len(slim), CACHE)
    return slim


def _aliases(name: str) -> list[str]:
    """Curated aliases plus a lowercase form with punctuation stripped."""
    out = list(CURATED_ALIASES.get(name, []))
    plain = name.lower().replace("-", " ").replace("/", " ")
    plain = " ".join(w for w in plain.split() if w not in _NOISE)
    if plain and plain != name.lower():
        out.append(plain)
    return sorted(set(out))


def _to_row(raw: dict) -> tuple[str, str, str, bool, list[str], list[str]] | None:
    name = (raw.get("name") or "").strip()
    if not name:
        return None
    if (raw.get("category") or "") in SKIP_CATEGORIES:
        return None

    primary = raw.get("primaryMuscles") or []
    group = next((MUSCLE_TO_GROUP[m] for m in primary if m in MUSCLE_TO_GROUP), None)
    if group is None:
        # No mappable primary muscle means we cannot file it under a training
        # group; skip rather than dumping it into a misleading bucket.
        return None

    equipment = EQUIPMENT_MAP.get(raw.get("equipment") or "", "other")
    is_compound = (raw.get("mechanic") or "") == "compound"

    secondary = sorted(
        {
            MUSCLE_TO_GROUP[m]
            for m in (raw.get("secondaryMuscles") or [])
            if m in MUSCLE_TO_GROUP and MUSCLE_TO_GROUP[m] != group
        }
    )

    return name, group, equipment, is_compound, secondary, _aliases(name)


async def run(group: str | None = None, refresh: bool = False) -> None:
    await init_db()

    rows = [r for r in (_to_row(x) for x in _download(refresh)) if r is not None]
    # The dataset has a handful of exact-duplicate names; keep the first.
    seen: set[str] = set()
    deduped = []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0])
        deduped.append(r)

    if group:
        deduped = [r for r in deduped if r[1] == group]
    if not deduped:
        log.warning("No exercises matched group=%r", group)
        return

    async with SessionLocal() as session:
        # `exercises` has no unique constraint on name, so ON CONFLICT isn't
        # available. Read existing names and insert only what's missing --
        # which also makes re-running this safe and non-destructive.
        existing = set((await session.execute(select(Exercise.name))).scalars().all())

        added = 0
        for name, muscle, equipment, compound, secondary, aliases in deduped:
            if name in existing:
                continue
            session.add(
                Exercise(
                    name=name,
                    muscle_group=muscle,
                    equipment=equipment,
                    is_compound=compound,
                    secondary_muscles=list(secondary),
                    aliases=list(aliases),
                )
            )
            added += 1

        await session.commit()

    log.info(
        "Catalogue: %d eligible, %d new, %d already present",
        len(deduped), added, len(deduped) - added,
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--group", default=None, help="chest | back | legs | shoulders | biceps | triceps | core | forearms | neck")
    p.add_argument("--refresh", action="store_true", help="re-download the cached dataset")
    args = p.parse_args()
    asyncio.run(run(args.group, args.refresh))


if __name__ == "__main__":
    main()
