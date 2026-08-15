"""Meal logging and daily summaries."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import BodyComposition, FoodItem, MealLog, User
from ..schemas import DailySummary, MealLogPublic, MealLogRequest
from .auth import current_user

router = APIRouter(prefix="/api/meals", tags=["meals"])


@router.post("/log", response_model=MealLogPublic, status_code=201)
async def log_meal(
    payload: MealLogRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> MealLogPublic:
    """Log a meal.

    Nutrition is snapshotted at log time rather than referenced. If a food's
    nutrition data is later corrected upstream, a user's history must not
    silently rewrite itself -- that destroys trust in the weekly report.
    """
    if payload.food_item_id:
        food = await session.get(FoodItem, payload.food_item_id)
        if food is None:
            raise HTTPException(status_code=404, detail="Food item not found.")

        factor = payload.grams / 100.0
        entry = MealLog(
            user_id=user.id,
            food_item_id=food.id,
            display_name=food.name if not food.brand else f"{food.brand} {food.name}",
            grams=payload.grams,
            serving_label=payload.serving_label,
            calories=round(food.calories * factor, 1),
            protein_g=round(food.protein_g * factor, 2),
            carbs_g=round(food.carbs_g * factor, 2),
            fat_g=round(food.fat_g * factor, 2),
            fiber_g=round(food.fiber_g * factor, 2),
            meal_type=payload.meal_type,
            logged_at=payload.logged_at or datetime.now(timezone.utc),
            recognition_id=payload.recognition_id,
        )
        # Popularity drives search ranking.
        await session.execute(
            update(FoodItem)
            .where(FoodItem.id == food.id)  # type: ignore[arg-type]
            .values(log_count=FoodItem.log_count + 1)
        )
    else:
        if payload.calories is None or not payload.display_name:
            raise HTTPException(
                status_code=400,
                detail="Provide either food_item_id, or display_name + calories.",
            )
        entry = MealLog(
            user_id=user.id,
            display_name=payload.display_name,
            grams=payload.grams,
            serving_label=payload.serving_label,
            calories=payload.calories,
            protein_g=payload.protein_g or 0,
            carbs_g=payload.carbs_g or 0,
            fat_g=payload.fat_g or 0,
            meal_type=payload.meal_type,
            logged_at=payload.logged_at or datetime.now(timezone.utc),
            recognition_id=payload.recognition_id,
        )

    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return MealLogPublic.model_validate(entry, from_attributes=True)


@router.get("/daily", response_model=DailySummary)
async def daily_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    on: date = Query(default_factory=date.today, alias="date"),
) -> DailySummary:
    start = datetime.combine(on, time.min, tzinfo=timezone.utc)
    end = datetime.combine(on, time.max, tzinfo=timezone.utc)

    rows = (
        await session.execute(
            select(MealLog)
            .where(
                MealLog.user_id == user.id,
                MealLog.logged_at >= start,
                MealLog.logged_at <= end,
            )
            .order_by(MealLog.logged_at)  # type: ignore[arg-type]
        )
    ).scalars().all()

    latest_target = await session.scalar(
        select(BodyComposition)
        .where(BodyComposition.user_id == user.id)
        .order_by(BodyComposition.week_start.desc())  # type: ignore[union-attr]
    )

    return DailySummary(
        date=on,
        calories=round(sum(r.calories for r in rows), 1),
        protein_g=round(sum(r.protein_g for r in rows), 1),
        carbs_g=round(sum(r.carbs_g for r in rows), 1),
        fat_g=round(sum(r.fat_g for r in rows), 1),
        fiber_g=round(sum(r.fiber_g for r in rows), 1),
        calorie_target=latest_target.calorie_target if latest_target else None,
        protein_target_g=latest_target.protein_target_g if latest_target else None,
        carb_target_g=latest_target.carb_target_g if latest_target else None,
        fat_target_g=latest_target.fat_target_g if latest_target else None,
        fiber_target_g=latest_target.fiber_target_g if latest_target else None,
        meals=[MealLogPublic.model_validate(r, from_attributes=True) for r in rows],
    )


@router.delete("/{meal_id}", status_code=204)
async def delete_meal(
    meal_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> None:
    entry = await session.get(MealLog, meal_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=404, detail="Meal not found.")
    await session.delete(entry)
    await session.commit()
