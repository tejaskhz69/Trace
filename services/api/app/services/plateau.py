"""Has this lift actually stopped moving?

WHAT THIS IS FOR
A plateau is the moment the product has something useful to say: the lifter is
working, the numbers are not moving, and the reason matters. Get it wrong in
one direction and the app nags after a single bad night's sleep. Get it wrong
in the other and somebody spends four months at the same weight while a
progress chart tells them everything is fine.

So the bar for saying "plateau" is deliberately high, and every path that is
NOT a plateau gets its own named status. `confounded` and `incomplete_
execution` are not failure modes of this detector -- they are most of its
value. Saying "you missed a third of your sets" is more useful than saying
"you have plateaued", and it is also true more often.

DETERMINISTIC, AND NO MODEL
Pure functions over facts the caller already has. No I/O, no clock, no LLM.
The same history always produces the same assessment, because a detector that
returned "watch" on Tuesday and "confirmed_plateau" on Wednesday from
identical data would be unexplainable and the user would be right not to
trust it. `today` is a parameter, not `date.today()`.

SEGMENTATION IS CONSUMED, NEVER RE-DERIVED
`GET /strength/progress` already groups history by
`(exercise, station, station_profile)`. This module takes those groups as
given. That is what makes equipment comparability a lookup rather than a
question: if the lifter moved from the PRIME row to the Hammer row, the two
sets of exposures arrive as two series and `not_comparable` falls out of the
structure. The user is never asked whether the equipment was the same --
`SetLog` already knows.

WHY LOAD IS NEVER CONVERTED BETWEEN STATIONS
It cannot be. Plate leverage runs 2:1 to 5:1, is unpublished, and varies
through the range of motion. 60 kg on one row machine and 60 kg on another
are not comparable numbers, and a "normalised" figure would be a fabrication
presented with a decimal point. Two stations means two trends. See the note
on `Station` in models.py.

WHAT THIS MODULE WILL NOT DO
It does not diagnose, it does not mention pain as a medical matter beyond
stopping, and it does not change a programme. It returns an assessment. Every
recommendation that alters training carries `requires_confirmation`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

__all__ = [
    "MIN_COMPLETION_RATE",
    "MIN_EXPOSURES",
    "MIN_SPAN_DAYS",
    "Exposure",
    "PerformanceSnapshot",
    "PlateauAssessment",
    "PlateauStatus",
    "Series",
    "SeriesKey",
    "assess_plateau",
]


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

#: Three qualifying exposures before "not moving" means anything. Two is a
#: bad week.
MIN_EXPOSURES = 3

#: ...and they must span about three weeks. THIS, not the exposure count, is
#: what governs how soon a verdict is possible: a movement trained three
#: times a week reaches three exposures in seven days and then waits on the
#: calendar. A programme that rotates exercises between weeks therefore never
#: satisfies this, whatever the training frequency -- which makes generator
#: design, not catalogue size, the thing that decides whether this detector
#: ever fires. See "Exercise prioritisation" in the upgrade plan.
MIN_SPAN_DAYS = 21

#: Four exposures over four weeks before it is called rather than watched.
CONFIRM_EXPOSURES = 4
CONFIRM_SPAN_DAYS = 28

#: Six over six weeks, still flat, is a different conversation.
PERSISTENT_EXPOSURES = 6
PERSISTENT_SPAN_DAYS = 42

#: Below this share of prescribed sets completed, the question is execution,
#: not programming.
MIN_COMPLETION_RATE = 0.80

#: Readiness is 0..1. Below this, a flat session has an explanation that is
#: not the programme.
POOR_READINESS = 0.5

#: How much a metric has to move to count as movement rather than noise.
#: e1RM from a top set carries a few percent of noise -- bar speed, sleep,
#: how honest the RIR call was. Matches strength.ON_TARGET_BAND.
IMPROVEMENT_BAND = 0.03

#: Volume swings more than e1RM does, so it needs more room before a rise
#: counts as progress.
VOLUME_IMPROVEMENT_BAND = 0.05


class PlateauStatus(str, Enum):
    """Ten outcomes. Only two of them are a plateau."""

    insufficient_data = "insufficient_data"
    progressing = "progressing"
    not_comparable = "not_comparable"
    incomplete_execution = "incomplete_execution"
    deload_period = "deload_period"
    confounded = "confounded"
    watch = "watch"
    confirmed_plateau = "confirmed_plateau"
    persistent_plateau = "persistent_plateau"
    safety_stop = "safety_stop"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Exposure:
    """One session of one movement, on one station, at one setting.

    Assembled by the router from `SetLog`. Everything optional is genuinely
    unknown rather than defaulted -- `readiness=None` means we did not ask,
    which is not the same as "readiness was fine", and treating it as fine is
    how a detector starts blaming the programme for a bad week.
    """

    performed_on: date
    top_set_weight_kg: float
    top_set_reps: int
    top_set_e1rm: float | None
    volume_load: float
    sets_prescribed: int
    sets_completed: int
    top_set_rir: float | None = None
    deload: bool = False
    pain_flag: bool = False
    readiness: float | None = None

    @property
    def completion_rate(self) -> float:
        """Unprescribed sessions count as fully executed -- a lifter freestyle
        logging has not missed anything."""
        if self.sets_prescribed <= 0:
            return 1.0
        return self.sets_completed / self.sets_prescribed


@dataclass(frozen=True)
class SeriesKey:
    """Which movement on which machine at which setting."""

    exercise_id: str
    exercise_name: str
    station_id: str | None = None
    station_profile: str | None = None
    #: "Not recorded" for station-less work. Named rather than blank so no
    #: explanation ever contains an anonymous piece of equipment.
    station_name: str = "Not recorded"

    def describe(self) -> str:
        where = (
            "" if self.station_id is None else f" on the {self.station_name}"
        )
        setting = (
            "" if not self.station_profile else f" at setting {self.station_profile}"
        )
        return f"{self.exercise_name}{where}{setting}"


@dataclass(frozen=True)
class Series:
    """One comparable trend, exactly as `/strength/progress` grouped it."""

    key: SeriesKey
    exposures: tuple[Exposure, ...] = ()

    def ordered(self) -> tuple[Exposure, ...]:
        return tuple(sorted(self.exposures, key=lambda e: e.performed_on))


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PerformanceSnapshot:
    """What the lift looked like at one end of the window."""

    performed_on: date
    top_set_weight_kg: float
    top_set_reps: int
    top_set_e1rm: float | None
    volume_load: float
    top_set_rir: float | None = None

    @classmethod
    def of(cls, e: Exposure) -> PerformanceSnapshot:
        return cls(
            performed_on=e.performed_on,
            top_set_weight_kg=e.top_set_weight_kg,
            top_set_reps=e.top_set_reps,
            top_set_e1rm=e.top_set_e1rm,
            volume_load=e.volume_load,
            top_set_rir=e.top_set_rir,
        )


@dataclass(frozen=True)
class PlateauAssessment:
    """Frozen, and complete enough to show the user its own reasoning.

    `evidence` is the list of sessions actually considered. The spec requires
    the user be able to see which sessions were counted, and an assessment
    that cannot show its working is one the user has to take on faith.
    """

    status: PlateauStatus
    series: SeriesKey
    reason: str
    recommendation: str
    confidence: float = 0.0
    evidence: tuple[date, ...] = ()
    baseline: PerformanceSnapshot | None = None
    current: PerformanceSnapshot | None = None
    stalled_metric: str | None = None
    requires_confirmation: bool = False
    #: Metrics that DID move, when the answer is `progressing`. Named so the
    #: user sees what is working rather than a bare "keep going".
    improving_metrics: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_plateau(self) -> bool:
        return self.status in (
            PlateauStatus.confirmed_plateau,
            PlateauStatus.persistent_plateau,
        )


# ---------------------------------------------------------------------------
# The detector
# ---------------------------------------------------------------------------


def assess_plateau(
    series: Sequence[Series],
    *,
    today: date,
    adjudication_insufficient: bool = False,
    window_days: int = 56,
) -> PlateauAssessment:
    """Assess the most recent comparable trend for one exercise.

    `series` is every group `/strength/progress` returned for this exercise --
    one per (station, profile). Passing them all is what lets a machine change
    be detected without asking the user about it.

    `adjudication_insufficient` is passed in rather than looked up, because
    this module does no I/O and because the dependency should be visible at
    the call site. When the adjudication engine cannot reach a verdict, this
    detector stays quiet: the two would otherwise contradict each other in the
    same screen, one saying "not enough data to tell you anything" and the
    other naming a plateau.
    """
    key = _primary_key(series)

    # 1. Suppressed while the strength engine itself has nothing to say.
    if adjudication_insufficient:
        return PlateauAssessment(
            status=PlateauStatus.insufficient_data,
            series=key,
            reason=(
                "There isn't enough training history yet to say anything "
                "reliable about this lift."
            ),
            recommendation="Keep logging your sets.",
        )

    active, others = _active_series(series, today=today, window_days=window_days)
    if active is None:
        return PlateauAssessment(
            status=PlateauStatus.insufficient_data,
            series=key,
            reason="No sessions logged for this lift in the recent window.",
            recommendation="Log this lift to start a trend.",
        )

    key = active.key
    window = _window(active, today=today, window_days=window_days)

    # 2. Safety outranks everything. A flagged session is not a data point
    #    about programming.
    painful = [e for e in window if e.pain_flag]
    if painful:
        return PlateauAssessment(
            status=PlateauStatus.safety_stop,
            series=key,
            reason=(
                f"You flagged pain on {_dates(painful)} for "
                f"{key.describe()}, so we've stopped progression advice here."
            ),
            recommendation=(
                "Hold off on adding load and consider speaking to a "
                "qualified physio or clinician before pushing this lift again."
            ),
            evidence=_dates_tuple(window),
            confidence=1.0,
            requires_confirmation=False,
        )

    # 3. A deload is a planned drop. Reading it as a stall would punish the
    #    user for following the plan.
    deloaded = [e for e in window if e.deload]
    if deloaded:
        return PlateauAssessment(
            status=PlateauStatus.deload_period,
            series=key,
            reason=(
                f"{len(deloaded)} of these sessions were part of a deload, "
                f"so lower numbers are expected."
            ),
            recommendation=(
                "Nothing to change. We'll reassess once you're back to "
                "normal training."
            ),
            evidence=_dates_tuple(window),
            confidence=1.0,
        )

    # 4. Did the equipment change? This is why the series arrive ungrouped.
    switch = _equipment_switch(active, others, today=today, window_days=window_days)
    if switch is not None:
        return switch

    ordered = tuple(sorted(window, key=lambda e: e.performed_on))

    # 5. Enough sessions, over enough calendar.
    if len(ordered) < MIN_EXPOSURES:
        return PlateauAssessment(
            status=PlateauStatus.insufficient_data,
            series=key,
            reason=(
                f"Only {len(ordered)} comparable "
                f"{_sessions(len(ordered))} so far -- we need at least "
                f"{MIN_EXPOSURES} before reading anything into a flat number."
            ),
            recommendation="Keep training this lift as planned.",
            evidence=_dates_tuple(ordered),
        )

    span = (ordered[-1].performed_on - ordered[0].performed_on).days
    if span < MIN_SPAN_DAYS:
        return PlateauAssessment(
            status=PlateauStatus.insufficient_data,
            series=key,
            reason=(
                f"These {len(ordered)} sessions span {span} days. Strength "
                f"moves on a scale of weeks, so we wait for about "
                f"{MIN_SPAN_DAYS} days before calling a lift flat."
            ),
            recommendation="Keep training this lift as planned.",
            evidence=_dates_tuple(ordered),
        )

    baseline, current = ordered[0], ordered[-1]

    # 6. Execution before programming. "You completed 60% of your sets" is a
    #    more useful and more often correct answer than "you have plateaued".
    completion = _mean(e.completion_rate for e in ordered)
    if completion < MIN_COMPLETION_RATE:
        return PlateauAssessment(
            status=PlateauStatus.incomplete_execution,
            series=key,
            reason=(
                f"You completed about {completion:.0%} of the prescribed sets "
                f"across these sessions. That's the more likely reason the "
                f"numbers are flat."
            ),
            recommendation=(
                "Aim to complete the prescribed sets before we change the "
                "programming."
            ),
            evidence=_dates_tuple(ordered),
            baseline=PerformanceSnapshot.of(baseline),
            current=PerformanceSnapshot.of(current),
            confidence=_confidence(ordered, span),
        )

    # 7. Anything improving means this is not a plateau, whatever else is
    #    true. Checked before the confounders so a good result is never
    #    explained away.
    improving = _improving_metrics(baseline, current)
    if improving:
        return PlateauAssessment(
            status=PlateauStatus.progressing,
            series=key,
            reason=(
                f"{key.describe()} is still moving: "
                f"{_join(improving)} improved over these "
                f"{len(ordered)} sessions."
            ),
            recommendation="Keep going -- the current approach is working.",
            evidence=_dates_tuple(ordered),
            baseline=PerformanceSnapshot.of(baseline),
            current=PerformanceSnapshot.of(current),
            improving_metrics=improving,
            confidence=_confidence(ordered, span),
        )

    # 8. Something outside the programme explains it.
    poor = [
        e for e in ordered if e.readiness is not None and e.readiness < POOR_READINESS
    ]
    if len(poor) * 2 >= len(ordered):
        return PlateauAssessment(
            status=PlateauStatus.confounded,
            series=key,
            reason=(
                f"Readiness was low for {len(poor)} of these "
                f"{len(ordered)} sessions -- sleep, stress or accumulated "
                f"fatigue is the likelier explanation than the programme."
            ),
            recommendation=(
                "Look at sleep and overall load before changing this lift."
            ),
            evidence=_dates_tuple(ordered),
            baseline=PerformanceSnapshot.of(baseline),
            current=PerformanceSnapshot.of(current),
            confidence=_confidence(ordered, span),
        )

    # 9. Nothing improved, nothing explains it.
    stalled = _stalled_metric(baseline, current)
    if len(ordered) >= PERSISTENT_EXPOSURES and span >= PERSISTENT_SPAN_DAYS:
        status = PlateauStatus.persistent_plateau
    elif len(ordered) >= CONFIRM_EXPOSURES and span >= CONFIRM_SPAN_DAYS:
        status = PlateauStatus.confirmed_plateau
    else:
        status = PlateauStatus.watch

    return PlateauAssessment(
        status=status,
        series=key,
        reason=_flat_reason(key, ordered, span, current),
        recommendation=_ladder(status, current),
        evidence=_dates_tuple(ordered),
        baseline=PerformanceSnapshot.of(baseline),
        current=PerformanceSnapshot.of(current),
        stalled_metric=stalled,
        confidence=_confidence(ordered, span),
        # Every step of the ladder past "verify execution" changes training,
        # and the spec is explicit that those are recommended, never applied.
        requires_confirmation=status is not PlateauStatus.watch,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _primary_key(series: Sequence[Series]) -> SeriesKey:
    """A key to attach to an assessment made before a series was chosen."""
    if series:
        return series[0].key
    return SeriesKey(exercise_id="", exercise_name="this lift")


def _window(series: Series, *, today: date, window_days: int) -> list[Exposure]:
    return [
        e
        for e in series.ordered()
        if (today - e.performed_on).days <= window_days
        and e.performed_on <= today
    ]


def _active_series(
    series: Sequence[Series], *, today: date, window_days: int
) -> tuple[Series | None, list[Series]]:
    """The series holding the most recent exposure, and the rest.

    Ties break on the series with more exposures, then on the full identity
    of the series -- station name, id and profile. Name alone is not enough:
    two cam settings on one machine share a name, and a tie broken by input
    order would make the answer depend on dict iteration. Determinism is a
    requirement, not a nicety.
    """
    populated = [
        s for s in series if _window(s, today=today, window_days=window_days)
    ]
    if not populated:
        return None, []

    def rank(s: Series) -> tuple[date, int, str, str, str]:
        w = _window(s, today=today, window_days=window_days)
        return (
            max(e.performed_on for e in w),
            len(w),
            s.key.station_name,
            s.key.station_id or "",
            s.key.station_profile or "",
        )

    best = max(populated, key=rank)
    return best, [s for s in populated if s is not best]


def _equipment_switch(
    active: Series,
    others: Sequence[Series],
    *,
    today: date,
    window_days: int,
) -> PlateauAssessment | None:
    """`not_comparable`, decided by lookup and never by asking the user.

    Only fires when the lifter has too little history on the CURRENT setup to
    judge but enough overall -- i.e. the reason we cannot answer is the switch
    itself. If they have plenty of recent history on the new machine, the old
    machine is simply history and not worth mentioning.
    """
    current = _window(active, today=today, window_days=window_days)
    if len(current) >= MIN_EXPOSURES:
        return None

    prior = [
        s
        for s in others
        if _window(s, today=today, window_days=window_days)
    ]
    if not prior:
        return None

    combined = len(current) + sum(
        len(_window(s, today=today, window_days=window_days)) for s in prior
    )
    if combined < MIN_EXPOSURES:
        return None

    previous = max(
        prior,
        key=lambda s: (
            max(
                e.performed_on
                for e in _window(s, today=today, window_days=window_days)
            ),
            s.key.station_name,
            s.key.station_id or "",
            s.key.station_profile or "",
        ),
    )
    return PlateauAssessment(
        status=PlateauStatus.not_comparable,
        series=active.key,
        reason=_switch_reason(previous.key, active.key),
        recommendation=(
            "Nothing to change. We'll start a fresh trend on this setup -- "
            "loads don't carry across from other equipment."
        ),
        evidence=_dates_tuple(current),
        confidence=1.0,
    )


def _switch_reason(before: SeriesKey, after: SeriesKey) -> str:
    """Plain terms, as the spec requires. Same machine at a new cam setting
    is a different stimulus at the same load, so it is named separately."""
    if (
        before.station_id == after.station_id
        and before.station_profile != after.station_profile
    ):
        return (
            f"You changed the setting on the {after.station_name} from "
            f"{before.station_profile or 'unset'} to "
            f"{after.station_profile or 'unset'}. That's a different "
            f"stimulus at the same load, so we compare it separately."
        )
    return (
        f"You moved from the {before.station_name} to the "
        f"{after.station_name}. The same number on the two machines isn't "
        f"the same effort, so we don't compare them."
    )


def _relative(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or before <= 0:
        return None
    return (after - before) / before


def _improving_metrics(
    baseline: Exposure, current: Exposure
) -> tuple[str, ...]:
    """Every tracked metric that genuinely moved up.

    "Reps at the same load" and "RIR at the same load" are only meaningful
    when the load IS the same -- comparing reps across different weights says
    nothing, and counting it would let a drop in weight read as progress.
    """
    out: list[str] = []

    e = _relative(baseline.top_set_e1rm, current.top_set_e1rm)
    if e is not None and e > IMPROVEMENT_BAND:
        out.append("estimated 1RM")

    v = _relative(baseline.volume_load, current.volume_load)
    if v is not None and v > VOLUME_IMPROVEMENT_BAND:
        out.append("total volume")

    same_load = baseline.top_set_weight_kg == current.top_set_weight_kg
    if same_load and current.top_set_reps > baseline.top_set_reps:
        out.append("reps at the same weight")
    if (
        same_load
        and baseline.top_set_rir is not None
        and current.top_set_rir is not None
        and current.top_set_rir > baseline.top_set_rir
        and current.top_set_reps >= baseline.top_set_reps
    ):
        # More left in the tank for the same work is a real improvement.
        out.append("reps in reserve at the same weight")

    return tuple(out)


def _stalled_metric(baseline: Exposure, current: Exposure) -> str:
    if baseline.top_set_e1rm is not None and current.top_set_e1rm is not None:
        return "estimated 1RM"
    if baseline.top_set_weight_kg == current.top_set_weight_kg:
        return "reps at the same weight"
    return "total volume"


def _flat_reason(
    key: SeriesKey, ordered: Sequence[Exposure], span: int, current: Exposure
) -> str:
    reps = current.top_set_reps
    rir = (
        ""
        if current.top_set_rir is None
        else f" at about {current.top_set_rir:g} reps in reserve"
    )
    return (
        f"{key.describe()} has stayed at "
        f"{current.top_set_weight_kg:g} kg across {len(ordered)} qualifying "
        f"{_sessions(len(ordered))} over {span} days. You're still "
        f"completing {reps} {_reps(reps)}{rir}, and you completed the sets "
        f"you were given -- so this looks like a progression plateau rather "
        f"than a bad session."
    )


def _ladder(status: PlateauStatus, current: Exposure) -> str:
    """The response ladder, as options rather than instructions.

    Never "add 5 kg". The step size depends on what the station can actually
    load, which this module does not know and must not guess -- prescribing a
    weight that cannot be put on the machine is worse than prescribing
    nothing.
    """
    base = (
        "Options: hold the weight and aim for one more rep, try the smallest "
        "increase the equipment allows, add a set, or review a temporary "
        "variation."
    )
    if status is PlateauStatus.watch:
        return (
            "Nothing to change yet -- we're watching this one. " + base
        )
    if status is PlateauStatus.persistent_plateau:
        return (
            base + " A planned deload is also worth considering at this "
            "point. Tell us which you'd like and we'll adjust the plan."
        )
    return base + " Tell us which you'd like and we'll adjust the plan."


def _confidence(ordered: Sequence[Exposure], span: int) -> float:
    """More sessions over more weeks, with fewer unknowns, means more
    confidence. Bounded well below 1.0: this is an inference from a handful
    of sessions, and presenting it as certainty would be dishonest."""
    n = min(len(ordered) / PERSISTENT_EXPOSURES, 1.0)
    s = min(span / PERSISTENT_SPAN_DAYS, 1.0)
    known = _mean(1.0 if e.readiness is not None else 0.6 for e in ordered)
    return round(min(0.5 * n + 0.3 * s + 0.2 * known, 0.95), 2)


def _mean(values) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0


def _dates_tuple(exposures: Sequence[Exposure]) -> tuple[date, ...]:
    return tuple(sorted(e.performed_on for e in exposures))


def _dates(exposures: Sequence[Exposure]) -> str:
    return _join([d.isoformat() for d in _dates_tuple(exposures)])


def _join(items: Sequence[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return items[0] if items else ""
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _sessions(n: int) -> str:
    return "session" if n == 1 else "sessions"


def _reps(n: int) -> str:
    return "rep" if n == 1 else "reps"
