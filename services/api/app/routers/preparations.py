"""As-prepared conversion endpoints.

The logging flow this enables:

  1. User scans MTR Rava Idli Mix -> we return the food AND the fact that it
     has a known preparation (`preparation_key: "rava_idli"`).
  2. Instead of asking "how many grams of dry mix?" (which nobody knows), the
     app asks "how many idlis?" and offers to adjust the curd and oil.
  3. We convert and log the real numbers.

That is a materially better logging experience AND a materially more accurate
one, from the same data. No competitor does either half.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import FoodItem, User
from ..services.preparation import (
    INGREDIENTS,
    PREPARATIONS,
    Nutrients,
    dilution_factor,
    prepare,
)
from .auth import current_user

router = APIRouter(prefix="/api/preparations", tags=["preparations"])


class PreparationSummary(BaseModel):
    key: str
    display_name: str
    reference_batch_g: float
    transform: str
    pieces: int | None
    piece_name: str
    dilution_factor: float
    adjustable_ingredients: list[dict[str, Any]]
    source_note: str


class PrepareRequest(BaseModel):
    food_item_id: str
    preparation_key: str | None = Field(
        default=None,
        description="Defaults to the key stored on the food item.",
    )
    dry_mix_g: float | None = Field(default=None, gt=0, le=5000)
    overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Grams per added ingredient, e.g. {'oil': 10}",
    )


class PreparedNutrition(BaseModel):
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    sugar_g: float
    sodium_mg: float


class PrepareResponse(BaseModel):
    display_name: str
    prepared_weight_g: float
    per_100g: PreparedNutrition
    total: PreparedNutrition
    pieces: int | None
    grams_per_piece: float | None
    per_piece: PreparedNutrition | None
    breakdown: dict[str, float]
    notes: list[str]
    dilution_factor: float
    warning: str


def _to_model(n: Nutrients) -> PreparedNutrition:
    return PreparedNutrition(
        kcal=n.kcal, protein_g=n.protein_g, carbs_g=n.carbs_g,
        fat_g=n.fat_g, fiber_g=n.fiber_g, sugar_g=n.sugar_g,
        sodium_mg=n.sodium_mg,
    )


@router.get("", response_model=list[PreparationSummary])
async def list_preparations(
    user: Annotated[User, Depends(current_user)],
) -> list[PreparationSummary]:
    return [
        PreparationSummary(
            key=spec.key,
            display_name=spec.display_name,
            reference_batch_g=spec.dry_mix_g,
            transform=spec.transform.value,
            pieces=spec.pieces,
            piece_name=spec.piece_name,
            dilution_factor=round(dilution_factor(spec), 2),
            adjustable_ingredients=[
                {
                    "ingredient": a.ingredient,
                    "default_grams": a.grams,
                    "note": a.note,
                    "kcal_per_100g": INGREDIENTS[a.ingredient].kcal
                    if a.ingredient in INGREDIENTS
                    else None,
                }
                for a in spec.added
                if a.user_adjustable
            ],
            source_note=spec.source_note,
        )
        for spec in PREPARATIONS.values()
    ]


@router.post("/convert", response_model=PrepareResponse)
async def convert(
    payload: PrepareRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> PrepareResponse:
    """Convert a dry-mix food item into the finished dish."""
    food = await session.get(FoodItem, payload.food_item_id)
    if food is None:
        raise HTTPException(status_code=404, detail="Food item not found.")

    key = payload.preparation_key or (food.names_i18n or {}).get("preparation_key")
    if not key:
        raise HTTPException(
            status_code=400,
            detail=(
                "This food has no known preparation. Log it directly, or "
                "pass a preparation_key from GET /api/preparations."
            ),
        )

    spec = PREPARATIONS.get(key)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown preparation {key!r}.")

    unknown = set(payload.overrides) - {a.ingredient for a in spec.added}
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"{spec.display_name} does not use: {', '.join(sorted(unknown))}",
        )

    per_100g = Nutrients(
        kcal=food.calories,
        protein_g=food.protein_g,
        carbs_g=food.carbs_g,
        fat_g=food.fat_g,
        fiber_g=food.fiber_g,
        sugar_g=food.sugar_g,
        sodium_mg=food.sodium_mg,
    )

    result = prepare(
        spec,
        per_100g,
        dry_mix_g=payload.dry_mix_g,
        overrides=payload.overrides or None,
    )
    df = dilution_factor(spec)

    return PrepareResponse(
        display_name=result.display_name,
        prepared_weight_g=result.prepared_weight_g,
        per_100g=_to_model(result.per_100g),
        total=_to_model(result.total),
        pieces=result.pieces,
        grams_per_piece=result.grams_per_piece,
        per_piece=_to_model(result.per_piece) if result.per_piece else None,
        breakdown=result.breakdown,
        notes=result.notes,
        dilution_factor=round(df, 2),
        warning=(
            f"The label on this pack is per 100 g of DRY MIX. Prepared, it "
            f"weighs {df:.1f}x more. Logging the label value against the "
            f"finished dish would overstate your intake by about {df:.1f}x."
        ),
    )
