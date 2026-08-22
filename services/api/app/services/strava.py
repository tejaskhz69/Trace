"""Strava activity import: energy estimation and normalisation.

PURE FUNCTIONS ONLY. The HTTP client, the OAuth dance and the database writes
live in `app/routers/strava.py`. Everything here is arithmetic over a payload,
so the numbers a user sees can be tested exhaustively without a network.

THE ONE RULE, RESTATED
----------------------
Importing a ride does NOT change the user's calorie target. Not by a kilo-
calorie. The adaptive TDEE already contains that ride via the weight trend
(see `services/activity.py` for the full argument), so adding it back is
double-counting — and it is double-counting a number that consumer devices
overestimate by 25-90%.

`import_effects()` exists to make that visible rather than merely true: the
review screen lists what an import changes and what it does not, and
"Today's calorie target — Unchanged" is a line the user reads every time.

WHY TWO ESTIMATES
-----------------
A ride with a power meter carries `kilojoules`, which is MEASURED MECHANICAL
WORK, not a model output. That is a genuinely different class of evidence from
Strava's `calories`, which is an estimate from their own algorithm. Showing
both, labelled, and preferring the measured one is honest in a way that
silently picking one is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Energy from measured mechanical work
# ---------------------------------------------------------------------------

# 1 kcal = 4.184 kJ.
KJ_PER_KCAL = 4.184

# Gross mechanical efficiency of cycling: the fraction of metabolic energy that
# becomes work at the pedals. The literature clusters at 20-25% across trained
# and untrained riders, and it is remarkably stable — which is what makes this
# calculation trustworthy rather than a guess.
#
# Note the happy accident this produces: dividing kJ by 4.184 and then by ~0.24
# is very nearly multiplying by 1. That is the origin of the "kJ ≈ kcal" rule
# of thumb cyclists use. We do the real arithmetic anyway, so that changing the
# efficiency constant actually changes the answer.
CYCLING_GROSS_EFFICIENCY = 0.24

# Sanity bounds. A "ride" reporting 40,000 kcal is corrupt data, not an
# achievement, and it must not reach the weekly training load.
MAX_PLAUSIBLE_KCAL_PER_HOUR = 1_500.0
MIN_DURATION_MINUTES = 1.0


def kcal_from_kilojoules(kilojoules: float) -> float:
    """Convert measured pedal work to metabolic energy expenditure."""
    if kilojoules <= 0:
        return 0.0
    return (kilojoules / KJ_PER_KCAL) / CYCLING_GROSS_EFFICIENCY


@dataclass
class EnergyEstimate:
    """What we think the activity cost, and how confident we are in that."""

    kcal: float
    source: str          # 'power' | 'strava' | 'duration'
    label: str           # shown in the UI, e.g. "From power"
    detail: str          # e.g. "1,012 kJ measured"
    # True only when the number came from a sensor rather than a model. The UI
    # leans on this to decide whether to say "measured" or "estimated".
    is_measured: bool


@dataclass
class EnergyOptions:
    """Every estimate we can offer, best first.

    The review screen shows all of them so the user can see that we did not
    invent a number — and can pick the other one if they disagree.
    """

    chosen: EnergyEstimate
    alternatives: list[EnergyEstimate] = field(default_factory=list)


def estimate_energy(
    *,
    kilojoules: float | None,
    strava_calories: float | None,
    duration_minutes: float,
    activity_type: str,
    weight_kg: float | None = None,
) -> EnergyOptions | None:
    """Rank the available energy estimates for one activity.

    Returns None when there is nothing to go on at all — refusing to answer
    beats inventing a number (CLAUDE.md non-negotiable #3). A caller that gets
    None should store the activity with no energy figure rather than a zero,
    because zero reads as "you burned nothing" instead of "we don't know".
    """
    options: list[EnergyEstimate] = []

    # 1. Measured work. Only meaningful for pedal-based activities, where the
    #    power meter is measuring the thing that actually moves the bike.
    if kilojoules and kilojoules > 0 and activity_type in _POWER_METER_SPORTS:
        options.append(
            EnergyEstimate(
                kcal=round(kcal_from_kilojoules(kilojoules)),
                source="power",
                label="From power",
                detail=f"{kilojoules:,.0f} kJ measured",
                is_measured=True,
            )
        )

    # 2. Strava's own model. An estimate, and labelled as one.
    if strava_calories and strava_calories > 0:
        options.append(
            EnergyEstimate(
                kcal=round(strava_calories),
                source="strava",
                label="Strava est.",
                detail="their model",
                is_measured=False,
            )
        )

    # 3. Last resort: MET-based, from duration and body weight. Crude, and the
    #    UI should say so.
    if not options and duration_minutes >= MIN_DURATION_MINUTES and weight_kg:
        met = MET_BY_SPORT.get(activity_type, 6.0)
        kcal = met * weight_kg * (duration_minutes / 60.0)
        options.append(
            EnergyEstimate(
                kcal=round(kcal),
                source="duration",
                label="Estimated",
                detail=f"{met:g} MET × {duration_minutes:.0f} min",
                is_measured=False,
            )
        )

    options = [o for o in options if _plausible(o.kcal, duration_minutes)]
    if not options:
        return None

    return EnergyOptions(chosen=options[0], alternatives=options[1:])


def _plausible(kcal: float, duration_minutes: float) -> bool:
    """Reject figures no human produces, so corrupt data can't poison the load."""
    if kcal <= 0:
        return False
    hours = max(duration_minutes, MIN_DURATION_MINUTES) / 60.0
    return kcal <= MAX_PLAUSIBLE_KCAL_PER_HOUR * hours


# Sports where a `kilojoules` field represents real measured work rather than
# a derived guess. Strava reports kilojoules only for rides with a power meter.
_POWER_METER_SPORTS = frozenset({"cycling", "virtual_cycling", "ebike"})

# Compendium of Physical Activities values, moderate intensity. Only used when
# nothing better exists.
MET_BY_SPORT: dict[str, float] = {
    "running": 9.8,
    "cycling": 8.0,
    "walking": 3.5,
    "swimming": 7.0,
    "rowing": 7.0,
    "hiit": 8.0,
    "badminton": 5.5,
    "pickleball": 4.8,
    "cricket": 4.8,
    "tennis": 7.3,
    "football": 7.0,
    "basketball": 6.5,
    "hiking": 6.0,
    "elliptical": 5.0,
    "stair_stepper": 9.0,
    "weight_training": 3.5,
    "yoga": 2.5,
    "workout": 5.0,
}


# ---------------------------------------------------------------------------
# Activity type normalisation
# ---------------------------------------------------------------------------

# Strava's `sport_type` vocabulary mapped onto ours. Anything unmapped falls
# back to "workout" rather than being dropped — an unknown sport is still a
# session that happened, and losing it silently would be worse than filing it
# under a generic label.
_STRAVA_SPORT_MAP: dict[str, str] = {
    "Ride": "cycling",
    "MountainBikeRide": "cycling",
    "GravelRide": "cycling",
    "VirtualRide": "virtual_cycling",
    "EBikeRide": "ebike",
    "Run": "running",
    "TrailRun": "running",
    "VirtualRun": "running",
    "Walk": "walking",
    "Hike": "hiking",
    "Swim": "swimming",
    "Rowing": "rowing",
    "VirtualRow": "rowing",
    "Workout": "workout",
    "WeightTraining": "weight_training",
    "Yoga": "yoga",
    "Elliptical": "elliptical",
    "StairStepper": "stair_stepper",
    "Badminton": "badminton",
    "Pickleball": "pickleball",
    "Tennis": "tennis",
    "Soccer": "football",
    "Golf": "golf",
    "HighIntensityIntervalTraining": "hiit",
    "Crossfit": "hiit",
}


def normalise_sport(sport_type: str | None, fallback_type: str | None = None) -> str:
    """Map Strava's sport vocabulary onto ours."""
    for candidate in (sport_type, fallback_type):
        if candidate and candidate in _STRAVA_SPORT_MAP:
            return _STRAVA_SPORT_MAP[candidate]
    return "workout"


# ---------------------------------------------------------------------------
# One imported activity
# ---------------------------------------------------------------------------


@dataclass
class ImportedActivity:
    external_id: str
    name: str
    activity_type: str
    started_at: datetime
    duration_minutes: float
    distance_km: float | None
    elevation_gain_m: float | None
    mean_heart_rate: float | None
    max_heart_rate: float | None
    energy: EnergyOptions | None

    @property
    def kcal(self) -> float | None:
        return self.energy.chosen.kcal if self.energy else None


def parse_activity(
    payload: dict, *, weight_kg: float | None = None
) -> ImportedActivity | None:
    """Turn one Strava activity object into our shape.

    Returns None for anything unusable — a manual entry with no duration, a
    corrupt record — rather than storing a placeholder. Strava's own manual
    entries are also skipped by the caller, since a user hand-typing "60 min
    ride" into Strava and then into Trace would otherwise appear twice.
    """
    ext_id = payload.get("id")
    if ext_id is None:
        return None

    moving = payload.get("moving_time") or payload.get("elapsed_time") or 0
    duration_minutes = float(moving) / 60.0
    if duration_minutes < MIN_DURATION_MINUTES:
        return None

    started_raw = payload.get("start_date")
    try:
        started = (
            datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))
            if started_raw
            else datetime.now(timezone.utc)
        )
    except ValueError:
        started = datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    activity_type = normalise_sport(payload.get("sport_type"), payload.get("type"))

    distance_m = _num(payload.get("distance"))
    return ImportedActivity(
        external_id=str(ext_id),
        name=str(payload.get("name") or "Activity").strip()[:120],
        activity_type=activity_type,
        started_at=started,
        duration_minutes=round(duration_minutes, 1),
        distance_km=round(distance_m / 1000.0, 2) if distance_m else None,
        elevation_gain_m=_num(payload.get("total_elevation_gain")),
        mean_heart_rate=_num(payload.get("average_heartrate")),
        max_heart_rate=_num(payload.get("max_heartrate")),
        energy=estimate_energy(
            kilojoules=_num(payload.get("kilojoules")),
            strava_calories=_num(payload.get("calories")),
            duration_minutes=duration_minutes,
            activity_type=activity_type,
            weight_kg=weight_kg,
        ),
    )


def _num(v: object) -> float | None:
    """Coerce a Strava field to a float, or None. Never raises.

    Their API returns nulls, strings and occasionally booleans in numeric
    fields; a bad value must degrade one number, not fail an entire import.
    """
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# What an import actually changes
# ---------------------------------------------------------------------------


@dataclass
class ImportEffect:
    label: str
    outcome: str
    changed: bool


def import_effects(activity: ImportedActivity) -> list[ImportEffect]:
    """The "where this goes" list on the review screen.

    The third row is the important one and is hardcoded to Unchanged, because
    it is not a computed result — it is a product invariant. If a future change
    ever makes an imported activity move the calorie target, this list becomes
    a lie, and `test_import_never_changes_the_calorie_target` fails first.
    """
    return [
        ImportEffect(
            label="Activity list",
            outcome="Added",
            changed=True,
        ),
        ImportEffect(
            label="Weekly training load",
            outcome="Added" if activity.kcal else "Added without energy",
            changed=True,
        ),
        ImportEffect(
            label="Today's calorie target",
            outcome="Unchanged",
            changed=False,
        ),
    ]


def calorie_target_delta(activities: list[ImportedActivity]) -> float:
    """How much importing these activities moves the calorie target.

    Always zero. This function exists so the invariant has a name, a test, and
    a place a reviewer can look — rather than being an absence of code that
    someone helpfully "fixes" later.
    """
    return 0.0


# ---------------------------------------------------------------------------
# Deduplication against other sources
# ---------------------------------------------------------------------------

# Two sources recording the same session is the normal case, not an edge case:
# a rider with Strava on their phone AND an Apple Watch gets both. Overlapping
# starts within this window and the same sport are treated as one session.
DUPLICATE_WINDOW_MINUTES = 20.0


def is_duplicate(
    candidate: ImportedActivity,
    existing_start: datetime,
    existing_type: str,
    existing_duration_minutes: float,
) -> bool:
    """Whether `candidate` is the same session as one we already hold.

    Matching on start time and sport rather than on distance or energy,
    because two devices reliably disagree about distance and energy but agree
    about when you set off.
    """
    if candidate.activity_type != existing_type:
        return False
    start = existing_start
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    gap = abs((candidate.started_at - start).total_seconds()) / 60.0
    if gap > DUPLICATE_WINDOW_MINUTES:
        return False
    # Same sport, near-simultaneous start: also require the durations to be in
    # the same ballpark, so a 20-minute warm-up ride isn't swallowed by the
    # three-hour ride that started at the same time.
    longer = max(candidate.duration_minutes, existing_duration_minutes, 1.0)
    shorter = min(candidate.duration_minutes, existing_duration_minutes)
    return shorter / longer >= 0.5
