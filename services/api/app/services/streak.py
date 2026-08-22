"""Consistency, and how the current phase is actually going.

TWO QUESTIONS, ONE FILE, BECAUSE THEY ARE THE SAME QUESTION
"Have I been doing this?" and "is it working?" are what someone opens a
tracker to find out, and answering the first without the second is how streak
mechanics turn into a slot machine. A 40-day streak on a bulk that has put on
nothing but fat is not an achievement, and this module is built so the app
can never show the streak without the verdict beside it.

WHY A STREAK AT ALL, GIVEN THAT
Because adherence IS the intervention. Adaptive TDEE needs logged days to
converge -- the expenditure estimate is derived from intake against weight
trend, so a week with four logged days produces a materially worse number than
a week with seven. The streak is not a game mechanic bolted on for retention;
it is a readout of how much the engine has to work with, which is why
`ConsistencyReport` carries `data_confidence` alongside the day count.

WHY MISSING A DAY DOES NOT RESET TO ZERO
It nearly always does in other apps, and it is the single most common reason
people quit: one missed day makes the number worthless, so the next day is
easier to skip too. Here a streak survives a configurable number of misses per
window (see `GRACE_DAYS_PER_WEEK`) and instead reports an honest consistency
percentage next to it. The percentage is the truthful measure; the streak is
the motivating one. Showing both means the motivating one cannot lie.

ALL PURE FUNCTIONS, NO I/O. The router hands in dates and weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

#: How many missed days a week may contain before the streak breaks.
#:
#: One. Life produces exactly one bad day a week fairly often -- a flight, a
#: wedding, a stomach bug -- and none of those mean somebody stopped caring.
#: Two in a week does mean the habit slipped, and the number should say so.
GRACE_DAYS_PER_WEEK = 1

#: Below this, the adaptive engine's output is a prior with noise on it rather
#: than a measurement, and the UI should say so instead of showing a verdict.
MIN_DAYS_FOR_CONFIDENCE = 10

#: A phase shorter than this cannot be judged. Water, glycogen and gut content
#: move the scale by more than two weeks of real tissue change.
MIN_PHASE_WEEKS = 2.0

#: Milestones worth marking. Deliberately sparse and deliberately unrounded at
#: the start: 3 and 7 are where the habit is actually won, and a first badge
#: at 30 days is a badge nobody ever sees.
MILESTONES: tuple[tuple[int, str], ...] = (
    (3, "Three days"),
    (7, "One week"),
    (14, "Two weeks"),
    (30, "One month"),
    (60, "Two months"),
    (100, "One hundred days"),
    (180, "Half a year"),
    (365, "One year"),
)


class PhaseVerdict(str, Enum):
    """How the current bulk or cut is going."""

    on_track = "on_track"
    too_fast = "too_fast"
    too_slow = "too_slow"
    wrong_way = "wrong_way"
    #: Non-negotiable #3. Not enough data is a real answer, not a gap to fill.
    insufficient_data = "insufficient_data"


@dataclass
class ConsistencyReport:
    current_streak: int
    longest_streak: int
    days_logged: int
    #: Days in the window we are measuring over.
    window_days: int
    #: Logged days as a fraction of the window. The honest number.
    consistency_pct: float
    #: True when today is already logged, so the UI knows whether to nudge.
    logged_today: bool
    #: How much the adaptive engine can trust its own output right now.
    data_confidence: float
    #: The milestone just reached, if any -- for a one-time celebration.
    milestone: str | None
    #: The next one, and how far away it is.
    next_milestone: str | None
    days_to_next: int | None
    headline: str = ""


@dataclass
class PhaseReport:
    verdict: PhaseVerdict
    #: 'gain', 'lose', 'recomp', 'maintain'
    goal: str
    weeks_elapsed: float
    start_weight_kg: float | None
    current_weight_kg: float | None
    total_change_kg: float | None
    rate_kg_per_week: float | None
    target_rate_kg_per_week: float | None
    headline: str = ""
    detail: str = ""
    notes: list[str] = field(default_factory=list)


def _weeks_between(a: date, b: date) -> float:
    return max(0.0, (b - a).days / 7.0)


def compute_streak(
    logged_days: set[date] | list[date],
    today: date,
    *,
    grace_per_week: int = GRACE_DAYS_PER_WEEK,
) -> tuple[int, int]:
    """Current and longest streak, walking backwards from today.

    A day counts if it was logged. A gap is forgiven while the running window
    has grace left; the streak ends at the gap that exhausts it.

    Today itself not being logged does NOT break the streak -- it is not over
    yet. Starting the walk at yesterday when today is blank is what stops the
    number flickering to zero every morning, which would be both wrong and
    demoralising at exactly the wrong moment.
    """
    days = set(logged_days)
    if not days:
        return 0, 0

    # ---- current -------------------------------------------------------
    cursor = today if today in days else today - timedelta(days=1)
    current = 0
    misses = 0
    while True:
        if cursor in days:
            current += 1
            misses = 0
        else:
            misses += 1
            if misses > grace_per_week:
                break
            # A forgiven day is not a credited day: it keeps the chain alive
            # without inflating the count, so the number stays a count of days
            # the user actually showed up.
        cursor -= timedelta(days=1)
        if (today - cursor).days > 3650:
            break

    # ---- longest -------------------------------------------------------
    ordered = sorted(days)
    longest = 0
    run = 0
    prev: date | None = None
    for d in ordered:
        if prev is None or (d - prev).days <= 1 + grace_per_week:
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        prev = d

    return current, max(longest, current)


def _milestones_for(streak: int) -> tuple[str | None, str | None, int | None]:
    hit = next((name for days, name in MILESTONES if days == streak), None)
    nxt = next(((days, name) for days, name in MILESTONES if days > streak), None)
    if nxt is None:
        return hit, None, None
    return hit, nxt[1], nxt[0] - streak


def consistency(
    logged_days: set[date] | list[date],
    today: date,
    window_days: int = 30,
) -> ConsistencyReport:
    """How consistently this person has been logging."""
    days = set(logged_days)
    window_start = today - timedelta(days=window_days - 1)
    in_window = {d for d in days if window_start <= d <= today}

    current, longest = compute_streak(days, today)
    pct = len(in_window) / window_days if window_days else 0.0
    hit, nxt, to_next = _milestones_for(current)

    # Confidence rises with logged days and saturates: past three weeks of
    # good data, more data barely improves the estimate, and implying
    # otherwise would make a 95% look meaningfully better than an 85%.
    confidence = min(1.0, len(in_window) / 21.0)

    if current == 0:
        headline = "Log anything today and the streak starts again."
    elif hit:
        headline = f"{hit}. That's {current} days of data the engine can use."
    elif len(in_window) < MIN_DAYS_FOR_CONFIDENCE:
        headline = (
            f"{current} day{'s' if current != 1 else ''} in. "
            f"{MIN_DAYS_FOR_CONFIDENCE - len(in_window)} more and your target "
            "stops being a formula's guess."
        )
    elif pct >= 0.85:
        headline = f"{current} days, {round(pct * 100)}% of the month logged."
    else:
        headline = (
            f"{current} days. Logging {round(pct * 100)}% of days — the more "
            "you log, the tighter your target gets."
        )

    return ConsistencyReport(
        current_streak=current,
        longest_streak=longest,
        days_logged=len(in_window),
        window_days=window_days,
        consistency_pct=round(pct, 3),
        logged_today=today in days,
        data_confidence=round(confidence, 2),
        milestone=hit,
        next_milestone=nxt,
        days_to_next=to_next,
        headline=headline,
    )


#: How far off the intended rate counts as "on track".
#:
#: Generous, because the trend itself carries noise and a tighter band would
#: have the app crying wolf every other week.
RATE_TOLERANCE = 0.45

#: A bulk faster than this is mostly fat; a cut faster than this costs muscle.
#: Expressed as a multiple of the target rate rather than an absolute, because
#: a 0.25 kg/wk target and a 0.75 kg/wk target have different definitions of
#: "too fast".
FAST_MULTIPLE = 1.6


def phase_progress(
    goal: str,
    start_weight_kg: float | None,
    current_weight_kg: float | None,
    started_on: date | None,
    today: date,
    target_rate_kg_per_week: float | None,
) -> PhaseReport:
    """Is this bulk or cut doing what it was supposed to do?

    Deliberately reports on the TREND weight the caller passes in, never on a
    single morning's weigh-in. The caller is responsible for smoothing; this
    function only judges.
    """
    weeks = _weeks_between(started_on, today) if started_on else 0.0
    base = PhaseReport(
        verdict=PhaseVerdict.insufficient_data,
        goal=goal,
        weeks_elapsed=round(weeks, 1),
        start_weight_kg=start_weight_kg,
        current_weight_kg=current_weight_kg,
        total_change_kg=None,
        rate_kg_per_week=None,
        target_rate_kg_per_week=target_rate_kg_per_week,
    )

    if start_weight_kg is None or current_weight_kg is None or started_on is None:
        base.headline = "Not enough weigh-ins yet"
        base.detail = (
            "Two weeks of weigh-ins is the minimum that means anything. "
            "Before that the scale is mostly water and salt."
        )
        return base

    change = current_weight_kg - start_weight_kg
    base.total_change_kg = round(change, 2)

    if weeks < MIN_PHASE_WEEKS:
        base.headline = f"{weeks:.1f} weeks in — too early to call"
        base.detail = (
            "Water, glycogen and gut content move the scale more than two "
            "weeks of real tissue change does. Ask again next week."
        )
        return base

    rate = change / weeks
    base.rate_kg_per_week = round(rate, 3)

    direction = 1.0 if goal == "gain" else -1.0 if goal == "lose" else 0.0
    target = target_rate_kg_per_week
    if target is None:
        target = 0.25 * direction if direction else 0.0
    base.target_rate_kg_per_week = round(target, 3)

    weeks_str = f"{weeks:.0f} week{'s' if weeks >= 2 else ''}"
    sign = "+" if change >= 0 else ""
    base.detail = f"{sign}{change:.1f} kg over {weeks_str}."

    # ---- recomp and maintenance are judged on STILLNESS -----------------
    if direction == 0.0:
        if abs(rate) <= 0.15:
            base.verdict = PhaseVerdict.on_track
            base.headline = "Holding steady"
            base.notes.append(
                "A flat scale is the point here. Whether it's recomposition "
                "rather than a stall is a question your lifts answer, not "
                "your weight."
            )
        else:
            base.verdict = PhaseVerdict.wrong_way
            base.headline = "Drifting"
            base.notes.append(
                f"You're moving {abs(rate):.2f} kg/wk when the plan was to "
                "hold. Worth a look at portions before anything else."
            )
        return base

    # ---- a real bulk or cut ---------------------------------------------
    going_backwards = (rate * direction) < 0
    if going_backwards:
        base.verdict = PhaseVerdict.wrong_way
        base.headline = "Going the wrong way"
        base.notes.append(
            "You're "
            + ("losing weight on a gaining phase." if direction > 0 else "gaining weight on a cut.")
            + " Before changing calories, check the obvious: are all your days "
            "actually logged?"
        )
        return base

    ratio = abs(rate) / abs(target) if target else 0.0

    if ratio >= FAST_MULTIPLE:
        base.verdict = PhaseVerdict.too_fast
        base.headline = "Faster than planned"
        base.notes.append(
            f"Moving {abs(rate):.2f} kg/wk against a {abs(target):.2f} target. "
            + (
                "Past roughly double the target, most of the extra is fat "
                "rather than muscle."
                if direction > 0
                else "Cutting this fast is where lifts start dropping, and a "
                "dropping lift means the weight coming off isn't all fat."
            )
        )
    elif abs(abs(rate) - abs(target)) <= RATE_TOLERANCE * abs(target):
        base.verdict = PhaseVerdict.on_track
        base.headline = "On track"
        base.notes.append(
            f"{abs(rate):.2f} kg/wk against a {abs(target):.2f} target. "
            "Nothing to change."
        )
    elif ratio < 1:
        base.verdict = PhaseVerdict.too_slow
        base.headline = "Slower than planned"
        base.notes.append(
            f"{abs(rate):.2f} kg/wk against a {abs(target):.2f} target. "
            + (
                "There's room to eat more — but check your logging is complete "
                "first, since under-logging looks identical to this."
                if direction > 0
                else "Slow is not a problem if your lifts are holding. It only "
                "becomes one if you're impatient enough to overcorrect."
            )
        )
    else:
        base.verdict = PhaseVerdict.on_track
        base.headline = "On track"
        base.notes.append(
            f"{abs(rate):.2f} kg/wk against a {abs(target):.2f} target."
        )

    return base
