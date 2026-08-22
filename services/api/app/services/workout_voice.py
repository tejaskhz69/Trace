"""Voice workout logging: speak your session, get structured sets back.

    "bench press, sixty kilos, ten, ten, eight. then incline dumbbells,
     twenty-two fives, twelve twelve ten. finished with lat pulldowns."

        -> Barbell Bench Press     60 x 10, 60 x 10, 60 x 8
           Incline Dumbbell Press  22.5 x 12, 22.5 x 12, 22.5 x 10
           Lat Pulldown            (weight asked for)

ONE OBJECT PER SET, NEVER A COUNT
`sets` is a list, not a number. A lifter who ramps up -- "sixty for five,
eighty for five, a hundred for three" -- performed three DIFFERENT sets, and
collapsing that to "3 sets at some weight" throws away the whole session and
makes the e1RM meaningless. Weight carries forward within an exercise, because
people say the load once and then just call the reps.

WHY GEMINI DOES THE AUDIO AND WE DO THE MATCHING
Gemini accepts audio natively, so one call handles transcription AND
extraction -- no separate speech engine, no native STT module, and it works in
Expo Go. But the model must NOT pick which exercise row this is. Matching a
spoken phrase to one of 736 catalogue entries is a deterministic problem with a
right answer, and doing it here means it is testable, explainable, and cannot
drift when the model changes. The model returns a *phrase*; `match_exercise`
turns that into a row.

NOTHING IS WRITTEN WITHOUT REVIEW
`transcribe_workout` returns a proposal, never a logged set. A misheard
"sixty" as "sixteen" silently entering someone's training history would
corrupt their e1RM, and the strength trend is half the product's verdict. The
client shows what was heard, what was understood, and requires a confirm.

REP RANGES ARE PRESERVED
A user who says "ten to fifteen reps" has described a range, and collapsing it
to a single number invents precision they did not offer. `reps_low`/`reps_high`
travel intact; the review screen asks for the actual count per set, pre-filled
from the range.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# Bounds. These are validation, not opinion: they exist so a mis-transcription
# ("one hundred and sixty" for "sixty") cannot enter the strength history.
MAX_SETS = 20
MAX_REPS = 100
MAX_WEIGHT_KG = 500.0
LB_PER_KG = 2.2046226


SYSTEM_PROMPT = """\
You transcribe a spoken gym log and extract every set described.

The speaker may be logging ONE set mid-workout, or narrating an entire
session afterwards. Both are normal. Expect short clipped speech, gym noise,
non-native English, numbers spoken as words ("sixty", "a hundred and ten"),
ranges ("ten to fifteen"), and per-set lists ("ten, ten, eight").

THE MOST IMPORTANT RULE
`sets` is an ARRAY, with ONE OBJECT PER SET ACTUALLY PERFORMED. Never collapse
sets into a count.

  "bench press three sets of ten at sixty kilos"
      -> sets: [{reps:10,weight:60},{reps:10,weight:60},{reps:10,weight:60}]

  "bench press sixty kilos, ten, ten, eight"
      -> sets: [{reps:10,weight:60},{reps:10,weight:60},{reps:8,weight:60}]

  "squats, worked up: sixty for five, eighty for five, a hundred for three"
      -> sets: [{reps:5,weight:60},{reps:5,weight:80},{reps:3,weight:100}]

That third example is why the array matters: a lifter who ramps up has three
different sets, and reporting "3 sets" with one weight throws away the session.

OTHER RULES
- Return the exercise EXACTLY as spoken, in `exercise_phrase`. Do not
  normalise it, do not guess a catalogue name, do not expand abbreviations
  beyond the obvious ("bench" stays "bench").
- Weight carries forward within one exercise until the speaker changes it.
  "Sixty for ten, then ten again" means both sets were at sixty.
- If the speaker gives a rep RANGE for a set ("ten to fifteen"), put the range
  in reps_low/reps_high on that set and leave `reps` null. A range is a target
  they described, not a count they hit.
- Weight unit: set `unit` to "kg" or "lb" as spoken, per entry. If no unit is
  spoken anywhere, set it to "unknown" -- do NOT assume one.
- If no weight is mentioned at all (bodyweight work), omit weight.
- If the speaker says a set was a warm-up, set `is_warmup` true on that set.
- If they say how much was left in the tank ("two reps in reserve", "left two
  in the tank", "that was to failure", "RPE eight"), put the REPS IN RESERVE
  on that set as `rir`. To failure is rir 0. RPE 8 is rir 2.
- Multiple exercises produce multiple entries, IN THE ORDER SPOKEN.
- If they mention how long the session took, set `duration_min`.
- Set `confidence` per entry to your real belief you heard the numbers right.
  Gym noise should lower it. Being unsure is far better than being confidently
  wrong about a weight.
- Put your best plain transcription of the whole recording in `transcript`.

If the audio contains no workout information at all, return an empty entries
list rather than inventing one.

Call the `log_workout` tool exactly once. Never write prose.
"""

TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "name": "log_workout",
    "description": "Report the sets described in the audio.",
    "parameters": {
        "type": "object",
        "properties": {
            "transcript": {
                "type": "string",
                "description": "Plain transcription of what was said.",
            },
            "duration_min": {
                "type": "number",
                "description": "Session length, only if the speaker said it.",
            },
            "entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "exercise_phrase": {
                            "type": "string",
                            "description": "The exercise exactly as spoken.",
                        },
                        "sets": {
                            "type": "array",
                            "description": "ONE OBJECT PER SET PERFORMED.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "reps": {"type": "number"},
                                    "reps_low": {"type": "number"},
                                    "reps_high": {"type": "number"},
                                    "weight": {"type": "number"},
                                    "rir": {
                                        "type": "number",
                                        "description": "Reps left in reserve.",
                                    },
                                    "is_warmup": {"type": "boolean"},
                                },
                            },
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["kg", "lb", "unknown"],
                        },
                        "confidence": {"type": "number"},
                    },
                    "required": ["exercise_phrase", "sets"],
                },
            },
        },
        "required": ["transcript", "entries"],
    },
}


# ---------------------------------------------------------------------------
# Exercise matching -- pure, and deliberately not the model's job
# ---------------------------------------------------------------------------

# TWO KINDS OF SHORTHAND, AND THEY MUST BE SCOPED DIFFERENTLY.
#
# ABBREVIATIONS are unambiguous wherever they appear: "db" is always
# "dumbbell", "rdl" is always "romanian deadlift". Safe to expand word-by-word.
ABBREVIATIONS: dict[str, str] = {
    "db": "dumbbell",
    "bb": "barbell",
    "ohp": "overhead press",
    "dl": "deadlift",
    "rdl": "romanian deadlift",
    "deads": "deadlift",
    "squats": "squat",
    "curls": "curl",
    "pullups": "pull up",
    "chinups": "chin up",
    "pulldowns": "pulldown",
    "bicep": "biceps",
    "tricep": "triceps",
    "hammers": "hammer curl",
    "raises": "raise",
    "crushers": "crusher",
    "thrusts": "thrust",
    "dips": "dip",
    "presses": "press",
    "rows": "row",
    "flyes": "fly",
    "flies": "fly",
}

# WHOLE-PHRASE shorthand is only safe when it is the ENTIRE utterance. "bench"
# alone means bench press; "bench dips" does not, and expanding the word
# in-place turned "bench dips" into "bench press dips" -- which then matched
# Dumbbell Bench Press better than it matched Bench Dips.
WHOLE_PHRASE: dict[str, str] = {
    "bench": "bench press",
    "benching": "bench press",
    "military": "overhead press",
    "squat": "squat",
    "deadlift": "deadlift",
}

_STOPWORDS = frozenset({"the", "a", "an", "of", "on", "with", "and", "my"})


def normalise(phrase: str, *, expand: bool = True) -> str:
    """Lowercase, strip punctuation, and optionally expand spoken shorthand.

    `expand` MUST be False for catalogue names. Expanding them corrupts real
    exercises: "Bench Dips" becomes "bench press dips", which then matches the
    spoken phrase "bench press" perfectly and outranks "Barbell Bench Press".
    Synonyms describe how people SPEAK; they are not facts about the catalogue.
    """
    s = re.sub(r"[^a-z0-9\s]", " ", phrase.lower())
    s = re.sub(r"\s+", " ", s).strip()
    if expand:
        # Whole-phrase first, and only when it IS the whole phrase.
        if s in WHOLE_PHRASE:
            s = WHOLE_PHRASE[s]
        for key in sorted(ABBREVIATIONS, key=len, reverse=True):
            s = re.sub(rf"\b{re.escape(key)}\b", ABBREVIATIONS[key], s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s: str, *, expand: bool = True) -> set[str]:
    return {
        t for t in normalise(s, expand=expand).split() if t and t not in _STOPWORDS
    }


@dataclass
class ExerciseMatch:
    exercise_id: str | None
    name: str | None
    score: float
    # Runner-up rows, so the review screen can offer a correction instead of
    # a dead end when the match is weak.
    alternatives: list[tuple[str, str]] = field(default_factory=list)


# Below this, we do not claim a match. The review screen then asks the user to
# pick, which is a far better failure than silently logging bench press
# because someone said "bench dips".
MATCH_FLOOR = 0.5


def match_exercise(
    phrase: str, catalogue: list[tuple[str, str]]
) -> ExerciseMatch:
    """Map a spoken phrase onto a catalogue row.

    `catalogue` is [(exercise_id, name), ...]. Scoring is token-overlap
    weighted toward the spoken tokens: every word the user said should appear
    in the exercise name, but the name is allowed extra words they omitted
    ("bench press" matching "Barbell Bench Press" is correct, and the reverse
    containment would rank "Bench Press" above it for the phrase "barbell
    bench press", which is wrong).
    """
    want = _tokens(phrase)
    spoken = normalise(phrase)
    if not want:
        return ExerciseMatch(None, None, 0.0)

    scored: list[tuple[float, str, str]] = []
    for ex_id, name in catalogue:
        have = _tokens(name, expand=False)
        if not have:
            continue
        covered = len(want & have) / len(want)
        # Tie-break toward the shorter name, so "Squat" beats "Squat With
        # Chains" when the user just said "squat".
        brevity = 1.0 / (1.0 + max(0, len(have) - len(want)))
        # A contiguous phrase match beats a scattered token match: "bench
        # press" is really in "Barbell Bench Press" and only incidentally in
        # "Bench Dips".
        contiguous = 0.25 if spoken in normalise(name, expand=False) else 0.0
        scored.append((covered + 0.15 * brevity + contiguous, ex_id, name))

    if not scored:
        return ExerciseMatch(None, None, 0.0)

    # Sort by score descending, then by NAME ascending. Sorting the raw tuples
    # would tie-break on exercise_id, which is a random UUID -- so "bench
    # press" would resolve to a different row on a different machine. Name
    # ordering is deterministic and, usefully, puts "Barbell Bench Press"
    # ahead of "Dumbbell Bench Press" for an unqualified "bench press", which
    # is what a lifter means.
    scored.sort(key=lambda t: (-t[0], t[2].lower()))
    best_score, best_id, best_name = scored[0]
    if best_score < MATCH_FLOOR:
        return ExerciseMatch(
            None, None, round(best_score, 3),
            alternatives=[(i, n) for _, i, n in scored[:5]],
        )
    return ExerciseMatch(
        best_id, best_name, round(best_score, 3),
        alternatives=[(i, n) for _, i, n in scored[1:4]],
    )


# ---------------------------------------------------------------------------
# Normalising one spoken entry
# ---------------------------------------------------------------------------


@dataclass
class ParsedSet:
    """One set, as spoken. This is the unit the database stores."""

    reps: int
    weight_kg: float | None
    rir: float | None
    is_warmup: bool
    # A spoken range ("ten to fifteen") is a TARGET the lifter described, not
    # a count they hit. It travels intact so the review screen can pre-fill
    # the low end and ask, rather than inventing a number in the middle.
    reps_low: int | None = None
    reps_high: int | None = None


@dataclass
class ParsedEntry:
    exercise_phrase: str
    exercise_id: str | None
    exercise_name: str | None
    match_score: float
    alternatives: list[dict]
    sets: list[ParsedSet]
    weight_was_converted: bool
    unit_assumed: bool
    confidence: float
    warnings: list[str] = field(default_factory=list)


def _coerce_sets(raw: dict) -> list[dict]:
    """Accept both the per-set array and the older scalar-count shape.

    The model is instructed to emit one object per set, which is what the
    database actually stores and what lets "sixty for five, eighty for five,
    a hundred for three" survive as three different sets. But a model under
    load occasionally falls back to `sets: 3` with a rep range at the entry
    level, and dropping the whole entry because of that would lose a real
    set the user spoke. So the old shape is expanded rather than rejected.
    """
    sets = raw.get("sets")
    if isinstance(sets, list):
        return [s for s in sets if isinstance(s, dict)]

    count = _clamp_int(sets, 1, MAX_SETS, default=1)
    template = {
        "weight": raw.get("weight"),
        "reps": raw.get("reps"),
        "reps_low": raw.get("reps_low"),
        "reps_high": raw.get("reps_high"),
        "rir": raw.get("rir"),
    }
    return [dict(template) for _ in range(count)]


def normalise_entry(
    raw: dict,
    catalogue: list[tuple[str, str]],
    *,
    default_unit: str = "kg",
) -> ParsedEntry | None:
    """Turn one spoken exercise into something safe to show the user.

    Returns None only when there is no exercise phrase at all -- anything else
    is surfaced WITH WARNINGS rather than dropped, because a user who spoke a
    set and sees nothing appear simply stops trusting the feature.
    """
    phrase = str(raw.get("exercise_phrase") or "").strip()
    if not phrase:
        return None

    warnings: list[str] = []

    unit = str(raw.get("unit") or "unknown").lower()
    unit_assumed = unit not in ("kg", "lb")
    if unit_assumed:
        unit = default_unit

    raw_sets = _coerce_sets(raw)
    if len(raw_sets) > MAX_SETS:
        warnings.append(f"Heard {len(raw_sets)} sets; kept the first {MAX_SETS}.")
        raw_sets = raw_sets[:MAX_SETS]

    parsed: list[ParsedSet] = []
    converted = False
    saw_weight = False
    # Weight carries forward within an exercise: a lifter says the load once
    # and then just calls the reps. Re-asking for it on every set is exactly
    # the typing this feature exists to remove.
    last_weight: float | None = None

    for item in raw_sets:
        w = _num(item.get("weight"))
        weight_kg: float | None = None
        if w is not None and w > 0:
            saw_weight = True
            weight_kg = w / LB_PER_KG if unit == "lb" else w
            converted = converted or unit == "lb"
            if weight_kg > MAX_WEIGHT_KG:
                warnings.append(
                    f"Heard {weight_kg:.0f} kg, which is past the world record. "
                    f"Check it before saving."
                )
                weight_kg = None
            else:
                weight_kg = round(weight_kg, 1)
                last_weight = weight_kg
        elif last_weight is not None:
            weight_kg = last_weight

        lo = hi = None
        n = _num(item.get("reps"))
        if n is None:
            lo_raw, hi_raw = _num(item.get("reps_low")), _num(item.get("reps_high"))
            if lo_raw is not None or hi_raw is not None:
                lo = _clamp_int(lo_raw if lo_raw is not None else hi_raw, 1, MAX_REPS, default=1)
                hi = _clamp_int(hi_raw if hi_raw is not None else lo_raw, 1, MAX_REPS, default=lo)
                if hi < lo:
                    lo, hi = hi, lo
                # Pre-fill the LOW end. An unedited confirm can then only ever
                # under-claim, never inflate the training history.
                reps = lo
            else:
                reps = 1
                warnings.append("A set had no rep count; defaulted to 1.")
        else:
            reps = _clamp_int(n, 1, MAX_REPS, default=1)

        rir = _num(item.get("rir"))
        if rir is not None:
            rir = max(0.0, min(10.0, rir))

        parsed.append(
            ParsedSet(
                reps=reps,
                weight_kg=weight_kg,
                rir=rir,
                is_warmup=bool(item.get("is_warmup")),
                reps_low=lo,
                reps_high=hi,
            )
        )

    if saw_weight and unit_assumed:
        warnings.append(f"No unit was spoken — assumed {default_unit}.")

    m = match_exercise(phrase, catalogue)
    if m.exercise_id is None:
        warnings.append(f"Couldn't match “{phrase}” to an exercise. Pick one below.")

    return ParsedEntry(
        exercise_phrase=phrase,
        exercise_id=m.exercise_id,
        exercise_name=m.name,
        match_score=m.score,
        alternatives=[{"id": i, "name": n} for i, n in m.alternatives],
        sets=parsed,
        weight_was_converted=converted,
        unit_assumed=unit_assumed and saw_weight,
        confidence=float(_num(raw.get("confidence")) or 0.5),
        warnings=warnings,
    )


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _clamp_int(v: Any, lo: int, hi: int, *, default: int) -> int:
    n = _num(v)
    if n is None:
        return default
    return int(max(lo, min(hi, round(n))))


# ---------------------------------------------------------------------------
# The model call
# ---------------------------------------------------------------------------


@dataclass
class VoiceResult:
    transcript: str
    entries: list[ParsedEntry]
    model_used: str
    latency_ms: int
    duration_min: int | None = None

    @property
    def total_sets(self) -> int:
        return sum(len(e.sets) for e in self.entries)

    @property
    def needs_attention(self) -> bool:
        """True when at least one entry cannot be saved without a human.

        The whole-session flow saves everything in one tap, so the review
        screen has to be able to say, before that tap, whether anything in
        here is unresolved. An unmatched exercise is the case that matters:
        we will not guess which of 736 rows the user meant.
        """
        return any(e.exercise_id is None for e in self.entries)


async def transcribe_workout(
    audio: bytes,
    *,
    mime_type: str,
    catalogue: list[tuple[str, str]],
    default_unit: str = "kg",
) -> VoiceResult:
    """Audio in, a PROPOSAL out. Nothing is written here."""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    # Reuse the vision module's cached client: same credential, same warm
    # connection pool, and a new client per utterance costs a TLS handshake.
    from .vision import _client

    client = _client()
    model = settings.VOICE_MODEL
    started = time.perf_counter()

    resp = await client.aio.interactions.create(
        model=model,
        system_instruction=SYSTEM_PROMPT,
        input=[
            {
                "type": "audio",
                "data": base64.standard_b64encode(audio).decode("ascii"),
                "mime_type": mime_type,
            }
        ],
        tools=[TOOL_SCHEMA],
        # A whole-session dictation can be a dozen exercises with per-set
        # detail, which is far more JSON than a single spoken set. Too small a
        # budget truncates the tool call and the last exercises silently
        # vanish -- the failure looks like the model "missing" them.
        generation_config={"max_output_tokens": 4096, "tool_choice": "any"},
    )

    payload: dict[str, Any] = {}
    for step in getattr(resp, "steps", []) or []:
        if getattr(step, "type", None) == "function_call":
            args = step.arguments
            payload = json.loads(args) if isinstance(args, str) else (args or {})
            break

    entries = []
    for raw in payload.get("entries", []) or []:
        parsed = normalise_entry(raw, catalogue, default_unit=default_unit)
        if parsed is not None:
            entries.append(parsed)

    duration = _num(payload.get("duration_min"))
    return VoiceResult(
        transcript=str(payload.get("transcript") or "").strip(),
        entries=entries,
        model_used=model,
        latency_ms=int((time.perf_counter() - started) * 1000),
        # Only when the speaker actually said it. Inferring a duration from
        # the length of the recording would be nonsense -- the narration
        # happens after the session, not during it.
        duration_min=int(max(1, min(600, duration))) if duration else None,
    )
