"""Weekly training volume per muscle, and whether it is actually productive.

WHAT EVERY OTHER APP DOES
Counts your sets and prints the number. "Biceps: 19." That is a fact with no
verdict attached, and the user is left to guess whether 19 is good. It usually
isn't -- most people under-train their back and over-train their arms, and a
bare tally will never tell them so.

WHAT THIS DOES
Counts the sets, then places the count against the volume range the training
literature associates with growth for that muscle, and says which side of it
you are on. That is the same move the coach engine makes elsewhere: reach for
the cheapest lever, and name it.

A SET IS NOT A UNIT OF WORK FOR ONE MUSCLE
A bench press trains the triceps. Not as much as a triceps pushdown does, but
not zero either, and an app that counts it as zero will tell a lifter to add
arm work they do not need. Secondary muscles therefore count as a FRACTION of
a set (`SECONDARY_CREDIT`), which is the standard convention and is honest
about being a convention.

WHERE THE NUMBERS COME FROM, AND THEIR LIMITS
The ranges below follow the widely-cited landmark framework (Israetel et al.):
a minimum effective volume, a productive band, and a point past which more
sets stop paying and start costing recovery. They are POPULATION guidelines
with large individual variation -- training age, sleep, calories and genetics
all move them. So the copy says "typically" and never "you must", and a user
sitting outside a band is told what it means rather than told off. Do not
present these as measured facts about the person.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# A secondary muscle gets this fraction of a set's credit. Half is the common
# convention: real, but clearly less than direct work.
SECONDARY_CREDIT = 0.5

# Weekly hard sets: (minimum effective, productive ceiling).
#
# Below the first number a muscle is being maintained rather than grown; above
# the second, added sets mostly buy fatigue. `core`, `forearms` and `neck` get
# a zero floor because there is no evidence anyone needs direct work there to
# be healthy -- they are trained plenty as secondaries.
LANDMARKS: dict[str, tuple[float, float]] = {
    "chest": (10, 22),
    "back": (10, 25),
    "legs": (8, 20),
    "shoulders": (8, 26),
    "biceps": (8, 26),
    "triceps": (6, 18),
    "core": (0, 25),
    "forearms": (0, 25),
    "neck": (0, 12),
}
DEFAULT_LANDMARK = (8.0, 20.0)


class VolumeStatus(str, Enum):
    UNTRAINED = "UNTRAINED"    # zero sets this week
    UNDER = "UNDER"            # below the minimum effective volume
    IN_RANGE = "IN_RANGE"      # in the productive band
    OVER = "OVER"              # past the point where sets stop paying


@dataclass
class MuscleVolume:
    muscle: str
    sets: float               # credited sets, secondaries included
    direct_sets: int          # sets where this was the primary muscle
    sessions: int             # distinct days it was trained
    volume_kg: float
    min_effective: float
    productive_max: float
    status: VolumeStatus
    note: str


@dataclass
class VolumeReport:
    days: int
    muscles: list[MuscleVolume]
    total_sets: int
    total_volume_kg: float
    headline: str
    weakest: str | None       # the muscle most worth adding sets to


def landmarks_for(muscle: str, days: int) -> tuple[float, float]:
    """The band for this muscle, scaled to the window being reported.

    The published numbers are PER WEEK. Reporting a 30-day count against a
    weekly band would tell everyone they are massively over-training, so the
    band is scaled by the window instead of the count being squashed into it
    -- that way the raw set count on screen stays the real number the user
    can verify by counting.
    """
    lo, hi = LANDMARKS.get(muscle.lower(), DEFAULT_LANDMARK)
    scale = days / 7.0
    return round(lo * scale, 1), round(hi * scale, 1)


def _status(sets: float, lo: float, hi: float) -> VolumeStatus:
    if sets <= 0:
        return VolumeStatus.UNTRAINED
    if sets < lo:
        return VolumeStatus.UNDER
    if sets > hi:
        return VolumeStatus.OVER
    return VolumeStatus.IN_RANGE


def _note(muscle: str, sets: float, lo: float, hi: float, st: VolumeStatus) -> str:
    """One sentence. It must say what to DO, not just what is true."""
    n = f"{sets:g}"
    if st is VolumeStatus.UNTRAINED:
        if lo <= 0:
            return "Not trained directly. That is fine — it works on other lifts."
        return f"Not trained. {lo:g} sets is where growth typically starts."
    if st is VolumeStatus.UNDER:
        gap = lo - sets
        return (
            f"{n} sets — maintaining, not building. "
            f"About {gap:.0f} more would put it in the productive range."
        )
    if st is VolumeStatus.OVER:
        return (
            f"{n} sets is past the point where more usually pays. "
            f"Those sets would do more for a muscle you are under-training."
        )
    return f"{n} sets — in the range that typically drives growth."


def build_report(
    rows: list[tuple[str, list[str], float, str]],
    *,
    days: int = 7,
) -> VolumeReport:
    """Roll working sets into a per-muscle report.

    `rows` is one tuple per SET:
        (primary_muscle, secondary_muscles, volume_kg, day_key)

    `day_key` is any stable per-day string; it is only used to count distinct
    sessions, so the caller decides whether that means calendar days or
    workout sessions.
    """
    direct: dict[str, int] = {}
    credited: dict[str, float] = {}
    load: dict[str, float] = {}
    days_seen: dict[str, set[str]] = {}

    for primary, secondaries, vol, day in rows:
        p = (primary or "").lower()
        if not p:
            continue
        direct[p] = direct.get(p, 0) + 1
        credited[p] = credited.get(p, 0.0) + 1.0
        load[p] = load.get(p, 0.0) + vol
        days_seen.setdefault(p, set()).add(day)
        for sec in secondaries or []:
            s = (sec or "").lower()
            if not s or s == p:
                continue
            credited[s] = credited.get(s, 0.0) + SECONDARY_CREDIT
            days_seen.setdefault(s, set()).add(day)

    # Every known muscle appears, trained or not. A muscle you have not
    # touched is the single most useful row on this screen, and omitting it
    # because the count is zero hides exactly the thing worth showing.
    muscles: list[MuscleVolume] = []
    for name in sorted(set(LANDMARKS) | set(credited)):
        sets = round(credited.get(name, 0.0), 1)
        lo, hi = landmarks_for(name, days)
        st = _status(sets, lo, hi)
        muscles.append(
            MuscleVolume(
                muscle=name,
                sets=sets,
                direct_sets=direct.get(name, 0),
                sessions=len(days_seen.get(name, ())),
                volume_kg=round(load.get(name, 0.0), 1),
                min_effective=lo,
                productive_max=hi,
                status=st,
                note=_note(name, sets, lo, hi, st),
            )
        )

    muscles.sort(key=lambda m: m.sets, reverse=True)
    total_sets = sum(direct.values())
    total_load = round(sum(load.values()), 1)

    # The weakest link is the one furthest BELOW its floor, measured as a
    # FRACTION of that floor -- so "2 of 10 chest sets" outranks "6 of 8
    # triceps sets", which is the correct priority even though the raw
    # difference is smaller. Muscles with a zero floor can never be the
    # answer, because nobody needs prescribed ab work.
    #
    # A week with nothing logged has no weakest link. Every muscle is at
    # 100% deficit, so picking one would be picking alphabetically and
    # dressing it up as advice.
    behind = [
        m for m in muscles if m.min_effective > 0 and m.sets < m.min_effective
    ]
    weakest = (
        max(behind, key=lambda m: (m.min_effective - m.sets) / m.min_effective).muscle
        if behind and total_sets > 0
        else None
    )

    return VolumeReport(
        days=days,
        muscles=muscles,
        total_sets=total_sets,
        total_volume_kg=total_load,
        headline=_headline(muscles, total_sets, weakest, days),
        weakest=weakest,
    )


def _headline(
    muscles: list[MuscleVolume], total_sets: int, weakest: str | None, days: int
) -> str:
    if total_sets == 0:
        return f"No sets logged in {days} days."
    in_range = sum(1 for m in muscles if m.status is VolumeStatus.IN_RANGE)
    over = [m for m in muscles if m.status is VolumeStatus.OVER]
    if weakest:
        return f"{total_sets} sets · {weakest.capitalize()} is the gap"
    if over:
        return f"{total_sets} sets · {over[0].muscle.capitalize()} is past useful"
    return f"{total_sets} sets · {in_range} muscle groups in range"
