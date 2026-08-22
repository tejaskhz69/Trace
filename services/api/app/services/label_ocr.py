"""Read a nutrition label off a photo of the package.

WHY THIS MATTERS MORE THAN IT SOUNDS
The barcode path only works if someone already put that barcode in a database.
For a local Indian brand, a supermarket own-label in a small market, or
anything bought outside the countries Open Food Facts covers well, the scan
fails and the user is left typing eleven numbers off the back of a packet.
That is the moment people stop logging.

The label itself, though, is always there. Reading it is a bounded, verifiable
task — unlike estimating a plate of food from a photo, the right answer is
literally printed on the box.

THIS IS THE OPPOSITE OF THE PLATE SCANNER, AND THE UNCERTAINTY RULE FLIPS
`vision.recognize` estimates, so it must return a range and the UI must show
`±`. This function TRANSCRIBES, so a range would be nonsense — the number is
printed. What it must do instead is refuse: when a field is unreadable it
returns None rather than a plausible guess, because a hallucinated "12 g
protein" that looks exactly like a real reading is far worse than a blank the
user fills in.

    plate photo  -> estimate + band    (never a single confident number)
    label photo  -> transcription      (never an invented number)

EVERYTHING IS VALIDATED BEFORE IT IS OFFERED
The panel goes through `nutrition_validator` exactly like an imported row.
Labels are misprinted, mis-transcribed, and sometimes state per-serving values
under a "per 100 g" heading. If the macros cannot account for the calories,
the user is told the reading looks wrong rather than being handed it.

PER-SERVING VS PER-100G IS THE CLASSIC TRAP
US labels are per serving; EU labels are per 100 g and usually both. Getting
this wrong scales every number by the serving size, silently, and the error is
invisible in the result. So the model must report which basis it read, and we
convert to per-100 g ourselves rather than trusting it to do the arithmetic.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..config import get_settings
from .nutrition_validator import Verdict, validate

log = logging.getLogger(__name__)
settings = get_settings()

# A serving smaller or larger than this is almost certainly a misread decimal
# point, not a real portion.
MIN_SERVING_G = 1.0
MAX_SERVING_G = 2000.0

SYSTEM_PROMPT = """\
You transcribe nutrition information panels from photographs of food
packaging. You are reading printed text, not estimating.

RULES
- Report ONLY what is printed. If a value is blurred, cropped, obscured or
  simply absent from the label, return null for that field. NEVER infer a
  value from the other numbers, and never fill a gap with a typical value for
  that kind of food.
- `basis` says which column you read: "100g" for a per-100-g or per-100-ml
  column, "serving" for a per-serving column. If the label shows both, READ
  THE PER-100G COLUMN and set basis to "100g".
- `serving_size_g` is the stated serving in grams or millilitres, if printed.
- Energy: prefer the kcal figure. If only kJ is printed, report the kJ value
  in `energy_kj` and leave `calories` null -- do not convert.
- Sodium and salt are different fields and are NOT interchangeable. Report
  whichever the label prints, in its own field.
- `product_name` and `brand` come from the front of the pack if visible;
  null if you cannot read them.
- Set `legible` to false if the panel is too blurred, angled or dark to read
  reliably. A refusal is a correct answer here.
- `confidence` is your real belief that you read the digits correctly. Glare
  on foil, a curved surface, or a low-resolution crop should lower it.

Call the `read_label` tool exactly once. Never write prose.
"""

TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "name": "read_label",
    "description": "Report the nutrition panel exactly as printed.",
    "parameters": {
        "type": "object",
        "properties": {
            "legible": {"type": "boolean"},
            "basis": {"type": "string", "enum": ["100g", "serving", "unknown"]},
            "serving_size_g": {"type": "number"},
            "product_name": {"type": "string"},
            "brand": {"type": "string"},
            "calories": {"type": "number", "description": "kcal"},
            "energy_kj": {"type": "number"},
            "protein_g": {"type": "number"},
            "carbs_g": {"type": "number"},
            "sugar_g": {"type": "number"},
            "fat_g": {"type": "number"},
            "saturated_fat_g": {"type": "number"},
            "fiber_g": {"type": "number"},
            "sodium_mg": {"type": "number"},
            "salt_g": {"type": "number"},
            "confidence": {"type": "number"},
            "notes": {"type": "string"},
        },
        "required": ["legible", "basis", "confidence"],
    },
}

# Salt to sodium. Salt is sodium chloride; sodium is 39.34% of it by mass.
# EU labels print salt, US labels print sodium, and treating them as the same
# number over-states sodium by 2.5x.
SALT_G_TO_SODIUM_MG = 393.4

KJ_PER_KCAL = 4.184


@dataclass
class LabelReading:
    legible: bool
    basis: str
    per_100g: dict[str, float | None]
    serving_size_g: float | None
    product_name: str | None
    brand: str | None
    confidence: float
    quality: float
    verdict: str
    warnings: list[str] = field(default_factory=list)
    model_used: str = ""
    latency_ms: int = 0


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # Negative nutrition is a misread minus sign or a stray character.
    return f if f >= 0 else None


def to_per_100g(raw: dict[str, Any]) -> tuple[dict[str, float | None], list[str]]:
    """Normalise a reading onto a per-100-g basis.

    WE DO THE ARITHMETIC, NOT THE MODEL. Asking it to convert introduces a
    silent multiplicative error into every field at once, and the result still
    looks like a perfectly ordinary nutrition panel. Doing it here means the
    conversion is one line that can be tested.
    """
    warnings: list[str] = []

    kcal = _num(raw.get("calories"))
    if kcal is None:
        kj = _num(raw.get("energy_kj"))
        if kj is not None:
            kcal = round(kj / KJ_PER_KCAL, 1)
            warnings.append("Only kilojoules were printed; converted to kcal.")

    sodium = _num(raw.get("sodium_mg"))
    if sodium is None:
        salt = _num(raw.get("salt_g"))
        if salt is not None:
            sodium = round(salt * SALT_G_TO_SODIUM_MG, 1)
            warnings.append("Label printed salt; converted to sodium.")

    panel: dict[str, float | None] = {
        "calories": kcal,
        "protein_g": _num(raw.get("protein_g")),
        "carbs_g": _num(raw.get("carbs_g")),
        "sugar_g": _num(raw.get("sugar_g")),
        "fat_g": _num(raw.get("fat_g")),
        "saturated_fat_g": _num(raw.get("saturated_fat_g")),
        "fiber_g": _num(raw.get("fiber_g")),
        "sodium_mg": sodium,
    }

    basis = str(raw.get("basis") or "unknown").lower()
    serving = _num(raw.get("serving_size_g"))

    if basis == "serving":
        if serving is None or not (MIN_SERVING_G <= serving <= MAX_SERVING_G):
            # Per-serving numbers with no serving size cannot be normalised.
            # Handing them back labelled "per 100 g" would be wrong by an
            # unknown factor, so we refuse the conversion and say so.
            warnings.append(
                "The label was read per serving but no usable serving size was "
                "printed, so these numbers could not be put on a per-100 g "
                "basis. Check them before saving."
            )
            return panel, warnings
        factor = 100.0 / serving
        panel = {k: (round(v * factor, 2) if v is not None else None) for k, v in panel.items()}
        warnings.append(
            f"Label was per {serving:g} g serving; scaled to per 100 g."
        )
    elif basis == "unknown":
        warnings.append(
            "Could not tell whether the panel was per 100 g or per serving. "
            "Check the numbers against the packet."
        )

    return panel, warnings


def assess(raw: dict[str, Any]) -> LabelReading:
    """Turn a raw model reading into something safe to offer the user."""
    legible = bool(raw.get("legible", False))
    confidence = _num(raw.get("confidence")) or 0.0
    panel, warnings = to_per_100g(raw)

    if raw.get("notes"):
        warnings.append(str(raw["notes"]))

    # Validate exactly like an imported row. A label can be misprinted, and a
    # panel whose macros cannot account for its calories is not usable data
    # regardless of how confidently it was read.
    checked = validate(
        {k: v for k, v in panel.items() if v is not None},  # type: ignore[arg-type]
        source_quality=0.9 if legible else 0.4,
    )
    if checked.verdict is Verdict.quarantine:
        warnings.append(
            "These numbers do not add up — the macros cannot account for the "
            "stated calories. Re-shoot the label straight on, or type them in."
        )
    for issue in checked.issues[:3]:
        warnings.append(issue.message)

    if not legible:
        warnings.insert(0, "The panel was too unclear to read reliably.")

    return LabelReading(
        legible=legible,
        basis=str(raw.get("basis") or "unknown").lower(),
        per_100g=panel,
        serving_size_g=_num(raw.get("serving_size_g")),
        product_name=(str(raw.get("product_name")).strip() or None)
        if raw.get("product_name")
        else None,
        brand=(str(raw.get("brand")).strip() or None) if raw.get("brand") else None,
        confidence=confidence,
        quality=checked.quality_score,
        verdict=checked.verdict.value,
        warnings=warnings,
    )


async def read_label(image: bytes) -> LabelReading:
    """Photo of a nutrition panel in, a transcription out.

    Uses the ACCURATE model, unlike the plate scanner's fast pass. The
    trade-off is different: a plate scan is one of several a day and the user
    is standing over their food waiting, so latency wins. A label is scanned
    once per product ever and the result is written into a database other
    people will use, so getting the digits right wins.
    """
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    from .vision import _client, prepare_image  # noqa: PLC2701

    payload_bytes, mime, _ = prepare_image(image)
    client = _client()
    model = settings.VISION_MODEL_ACCURATE
    started = time.perf_counter()

    import base64

    resp = await client.aio.interactions.create(
        model=model,
        system_instruction=SYSTEM_PROMPT,
        input=[
            {
                "type": "image",
                "data": base64.standard_b64encode(payload_bytes).decode("ascii"),
                "mime_type": mime,
            }
        ],
        tools=[TOOL_SCHEMA],
        generation_config={"max_output_tokens": 1024, "tool_choice": "any"},
    )

    raw: dict[str, Any] = {}
    for step in getattr(resp, "steps", []) or []:
        if getattr(step, "type", None) == "function_call":
            args = step.arguments
            raw = json.loads(args) if isinstance(args, str) else (args or {})
            break

    reading = assess(raw)
    reading.model_used = model
    reading.latency_ms = int((time.perf_counter() - started) * 1000)
    return reading
