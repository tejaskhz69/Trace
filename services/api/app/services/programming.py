"""Deterministic, beginner-safe training programme generation.

PURE FUNCTIONS, NO I/O. Same inputs, same output, every time -- which is what
makes a generated programme reviewable by a human and reproducible in CI. The
router loads rows and hands them in; nothing here opens a session.

WHY DETERMINISTIC FIRST, MODEL LATER
This is the whole MVP: rules in, programme out. No LLM, no network dependency,
no prompt. When AI generation lands it becomes one more producer writing the
same rows -- `generated_by` flips from 'template' to 'ai' and the schema does
not move. Building it in this order means every table, ownership check and
mobile screen is exercised before a model is ever involved.

BEGINNER-SAFE IS A CONSTRAINT, NOT A DEFAULT
A new lifter gets bodyweight and dumbbell work, conservative set counts, and
three reps in reserve. Never a barbell prescription derived from a strength
history that does not exist. `suggested_weight_kg` is deliberately absent from
everything this module produces: with no logged history there is no basis for
a number, and inventing one is exactly the confident-wrong answer the project
refuses to give.

NOT MEDICAL ADVICE. The cues below are coaching language about movement. They
say nothing about injury, treatment, or whether a person should train.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: What a beginner is allowed to be prescribed. Both are forgiving of technique
#: error and need no spotter or rack -- the two things a barbell prescription
#: assumes and a first-week lifter does not have.
BEGINNER_EQUIPMENT = frozenset({"bodyweight", "dumbbell"})

#: Reps in reserve for every beginner prescription. Three is deliberately
#: conservative: technique degrades near failure, and a beginner cannot yet
#: tell the difference between hard and unsafe.
BEGINNER_TARGET_RIR = 3

#: Conservative set counts by exercise class. A beginner adapts to far less
#: volume than an intermediate, and the cheapest way to fail a new lifter is
#: to make week one so sore they do not come back for week two.
SETS_BY_CLASS: dict[str, int] = {
    "compound": 3,
    "machine": 3,
    "isolation": 2,
}

#: Double progression: add reps within the range, then add load and drop back
#: to the bottom of the range. The one progression rule that needs no
#: percentages, no maxes, and no arithmetic mid-set.
BEGINNER_PROGRESSION = "double_progression"

#: Minutes of session time one exercise is assumed to occupy, including rest.
#: Rounded up on purpose -- a beginner sets up slower than the arithmetic says.
MINUTES_PER_EXERCISE = 12

MIN_EXERCISES_PER_SESSION = 3
MAX_EXERCISES_PER_SESSION = 8

#: Movement patterns a beginner programme draws from, in priority order.
#: Compounds first: they are where the adaptation is, and they are what a
#: shortened session should keep.
PATTERN_PRIORITY: tuple[str, ...] = (
    "squat",
    "hinge",
    "push_horizontal",
    "pull_horizontal",
    "push_vertical",
    "pull_vertical",
    "carry",
    "isolation",
)

_CLASS_PRIORITY: dict[str, int] = {"compound": 0, "machine": 1, "isolation": 2}

#: Form and safety guidance, keyed by movement pattern. COACHING LANGUAGE
#: ONLY -- these describe how to move, never whether someone is injured, what
#: an ache means, or whether they should be training at all. Nothing here is
#: medical advice and none of it should ever be phrased as though it were.
FORM_CUES: dict[str, str] = {
    "squat": (
        "Keep your whole foot flat, sit down between your hips, and control "
        "the way down rather than dropping into it."
    ),
    "hinge": (
        "Push your hips back before your knees bend, and keep the weight "
        "close to your legs the whole way."
    ),
    "push_horizontal": (
        "Keep your shoulder blades pulled back against the bench or floor "
        "and stop before your elbows flare wide."
    ),
    "push_vertical": (
        "Brace your ribs down so the movement happens at the shoulder, not "
        "by leaning back."
    ),
    "pull_horizontal": (
        "Lead with your elbow, not your hand, and pause briefly at the top "
        "instead of yanking."
    ),
    "pull_vertical": (
        "Start each rep from a full hang and pull your shoulder blades down "
        "before your arms bend."
    ),
    "carry": (
        "Stand tall, keep your ribs stacked over your hips, and walk at a "
        "steady pace rather than rushing."
    ),
    "isolation": (
        "Use a weight you can control through the whole range -- this is not "
        "a movement that rewards momentum."
    ),
}

_DEFAULT_CUE = (
    "Move through a range you can control, and stop the set while your "
    "technique still looks the way it did on rep one."
)


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DayTemplate:
    """One training day in a weekly structure. No calendar date attached."""

    label: str
    focus: tuple[str, ...]
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class ExerciseOption:
    """A catalogue exercise that carries programming attributes.

    An exercise with no `exercise_attributes` row cannot become one of these,
    which is how "an unattributed exercise is never prescribed" is enforced:
    it is unrepresentable rather than filtered.
    """

    exercise_id: str
    name: str
    equipment: str
    muscle_group: str
    secondary_muscles: tuple[str, ...]
    movement_pattern: str
    exercise_class: str
    default_rep_min: int
    default_rep_max: int
    default_rest_seconds: int
    fatigue_cost: int
    is_unilateral: bool = False


@dataclass(frozen=True)
class Prescription:
    """What to do, for one exercise, in one session."""

    exercise_id: str
    order_index: int
    sets: int
    rep_min: int
    rep_max: int
    target_rir: int
    rest_seconds: int
    progression_rule: str


@dataclass(frozen=True)
class Education:
    """Why this exercise is here, in plain language."""

    primary_muscle: str
    secondary_muscles: tuple[str, ...]
    movement_pattern: str
    form_cue: str


# ---------------------------------------------------------------------------
# Split generation
# ---------------------------------------------------------------------------

_FULL_BODY_A = DayTemplate(
    label="Full body A",
    focus=("legs", "chest", "back"),
    patterns=("squat", "push_horizontal", "pull_horizontal", "isolation"),
)
_FULL_BODY_B = DayTemplate(
    label="Full body B",
    focus=("legs", "back", "shoulders"),
    patterns=("hinge", "pull_vertical", "push_vertical", "isolation"),
)
_FULL_BODY_C = DayTemplate(
    label="Full body C",
    focus=("legs", "chest", "back"),
    patterns=("squat", "push_vertical", "pull_horizontal", "carry"),
)
_UPPER = DayTemplate(
    label="Upper",
    focus=("chest", "back", "shoulders"),
    patterns=(
        "push_horizontal",
        "pull_horizontal",
        "push_vertical",
        "pull_vertical",
        "isolation",
    ),
)
_LOWER = DayTemplate(
    label="Lower",
    focus=("legs", "glutes"),
    patterns=("squat", "hinge", "isolation", "carry"),
)


def split_for(days_per_week: int) -> tuple[str, tuple[DayTemplate, ...]]:
    """The weekly structure for a given training frequency.

    FULL BODY UNTIL FOUR DAYS. A beginner training twice a week gets far more
    out of hitting everything twice than out of a split that trains chest once
    and then not again for seven days. Upper/lower only becomes worth its
    complexity at four sessions.

    Above four days the structure repeats rather than inventing new material:
    a beginner does not need six distinct sessions, and the honest answer to
    "I want to train six days" is a rotation plus a note about rest days.
    """
    if days_per_week < 1:
        raise ValueError("days_per_week must be at least 1")
    if days_per_week > 7:
        raise ValueError("days_per_week must be at most 7")

    if days_per_week <= 3:
        rotation = (_FULL_BODY_A, _FULL_BODY_B, _FULL_BODY_C)
        return "full_body", rotation[:days_per_week]

    rotation = (_UPPER, _LOWER)
    days = tuple(rotation[i % 2] for i in range(days_per_week))
    # Distinct labels: two days both called "Upper" in one week is ambiguous
    # the moment a user tries to say which one they skipped.
    numbered = []
    seen: dict[str, int] = {}
    for day in days:
        seen[day.label] = seen.get(day.label, 0) + 1
        suffix = " " + "AB CDEFG"[seen[day.label] - 1].strip()
        numbered.append(
            DayTemplate(
                label=f"{day.label}{suffix}".strip(),
                focus=day.focus,
                patterns=day.patterns,
            )
        )
    return "upper_lower", tuple(numbered)


def programme_name(split_type: str, days_per_week: int) -> str:
    """A name a person would recognise, not a slug."""
    pretty = {"full_body": "Full body", "upper_lower": "Upper/Lower"}
    return f"{pretty.get(split_type, split_type)} — {days_per_week} day"


def programme_notes(days_per_week: int) -> tuple[str, ...]:
    """Plain-language notes attached to a generated session.

    These are training notes, not health claims. Nothing here tells anyone
    whether they are well enough to train.
    """
    notes = [
        "Start lighter than you think you need to. The first week is for "
        "learning the movements, not testing them.",
        f"Leave about {BEGINNER_TARGET_RIR} reps in the tank on every set.",
        "Add a rep before you add weight. When you reach the top of the rep "
        "range on every set, increase the load and start again at the bottom.",
    ]
    if days_per_week >= 5:
        notes.append(
            "At this frequency, keep at least one full rest day in the week "
            "and take another whenever a session feels harder than it should."
        )
    return tuple(notes)


# ---------------------------------------------------------------------------
# Exercise selection
# ---------------------------------------------------------------------------


def beginner_equipment(available: object = None) -> frozenset[str]:
    """The equipment a beginner programme may draw on.

    Intersected with what the user says they have, but never widened: a user
    who owns a barbell still gets bodyweight and dumbbell work in the MVP.
    An empty or unusable `available` is read as "no constraint stated", not as
    "no equipment", because the latter would silently produce an empty
    programme for anyone who skipped the question.
    """
    if not available or not isinstance(available, (list, tuple, set, frozenset)):
        return BEGINNER_EQUIPMENT
    stated = {str(e).strip().lower() for e in available if str(e).strip()}
    if not stated:
        return BEGINNER_EQUIPMENT
    narrowed = BEGINNER_EQUIPMENT & stated
    # Bodyweight always survives: it needs nothing, so "I have no equipment"
    # must still produce a programme rather than an error.
    return narrowed or frozenset({"bodyweight"})


def exercise_budget(preferred_minutes: int) -> int:
    """How many exercises fit in a session of this length."""
    raw = preferred_minutes // MINUTES_PER_EXERCISE
    return max(MIN_EXERCISES_PER_SESSION, min(MAX_EXERCISES_PER_SESSION, raw))


def _sort_key(option: ExerciseOption) -> tuple:
    """Total order over candidates. `exercise_id` last makes it a TOTAL one.

    Without that final tie-break two exercises identical on every other field
    would order by whatever the database returned, and the same profile would
    generate two different programmes on two different days.
    """
    return (
        _CLASS_PRIORITY.get(option.exercise_class, 9),
        -option.fatigue_cost,
        option.name,
        option.exercise_id,
    )


def eligible(
    options: "list[ExerciseOption] | tuple[ExerciseOption, ...]",
    *,
    equipment: frozenset[str],
    disliked: "object" = None,
) -> tuple[ExerciseOption, ...]:
    """Candidates a beginner may be prescribed, in deterministic order."""
    blocked = set()
    if isinstance(disliked, (list, tuple, set, frozenset)):
        blocked = {str(d) for d in disliked}
    kept = [
        o
        for o in options
        if o.equipment in equipment and o.exercise_id not in blocked
    ]
    return tuple(sorted(kept, key=_sort_key))


def select_for_day(
    day: DayTemplate,
    candidates: "tuple[ExerciseOption, ...]",
    budget: int,
) -> tuple[ExerciseOption, ...]:
    """Pick this day's exercises, one movement pattern at a time.

    ONE EXERCISE PER PATTERN BEFORE ANY SECOND ONE. A beginner session that
    contains three chest movements and no pulling is a worse session than one
    that covers the day's patterns once each, however good the individual
    choices were.

    Patterns are visited in the day's own order first, then the global
    priority order, so a shortened session drops accessory work rather than
    the movement the day exists for.
    """
    chosen: list[ExerciseOption] = []
    used: set[str] = set()

    ordered_patterns = list(day.patterns) + [
        p for p in PATTERN_PRIORITY if p not in day.patterns
    ]

    for pattern in ordered_patterns:
        if len(chosen) >= budget:
            break
        for option in candidates:
            if option.movement_pattern != pattern:
                continue
            if option.exercise_id in used:
                continue
            chosen.append(option)
            used.add(option.exercise_id)
            break

    return tuple(chosen[:budget])


def prescribe(selected: "tuple[ExerciseOption, ...]") -> tuple[Prescription, ...]:
    """Turn chosen exercises into a prescription, preserving their order.

    `order_index` comes from position, so the ordering decided in
    `select_for_day` is the ordering stored, and `uq_prescribed_order` makes
    it unambiguous on read.

    Rep ranges come from the exercise's own attributes rather than a global
    constant: a goblet squat and a lateral raise do not belong in the same
    range, and the catalogue already knows the difference.
    """
    out: list[Prescription] = []
    for index, option in enumerate(selected):
        out.append(
            Prescription(
                exercise_id=option.exercise_id,
                order_index=index,
                sets=SETS_BY_CLASS.get(option.exercise_class, 2),
                rep_min=option.default_rep_min,
                rep_max=option.default_rep_max,
                target_rir=BEGINNER_TARGET_RIR,
                rest_seconds=option.default_rest_seconds,
                progression_rule=BEGINNER_PROGRESSION,
            )
        )
    return tuple(out)


def estimated_minutes(prescriptions: "tuple[Prescription, ...]") -> int:
    """Rough session length. Rounded to the nearest minute, never to zero."""
    if not prescriptions:
        return 0
    seconds = 0
    for p in prescriptions:
        # Working time per set is an estimate; rest is the part we actually
        # know, because it is prescribed.
        seconds += p.sets * (45 + p.rest_seconds)
    return max(1, round(seconds / 60))


def education_for(option: ExerciseOption) -> Education:
    """What this exercise trains, and how to do it without hurting yourself.

    The cue is coaching language. It does not diagnose, does not mention
    injury or pain, and must never be written as though it did.
    """
    return Education(
        primary_muscle=option.muscle_group,
        secondary_muscles=tuple(option.secondary_muscles),
        movement_pattern=option.movement_pattern,
        form_cue=FORM_CUES.get(option.movement_pattern, _DEFAULT_CUE),
    )
