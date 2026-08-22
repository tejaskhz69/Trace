"""A weekly calorie budget, with planned redistribution.

THE BET
The daily target is what makes people quit at 8pm. You are 300 over, the day
is "ruined", and the rational move — eat less tomorrow — is invisible because
the app resets to a fresh verdict at midnight. So people either give up for
the evening or give up entirely.

A week-level budget fixes the accounting to match how eating actually works.
Being 300 over on Tuesday is not a failure, it is 300 borrowed from Thursday.
Dinner out on Saturday is not a lapse, it is something you SCHEDULE, and the
app moves the calories for you before it happens.

THE ONE RULE THAT MAKES THIS SAFE
**Nothing carries into the next week.** An overspend is settled inside the
same seven days and then forgotten. This is the difference between a budget
and a debt: rolling a deficit forward compounds, and a user who starts Monday
already 900 in the hole has been handed a reason to quit that the app
invented. `settle()` exists precisely so this cannot happen by accident.

WHY REDISTRIBUTION IS CAPPED
Moving the whole week into Saturday would technically balance and would also
be terrible advice — three days at 1,200 kcal to fund one at 4,000 costs
muscle and makes adherence worse, not better. `MAX_DAILY_SHIFT_PCT` bounds how
far any single day may move from its baseline in either direction.

PURE FUNCTIONS, NO I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

#: How far a single day may be pushed from its baseline, either way.
#:
#: 25%: on a 2,700 kcal target that is ±675, which comfortably funds a dinner
#: out without producing a day so low that it costs training quality or so
#: high that it stops being a plan.
MAX_DAILY_SHIFT_PCT = 0.25

#: A day already logged is history. Only days from today forward can absorb
#: a shift, which is the difference between planning and rewriting the past.
#: (Today counts as adjustable: most of it is usually still ahead.)


@dataclass
class DayPlan:
    day: date
    #: What this day started as, before any planning.
    baseline_kcal: float
    #: What it is now, after redistribution.
    planned_kcal: float
    #: Actual intake, when the day is done or in progress.
    logged_kcal: float | None
    #: True when the user marked this day as an event (dinner out, party).
    flagged: bool = False
    is_past: bool = False
    is_today: bool = False

    @property
    def shift(self) -> float:
        return round(self.planned_kcal - self.baseline_kcal, 1)

    @property
    def delta(self) -> float | None:
        """Logged minus planned. Negative is under."""
        if self.logged_kcal is None:
            return None
        return round(self.logged_kcal - self.planned_kcal, 1)


@dataclass
class WeekBudget:
    start: date
    end: date
    daily_target: float
    week_target: float
    spent: float
    remaining: float
    days_left: int
    #: What the remaining days average out to. The number the user acts on.
    per_day_remaining: float | None
    #: 'on_pace' | 'ahead' | 'behind' | 'blown'
    status: str
    days: list[DayPlan] = field(default_factory=list)
    headline: str = ""
    detail: str = ""
    notes: list[str] = field(default_factory=list)


def week_bounds(today: date, week_starts_monday: bool = True) -> tuple[date, date]:
    """The seven days the budget covers.

    Monday-start by default. It matters more than it sounds: a Sunday-start
    week puts the two days people most often eat out at the START of the
    budget, so they spend the surplus before knowing whether they need it.
    """
    offset = today.weekday() if week_starts_monday else (today.weekday() + 1) % 7
    start = today - timedelta(days=offset)
    return start, start + timedelta(days=6)


def build_week(
    today: date,
    daily_target: float,
    logged_by_day: dict[date, float],
    flagged_days: set[date] | None = None,
    week_starts_monday: bool = True,
) -> WeekBudget:
    """Build the week's plan, redistributing around any flagged days."""
    start, end = week_bounds(today, week_starts_monday)
    flagged = flagged_days or set()
    week_target = daily_target * 7

    days: list[DayPlan] = []
    for i in range(7):
        d = start + timedelta(days=i)
        days.append(
            DayPlan(
                day=d,
                baseline_kcal=daily_target,
                planned_kcal=daily_target,
                logged_kcal=logged_by_day.get(d),
                flagged=d in flagged,
                is_past=d < today,
                is_today=d == today,
            )
        )

    _redistribute(days, today, daily_target)

    spent = sum(d.logged_kcal or 0.0 for d in days if d.logged_kcal is not None)
    remaining = week_target - spent
    future = [d for d in days if not d.is_past]
    days_left = len(future)
    per_day = remaining / days_left if days_left else None

    status, headline, detail, notes = _assess(
        remaining, days_left, per_day, daily_target, days
    )

    return WeekBudget(
        start=start,
        end=end,
        daily_target=round(daily_target, 1),
        week_target=round(week_target, 1),
        spent=round(spent, 1),
        remaining=round(remaining, 1),
        days_left=days_left,
        per_day_remaining=round(per_day, 1) if per_day is not None else None,
        status=status,
        days=days,
        headline=headline,
        detail=detail,
        notes=notes,
    )


def _redistribute(days: list[DayPlan], today: date, daily_target: float) -> None:
    """Move calories into flagged days, out of the other adjustable ones.

    Only days from today forward can give or receive. A past day is history,
    and quietly rewriting what Tuesday "should" have been would make every
    number the user already saw retroactively wrong.
    """
    adjustable = [d for d in days if not d.is_past]
    receivers = [d for d in adjustable if d.flagged]
    donors = [d for d in adjustable if not d.flagged]
    if not receivers or not donors:
        return

    cap = daily_target * MAX_DAILY_SHIFT_PCT

    # Each flagged day asks for the cap; the donors fund what they can between
    # them, also capped. The bound applies to BOTH sides, so a big ask cannot
    # strip one donor day down to nothing.
    want = cap * len(receivers)
    can_give = cap * len(donors)
    moved = min(want, can_give)
    if moved <= 0:
        return

    per_receiver = moved / len(receivers)
    per_donor = moved / len(donors)

    for d in receivers:
        d.planned_kcal = round(d.baseline_kcal + per_receiver, 1)
    for d in donors:
        d.planned_kcal = round(d.baseline_kcal - per_donor, 1)


def _assess(
    remaining: float,
    days_left: int,
    per_day: float | None,
    daily_target: float,
    days: list[DayPlan],
) -> tuple[str, str, str, list[str]]:
    notes: list[str] = [
        "Nothing carries into next week. An overspend is settled inside these "
        "seven days and then forgotten — debt across weeks is how people quit."
    ]

    if days_left == 0:
        over = -remaining
        if remaining >= 0:
            return (
                "on_pace",
                "Week closed on target",
                f"{round(remaining):,} kcal under. Next week starts clean.",
                notes,
            )
        return (
            "behind",
            "Week closed over",
            f"{round(over):,} kcal over. Next week starts clean anyway.",
            notes,
        )

    if per_day is None:
        return "on_pace", "Week open", "", notes

    # BLOWN means the week cannot be recovered without a day so low it would
    # be bad advice to attempt. Saying so plainly beats showing a target
    # nobody should hit.
    floor = daily_target * (1 - MAX_DAILY_SHIFT_PCT)
    if per_day < floor * 0.8:
        return (
            "blown",
            "This week got away",
            f"Hitting the week now would mean {round(per_day):,}/day, which is "
            "too low to be worth doing. Eat at your normal target and let this "
            "one go — it's seven days out of a trend measured in months.",
            notes,
        )

    ratio = per_day / daily_target
    if ratio >= 1.08:
        status, headline = "ahead", "Ahead of the budget"
    elif ratio <= 0.92:
        status, headline = "behind", "Behind the budget"
    else:
        status, headline = "on_pace", "On pace"

    day_word = "day" if days_left == 1 else "days"
    detail = (
        f"{round(remaining):,} kcal across {days_left} {day_word} — "
        f"{round(per_day):,}/day."
    )

    flagged = [d for d in days if d.flagged and not d.is_past]
    if flagged:
        moved = round(flagged[0].shift)
        if moved > 0:
            notes.insert(
                0,
                f"You've flagged {flagged[0].day.strftime('%A')}. "
                f"Trace moved +{moved:,} kcal into it from the rest of the "
                "week, so eating out costs you nothing — the week still lands "
                "on target.",
            )

    return status, headline, detail, notes


def settle(week: WeekBudget) -> float:
    """What carries into next week.

    Always zero. This function exists so that the rule is a thing in the code
    with a test on it, rather than an omission somebody later "fixes" by
    adding a carry-over they think is a feature.
    """
    return 0.0
