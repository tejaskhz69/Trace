"""The sport catalogue, and what a session of one costs in energy.

WHY THIS IS A SEPARATE FILE FROM activity.py
`activity.py` interprets passive signal — steps, sleep, the NEAT drift that
predicts a stall. This file is about a session the user *chose to do and told
us about*: badminton for 45 minutes, a 6 km run, an hour of cricket nets.

THE ESTIMATE IS DELIBERATELY CRUDE, AND SAYING SO IS THE POINT
Burn is estimated from METs — the Compendium of Physical Activities' unit of
"how many times resting metabolism does this cost". The formula is

    kcal/min = MET x 3.5 x weight_kg / 200

and it is a population average applied to one person. Two people of the same
mass playing the same 45 minutes of badminton can differ by 40%, because skill
level determines how much of that 45 minutes is actually spent moving. So
`estimate_burn` returns a RANGE, not a number, exactly like the photo scanner
does. Non-negotiable #2 is not only about food.

THE RANGE IS ALSO WHY THIS NUMBER NEVER TOUCHES A CALORIE TARGET
Non-negotiable #1. Adaptive TDEE already contains this session, because the
session showed up in the weight trend. The estimate exists to explain a burn,
to build weekly training load, and to let someone see that their Sunday
cricket is not nothing. It is context. `WHERE_THIS_GOES` below is the copy the
UI shows to make that explicit rather than hoping the user infers it.

MET VALUES are from the 2011 Compendium of Physical Activities (Ainsworth et
al.) where it lists the sport. Where it does not -- pickleball, kabaddi,
CrossFit, padel are all either too new or too regional for it -- the value is
interpolated from the nearest listed activity of comparable intensity and
flagged `estimated=True`, so we never imply a citation we do not have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

#: kcal/min = MET x MET_TO_KCAL_FACTOR x weight_kg. The 3.5/200 in the
#: standard formula, pre-divided.
MET_TO_KCAL_FACTOR = 3.5 / 200.0

#: How much the range spreads either side of the point estimate.
#:
#: +/-25% is not a hedge, it is the honest width. Validation studies of MET
#: prediction against indirect calorimetry routinely land in this band for
#: intermittent sports, and wider still for anything with a skill component.
BURN_UNCERTAINTY = 0.25

#: A session can't be negative and nobody plays badminton for nine hours.
#: Values outside this are a typo or a stuck timer, not a workout.
MIN_DURATION_MIN = 1.0
MAX_DURATION_MIN = 600.0

#: Fallback when we have no weight on file. The estimate is worse, and the
#: caller is told so via `assumed_weight`.
DEFAULT_WEIGHT_KG = 70.0


class Intensity(str, Enum):
    """How hard the user says they went.

    Offered because it is the single biggest lever on accuracy that costs the
    user one tap. "Badminton" spans a warm-up rally and a league match.
    """

    easy = "easy"
    moderate = "moderate"
    hard = "hard"


#: Multipliers on the base MET. Deliberately modest -- the sport's own MET
#: already encodes typical effort, so this adjusts rather than replaces it.
INTENSITY_FACTOR: dict[Intensity, float] = {
    Intensity.easy: 0.78,
    Intensity.moderate: 1.0,
    Intensity.hard: 1.28,
}


@dataclass(frozen=True)
class Sport:
    key: str
    name: str
    met: float
    group: str
    #: True when the MET is interpolated rather than read from the Compendium.
    estimated: bool = False
    #: Sports where distance is a natural thing to record.
    tracks_distance: bool = False
    aliases: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# THE CATALOGUE
#
# Ordered so the sports this product's users actually play come first, and
# GROUPED, because a flat list of a hundred chips is not a menu, it is a wall.
# The client renders one section per group in this order.
#
# Racket sports lead because badminton and pickleball are the two most played
# participation sports in this market and every competitor buries them under
# "Other". The EVERYDAY group at the end is the unusual choice: housework and
# a long shift on your feet are not sports, but they are real expenditure that
# people currently log as nothing -- and nothing is the least accurate option
# on the list.
#
# Several sports appear at more than one intensity (Cycling / Cycling, easy /
# Cycling, fast) rather than relying only on the intensity toggle. Both exist
# because they answer different questions: the toggle is "how hard did YOU go",
# the variant is "which activity was it". A commute and a group ride are not
# the same activity done at different efforts.
# ---------------------------------------------------------------------------
SPORTS: tuple[Sport, ...] = (
    # ---- racket ----------------------------------------------------------
    Sport("badminton", "Badminton", 5.5, "Racket", aliases=("shuttle",)),
    Sport("pickleball", "Pickleball", 5.0, "Racket", estimated=True),
    Sport("tennis", "Tennis", 7.3, "Racket"),
    Sport("tennis_doubles", "Tennis, doubles", 6.0, "Racket"),
    Sport("table_tennis", "Table tennis", 4.0, "Racket", aliases=("ping pong",)),
    Sport("squash", "Squash", 7.3, "Racket"),
    Sport("racquetball", "Racquetball", 7.0, "Racket"),
    Sport("padel", "Padel", 6.0, "Racket", estimated=True),
    # ---- team ------------------------------------------------------------
    Sport("cricket", "Cricket", 4.8, "Team"),
    Sport("football", "Football", 7.0, "Team", aliases=("soccer",)),
    Sport("futsal", "Futsal", 8.0, "Team", estimated=True),
    Sport("american_football", "American football", 8.0, "Team"),
    Sport("rugby", "Rugby", 8.3, "Team"),
    Sport("basketball", "Basketball", 6.5, "Team"),
    Sport("volleyball", "Volleyball", 4.0, "Team"),
    Sport("beach_volleyball", "Beach volleyball", 8.0, "Team"),
    Sport("hockey", "Field hockey", 7.8, "Team"),
    Sport("ice_hockey", "Ice hockey", 8.0, "Team"),
    Sport("handball", "Handball", 8.0, "Team"),
    Sport("kabaddi", "Kabaddi", 8.0, "Team", estimated=True),
    Sport("kho_kho", "Kho kho", 7.5, "Team", estimated=True),
    Sport("ultimate", "Ultimate frisbee", 8.0, "Team"),
    Sport("lacrosse", "Lacrosse", 8.0, "Team"),
    Sport("netball", "Netball", 6.0, "Team", estimated=True),
    Sport("softball", "Softball", 5.0, "Team", aliases=("baseball",)),
    Sport("water_polo", "Water polo", 10.0, "Team"),
    # ---- endurance -------------------------------------------------------
    Sport("running", "Running", 9.8, "Endurance", tracks_distance=True,
          aliases=("jog", "jogging")),
    Sport("trail_running", "Trail running", 10.5, "Endurance",
          tracks_distance=True),
    Sport("treadmill", "Treadmill", 8.5, "Endurance", tracks_distance=True),
    Sport("sprinting", "Sprints", 12.0, "Endurance", aliases=("intervals track",)),
    Sport("walking", "Walking", 3.5, "Endurance", tracks_distance=True),
    Sport("brisk_walking", "Brisk walking", 4.3, "Endurance",
          tracks_distance=True, aliases=("power walk",)),
    Sport("incline_walking", "Incline walking", 6.0, "Endurance",
          tracks_distance=True, aliases=("ruck", "rucking")),
    Sport("hiking", "Hiking", 6.0, "Endurance", tracks_distance=True,
          aliases=("trek", "trekking")),
    Sport("cycling", "Cycling", 7.5, "Endurance", tracks_distance=True,
          aliases=("bike", "ride", "biking")),
    Sport("cycling_leisure", "Cycling, easy", 5.8, "Endurance",
          tracks_distance=True),
    Sport("cycling_fast", "Cycling, fast", 10.0, "Endurance",
          tracks_distance=True),
    Sport("mountain_biking", "Mountain biking", 8.5, "Endurance",
          tracks_distance=True, aliases=("mtb",)),
    Sport("spinning", "Spin class", 8.5, "Endurance",
          aliases=("indoor cycling", "peloton")),
    Sport("swimming", "Swimming", 7.0, "Endurance", tracks_distance=True,
          aliases=("swim", "laps")),
    Sport("swimming_hard", "Swimming, hard", 9.8, "Endurance",
          tracks_distance=True),
    Sport("open_water", "Open water swim", 8.5, "Endurance",
          tracks_distance=True),
    Sport("rowing", "Rowing", 7.0, "Endurance", tracks_distance=True,
          aliases=("erg",)),
    Sport("rowing_hard", "Rowing, hard", 8.5, "Endurance",
          tracks_distance=True),
    Sport("elliptical", "Elliptical", 5.0, "Endurance",
          aliases=("cross trainer",)),
    Sport("stair_climbing", "Stair climbing", 8.8, "Endurance",
          aliases=("stairs", "stairmaster")),
    Sport("skipping", "Skipping", 11.0, "Endurance",
          aliases=("jump rope", "rope")),
    Sport("triathlon", "Triathlon", 9.5, "Endurance", estimated=True),
    Sport("assault_bike", "Air bike", 9.0, "Endurance", estimated=True,
          aliases=("assault bike", "echo bike")),
    Sport("ski_erg", "Ski erg", 8.0, "Endurance", estimated=True),
    # ---- conditioning ----------------------------------------------------
    Sport("hiit", "HIIT", 8.0, "Conditioning",
          aliases=("intervals", "tabata")),
    Sport("circuit", "Circuit training", 7.5, "Conditioning"),
    Sport("crossfit", "CrossFit", 8.0, "Conditioning", estimated=True,
          aliases=("wod", "metcon")),
    Sport("bootcamp", "Bootcamp", 7.5, "Conditioning", estimated=True),
    Sport("calisthenics", "Calisthenics", 6.0, "Conditioning",
          aliases=("bodyweight",)),
    Sport("kettlebells", "Kettlebells", 8.0, "Conditioning"),
    Sport("sled", "Sled push or pull", 9.0, "Conditioning", estimated=True,
          aliases=("prowler",)),
    Sport("battle_ropes", "Battle ropes", 8.0, "Conditioning", estimated=True),
    Sport("boxing", "Boxing", 7.8, "Conditioning",
          aliases=("bag work",)),
    Sport("boxing_sparring", "Boxing, sparring", 12.8, "Conditioning"),
    Sport("kickboxing", "Kickboxing", 10.3, "Conditioning"),
    Sport("martial_arts", "Martial arts", 10.3, "Conditioning",
          aliases=("karate", "judo", "taekwondo", "mma")),
    Sport("wrestling", "Wrestling", 6.0, "Conditioning"),
    Sport("bjj", "Brazilian jiu-jitsu", 10.0, "Conditioning", estimated=True,
          aliases=("jiu jitsu", "grappling")),
    Sport("fencing", "Fencing", 6.0, "Conditioning"),
    Sport("aerobics", "Aerobics", 7.3, "Conditioning",
          aliases=("step class",)),
    Sport("water_aerobics", "Water aerobics", 5.5, "Conditioning"),
    # ---- mobility --------------------------------------------------------
    Sport("yoga", "Yoga", 3.0, "Mobility", aliases=("hatha",)),
    Sport("power_yoga", "Power yoga", 4.0, "Mobility", aliases=("vinyasa",)),
    Sport("hot_yoga", "Hot yoga", 5.0, "Mobility", estimated=True,
          aliases=("bikram",)),
    Sport("pilates", "Pilates", 3.0, "Mobility"),
    Sport("barre", "Barre", 3.5, "Mobility", estimated=True),
    Sport("stretching", "Stretching", 2.3, "Mobility",
          aliases=("mobility", "flexibility")),
    Sport("tai_chi", "Tai chi", 3.0, "Mobility"),
    Sport("foam_rolling", "Foam rolling", 2.3, "Mobility", estimated=True),
    Sport("dancing", "Dancing", 5.0, "Mobility", aliases=("dance",)),
    Sport("zumba", "Zumba", 6.5, "Mobility"),
    Sport("bharatanatyam", "Classical dance", 6.0, "Mobility", estimated=True,
          aliases=("bharatanatyam", "kathak")),
    # ---- outdoor ---------------------------------------------------------
    Sport("climbing", "Climbing", 8.0, "Outdoor", aliases=("rock climbing",)),
    Sport("bouldering", "Bouldering", 7.0, "Outdoor", estimated=True),
    Sport("golf", "Golf, walking", 4.8, "Outdoor"),
    Sport("golf_cart", "Golf, with a cart", 3.5, "Outdoor"),
    Sport("skating", "Skating", 7.0, "Outdoor",
          aliases=("rollerblading", "ice skating")),
    Sport("skateboarding", "Skateboarding", 5.0, "Outdoor"),
    Sport("skiing", "Skiing", 7.0, "Outdoor"),
    Sport("snowboarding", "Snowboarding", 5.3, "Outdoor"),
    Sport("cross_country_ski", "Cross-country skiing", 9.0, "Outdoor",
          tracks_distance=True),
    Sport("surfing", "Surfing", 5.0, "Outdoor"),
    Sport("paddleboarding", "Paddleboarding", 6.0, "Outdoor",
          tracks_distance=True, aliases=("sup",)),
    Sport("kayaking", "Kayaking", 5.0, "Outdoor", tracks_distance=True,
          aliases=("canoeing", "paddling")),
    Sport("sailing", "Sailing", 3.3, "Outdoor"),
    Sport("horse_riding", "Horse riding", 5.5, "Outdoor",
          aliases=("equestrian",)),
    Sport("archery", "Archery", 4.3, "Outdoor"),
    Sport("gardening", "Gardening", 3.8, "Outdoor", aliases=("yard work",)),
    # ---- everyday --------------------------------------------------------
    #
    # Not sports, and deliberately here anyway. A day of housework or a long
    # shift on your feet is real expenditure that people currently log as
    # nothing, and "nothing" is the least accurate option on the list.
    Sport("housework", "Housework", 3.3, "Everyday", aliases=("cleaning",)),
    Sport("cooking", "Cooking", 2.5, "Everyday"),
    Sport("shopping", "Shopping", 2.3, "Everyday", aliases=("errands",)),
    Sport("childcare", "Carrying a child", 3.5, "Everyday",
          aliases=("kids", "playing with kids")),
    Sport("dog_walking", "Walking the dog", 3.0, "Everyday",
          tracks_distance=True),
    Sport("moving_boxes", "Lifting and carrying", 6.0, "Everyday",
          aliases=("moving house", "loading")),
    Sport("standing_work", "On your feet at work", 2.3, "Everyday",
          estimated=True),
    Sport("manual_labour", "Manual labour", 5.5, "Everyday",
          aliases=("construction", "site work")),
    Sport("stairs_daily", "Stairs at home", 4.0, "Everyday", estimated=True),
    Sport("other", "Something else", 5.0, "Other", estimated=True),
)

BY_KEY: dict[str, Sport] = {s.key: s for s in SPORTS}


def groups() -> list[str]:
    """Group names, in catalogue order, without duplicates."""
    seen: list[str] = []
    for s in SPORTS:
        if s.group not in seen:
            seen.append(s.group)
    return seen


def find(term: str) -> Sport | None:
    """Resolve a key, a display name, or a colloquial alias to a Sport.

    Aliases exist because the voice logger and the search box both hand us
    whatever the user actually said. Somebody who says "went for a ride"
    should not have to know we filed it under `cycling`.
    """
    if not term:
        return None
    t = term.strip().lower().replace("-", " ").replace("_", " ")
    for s in SPORTS:
        if t == s.key.replace("_", " ") or t == s.name.lower():
            return s
    for s in SPORTS:
        if t in s.aliases or any(a in t for a in s.aliases):
            return s
    # Last resort: a containment match on the display name, so "table tennis
    # doubles" still lands. Checked last so it can never beat an exact hit.
    for s in SPORTS:
        if s.name.lower() in t:
            return s
    return None


@dataclass(frozen=True)
class BurnEstimate:
    """What a session probably cost, and how sure we are.

    `point` is never shown on its own in the UI -- `low` and `high` go with
    it, the same as a photo scan.
    """

    low: int
    point: int
    high: int
    met_used: float
    #: True when we had no body weight and fell back to DEFAULT_WEIGHT_KG.
    assumed_weight: bool
    #: True when the sport's MET is interpolated rather than cited.
    met_estimated: bool

    @property
    def band(self) -> int:
        """Half-width, for rendering as ``point ±band``."""
        return max(self.point - self.low, self.high - self.point)


class SportError(ValueError):
    """A session we refuse to estimate rather than guess at."""


def estimate_burn(
    sport_key: str,
    duration_minutes: float,
    weight_kg: float | None,
    intensity: Intensity | str = Intensity.moderate,
) -> BurnEstimate:
    """Estimate the energy cost of one session.

    Raises rather than returning a nonsense number when the inputs are not
    something a human did -- non-negotiable #3 applied here: refusing beats
    answering wrong, and a 14-hour badminton match is a stuck timer.
    """
    sport = BY_KEY.get(sport_key) or find(sport_key)
    if sport is None:
        raise SportError(f"Unknown sport: {sport_key!r}")

    if not (MIN_DURATION_MIN <= duration_minutes <= MAX_DURATION_MIN):
        raise SportError(
            f"Duration must be between {MIN_DURATION_MIN:g} and "
            f"{MAX_DURATION_MIN:g} minutes."
        )

    if isinstance(intensity, str):
        try:
            intensity = Intensity(intensity)
        except ValueError as exc:
            raise SportError(f"Unknown intensity: {intensity!r}") from exc

    assumed = weight_kg is None or weight_kg <= 0
    mass = DEFAULT_WEIGHT_KG if assumed else float(weight_kg)  # type: ignore[arg-type]

    met = sport.met * INTENSITY_FACTOR[intensity]
    point = met * MET_TO_KCAL_FACTOR * mass * duration_minutes

    # A guessed body weight is a second source of error stacked on the first,
    # so the band widens to cover it rather than pretending it didn't happen.
    spread = BURN_UNCERTAINTY * (1.35 if assumed else 1.0)

    return BurnEstimate(
        low=max(0, round(point * (1 - spread))),
        point=round(point),
        high=round(point * (1 + spread)),
        met_used=round(met, 2),
        assumed_weight=assumed,
        met_estimated=sport.estimated,
    )


#: The copy the activity-detail screen shows under "Where this goes".
#:
#: It lives here rather than in the client because it is a statement about how
#: the engine works, and the engine is here. If someone ever changes the
#: answer on the third line, the change should be impossible to make without
#: reading why it says what it says.
WHERE_THIS_GOES: tuple[tuple[str, str], ...] = (
    ("Activity list", "Added"),
    ("Weekly training load", "Added"),
    ("Today's calorie target", "Unchanged"),
)

TARGET_EXPLAINER = (
    "This does not become calories to eat back. Your target already contains "
    "the training you normally do -- adding it on top is the single most "
    "common way a tracker makes you gain fat."
)
