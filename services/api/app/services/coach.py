"""The coach.

Turns six independent signals — nutrition, weight trend, strength, steps,
sleep, and training load — into ONE thing the user should do today.

DESIGN PRINCIPLES
-----------------
1. **One recommendation, not a dashboard.** A list of six observations is a
   report. A coach says one thing. We rank candidate insights by urgency and
   surface the top one, with the rest available underneath.

2. **Always name the cause, never just the symptom.** "You're stalled" is
   useless. "You're stalled and your steps fell 3,000/day" is actionable, and
   crucially it offers a fix that isn't "eat less" — which is the fix people
   can actually sustain.

3. **Diagnose from the cheapest fixable cause first.** Order of intervention:
   sleep → activity → adherence → protein → calories. Cutting calories is the
   LAST lever, not the first, because it's the one with the worst adherence
   cost and it's often treating a symptom.

4. **Never invent certainty.** Every insight carries the data behind it and
   the confidence we have in it. If we don't know, we say so.

5. **No medical claims.** We report trends and suggest training/nutrition
   adjustments. We never diagnose, never mention specific conditions, and
   never tell someone their symptoms mean something clinical.

The deterministic rules below produce the insight. A Claude call (in
`narrate()`) only rewrites it in the user's voice — it never decides anything.
That separation matters: the recommendation must be reproducible and testable,
and a model must never be able to invent a calorie change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .activity import ActivityTrend, NeatDrift, SleepSummary
from .adjudication import AdjudicationResult, Verdict


class Urgency(int, Enum):
    """Higher wins when ranking insights."""

    critical = 100   # something is actively going wrong
    high = 75        # a clear, fixable problem
    medium = 50      # worth knowing
    low = 25         # positive reinforcement
    info = 10


class Lever(str, Enum):
    sleep = "sleep"
    activity = "activity"
    adherence = "adherence"
    protein = "protein"
    calories = "calories"
    training = "training"
    none = "none"


@dataclass
class Insight:
    key: str
    urgency: Urgency
    lever: Lever
    headline: str
    detail: str
    action: str | None = None
    evidence: dict = field(default_factory=dict)
    confidence: float = 0.7


@dataclass
class CoachBriefing:
    primary: Insight | None
    secondary: list[Insight]
    prompts: list[str]          # things to ask the user for (e.g. weigh-in)
    generated_for: date
    data_completeness: float    # 0..1 — how much we actually had to work with


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass
class CoachInput:
    today: date
    body_weight_kg: float
    goal_type: str

    adjudication: AdjudicationResult | None = None
    neat: NeatDrift | None = None
    sleep: SleepSummary | None = None

    # Nutrition
    logged_days_last_14: int = 0
    mean_protein_g: float | None = None
    mean_calories: float | None = None
    calorie_target: float | None = None

    # Training
    sessions_last_7: int = 0
    sessions_last_14: int = 0
    mean_sessions_baseline: float | None = None

    # Weigh-ins
    weigh_ins_last_14: int = 0
    weigh_in_prompt: str | None = None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def _sleep_insight(inp: CoachInput) -> Insight | None:
    s = inp.sleep
    if not s or not s.is_concerning or s.mean_hours is None:
        return None

    # Sleep outranks everything because it makes every other signal unreliable.
    return Insight(
        key="sleep_debt",
        urgency=Urgency.critical,
        lever=Lever.sleep,
        headline=f"You're running on {s.mean_hours:.1f} hours",
        detail=(
            f"About {s.debt_hours:.0f} hours of sleep debt over the last "
            f"{s.nights} nights. Under-slept, your strength drops, your "
            f"appetite regulation gets worse, and more of any weight you lose "
            f"comes from muscle. Every other number I'm tracking gets noisier "
            f"too."
        ),
        action="Fix sleep before we change anything about your food.",
        evidence={
            "mean_hours": s.mean_hours,
            "debt_hours": s.debt_hours,
            "worst_night": s.worst_night_hours,
            "nights": s.nights,
        },
        confidence=0.85,
    )


def _neat_insight(inp: CoachInput) -> Insight | None:
    """The headline feature of the fitness side.

    When someone stalls on a cut, the reflex is to cut calories again. Very
    often the real cause is that their unconscious daily movement collapsed —
    and walking more is far easier to sustain than eating less.
    """
    n = inp.neat
    if not n or not n.is_significant or n.trend is not ActivityTrend.falling:
        return None

    stalled = (
        inp.adjudication is not None
        and inp.adjudication.verdict
        in (Verdict.fat_gain, Verdict.insufficient_data)
    )

    return Insight(
        key="neat_drift_down",
        urgency=Urgency.critical if stalled else Urgency.high,
        lever=Lever.activity,
        headline="Your daily movement has dropped",
        detail=(
            f"Steps are down from about {n.baseline_steps:,} to "
            f"{n.recent_steps:,} a day — roughly "
            f"{abs(n.estimated_kcal_delta or 0):.0f} kcal/day less burn. "
            + (
                "That almost certainly explains the stall. "
                if stalled
                else ""
            )
            + "This happens unconsciously when you're in a deficit: you take "
            "the lift, you fidget less, you walk slower."
        ),
        action=(
            f"Get back to ~{n.baseline_steps:,} steps before we cut your "
            f"calories again. It's the same energy, and it's far easier to "
            f"stick to."
        ),
        evidence={
            "baseline_steps": n.baseline_steps,
            "recent_steps": n.recent_steps,
            "delta_steps": n.delta_steps,
            "kcal_delta": n.estimated_kcal_delta,
        },
        confidence=0.8,
    )


def _adherence_insight(inp: CoachInput) -> Insight | None:
    if inp.logged_days_last_14 >= 10:
        return None

    return Insight(
        key="low_logging",
        urgency=Urgency.high,
        lever=Lever.adherence,
        headline="I can't see enough to coach you",
        detail=(
            f"You logged food on {inp.logged_days_last_14} of the last 14 days. "
            f"Below about 10, my estimate of what you're actually eating — and "
            f"therefore your target — is guesswork."
        ),
        action="Aim for 10 days out of 14. It doesn't have to be perfect, it has to be honest.",
        evidence={"logged_days": inp.logged_days_last_14, "of": 14},
        confidence=0.95,
    )


def _weigh_in_insight(inp: CoachInput) -> Insight | None:
    if inp.weigh_ins_last_14 >= 8:
        return None
    return Insight(
        key="low_weigh_ins",
        urgency=Urgency.medium,
        lever=Lever.adherence,
        headline="I need more weigh-ins",
        detail=(
            f"Only {inp.weigh_ins_last_14} weigh-ins in 14 days. The trend line "
            f"smooths out daily noise, but it needs data points to smooth. "
            f"Daily is ideal; every other day works."
        ),
        action="Weigh yourself first thing, after the loo, before eating.",
        evidence={"weigh_ins": inp.weigh_ins_last_14, "of": 14},
        confidence=0.95,
    )


def _protein_insight(inp: CoachInput) -> Insight | None:
    if inp.mean_protein_g is None:
        return None
    per_kg = inp.mean_protein_g / inp.body_weight_kg
    if per_kg >= 1.5:
        return None

    target = round(inp.body_weight_kg * 1.6)
    return Insight(
        key="low_protein",
        urgency=Urgency.high if per_kg < 1.2 else Urgency.medium,
        lever=Lever.protein,
        headline=f"Protein is low at {per_kg:.1f} g/kg",
        detail=(
            f"You're averaging {inp.mean_protein_g:.0f} g a day. Below about "
            f"1.6 g/kg, more of any weight you lose comes from muscle — and "
            f"the strength verdict I give you becomes much harder to read, "
            f"because flat lifts could just be under-eating protein."
        ),
        action=f"Target {target} g a day.",
        evidence={"current_g": round(inp.mean_protein_g), "per_kg": round(per_kg, 2), "target_g": target},
        confidence=0.9,
    )


def _training_insight(inp: CoachInput) -> Insight | None:
    baseline = inp.mean_sessions_baseline
    if baseline is None or baseline < 1:
        return None

    if inp.sessions_last_7 == 0 and baseline >= 2:
        return Insight(
            key="training_stopped",
            urgency=Urgency.high,
            lever=Lever.training,
            headline="No sessions logged this week",
            detail=(
                f"You normally train about {baseline:.1f} times a week. A gap "
                f"is fine — life happens — but if you're cutting, training is "
                f"what tells your body to keep the muscle."
            ),
            action="Even one session this week protects your progress.",
            evidence={"sessions_last_7": 0, "baseline": round(baseline, 1)},
            confidence=0.75,
        )

    if inp.sessions_last_7 >= baseline * 1.6 and inp.sessions_last_7 >= 5:
        return Insight(
            key="training_spike",
            urgency=Urgency.medium,
            lever=Lever.training,
            headline="You've ramped up hard this week",
            detail=(
                f"{inp.sessions_last_7} sessions against a usual "
                f"{baseline:.1f}. Big jumps in volume are where injuries and "
                f"burnout come from, and it'll also make your weight trend "
                f"jump around from inflammation and glycogen."
            ),
            action="Hold this volume for a couple of weeks before adding more.",
            evidence={"sessions_last_7": inp.sessions_last_7, "baseline": round(baseline, 1)},
            confidence=0.7,
        )

    return None


def _verdict_insight(inp: CoachInput) -> Insight | None:
    """Wrap the strength adjudication as a coach insight."""
    a = inp.adjudication
    if a is None or a.verdict is Verdict.insufficient_data:
        return None

    urgency = {
        Verdict.muscle_loss_risk: Urgency.critical,
        Verdict.fat_gain: Urgency.high,
        Verdict.lean_gain: Urgency.low,
        Verdict.clean_cut: Urgency.low,
        Verdict.recomposition: Urgency.low,
    }.get(a.verdict, Urgency.medium)

    action = None
    if a.recommended_calorie_delta:
        direction = "Add" if a.recommended_calorie_delta > 0 else "Cut"
        action = f"{direction} {abs(a.recommended_calorie_delta):.0f} kcal/day."
    if a.recommended_protein_g:
        action = f"{action or ''} Get protein to {a.recommended_protein_g} g.".strip()

    return Insight(
        key=f"verdict_{a.verdict.value}",
        urgency=urgency,
        lever=Lever.calories if a.recommended_calorie_delta else Lever.none,
        headline=a.headline,
        detail=a.explanation,
        action=action,
        evidence=a.math,
        confidence=0.8 if not a.guardrails_triggered else 0.6,
    )


def _positive_insight(inp: CoachInput) -> Insight | None:
    """Something true and specific when things are going well.

    'Everything's on track' is a churn message. Give them a number.
    """
    a = inp.adjudication
    if a is None or a.verdict not in (
        Verdict.lean_gain,
        Verdict.clean_cut,
        Verdict.recomposition,
    ):
        return None

    return Insight(
        key="on_track",
        urgency=Urgency.low,
        lever=Lever.none,
        headline=a.headline,
        detail=(
            a.explanation
            + " Nothing to change — the plan is working, so let it run."
        ),
        evidence=a.math,
        confidence=0.8,
    )


# ---------------------------------------------------------------------------
# The briefing
# ---------------------------------------------------------------------------


RULES = (
    _sleep_insight,
    _neat_insight,
    _adherence_insight,
    _protein_insight,
    _verdict_insight,
    _training_insight,
    _weigh_in_insight,
    _positive_insight,
)


def build_briefing(inp: CoachInput) -> CoachBriefing:
    """Run every rule, rank by urgency, surface one.

    Ties break toward the CHEAPER lever — sleep and activity before calories —
    because those are the interventions people can actually sustain.
    """
    lever_priority = {
        Lever.sleep: 0,
        Lever.activity: 1,
        Lever.adherence: 2,
        Lever.protein: 3,
        Lever.training: 4,
        Lever.calories: 5,
        Lever.none: 6,
    }

    insights = [i for rule in RULES if (i := rule(inp)) is not None]
    insights.sort(key=lambda i: (-i.urgency.value, lever_priority[i.lever]))

    # Deduplicate: if the verdict already says "cut calories" and NEAT drift
    # explains why, show the NEAT one — it has the better action.
    seen_levers: set[Lever] = set()
    deduped: list[Insight] = []
    for i in insights:
        if i.lever in seen_levers and i.lever is not Lever.none:
            continue
        seen_levers.add(i.lever)
        deduped.append(i)

    prompts = [inp.weigh_in_prompt] if inp.weigh_in_prompt else []

    # How much did we actually have to work with?
    signals = [
        inp.adjudication is not None,
        inp.neat is not None and inp.neat.trend is not ActivityTrend.insufficient_data,
        inp.sleep is not None and inp.sleep.mean_hours is not None,
        inp.logged_days_last_14 >= 5,
        inp.weigh_ins_last_14 >= 5,
        inp.sessions_last_14 >= 2,
    ]
    completeness = round(sum(signals) / len(signals), 2)

    return CoachBriefing(
        primary=deduped[0] if deduped else None,
        secondary=deduped[1:4],
        prompts=prompts,
        generated_for=inp.today,
        data_completeness=completeness,
    )


# ---------------------------------------------------------------------------
# Narration
# ---------------------------------------------------------------------------


NARRATOR_SYSTEM = """\
You are the voice of Trace, a fitness and nutrition coach app.

You will be given a STRUCTURED INSIGHT that has already been decided by a
deterministic engine. Your ONLY job is to rewrite it in a warm, direct,
second-person voice. Two to four sentences.

ABSOLUTE RULES — violating any of these is a failure:
- Do NOT change any number. Not calories, not steps, not grams, not hours.
- Do NOT invent a recommendation the insight doesn't contain.
- Do NOT add medical claims, diagnoses, or references to conditions.
- Do NOT hedge the recommendation into meaninglessness.
- Do NOT use hype, exclamation marks, or motivational-poster language.
- If the insight says we lack data, say that plainly rather than guessing.

Voice: a knowledgeable friend who lifts. Specific, calm, never preachy. You
respect that the user is an adult who can handle a direct answer. Lead with
what's happening, then what to do about it.
"""


def narration_prompt(insight: Insight, briefing: CoachBriefing) -> str:
    """Build the user message for the narration call.

    Kept as a pure function so the prompt can be tested and diffed without
    making a network call.
    """
    lines = [
        f"INSIGHT KEY: {insight.key}",
        f"LEVER: {insight.lever.value}",
        f"HEADLINE: {insight.headline}",
        f"DETAIL: {insight.detail}",
    ]
    if insight.action:
        lines.append(f"ACTION: {insight.action}")
    lines.append(f"EVIDENCE: {insight.evidence}")
    lines.append(f"CONFIDENCE: {insight.confidence}")
    lines.append(f"DATA COMPLETENESS: {briefing.data_completeness}")
    if briefing.secondary:
        lines.append(
            "ALSO TRUE (mention at most one, only if it fits naturally): "
            + "; ".join(f"{s.headline}" for s in briefing.secondary)
        )
    return "\n".join(lines)
