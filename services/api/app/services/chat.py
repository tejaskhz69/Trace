"""AI Trainer -- single-turn Q&A for the pre-login "ask a quick question" box.

Deliberately small. This is not the coach engine (`coach.py`, which reasons
over a signed-in user's logs) and not a persisted conversation -- it's one
question, asked before the user has an account, answered with no personal
data because there is none to give it yet. No `ChatThread`/`ChatMessage`
tables, no history: that's for a later pass once there's a real key and a
real signed-in surface to attach it to.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import get_settings

settings = get_settings()

MAX_QUESTION_LEN = 500

SYSTEM_PROMPT = """\
You are the Trace AI Trainer, answering one quick question from someone who \
has not signed in yet. You have no access to their logs, weight trend, or \
targets, so:
  - Never invent personal numbers (calorie targets, macros, TDEE) -- you do \
    not have their data. Say so, and suggest they sign in for a real number.
  - If asked what Trace does: it tells you whether you're gaining muscle or \
    fat, not just whether the scale moved.
  - If asked about coaching priority, the order is always sleep, then \
    activity, then logging adherence, then protein, then calories -- \
    calories last, because it's the most disruptive lever and the least \
    often the actual problem.
  - Exercise calories are never added on top of a calorie target -- the \
    adaptive weight trend already accounts for them.
  - Be concise: 2-4 sentences, no bullet lists or headers. This is a \
    quick-question box on the login screen, not a chat thread.
"""


def validate_question(raw: str) -> str:
    """Pure validation -- trims and bounds the question. No I/O."""
    question = (raw or "").strip()
    if not question:
        raise ValueError("Ask something first.")
    if len(question) > MAX_QUESTION_LEN:
        raise ValueError(f"Keep it under {MAX_QUESTION_LEN} characters.")
    return question


@dataclass
class ChatAnswer:
    answer: str
    model_used: str


async def ask(question: str) -> ChatAnswer:
    """Call Gemini for one answer. Mirrors vision.recognize()'s guard."""
    # Reuse vision's cached client: same credential, same connection pool,
    # and constructing a new one per question paid a TLS handshake every time.
    from .vision import _client

    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    client = _client()
    model = settings.CHAT_MODEL

    resp = await client.aio.interactions.create(
        model=model,
        system_instruction=SYSTEM_PROMPT,
        input=question,
        generation_config={
            # Gemini 3.x models think before answering, and those reasoning
            # tokens are billed against max_output_tokens. The old 300-token
            # budget was sized for a non-thinking model and silently truncated
            # the reply mid-sentence. "low" is right here: this is a
            # two-sentence answer to a general question, not a reasoning task.
            # (The SDK's type hint also lists "minimal", but gemini-3.7-flash
            # rejects it at request time -- the hint is broader than the
            # model's real support, so trust the API, not the annotation.)
            "thinking_level": "low",
            "max_output_tokens": 800,
        },
    )
    text = (getattr(resp, "output_text", "") or "").strip()

    return ChatAnswer(
        answer=text[:2000] or "I couldn't come up with an answer to that -- try rephrasing?",
        model_used=model,
    )
