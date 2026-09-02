"""Photo food recognition endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..config import get_settings
from ..db import get_session
from ..models import Recognition, RecognitionFeedback, User
from ..schemas import RecognitionCorrection, RecognitionResponse
from ..services import image_quality, label_ocr, vision
from .auth import current_user

router = APIRouter(prefix="/api/foods", tags=["recognition"])
settings = get_settings()

MAX_UPLOAD_BYTES = 12 * 1024 * 1024


@router.post("/recognize", response_model=RecognitionResponse)
async def recognize_food(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    image: UploadFile = File(...),
    hint: str | None = Form(default=None),
) -> RecognitionResponse:
    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image upload.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 12 MB).")

    # --- Image quality, BEFORE the quota is spent ------------------------
    #
    # ORDER MATTERS. This sits above the free-tier check on purpose: a photo
    # of a dark worktop must not consume one of three daily scans. Charging
    # someone a scan to be told "too dark, try again" is the worst possible
    # arrangement of these two gates.
    #
    # Only REJECT stops the request -- frames with nothing in them, too small
    # to resolve print, or undecodable. Dark, washed-out and soft-focus images
    # are MARGINAL and go to the model anyway: the estimate returns with lower
    # confidence and the existing band-widening handles it, which beats
    # refusing a photo a person could read. See services/image_quality.py for
    # why every threshold leans that way.
    quality = image_quality.assess_image(raw)
    if not quality.should_upload:
        raise HTTPException(
            status_code=422,
            detail={
                "message": quality.message,
                "reasons": list(quality.reasons),
                # Scalar statistics only. Never the image, never a crop.
                "stats": quality.stats,
                "retryable": True,
            },
        )

    # --- Free tier quota -------------------------------------------------
    if not user.is_pro:
        since = datetime.now(UTC) - timedelta(days=1)
        used = await session.scalar(
            select(func.count(Recognition.id)).where(
                Recognition.user_id == user.id, Recognition.created_at >= since
            )
        )
        if (used or 0) >= settings.FREE_TIER_SCANS_PER_DAY:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"You've used your {settings.FREE_TIER_SCANS_PER_DAY} free "
                    "scans today. Barcode and search are still unlimited — or "
                    "go Pro for unlimited scans."
                ),
            )

    # --- Deterministic cache --------------------------------------------
    # Same photo -> same numbers, always. This alone fixes the single most
    # common complaint about photo trackers ("it gives me different calories
    # every time I scan the same meal").
    _, _, phash = vision.prepare_image(raw)
    cached = await session.scalar(
        select(Recognition)
        .where(Recognition.user_id == user.id, Recognition.image_hash == phash)
        .order_by(Recognition.created_at.desc())  # type: ignore[union-attr]
    )
    if cached:
        return RecognitionResponse(
            recognition_id=cached.id,
            items=cached.raw_output.get("items", []),
            hidden_ingredients=cached.raw_output.get("hidden_ingredients", []),
            overall_confidence=cached.overall_confidence,
            model_used=cached.model_used,
            latency_ms=0,
            cached=True,
            review_required=bool(cached.raw_output.get("review_required")),
        )

    try:
        result = await vision.recognize(raw, hint=hint)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Couldn't read that photo. Try again, or log it manually.",
        ) from exc

    record = Recognition(
        user_id=user.id,
        image_hash=result.image_hash,
        model_used=result.model_used,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        overall_confidence=result.payload["overall_confidence"],
        raw_output=result.payload,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    return RecognitionResponse(
        recognition_id=record.id,
        items=result.payload["items"],
        hidden_ingredients=result.payload["hidden_ingredients"],
        overall_confidence=result.payload["overall_confidence"],
        model_used=result.model_used,
        latency_ms=result.latency_ms,
        cached=False,
        review_required=bool(result.payload.get("review_required")),
    )


@router.post("/recognize/{recognition_id}/correct", status_code=201)
async def correct_recognition(
    recognition_id: str,
    payload: RecognitionCorrection,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    """Capture a user's correction.

    THIS IS THE MOST VALUABLE ENDPOINT IN THE PRODUCT. Every row here is a
    labelled example of exactly the food your users actually eat, corrected by
    the person who ate it. After six months this is a proprietary dataset that
    no competitor can buy or scrape, and it is what lets you few-shot the
    prompt with your own hardest cases (and, eventually, justify a custom
    model). Ship this in week one, not week forty.
    """
    rec = await session.get(Recognition, recognition_id)
    if rec is None or rec.user_id != user.id:
        raise HTTPException(status_code=404, detail="Recognition not found.")

    feedback = RecognitionFeedback(
        recognition_id=rec.id,
        user_id=user.id,
        ai_output=rec.raw_output,
        user_correction={
            "items": payload.corrected_items,
            "notes": payload.notes,
        },
        correction_type=payload.correction_type,
    )
    session.add(feedback)
    await session.commit()
    return {"status": "recorded", "id": feedback.id}


@router.post("/read-label")
async def read_nutrition_label(
    user: Annotated[User, Depends(current_user)],
    image: UploadFile = File(...),
) -> dict:
    """Photograph the nutrition panel; get the numbers typed for you.

    WHY THIS EXISTS ALONGSIDE THE BARCODE SCANNER
    A barcode only resolves if somebody already put that product in a
    database. For a local Indian brand, a small-market own-label, or anything
    from a country Open Food Facts covers thinly, the scan misses and the user
    faces eleven numbers on the back of a packet. That is the moment people
    stop logging. The label is always there, and reading it is a bounded task
    with a printed right answer.

    NOTE THE INVERTED UNCERTAINTY RULE. `/recognize` estimates a plate and so
    must return a range (non-negotiable #2). This TRANSCRIBES, so a range
    would be meaningless -- the number is printed on the box. What it does
    instead is refuse: an unreadable field comes back null, never a plausible
    guess, and the client renders the blank for the user to fill.
    """
    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image upload.")

    try:
        reading = await label_ocr.read_label(raw)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "legible": reading.legible,
        "basis": reading.basis,
        "per_100g": reading.per_100g,
        "serving_size_g": reading.serving_size_g,
        "product_name": reading.product_name,
        "brand": reading.brand,
        "confidence": reading.confidence,
        "quality": reading.quality,
        "verdict": reading.verdict,
        "warnings": reading.warnings,
        "model": reading.model_used,
        "latency_ms": reading.latency_ms,
        # A quarantined panel is offered for CORRECTION, never for one-tap
        # saving. The client must keep the save disabled until the user has
        # looked at the numbers the validator objected to.
        "safe_to_save": reading.legible and reading.verdict != "quarantine",
    }
