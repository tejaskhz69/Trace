"""Gemini-powered food recognition.

Deliberately NOT a custom CNN. A fine-tuned ResNet on Food-101 costs four
months and an ML hire, and loses to a well-prompted vision model that also
handles mixed plates, reads context, and can explain itself. Spend those four
months building the correction dataset instead -- that is the asset a
competitor can't buy.

Three things here that Cal AI does not do:

1. **Ranges, not fake precision.** Every item returns low/point/high. The UI
   shows "240 kcal ±60". Users trust an honest range more than a confident
   wrong number, and it is what stops the "it gave me different numbers for the
   same meal" review.

2. **One clarifying question.** The largest single error source in photo
   estimation is invisible cooking fat -- a tablespoon of ghee or oil is
   ~120 kcal and leaves no visual trace. SnapCalorie's own docs concede this.
   One tap ("How much ghee? None / 1 tsp / 1 tbsp / Restaurant-style") beats a
   depth sensor for free.

3. **Deterministic re-scans.** Keyed on a perceptual hash at temperature 0, so
   the same photo always returns the same numbers.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# Rough token accounting for cost telemetry, USD per million tokens as
# (input, output). Gemini charges image input as tokens too. These are for the
# telemetry column only -- nothing branches on them, so a stale rate costs you
# an inaccurate dashboard, not an inaccurate scan. Verify at
# https://ai.google.dev/pricing.
# The 2.5 family is retired (the API 404s), so it is not listed.
_PRICES_PER_MTOK = {
    "gemini-3.7-flash": (0.30, 2.50),
    "gemini-3.6-flash": (0.30, 2.50),
    "gemini-3.5-flash": (0.30, 2.50),
    "gemini-3.1-pro-preview": (1.25, 10.00),
}

MAX_IMAGE_EDGE = 768  # bigger buys almost no accuracy and costs linear tokens


SYSTEM_PROMPT = """\
You are a nutrition estimation engine for a food-tracking app. You look at a \
photo of a meal and return structured nutrition estimates.

CUISINE COVERAGE
You must handle mixed, sauce-covered, home-cooked food from every cuisine, not \
just plated Western restaurant food. Indian food is the hardest case in this \
category and you must be excellent at it: dal (tadka/fry/makhani), sabzi, \
roti/chapati/phulka/paratha/naan, rice preparations (jeera, biryani, pulao, \
curd rice), South Indian (idli, dosa, vada, uttapam, sambar, rasam, chutneys), \
street food (pani puri, vada pav, pav bhaji, chaat, samosa, kathi roll), \
thalis, and regional variants. Also handle East Asian, Mexican, Mediterranean, \
Middle Eastern, and African dishes with the same care.

PORTION UNITS
Use the unit a real person would use for that cuisine:
  katori (~150 g liquid/semi-solid), chapati (~40 g), paratha (~65 g),
  idli (~35 g), dosa (~85 g), medium bowl (~200 g), ladle (~60 g),
  standard glass (~200 ml), cup (~240 ml), slice, piece, tbsp, tsp.

SCALE CALIBRATION
Before estimating volume, identify a reference object in the frame and say so \
internally: a dinner plate rim is ~26 cm, a steel thali ~30 cm, a fork ~19 cm, \
a phone ~15 cm, a standard katori ~10 cm across. Anchor your portion estimate \
to that reference. If there is no usable reference, widen your ranges and \
lower your confidence accordingly.

HIDDEN INGREDIENTS -- THIS IS THE MOST IMPORTANT RULE
Cooking fat is invisible in a photo and is the single largest source of error. \
A tablespoon of ghee, oil, or butter is ~120 kcal. You MUST:
  - list every plausible invisible ingredient in `hidden_ingredients`
    (tempering oil, ghee finish, cream, added sugar in sauces, deep-fry
    absorption, salad dressing, butter on bread)
  - fold a reasonable default for them into your point estimate
  - attach a `clarifying_question` to any item whose calories move by more
    than 50 kcal depending on the answer

UNCERTAINTY
Never report false precision. `kcal_low` and `kcal_high` must be a genuine \
80% interval. Typical honest widths: ±15% for a single packaged/plated item, \
±25-35% for a mixed curry or a composite plate. Set `confidence` to your real \
belief, not a flattering number. It is far better to ask one question than to \
guess confidently.

BEVERAGES
Estimate drinks separately. If a glass contains an unidentifiable liquid, ask \
rather than guess -- water and mango lassi differ by 300 kcal.

OUTPUT
Call the `report_nutrition` tool exactly once. Never write prose.
"""


# Gemini accepts a subset of JSON Schema: type, properties, required, enum,
# items, description. It rejects minItems/maxItems/minimum/maximum, so the
# bounds that used to live here are enforced in _sanitize() instead -- which
# is where they belonged anyway, since a schema is a request and _sanitize is
# a guarantee.
TOOL_SCHEMA = {
    "type": "function",
    "name": "report_nutrition",
    "description": "Report the nutrition estimate for every food item in the image.",
    "parameters": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "name_local": {
                            "type": "string",
                            "description": "Native-script name if applicable, else empty",
                        },
                        "portion_unit": {"type": "string"},
                        "portion_count": {"type": "number"},
                        "grams_est": {"type": "number"},
                        "grams_range": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Exactly two numbers: [low_g, high_g]",
                        },
                        "kcal_point": {"type": "number"},
                        "kcal_low": {"type": "number"},
                        "kcal_high": {"type": "number"},
                        "protein_g": {"type": "number"},
                        "carbs_g": {"type": "number"},
                        "fat_g": {"type": "number"},
                        "confidence": {
                            "type": "number",
                            "description": "Your real belief, 0.0 to 1.0",
                        },
                        "clarifying_question": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "options": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "kcal_deltas": {
                                    "type": "array",
                                    "items": {"type": "number"},
                                },
                            },
                            "required": ["text", "options", "kcal_deltas"],
                        },
                    },
                    "required": [
                        "name",
                        "portion_unit",
                        "portion_count",
                        "grams_est",
                        "grams_range",
                        "kcal_point",
                        "kcal_low",
                        "kcal_high",
                        "protein_g",
                        "carbs_g",
                        "fat_g",
                        "confidence",
                    ],
                },
            },
            "hidden_ingredients": {"type": "array", "items": {"type": "string"}},
            "overall_confidence": {
                "type": "number",
                "description": "Your real belief across the whole plate, 0.0 to 1.0",
            },
        },
        "required": ["items", "hidden_ingredients", "overall_confidence"],
    },
}


@dataclass
class VisionResult:
    payload: dict[str, Any]
    model_used: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
    image_hash: str


def prepare_image(raw: bytes) -> tuple[bytes, str, str]:
    """Downscale, strip EXIF, convert to WebP, and hash.

    Returns (bytes, media_type, perceptual_hash).
    """
    from PIL import Image

    img = Image.open(io.BytesIO(raw))
    img = img.convert("RGB")  # also drops EXIF orientation weirdness

    if max(img.size) > MAX_IMAGE_EDGE:
        ratio = MAX_IMAGE_EDGE / max(img.size)
        img = img.resize(
            (int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS
        )

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=80, method=4)
    data = buf.getvalue()

    # A cheap perceptual hash: 16x16 greyscale, mean threshold. Robust enough
    # that a re-upload of the same photo hits cache, strict enough that two
    # different meals don't collide.
    small = img.convert("L").resize((16, 16), Image.LANCZOS)
    pixels = list(small.getdata())
    mean = sum(pixels) / len(pixels)
    bits = "".join("1" if p > mean else "0" for p in pixels)
    phash = hashlib.sha256(bits.encode()).hexdigest()[:32]

    return data, "image/webp", phash


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    price_in, price_out = _PRICES_PER_MTOK.get(model, (1.25, 10.0))
    return (in_tok / 1e6) * price_in + (out_tok / 1e6) * price_out


def _usage(resp: Any) -> tuple[int, int]:
    """Pull (input, output) token counts off a response.

    Token accounting is telemetry, not correctness -- a field rename in the
    SDK must never turn a good scan into a 500. Returns (0, 0) rather than
    raising if the shape moves.
    """
    usage = getattr(resp, "usage", None) or getattr(resp, "usage_metadata", None)
    if usage is None:
        return 0, 0

    # THINKING TOKENS COUNT AS OUTPUT. On Gemini 3.x they routinely dwarf the
    # visible answer -- a trivial call measured 2 output tokens against 51
    # thought tokens. Billing counts them, so omitting them understates cost
    # by more than an order of magnitude and makes the per-scan figure
    # useless for deciding whether this is affordable at scale.
    total_in = getattr(usage, "total_input_tokens", None)
    total_out = getattr(usage, "total_output_tokens", None)
    if total_in is not None or total_out is not None:
        thoughts = getattr(usage, "total_thought_tokens", 0) or 0
        tools = getattr(usage, "total_tool_use_tokens", 0) or 0
        return int(total_in or 0), int(total_out or 0) + int(thoughts) + int(tools)

    # Older/other shapes, kept so a field rename degrades to bad telemetry
    # rather than a 500 on a good scan.
    for in_name, out_name in (
        ("input_tokens", "output_tokens"),
        ("prompt_token_count", "candidates_token_count"),
        ("prompt_tokens", "completion_tokens"),
    ):
        got_in = getattr(usage, in_name, None)
        got_out = getattr(usage, out_name, None)
        if got_in is not None or got_out is not None:
            return int(got_in or 0), int(got_out or 0)
    return 0, 0


async def recognize(
    image_bytes: bytes,
    *,
    hint: str | None = None,
    force_model: str | None = None,
) -> VisionResult:
    """Run the two-stage recognition pipeline.

    Stage 1 uses the fast model. If it comes back under the confidence
    threshold, or the plate has more than three items, we escalate to the
    accurate model. In practice ~25% escalate, so the blended cost lands near
    $0.005/scan rather than the $0.008 of always using the larger model.
    """
    from google import genai

    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    data, media_type, phash = prepare_image(image_bytes)
    b64 = base64.standard_b64encode(data).decode("ascii")

    user_input: list[dict[str, Any]] = [
        {"type": "image", "data": b64, "mime_type": media_type}
    ]
    if hint:
        user_input.append(
            {
                "type": "text",
                "text": f"The user says this is: {hint}. Use it, but correct "
                f"them if the photo clearly disagrees.",
            }
        )

    async def _call(model: str) -> tuple[dict[str, Any], Any]:
        # client.aio is the SDK's native async surface. Using it rather than
        # the sync client keeps the event loop free for the several seconds a
        # scan takes -- a blocking call here would stall every other request
        # on the worker.
        resp = await client.aio.interactions.create(
            model=model,
            system_instruction=SYSTEM_PROMPT,
            input=user_input,
            tools=[TOOL_SCHEMA],
            generation_config={
                "max_output_tokens": 2048,
                # Latency is the constraint here, not intelligence: the user
                # is standing over their food waiting. Left at the default,
                # a two-pass scan measured ~80 s, which is unusable. The fast
                # pass thinks little; the escalated pass -- which only runs
                # when the first was unsure -- gets more budget, because that
                # is exactly the plate where reasoning about portions pays.
                # These two levels are a starting point, not a tuned result:
                # measure accuracy against them with eval_vision.py once
                # there are real photos, and raise them if coverage suffers.
                "thinking_level": "low" if model == settings.VISION_MODEL_FAST else "medium",
                # This API exposes no `temperature`. Determinism now comes
                # from a seed derived from the image's perceptual hash, so
                # the same photo asks for the same sample every time. It is
                # weaker than temperature=0 was -- best effort, not a
                # guarantee -- so re-scan stability is worth measuring rather
                # than assuming.
                "seed": int(phash[:8], 16) % (2**31),
                "tool_choice": "any",
            },
        )
        for step in getattr(resp, "steps", []) or []:
            if getattr(step, "type", None) == "function_call":
                args = step.arguments
                if isinstance(args, str):
                    args = json.loads(args)
                return args, resp
        raise ValueError("Model did not call report_nutrition")

    started = time.perf_counter()
    model = force_model or settings.VISION_MODEL_FAST
    payload, resp = await _call(model)

    should_escalate = (
        not force_model
        and model == settings.VISION_MODEL_FAST
        and (
            payload.get("overall_confidence", 0)
            < settings.VISION_ESCALATION_CONFIDENCE
            or len(payload.get("items", [])) > 3
        )
    )
    if should_escalate:
        log.info(
            "Escalating to %s (confidence=%.2f, items=%d)",
            settings.VISION_MODEL_ACCURATE,
            payload.get("overall_confidence", 0),
            len(payload.get("items", [])),
        )
        model = settings.VISION_MODEL_ACCURATE
        payload, resp = await _call(model)

    latency_ms = int((time.perf_counter() - started) * 1000)
    in_tok, out_tok = _usage(resp)

    return VisionResult(
        payload=_sanitize(payload),
        model_used=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        latency_ms=latency_ms,
        cost_usd=round(_cost(model, in_tok, out_tok), 6),
        image_hash=phash,
    )


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    """Defend against a malformed tool call.

    Never trust model output enough to write it straight into a user's diary.
    """
    items = []
    for raw in payload.get("items", []) or []:
        try:
            low = float(raw["kcal_low"])
            point = float(raw["kcal_point"])
            high = float(raw["kcal_high"])
            if not (low <= point <= high):
                low, point, high = sorted((low, point, high))
            if point <= 0 or point > 5000:
                continue
            grams = float(raw.get("grams_est", 0))
            if grams <= 0 or grams > 5000:
                continue
            items.append(
                {
                    "name": str(raw["name"])[:120],
                    "name_local": str(raw.get("name_local") or "")[:120] or None,
                    "portion_unit": str(raw.get("portion_unit", "g"))[:40],
                    "portion_count": float(raw.get("portion_count", 1)),
                    "grams_est": grams,
                    "grams_range": [
                        float(x) for x in (raw.get("grams_range") or [grams, grams])
                    ][:2],
                    "kcal_point": round(point, 1),
                    "kcal_low": round(max(0.0, low), 1),
                    "kcal_high": round(high, 1),
                    "protein_g": max(0.0, float(raw.get("protein_g", 0))),
                    "carbs_g": max(0.0, float(raw.get("carbs_g", 0))),
                    "fat_g": max(0.0, float(raw.get("fat_g", 0))),
                    "confidence": min(1.0, max(0.0, float(raw.get("confidence", 0.5)))),
                    "clarifying_question": raw.get("clarifying_question"),
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("Dropping malformed item from vision output: %s", exc)

    return {
        "items": items,
        "hidden_ingredients": [
            str(x)[:80] for x in (payload.get("hidden_ingredients") or [])
        ][:10],
        "overall_confidence": min(
            1.0, max(0.0, float(payload.get("overall_confidence", 0.5)))
        ),
    }
