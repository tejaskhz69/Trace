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

from collections.abc import Iterable
from dataclasses import dataclass

from .strength import REST_COMPOUND_S, REST_ISOLATION_S, REST_MACHINE_S

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

#: Rest between sets, by derived class.
#:
#: WHY THIS EXISTS RATHER THAN `default_rest_seconds`. The column on
#: `exercise_attributes` is the constant 120 on all 154 rows -- NOT NULL,
#: fully populated, and carrying no information, which is why every
#: null-counting audit passed it clean. Meanwhile `REST_COMPOUND_S = 180`
#: and `REST_ISOLATION_S = 90` in `strength.py` were meaningful and
#: unreachable, because the generator read the flat column instead. The
#: informative system was disconnected and the uninformative one was live.
#:
#: Prescriptions now take rest from here. `default_rest_seconds` is no
#: longer read by generation. It is left on the table rather than dropped
#: because dropping a column is the one edit a downgrade cannot undo, and
#: because it is the natural home for a genuine per-exercise override if one
#: is ever curated -- at which point it should hold NULL for "no override"
#: rather than a default duplicated onto every row.
REST_BY_CLASS: dict[str, int] = {
    "compound": REST_COMPOUND_S,
    "machine": REST_MACHINE_S,
    "isolation": REST_ISOLATION_S,
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
#: The slot templates use to ask for isolation work.
#:
#: NOT a movement pattern, and deliberately not stored as one. An
#: eight-pattern taxonomy describes compounds; a bicep curl satisfies
#: none of them, so `movement_pattern` is NULL for isolation and
#: `is_isolation` carries it instead. A NULL pattern is an answer, not
#: a coverage gap -- see services/movement.py.
ISOLATION_SLOT = "isolation"

PATTERN_PRIORITY: tuple[str, ...] = (
    "squat",
    "hinge",
    "h-push",
    "h-pull",
    "v-push",
    "v-pull",
    "carry",
    "isolation",
)

_CLASS_PRIORITY: dict[str, int] = {"compound": 0, "machine": 1, "isolation": 2}

#: Equipment that stabilises the lifter, so the movement costs less to
#: perform and to recover from than the free-weight equivalent.
_MACHINE_EQUIPMENT = frozenset({"machine", "smith"})


def derived_class(option: "ExerciseOption") -> str:
    """Which of compound / machine / isolation this movement is.

    DERIVED, NOT STORED, and `is_isolation` is tested FIRST. Both halves of
    that matter.

    NOT STORED, because `exercise_attributes.exercise_class` was NULL on all
    154 rows and everything downstream silently fell back to a default: every
    exercise got `SETS_BY_CLASS.get(None, 2)` -- two sets for a squat and two
    for a lateral raise -- and `_CLASS_PRIORITY.get(None, 9)` put every row in
    the same bucket, so the ordering logic never executed at all. The column
    is a function of `is_isolation` and `equipment`, both of which are NOT
    NULL on every row, so there is nothing to store and nothing to curate.

    `is_isolation` FIRST, because testing equipment first -- which is what
    `exercise_classify.py` does -- sends eleven machine-based isolations down
    the machine branch: leg extension, lying and seated leg curl, the three
    calf raises, hip abduction and adduction, machine lateral raise, machine
    preacher curl, triceps extension machine. That hands a leg extension a
    machine chest press's set count and sorts it AHEAD of a dumbbell lateral
    raise. Complexity outranks modality here; a calf raise is isolation work
    performed on a machine, not machine work.

    Total by construction: `is_isolation` is NOT NULL and `equipment` is NOT
    NULL, so every row lands in exactly one bucket and no caller needs a
    fallback for an unclassifiable exercise.
    """
    if option.is_isolation:
        return "isolation"
    if option.equipment in _MACHINE_EQUIPMENT:
        return "machine"
    return "compound"

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
    "h-push": (
        "Keep your shoulder blades pulled back against the bench or floor "
        "and stop before your elbows flare wide."
    ),
    "v-push": (
        "Brace your ribs down so the movement happens at the shoulder, not "
        "by leaning back."
    ),
    "h-pull": (
        "Lead with your elbow, not your hand, and pause briefly at the top "
        "instead of yanking."
    ),
    "v-pull": (
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
    #: NULL for isolation work. See ISOLATION_SLOT.
    movement_pattern: str | None
    exercise_class: str | None
    #: NULLABLE since `b8d47f1c39ae`. A classified movement need not yet be a
    #: prescribable one, and `eligible()` is what enforces the difference.
    default_rep_min: int | None
    default_rep_max: int | None
    default_rest_seconds: int
    #: NOT READ BY SELECTION, on purpose. The stored column is the constant
    #: 3 on every row, and deriving it from the columns we hold only
    #: re-encodes `_CLASS_PRIORITY`. The version of this column that would
    #: earn its place is fatigue MEASURED FROM LOGGED DATA -- session RPE,
    #: next-session performance decrement -- which nobody can seed and which
    #: Trace could uniquely derive once there is real usage.
    fatigue_cost: int
    is_unilateral: bool = False
    #: Exactly the rows with no pattern. Enforced by a CHECK.
    is_isolation: bool = False


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
    movement_pattern: str | None
    form_cue: str


# ---------------------------------------------------------------------------
# Split generation
# ---------------------------------------------------------------------------

_FULL_BODY_A = DayTemplate(
    label="Full body A",
    focus=("legs", "chest", "back"),
    patterns=("squat", "h-push", "h-pull", "isolation"),
)
_FULL_BODY_B = DayTemplate(
    label="Full body B",
    focus=("legs", "back", "shoulders"),
    patterns=("hinge", "v-pull", "v-push", "isolation"),
)
_FULL_BODY_C = DayTemplate(
    label="Full body C",
    focus=("legs", "chest", "back"),
    patterns=("squat", "v-push", "h-pull", "carry"),
)
_UPPER = DayTemplate(
    label="Upper",
    focus=("chest", "back", "shoulders"),
    patterns=(
        "h-push",
        "h-pull",
        "v-push",
        "v-pull",
        "isolation",
    ),
)
_LOWER = DayTemplate(
    label="Lower",
    focus=("legs", "glutes"),
    patterns=("squat", "hinge", "isolation", "carry"),
)


#: Every template, so "which slots do we ask for" has one answer.
ALL_TEMPLATES: tuple[DayTemplate, ...] = (
    _FULL_BODY_A,
    _FULL_BODY_B,
    _FULL_BODY_C,
    _UPPER,
    _LOWER,
)

#: Slots we KNOW nothing can fill, each with the reason and what removes it.
#:
#: `carry` -- there are no curated loaded carries. The catalogue holds four
#: (Farmer's Carry, Farmer's Walk, Rickshaw Carry, Yoke Walk) but none is in
#: the 154 rows `seed_movements` writes, so none has an `exercise_attributes`
#: row, and generation inner-joins that table. REMOVE THIS ENTRY once any
#: carry is curated; the guard below will fail and tell you to.
#:
#: This constant exists so the gap is visible in code. It was invisible at
#: runtime: `_LOWER` has asked for a carry since it was written, that slot
#: has always resolved to nothing, and the only symptom was a lower-body day
#: with three exercises instead of four.
KNOWN_EMPTY_PATTERNS: frozenset[str] = frozenset({"carry"})


def template_slots() -> frozenset[str]:
    """Every slot any template asks for."""
    return frozenset(slot for t in ALL_TEMPLATES for slot in t.patterns)


def unfilled_slots(
    classified: "Iterable[tuple[str | None, bool]]",
) -> frozenset[str]:
    """Which template slots nothing can fill.

    `classified` is (movement_pattern, is_isolation) for every classified
    movement -- so this works equally over the curated constant the seed
    writes and over a live `exercise_attributes` table, which is the point:
    the test checks the seed, `/healthz/db` checks the database, and the two
    cannot disagree about what "unfilled" means.
    """
    pairs = list(classified)
    has_isolation = any(iso for _pattern, iso in pairs)
    patterns = {pattern for pattern, _iso in pairs if pattern is not None}

    empty: set[str] = set()
    for slot in template_slots():
        filled = has_isolation if slot == ISOLATION_SLOT else slot in patterns
        if not filled:
            empty.add(slot)
    return frozenset(empty)


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

    `fatigue_cost` IS DELIBERATELY NOT A TERM HERE. It was, and it did
    nothing: the column is the constant 3 on all 154 rows. Deriving it from
    `is_isolation`, `equipment` and `movement_pattern` -- the obvious fix --
    was measured and rejected, because every split the derivation produces,
    `_CLASS_PRIORITY` already produces, in the same direction:

        within (class, pattern):  h-push {3,4}  squat {3,5}  v-pull {4}

    That is a re-encoding of the first term, not a second signal. Including
    it would have moved the column from one distinct value to four and
    satisfied a cardinality check while changing not one selected exercise
    -- the check gamed rather than passed.

    So the effective order is (class, name), and within one class tier that
    is ALPHABETICAL. Variety is not this function's job: a sort key picks a
    best candidate, and picking a DIFFERENT candidate on a different day is
    a separate mechanism seeded from the day, not a tie-break.
    """
    return (
        _CLASS_PRIORITY[derived_class(option)],
        option.name,
        option.exercise_id,
    )


def eligible(
    options: "list[ExerciseOption] | tuple[ExerciseOption, ...]",
    *,
    equipment: frozenset[str],
    disliked: "object" = None,
) -> tuple[ExerciseOption, ...]:
    """Candidates a beginner may be prescribed, in deterministic order.

    A MISSING REP RANGE MAKES AN EXERCISE INELIGIBLE, CHECKED HERE.

    `programmable_exercises` already filters these out, and generation reads
    that view -- so this is braces, not belt. It exists because the belt was
    silently unbuckled once already: the view was created to carry the
    not-null guarantee, `_load_options` kept its raw join for weeks
    afterwards, and the result was a 500 on every generation request that no
    test could see.

    `prescribed_exercises.rep_min` is NOT NULL, so an option with no range
    cannot be written. The only question is whether we find that out at
    SELECTION time, where it means "this exercise is not ready to be
    prescribed", or at INSERT time, where it means a stack trace. If some
    future query bypasses the view again, this still cannot produce an
    unprescribable exercise.
    """
    blocked = set()
    if isinstance(disliked, (list, tuple, set, frozenset)):
        blocked = {str(d) for d in disliked}
    kept = [
        o
        for o in options
        if o.equipment in equipment
        and o.exercise_id not in blocked
        and o.default_rep_min is not None
        and o.default_rep_max is not None
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
            if not _fills_slot(option, pattern):
                continue
            if option.exercise_id in used:
                continue
            chosen.append(option)
            used.add(option.exercise_id)
            break

    return tuple(chosen[:budget])


def _fills_slot(option: "ExerciseOption", slot: str) -> bool:
    """Whether this exercise satisfies a template slot.

    Two different questions wear the same shape here. A pattern slot asks
    "is this movement a hinge"; the isolation slot asks "is this isolation
    work", which is not a pattern at all -- those rows carry a NULL pattern
    on purpose. Comparing `movement_pattern == "isolation"` would match
    nothing, because the database CHECK does not permit that value.
    """
    if slot == ISOLATION_SLOT:
        return option.is_isolation
    return option.movement_pattern == slot


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
                sets=SETS_BY_CLASS[derived_class(option)],
                rep_min=option.default_rep_min,
                rep_max=option.default_rep_max,
                target_rir=BEGINNER_TARGET_RIR,
                rest_seconds=REST_BY_CLASS[derived_class(option)],
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
