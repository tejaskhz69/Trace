"""Deterministic classification of the exercise catalogue.

PURE FUNCTIONS, NO I/O. Same catalogue in, byte-identical classification out.
That property is the whole point: a human reviews the artifact once, and a
re-run that produces a different hash means the RULES or the CATALOGUE changed,
never that the classifier felt differently today.

WHAT THIS IS FOR
`exercise_attributes` is empty, and `services/programming.py` refuses to
prescribe an exercise that has no attributes row. This module proposes those
rows. It does not write them: it emits a reviewable proposal, and only rows a
human approves are ever seeded.

NOTHING IS EVER SILENTLY DROPPED. Every one of the 874 catalogue rows appears
in the output with a status and a reason, including the ones no rule matched.
An exercise that quietly vanished would be indistinguishable from one that was
never in the catalogue, and the difference matters when someone asks why their
favourite lift is never programmed.

THE CONSERVATIVE DIRECTION IS ALWAYS "NEEDS REVIEW".
Where two patterns both fire, where the derived class contradicts the
catalogue's own `is_compound` flag, where the name carries a brand, or where
nothing matches at all -- the answer is review, not a guess. A wrong rep range
on a barbell movement is advice, and bad advice is the failure mode this half
of the product has.

NOT MEDICAL ADVICE. `excluded_beginner` means "this needs coaching before a
novice should be handed it by an app". It is not a claim about anyone's health,
injury risk, or fitness to train, and the reasons below must never be phrased
as though it were.

MOVEMENT PATTERN VOCABULARY -- READ THIS BEFORE CHANGING IT
The emitted values are the LONG forms (`push_horizontal`, `pull_vertical`, ...)
because that is what `ck_exattr_movement_pattern` in migration f6a9c2e47d85
accepts. Short forms (`push_h`, `pull_v`) would be rejected by the database.
`SHORT_FORM` below maps between them for anyone reading the artifact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Optional

CLASSIFIER_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: The values ck_exattr_movement_pattern accepts. Long forms, deliberately.
MOVEMENT_PATTERNS = (
    "squat",
    "hinge",
    "lunge",
    "core",
    "push_horizontal",
    "push_vertical",
    "pull_horizontal",
    "pull_vertical",
    "carry",
    "isolation",
)

#: Shorthand <-> stored form. The artifact reports both so a reviewer reading
#: a spec written in shorthand can match rows up without guessing.
SHORT_FORM: dict[str, str] = {
    "squat": "squat",
    "hinge": "hinge",
    "lunge": "lunge",
    "core": "core",
    "push_horizontal": "push_h",
    "push_vertical": "push_v",
    "pull_horizontal": "pull_h",
    "pull_vertical": "pull_v",
    "carry": "carry",
    "isolation": "isolation",
}

EXERCISE_CLASSES = ("compound", "machine", "isolation")

REVIEW_APPROVED = "approved"
REVIEW_NEEDED = "needs_review"
REVIEW_EXCLUDED = "excluded_beginner"

#: Patterns whose movements are structural rather than single-joint.
_COMPOUND_PATTERNS = frozenset(
    {"squat", "hinge", "lunge", "push_horizontal", "push_vertical",
     "pull_horizontal", "pull_vertical", "carry"}
)
# NOTE `core` is deliberately absent. A plank is neither compound nor
# isolation, which is the same gap the binary has everywhere else in this
# codebase -- see docs/10-exercise-and-station-model.md.

#: Equipment a beginner programme may draw on. Mirrors
#: services/programming.BEGINNER_EQUIPMENT; asserted equal in the tests so the
#: two cannot drift apart.
BEGINNER_EQUIPMENT = frozenset({"bodyweight", "dumbbell"})

# ---------------------------------------------------------------------------
# Exclusion rules -- checked BEFORE pattern matching
# ---------------------------------------------------------------------------

#: (rule name, regex, reason). Reasons describe COACHING requirements, never
#: health, injury or medical status.
EXCLUSION_RULES: tuple[tuple[str, str, str], ...] = (
    (
        "olympic_lift",
        r"\b(snatch|clean|jerk)\b",
        "Weightlifting derivative -- needs coached technique before an app "
        "should prescribe it unsupervised.",
    ),
    (
        "plyometric",
        r"\b(jump|jumping|plyo|plyometric|depth drop|bound|bounding|hop|"
        r"hops|leap|skater)\b",
        "Plyometric. Landing mechanics need instruction, and load is not the "
        "variable a beginner should be progressing.",
    ),
    (
        "advanced_bodyweight",
        r"\b(muscle[- ]?up|pistol|planche|front lever|back lever|iron cross|"
        r"human flag|kipping|handstand)\b",
        "Advanced skill. A novice cannot perform it, so prescribing it is an "
        "instruction to fail.",
    ),
    (
        "conditioning_or_implement",
        r"\b(sled|prowler|tire|sprint|sprints|run|running|rope climb|battle "
        r"rope|atlas stone|log press|keg)\b",
        "Conditioning or strongman implement. Outside what a beginner "
        "hypertrophy template should assign.",
    ),
    (
        "isometric_hold",
        r"\b(isometric|hold|holds|static)\b",
        "Isometric hold. Reps and RIR do not describe it, so the prescription "
        "shape here would be misleading.",
    ),
)

#: Brand names. Not unsafe -- but a branded machine is gym-specific, so the
#: substitution graph must be reviewed before it is prescribed to anyone.
BRANDED_RULE = (
    "branded_machine",
    r"\b(smith|hammer strength|nautilus|cybex|life ?fitness|prime|technogym|"
    r"precor|matrix|atlantis)\b",
    "Branded or gym-specific machine. Needs a reviewed generic substitute "
    "before it can be programmed.",
)

#: Movements that are ordinary for a trained lifter and worth a second look
#: before an app hands them to a novice. Coaching judgement, not health advice.
CAUTION_RULES: tuple[tuple[str, str, str], ...] = (
    (
        "loaded_spinal_hinge",
        r"\b(good ?morning|jefferson|zercher)\b",
        "Loaded hinge with the bar on the back -- technique-sensitive enough "
        "that a novice should be taught it, not assigned it.",
    ),
    (
        "upright_row",
        r"\bupright row\b",
        "Upright row: coaching opinion is divided on shoulder positioning. "
        "Flagged for a human call rather than defaulted in.",
    ),
    (
        "behind_the_neck",
        r"\bbehind (the )?(neck|head|back)\b",
        "Behind-the-neck variation. Requires shoulder mobility most novices "
        "have not developed.",
    ),
)

# ---------------------------------------------------------------------------
# Movement pattern rules -- ORDER IS THE SPECIFICITY ORDER
# ---------------------------------------------------------------------------

#: (rule name, regex, pattern). Evaluated top to bottom; the first match wins.
#: Every OTHER rule is still evaluated, so a name matching two different
#: patterns can be detected and sent to review rather than silently resolved
#: by rule order.
PATTERN_RULES: tuple[tuple[str, str, str], ...] = (
    ("carry_named", r"\b(carry|carries|farmer'?s? walk|suitcase walk|yoke walk|"
                    r"waiter walk|overhead walk)\b", "carry"),
    ("vertical_pull", r"\b(pull[- ]?up|pull[- ]?ups|chin[- ]?up|chin[- ]?ups|"
                      r"pulldown|pull[- ]?down|lat pull)\b", "pull_vertical"),
    ("vertical_press", r"\b(overhead press|shoulder press|military press|"
                       r"arnold press|push press|overhead barbell press|"
                       r"z press)\b", "push_vertical"),
    ("horizontal_press", r"\b(bench press|chest press|push[- ]?up|push[- ]?ups|"
                         r"dip|dips|floor press|jm press|decline press|"
                         r"incline press)\b", "push_horizontal"),
    ("chest_fly", r"\b(fly|flyes|flys|flye|pec deck|pectoral)\b",
     "push_horizontal"),
    ("horizontal_pull", r"\b(row|rows|face pull|rear[- ]delt)\b",
     "pull_horizontal"),
    ("hinge_named", r"\b(deadlift|romanian|rdl|stiff[- ]legged|hip thrust|"
                    r"glute bridge|back extension|hyperextension|swing|"
                    r"swings|good ?morning|pull[- ]?through)\b", "hinge"),
    # MUST precede `squat_named`. Before this rule existed every lunge,
    # split squat and step-up matched `squat_named` and was stored as a
    # SQUAT -- five of them in the unclassified projection alone. Nothing
    # flagged it: a lunge in the squat slot has a pattern and is a compound,
    # so it disagrees with nothing and sails straight through review.
    ("lunge_named", r"\b(lunge|lunges|split squat|step[- ]?up|step[- ]?ups|"
                    r"bulgarian|rear[- ]foot[- ]elevated|"
                    r"front[- ]foot[- ]elevated)\b", "lunge"),
    ("squat_named", r"\b(squat|squats|leg press|hack|goblet)\b", "squat"),
    # MUST precede `isolation_named`. Crunches, planks, sit-ups and twists
    # all matched `isolation_named` and were stored as ISOLATION, so `core`
    # projected as an empty slot while ten core movements sat in the review
    # pile. They were never missing; they were misfiled.
    ("core_named", r"\b(crunch|crunches|plank|planks|sit[- ]?up|sit[- ]?ups|"
                   r"situp|situps|leg raise|leg raises|leg lift|leg lifts|"
                   r"rollout|roll[- ]?out|dead ?bug|hollow|pallof|"
                   r"russian twist|woodchop|wood chop|oblique|ab wheel|"
                   r"rotary torso|bicycle)\b", "core"),
    ("isolation_named", r"\b(curl|curls|extension|extensions|raise|raises|"
                        r"kickback|shrug|shrugs|calf|"
                        r"pushdown|push[- ]?down|pullover|twist|"
                        r"adduction|abduction|wrist|neck)\b", "isolation"),
)

# ---------------------------------------------------------------------------
# Prescription defaults by class
# ---------------------------------------------------------------------------

#: (rep_min, rep_max, rest_seconds, fatigue_cost). Every value sits inside the
#: CHECK constraints in models.py, and the tests assert that rather than trust
#: it.
CLASS_DEFAULTS: dict[str, tuple[int, int, int, int]] = {
    "compound": (6, 10, 120, 4),
    "machine": (8, 12, 90, 3),
    "isolation": (10, 15, 60, 2),
}

#: Squat and hinge cost more than other compounds and deserve longer rest.
_HEAVY_PATTERNS = frozenset({"squat", "hinge"})
_HEAVY_REST = 150
_HEAVY_FATIGUE = 5

#: Unilateral work is per-side, so the same rep number is twice the work.
_UNILATERAL_RULE = (
    r"\b(one[- ]arm|1[- ]arm|single[- ]arm|one[- ]leg|1[- ]leg|single[- ]leg|"
    r"one[- ]legged|single[- ]legged|unilateral|alternating|lunge|lunges|"
    r"split squat|step[- ]?up|bulgarian|side plank|suitcase)\b"
)

#: Below this, a proposal is never auto-approved.
APPROVAL_THRESHOLD = 0.8


@dataclass(frozen=True)
class Proposal:
    """One proposed `exercise_attributes` row, plus why."""

    exercise_id: str
    exercise_name: str
    equipment: str
    muscle_group: str
    movement_pattern: Optional[str]
    movement_pattern_short: Optional[str]
    exercise_class: Optional[str]
    is_unilateral: bool
    default_rep_min: Optional[int]
    default_rep_max: Optional[int]
    default_rest_seconds: Optional[int]
    fatigue_cost: Optional[int]
    confidence: float
    classification_rule: str
    review_status: str
    review_reason: str
    beginner_eligible: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _search(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.I) is not None


def _matching_patterns(name: str) -> list[tuple[str, str]]:
    """Every (rule, pattern) whose regex fires on this name, in rule order."""
    return [
        (rule, pattern)
        for rule, regex, pattern in PATTERN_RULES
        if _search(regex, name)
    ]


def classify(exercise: dict[str, Any]) -> Proposal:
    """Propose attributes for one catalogue row.

    Returns a proposal for EVERY input, including one that matched nothing --
    the review status carries that fact rather than the row disappearing.
    """
    ex_id = str(exercise["id"])
    name = str(exercise.get("name") or "").strip()
    equipment = str(exercise.get("equipment") or "").strip().lower()
    muscle = str(exercise.get("muscle_group") or "").strip().lower()
    db_is_compound = bool(exercise.get("is_compound"))

    unilateral = _search(_UNILATERAL_RULE, name)

    def _incomplete(rule: str, status: str, reason: str, confidence: float,
                    pattern: Optional[str] = None) -> Proposal:
        """A proposal carrying no numbers.

        Rep and rest values are deliberately NULL for anything not approved:
        an unreviewed row must not carry numbers that look ready to seed.
        """
        return Proposal(
            exercise_id=ex_id,
            exercise_name=name,
            equipment=equipment,
            muscle_group=muscle,
            movement_pattern=pattern,
            movement_pattern_short=SHORT_FORM.get(pattern) if pattern else None,
            exercise_class=None,
            is_unilateral=unilateral,
            default_rep_min=None,
            default_rep_max=None,
            default_rest_seconds=None,
            fatigue_cost=None,
            confidence=confidence,
            classification_rule=rule,
            review_status=status,
            review_reason=reason,
            beginner_eligible=False,
        )

    if not name:
        return _incomplete("empty_name", REVIEW_NEEDED,
                           "Exercise has no name to classify.", 0.0)

    # 1. Beginner exclusions, before anything else. An olympic lift is not a
    #    hinge with a note attached; it is out of scope for this template.
    for rule, regex, reason in EXCLUSION_RULES:
        if _search(regex, name):
            return _incomplete(rule, REVIEW_EXCLUDED, reason, 1.0)

    # 2. Branded machines: classifiable, but not prescribable until a generic
    #    substitute has been reviewed.
    brand_rule, brand_regex, brand_reason = BRANDED_RULE
    if _search(brand_regex, name):
        return _incomplete(brand_rule, REVIEW_NEEDED, brand_reason, 0.5)

    # 3. Movement pattern.
    matches = _matching_patterns(name)
    if not matches:
        return _incomplete(
            "no_rule_matched", REVIEW_NEEDED,
            "No movement-pattern rule matched this name.", 0.0,
        )

    rule, pattern = matches[0]
    distinct = {p for _r, p in matches}
    confidence = 1.0
    flags: list[str] = []

    if len(distinct) > 1:
        # Rule order would resolve this silently. It should not.
        others = sorted(distinct - {pattern})
        confidence = 0.6
        flags.append(
            f"Name also matches {', '.join(others)}; rule order chose "
            f"{pattern}."
        )

    # 4. Class, cross-checked against the catalogue's own compound flag.
    if equipment in ("machine", "smith"):
        derived = "machine"
    elif pattern == "isolation":
        derived = "isolation"
    else:
        derived = "compound"

    if derived != "machine":
        pattern_says_compound = pattern in _COMPOUND_PATTERNS
        if pattern_says_compound != db_is_compound:
            confidence = min(confidence, 0.7)
            flags.append(
                f"Catalogue says is_compound={db_is_compound}, but the "
                f"{pattern} pattern implies "
                f"{'compound' if pattern_says_compound else 'isolation'}."
            )

    # 5. Coaching cautions.
    for c_rule, c_regex, c_reason in CAUTION_RULES:
        if _search(c_regex, name):
            confidence = min(confidence, 0.5)
            flags.append(c_reason)
            rule = f"{rule}+{c_rule}"

    rep_min, rep_max, rest, fatigue = CLASS_DEFAULTS[derived]
    if pattern in _HEAVY_PATTERNS and derived == "compound":
        rest, fatigue = _HEAVY_REST, _HEAVY_FATIGUE

    approved = confidence >= APPROVAL_THRESHOLD and not flags
    status = REVIEW_APPROVED if approved else REVIEW_NEEDED
    reason = "Matched a single unambiguous rule." if approved else " ".join(flags)

    if not approved:
        return _incomplete(rule, status, reason, confidence, pattern)

    return Proposal(
        exercise_id=ex_id,
        exercise_name=name,
        equipment=equipment,
        muscle_group=muscle,
        movement_pattern=pattern,
        movement_pattern_short=SHORT_FORM[pattern],
        exercise_class=derived,
        is_unilateral=unilateral,
        default_rep_min=rep_min,
        default_rep_max=rep_max,
        default_rest_seconds=rest,
        fatigue_cost=fatigue,
        confidence=confidence,
        classification_rule=rule,
        review_status=status,
        review_reason=reason,
        beginner_eligible=equipment in BEGINNER_EQUIPMENT,
    )


def classify_all(catalogue: "list[dict[str, Any]]") -> tuple[Proposal, ...]:
    """Classify a whole catalogue, sorted stably by exercise_id.

    Sorting on the id rather than the name makes the output independent of
    both the query's ordering and of any later rename.
    """
    return tuple(
        sorted((classify(row) for row in catalogue), key=lambda p: p.exercise_id)
    )


def seedable(proposals: "tuple[Proposal, ...]") -> tuple[Proposal, ...]:
    """The strict subset safe to write to `exercise_attributes`.

    THIS IS THE GATE. Only approved rows are ever seeded, so an unreviewed
    classification never reaches the table -- which is what stops the generator
    consuming one, since generation joins `exercise_attributes` inner and an
    absent row is simply not a candidate.
    """
    return tuple(
        p
        for p in proposals
        if p.review_status == REVIEW_APPROVED
        and p.movement_pattern is not None
        and p.exercise_class is not None
    )


def summarise(proposals: "tuple[Proposal, ...]") -> dict[str, Any]:
    """Counts a reviewer needs before reading 874 rows."""
    def tally(key) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in proposals:
            k = key(p)
            out[str(k)] = out.get(str(k), 0) + 1
        return dict(sorted(out.items()))

    approved = seedable(proposals)
    return {
        "classifier_version": CLASSIFIER_VERSION,
        "total_exercises": len(proposals),
        "classified": len(approved),
        "review_required": sum(
            1 for p in proposals if p.review_status == REVIEW_NEEDED
        ),
        "beginner_excluded": sum(
            1 for p in proposals if p.review_status == REVIEW_EXCLUDED
        ),
        "unclassified": sum(1 for p in proposals if p.movement_pattern is None),
        "beginner_eligible": sum(1 for p in approved if p.beginner_eligible),
        "by_movement_pattern": tally(lambda p: p.movement_pattern),
        "by_exercise_class": tally(lambda p: p.exercise_class),
        "by_equipment": tally(lambda p: p.equipment),
        "by_review_status": tally(lambda p: p.review_status),
        "by_classification_rule": tally(lambda p: p.classification_rule),
    }
