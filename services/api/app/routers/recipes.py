"""User recipes: build one, keep it private, or publish it.

THE ACCESS RULE, IN ONE LINE
A recipe is readable if you wrote it, or it is published. There is no third
case, and every read path in this file goes through `_load_visible()` so
there is exactly one place that decision is made.

WHAT PUBLISHING MEANS HERE
Immediately visible to everyone, with no moderation queue -- because a queue
nobody staffs is a feature that never ships. What protects the catalogue
instead is that published recipes are gated on `services/recipes.publish_check`
(name, at least two ingredients, macros that can physically produce the stated
calories), and that they live in their OWN table. A published recipe never
enters `food_items`, so it can never become a reference panel for the AI scan
or a search result someone mistakes for verified data.

Un-publishing is allowed and takes effect immediately. Copies other people
already forked stay theirs -- that is what forking means.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import (
    FoodItem,
    MealLog,
    Recipe,
    RecipeIngredient,
    RecipeSave,
    RecipeVisibility,
    User,
)
from ..schemas import (
    MealLogPublic,
    NutritionPanel,
    PublishCheckResponse,
    RecipeIngredientPublic,
    RecipeListResponse,
    RecipeLogRequest,
    RecipePublic,
    RecipeRequest,
    RecipeSummary,
    RecipeVisibilityRequest,
)
from ..services import recipes as rx
from .auth import current_user

router = APIRouter(prefix="/api/recipes", tags=["recipes"])

#: A published recipe is user-generated, so it must never outrank curated or
#: USDA data anywhere the two are shown together. Mirrors the 0.3 that
#: hand-entered custom foods get.
RECIPE_DATA_QUALITY = 0.3

MAX_INGREDIENTS = 60
MAX_STEPS = 40


# ---------------------------------------------------------------------------
# Loading and access
# ---------------------------------------------------------------------------


async def _ingredients(session: AsyncSession, recipe_id: str) -> list[RecipeIngredient]:
    return list(
        (
            await session.execute(
                select(RecipeIngredient)
                .where(RecipeIngredient.recipe_id == recipe_id)
                .order_by(RecipeIngredient.sort_order)  # type: ignore[arg-type]
            )
        )
        .scalars()
        .all()
    )


async def _load_visible(
    session: AsyncSession, recipe_id: str, user: User
) -> tuple[Recipe, bool]:
    """Fetch a recipe the caller is allowed to see, or 404.

    404 rather than 403 for someone else's private recipe: a 403 confirms the
    id exists, which leaks that a particular person has a particular recipe.
    """
    recipe = await session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    is_owner = recipe.user_id == user.id
    if not is_owner and recipe.visibility != RecipeVisibility.published:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    return recipe, is_owner


async def _owned(session: AsyncSession, recipe_id: str, user: User) -> Recipe:
    recipe, is_owner = await _load_visible(session, recipe_id, user)
    if not is_owner:
        raise HTTPException(status_code=403, detail="This is not your recipe.")
    return recipe


def _to_ingredient(row: RecipeIngredient) -> rx.Ingredient:
    """DB row -> the pure service's value type."""
    return rx.Ingredient(
        name=row.display_name,
        grams=row.grams,
        food_item_id=row.food_item_id,
        note=row.note,
        per_100g=rx.Panel(
            calories=row.calories,
            protein_g=row.protein_g,
            carbs_g=row.carbs_g,
            fat_g=row.fat_g,
            fiber_g=row.fiber_g,
            sugar_g=row.sugar_g,
            sodium_mg=row.sodium_mg,
            saturated_fat_g=row.saturated_fat_g,
        ),
    )


def _compose(recipe: Recipe, rows: list[RecipeIngredient]) -> rx.Composed:
    return rx.compose(
        [_to_ingredient(r) for r in rows],
        servings=recipe.servings,
        cooked_weight_g=recipe.cooked_weight_g,
    )


def _panel(p: rx.Panel) -> NutritionPanel:
    return NutritionPanel(**p.as_dict())


def _search_text(recipe: Recipe, rows: list[RecipeIngredient]) -> str:
    parts = [recipe.name, recipe.cuisine or "", *(recipe.tags or [])]
    parts.extend(r.display_name for r in rows)
    return " ".join(p for p in parts if p).lower()


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


async def _replace_ingredients(
    session: AsyncSession, recipe: Recipe, payload: RecipeRequest
) -> list[RecipeIngredient]:
    """Rewrite a recipe's ingredient rows from the request.

    Full replace rather than a diff: the client owns the list, the ordering is
    meaningful, and a partial-update protocol for a list this small buys
    nothing but bugs.

    NUTRITION FOR A CATALOGUE INGREDIENT IS READ FROM THE CATALOGUE, never
    from the request body. A client that sends `food_item_id` for chicken plus
    made-up macros gets the real chicken panel.
    """
    if len(payload.ingredients) > MAX_INGREDIENTS:
        raise HTTPException(
            status_code=422,
            detail=f"A recipe can hold at most {MAX_INGREDIENTS} ingredients.",
        )

    await session.execute(
        sa_delete(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id)
    )

    wanted = [i.food_item_id for i in payload.ingredients if i.food_item_id]
    catalogue: dict[str, FoodItem] = {}
    if wanted:
        found = (
            (await session.execute(select(FoodItem).where(FoodItem.id.in_(wanted))))  # type: ignore[attr-defined]
            .scalars()
            .all()
        )
        catalogue = {f.id: f for f in found}

    rows: list[RecipeIngredient] = []
    for order, line in enumerate(payload.ingredients):
        food = catalogue.get(line.food_item_id) if line.food_item_id else None
        if line.food_item_id and food is None:
            raise HTTPException(
                status_code=404,
                detail=f"Ingredient '{line.display_name}' is no longer in the food database.",
            )

        src = food if food is not None else line
        rows.append(
            RecipeIngredient(
                recipe_id=recipe.id,
                # A line whose food row vanished upstream keeps its numbers but
                # loses the link, so the recipe still totals correctly.
                food_item_id=food.id if food else None,
                display_name=line.display_name.strip(),
                grams=line.grams,
                quantity_label=line.quantity_label,
                note=line.note,
                sort_order=order,
                calories=src.calories,
                protein_g=src.protein_g,
                carbs_g=src.carbs_g,
                fat_g=src.fat_g,
                fiber_g=src.fiber_g,
                sugar_g=getattr(src, "sugar_g", 0.0) or 0.0,
                sodium_mg=getattr(src, "sodium_mg", 0.0) or 0.0,
                saturated_fat_g=getattr(src, "saturated_fat_g", 0.0) or 0.0,
            )
        )

    for row in rows:
        session.add(row)
    return rows


def _apply_fields(recipe: Recipe, payload: RecipeRequest) -> None:
    recipe.name = payload.name.strip()
    recipe.description = payload.description
    recipe.cuisine = payload.cuisine
    recipe.photo_url = payload.photo_url
    recipe.servings = payload.servings
    recipe.cooked_weight_g = payload.cooked_weight_g
    recipe.prep_minutes = payload.prep_minutes
    recipe.cook_minutes = payload.cook_minutes
    recipe.steps = [s.strip() for s in payload.steps if s.strip()][:MAX_STEPS]
    recipe.tags = [t.strip().lower() for t in payload.tags if t.strip()][:12]
    recipe.updated_at = datetime.now(UTC)


def _cache_composition(
    recipe: Recipe, composed: rx.Composed, rows: list[RecipeIngredient]
) -> None:
    """Denormalise the composed totals onto the recipe row.

    Purely a read optimisation so the library list does not fan out to every
    recipe's ingredients. The ingredient rows remain the source of truth, and
    every write path in this file calls this immediately after `_compose`.
    """
    recipe.total_calories = composed.total.calories
    recipe.total_protein_g = composed.total.protein_g
    recipe.total_carbs_g = composed.total.carbs_g
    recipe.total_fat_g = composed.total.fat_g
    recipe.total_fiber_g = composed.total.fiber_g
    recipe.total_sugar_g = composed.total.sugar_g
    recipe.total_sodium_mg = composed.total.sodium_mg
    recipe.total_saturated_fat_g = composed.total.saturated_fat_g
    recipe.ingredient_grams = composed.ingredient_grams
    recipe.per_100g_calories = (
        composed.per_100g.calories if composed.per_100g else None
    )
    recipe.sourced_fraction = composed.sourced_fraction
    recipe.search_text = _search_text(recipe, rows)


def _publish_check(
    recipe: Recipe, rows: list[RecipeIngredient], composed: rx.Composed
) -> rx.PublishCheck:
    return rx.publish_check(
        recipe.name,
        [_to_ingredient(r) for r in rows],
        composed,
        steps=recipe.steps or [],
    )


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _public(
    recipe: Recipe,
    rows: list[RecipeIngredient],
    composed: rx.Composed,
    *,
    is_owner: bool,
    is_saved: bool = False,
    author_name: str | None = None,
) -> RecipePublic:
    return RecipePublic(
        id=recipe.id,
        name=recipe.name,
        description=recipe.description,
        cuisine=recipe.cuisine,
        photo_url=recipe.photo_url,
        visibility=recipe.visibility,
        published_at=recipe.published_at,
        servings=recipe.servings,
        cooked_weight_g=recipe.cooked_weight_g,
        yield_estimated=composed.yield_estimated,
        serving_grams=composed.serving_grams,
        prep_minutes=recipe.prep_minutes,
        cook_minutes=recipe.cook_minutes,
        steps=recipe.steps or [],
        tags=recipe.tags or [],
        total=_panel(composed.total),
        per_serving=_panel(composed.per_serving),
        per_100g=_panel(composed.per_100g) if composed.per_100g else None,
        ingredient_grams=composed.ingredient_grams,
        sourced_fraction=composed.sourced_fraction,
        warnings=composed.warnings,
        ingredients=[
            RecipeIngredientPublic.model_validate(r, from_attributes=True) for r in rows
        ],
        is_owner=is_owner,
        is_saved=is_saved,
        author_name=author_name,
        forked_from_id=recipe.forked_from_id,
        save_count=recipe.save_count,
        log_count=recipe.log_count,
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
    )


def _summary(
    recipe: Recipe,
    ingredient_count: int,
    *,
    is_owner: bool,
    is_saved: bool = False,
    author_name: str | None = None,
) -> RecipeSummary:
    """Built from the CACHED columns, not from a fresh compose.

    This is the whole reason those columns exist -- a library of 200 recipes
    would otherwise be 200 ingredient queries.
    """
    servings = recipe.servings or 1.0
    return RecipeSummary(
        id=recipe.id,
        name=recipe.name,
        cuisine=recipe.cuisine,
        photo_url=recipe.photo_url,
        visibility=recipe.visibility,
        servings=servings,
        calories_per_serving=round(recipe.total_calories / servings, 1),
        protein_per_serving_g=round(recipe.total_protein_g / servings, 1),
        ingredient_count=ingredient_count,
        yield_estimated=recipe.cooked_weight_g is None,
        author_name=author_name,
        is_owner=is_owner,
        is_saved=is_saved,
        save_count=recipe.save_count,
        log_count=recipe.log_count,
        updated_at=recipe.updated_at,
    )


async def _counts(session: AsyncSession, ids: list[str]) -> dict[str, int]:
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(RecipeIngredient.recipe_id, func.count())  # type: ignore[arg-type]
            .where(RecipeIngredient.recipe_id.in_(ids))  # type: ignore[attr-defined]
            .group_by(RecipeIngredient.recipe_id)  # type: ignore[arg-type]
        )
    ).all()
    return {r[0]: r[1] for r in rows}


async def _author_names(session: AsyncSession, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(User.id, User.display_name).where(User.id.in_(ids))  # type: ignore[attr-defined]
        )
    ).all()
    return {r[0]: (r[1] or "Someone") for r in rows}


async def _saved_ids(session: AsyncSession, user_id: str, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    rows = (
        await session.execute(
            select(RecipeSave.recipe_id).where(
                RecipeSave.user_id == user_id,
                RecipeSave.recipe_id.in_(ids),  # type: ignore[attr-defined]
            )
        )
    ).scalars().all()
    return set(rows)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=RecipePublic, status_code=201)
async def create_recipe(
    payload: RecipeRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> RecipePublic:
    """Create a recipe, private by default.

    A recipe asking to be born published still has to pass `publish_check` --
    the gate is on the state, not on the transition, so there is no way to
    reach `published` without clearing it.
    """
    recipe = Recipe(user_id=user.id, name=payload.name.strip())
    _apply_fields(recipe, payload)
    session.add(recipe)
    await session.flush()

    rows = await _replace_ingredients(session, recipe, payload)
    composed = _compose(recipe, rows)
    _cache_composition(recipe, composed, rows)

    if payload.visibility == RecipeVisibility.published:
        check = _publish_check(recipe, rows, composed)
        if not check.ok:
            await session.rollback()
            raise HTTPException(
                status_code=422,
                detail=PublishCheckResponse(
                    ok=False, blockers=check.blockers, cautions=check.cautions
                ).model_dump(),
            )
        recipe.visibility = RecipeVisibility.published
        recipe.published_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(recipe)
    return _public(recipe, rows, composed, is_owner=True, author_name=user.display_name)


@router.get("", response_model=RecipeListResponse)
async def my_library(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    scope: str = Query(default="mine", pattern="^(mine|saved|all)$"),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, le=100),
) -> RecipeListResponse:
    """The user's own library.

    `mine` is what they wrote (private and published alike), `saved` is what
    they kept from other people, `all` is both -- which is what the library
    tab shows, because from the user's side "my recipes" means everything on
    their shelf regardless of who cooked it first.
    """
    stmt = select(Recipe)
    if scope == "mine":
        stmt = stmt.where(Recipe.user_id == user.id)
    elif scope == "saved":
        saved = select(RecipeSave.recipe_id).where(RecipeSave.user_id == user.id)
        stmt = stmt.where(Recipe.id.in_(saved))  # type: ignore[attr-defined]
    else:
        saved = select(RecipeSave.recipe_id).where(RecipeSave.user_id == user.id)
        stmt = stmt.where(
            (Recipe.user_id == user.id) | (Recipe.id.in_(saved))  # type: ignore[attr-defined]
        )

    if q:
        stmt = stmt.where(Recipe.search_text.ilike(f"%{q.strip().lower()}%"))  # type: ignore[attr-defined]

    rows = (
        (await session.execute(stmt.order_by(Recipe.updated_at.desc()).limit(limit)))  # type: ignore[union-attr]
        .scalars()
        .all()
    )
    ids = [r.id for r in rows]
    counts = await _counts(session, ids)
    saved_ids = await _saved_ids(session, user.id, ids)
    authors = await _author_names(
        session, [r.user_id for r in rows if r.user_id != user.id]
    )

    return RecipeListResponse(
        recipes=[
            _summary(
                r,
                counts.get(r.id, 0),
                is_owner=r.user_id == user.id,
                is_saved=r.id in saved_ids,
                author_name=authors.get(r.user_id),
            )
            for r in rows
        ],
        total=len(rows),
    )


@router.get("/discover", response_model=RecipeListResponse)
async def discover(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    q: str | None = Query(default=None, max_length=120),
    cuisine: str | None = Query(default=None, max_length=60),
    #: Protein-forward sorting, because "high protein recipes" is the single
    #: most common thing anyone searches a fitness app's recipe list for.
    sort: str = Query(default="popular", pattern="^(popular|recent|protein)$"),
    limit: int = Query(default=30, le=60),
) -> RecipeListResponse:
    """Published recipes from everyone, including the caller's own."""
    stmt = select(Recipe).where(Recipe.visibility == RecipeVisibility.published)

    if q:
        needle = q.strip().lower()
        stmt = stmt.where(Recipe.search_text.ilike(f"%{needle}%"))  # type: ignore[attr-defined]
    if cuisine:
        stmt = stmt.where(Recipe.cuisine == cuisine)

    if sort == "recent":
        stmt = stmt.order_by(Recipe.published_at.desc())  # type: ignore[union-attr]
    elif sort == "protein":
        # Per serving, not per recipe -- otherwise a recipe wins by being big.
        stmt = stmt.order_by(
            (Recipe.total_protein_g / func.greatest(Recipe.servings, 0.25)).desc()
        )
    else:
        stmt = stmt.order_by(Recipe.save_count.desc(), Recipe.log_count.desc())  # type: ignore[union-attr]

    rows = (await session.execute(stmt.limit(limit))).scalars().all()
    ids = [r.id for r in rows]
    counts = await _counts(session, ids)
    saved_ids = await _saved_ids(session, user.id, ids)
    authors = await _author_names(session, [r.user_id for r in rows])

    return RecipeListResponse(
        recipes=[
            _summary(
                r,
                counts.get(r.id, 0),
                is_owner=r.user_id == user.id,
                is_saved=r.id in saved_ids,
                author_name=authors.get(r.user_id),
            )
            for r in rows
        ],
        total=len(rows),
    )


@router.get("/{recipe_id}", response_model=RecipePublic)
async def get_recipe(
    recipe_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> RecipePublic:
    recipe, is_owner = await _load_visible(session, recipe_id, user)
    rows = await _ingredients(session, recipe.id)
    composed = _compose(recipe, rows)
    saved = await _saved_ids(session, user.id, [recipe.id])
    authors = await _author_names(session, [recipe.user_id])
    return _public(
        recipe,
        rows,
        composed,
        is_owner=is_owner,
        is_saved=recipe.id in saved,
        author_name=authors.get(recipe.user_id),
    )


@router.put("/{recipe_id}", response_model=RecipePublic)
async def update_recipe(
    recipe_id: str,
    payload: RecipeRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> RecipePublic:
    """Edit a recipe.

    Editing an already-published recipe re-runs the publish gate: an edit that
    would fail the gate cannot be used as a back door to leaving broken data
    live. The edit is refused rather than silently un-publishing, because
    silently retracting someone's recipe is a worse surprise than a 422.
    """
    recipe = await _owned(session, recipe_id, user)
    was_published = recipe.visibility == RecipeVisibility.published

    _apply_fields(recipe, payload)
    rows = await _replace_ingredients(session, recipe, payload)
    composed = _compose(recipe, rows)
    _cache_composition(recipe, composed, rows)

    if was_published or payload.visibility == RecipeVisibility.published:
        check = _publish_check(recipe, rows, composed)
        if not check.ok:
            await session.rollback()
            raise HTTPException(
                status_code=422,
                detail=PublishCheckResponse(
                    ok=False, blockers=check.blockers, cautions=check.cautions
                ).model_dump(),
            )
        if not was_published:
            recipe.published_at = datetime.now(UTC)
        recipe.visibility = RecipeVisibility.published
    else:
        recipe.visibility = payload.visibility

    await session.commit()
    await session.refresh(recipe)
    return _public(recipe, rows, composed, is_owner=True, author_name=user.display_name)


@router.delete("/{recipe_id}", status_code=204)
async def delete_recipe(
    recipe_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> None:
    """Delete a recipe and everything pointing at it.

    Meals already logged from it are untouched -- MealLog snapshots its
    nutrition and holds no foreign key here, so a user's history survives the
    author deleting the recipe. That is the point of snapshotting.
    """
    recipe = await _owned(session, recipe_id, user)
    await session.execute(
        sa_delete(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id)
    )
    await session.execute(sa_delete(RecipeSave).where(RecipeSave.recipe_id == recipe.id))
    # Forks keep their provenance pointer dangling rather than cascading -- a
    # copy someone made is theirs, and deleting the original must not delete
    # it. Null the link so nothing tries to follow it.
    await session.execute(
        update(Recipe).where(Recipe.forked_from_id == recipe.id).values(forked_from_id=None)  # type: ignore[arg-type]
    )
    await session.delete(recipe)
    await session.commit()


@router.get("/{recipe_id}/publish-check", response_model=PublishCheckResponse)
async def check_publishable(
    recipe_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> PublishCheckResponse:
    """Dry run, so the publish sheet can show what will happen before it happens."""
    recipe = await _owned(session, recipe_id, user)
    rows = await _ingredients(session, recipe.id)
    check = _publish_check(recipe, rows, _compose(recipe, rows))
    return PublishCheckResponse(
        ok=check.ok, blockers=check.blockers, cautions=check.cautions
    )


@router.post("/{recipe_id}/visibility", response_model=RecipePublic)
async def set_visibility(
    recipe_id: str,
    payload: RecipeVisibilityRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> RecipePublic:
    """Publish, or take it back down.

    Un-publishing is immediate and total: the recipe drops out of discover and
    out of everyone else's reads. It does NOT reach into copies people already
    forked, and it does not delete their saves -- a save of a now-private
    recipe simply stops resolving, which `my_library` handles by 404ing that
    row rather than showing a ghost.
    """
    recipe = await _owned(session, recipe_id, user)
    rows = await _ingredients(session, recipe.id)
    composed = _compose(recipe, rows)

    if payload.visibility == RecipeVisibility.published:
        check = _publish_check(recipe, rows, composed)
        if not check.ok:
            raise HTTPException(
                status_code=422,
                detail=PublishCheckResponse(
                    ok=False, blockers=check.blockers, cautions=check.cautions
                ).model_dump(),
            )
        if recipe.visibility != RecipeVisibility.published:
            recipe.published_at = datetime.now(UTC)
        recipe.visibility = RecipeVisibility.published
    else:
        recipe.visibility = RecipeVisibility.private
        recipe.published_at = None

    recipe.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(recipe)
    return _public(recipe, rows, composed, is_owner=True, author_name=user.display_name)


@router.post("/{recipe_id}/save", status_code=204)
async def save_recipe(
    recipe_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> None:
    """Keep a published recipe on your shelf, still owned by its author.

    A save FOLLOWS the author's edits. Use fork instead to take a copy that
    does not.
    """
    recipe, is_owner = await _load_visible(session, recipe_id, user)
    if is_owner:
        raise HTTPException(status_code=400, detail="This one is already yours.")

    existing = await session.scalar(
        select(RecipeSave).where(
            RecipeSave.user_id == user.id, RecipeSave.recipe_id == recipe.id
        )
    )
    if existing is not None:
        return

    session.add(RecipeSave(user_id=user.id, recipe_id=recipe.id))
    await session.execute(
        update(Recipe)
        .where(Recipe.id == recipe.id)  # type: ignore[arg-type]
        .values(save_count=Recipe.save_count + 1)
    )
    await session.commit()


@router.delete("/{recipe_id}/save", status_code=204)
async def unsave_recipe(
    recipe_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> None:
    existing = await session.scalar(
        select(RecipeSave).where(
            RecipeSave.user_id == user.id, RecipeSave.recipe_id == recipe_id
        )
    )
    if existing is None:
        return
    await session.delete(existing)
    # Clamped at zero: a counter that has drifted must not go negative and
    # render as "-1 saves".
    await session.execute(
        update(Recipe)
        .where(Recipe.id == recipe_id)  # type: ignore[arg-type]
        .values(save_count=func.greatest(Recipe.save_count - 1, 0))
    )
    await session.commit()


@router.post("/{recipe_id}/fork", response_model=RecipePublic, status_code=201)
async def fork_recipe(
    recipe_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> RecipePublic:
    """Take a copy and make it yours.

    The copy is PRIVATE regardless of the original's visibility. Forking is
    how you start changing someone's recipe, and a half-edited copy of
    somebody else's dish is not something to publish on their behalf.
    """
    source, _ = await _load_visible(session, recipe_id, user)
    src_rows = await _ingredients(session, source.id)

    copy = Recipe(
        user_id=user.id,
        name=source.name,
        description=source.description,
        cuisine=source.cuisine,
        photo_url=source.photo_url,
        visibility=RecipeVisibility.private,
        servings=source.servings,
        cooked_weight_g=source.cooked_weight_g,
        prep_minutes=source.prep_minutes,
        cook_minutes=source.cook_minutes,
        steps=list(source.steps or []),
        tags=list(source.tags or []),
        forked_from_id=source.id,
    )
    session.add(copy)
    await session.flush()

    rows: list[RecipeIngredient] = []
    for r in src_rows:
        row = RecipeIngredient(
            recipe_id=copy.id,
            food_item_id=r.food_item_id,
            display_name=r.display_name,
            grams=r.grams,
            quantity_label=r.quantity_label,
            note=r.note,
            sort_order=r.sort_order,
            calories=r.calories,
            protein_g=r.protein_g,
            carbs_g=r.carbs_g,
            fat_g=r.fat_g,
            fiber_g=r.fiber_g,
            sugar_g=r.sugar_g,
            sodium_mg=r.sodium_mg,
            saturated_fat_g=r.saturated_fat_g,
        )
        session.add(row)
        rows.append(row)

    composed = _compose(copy, rows)
    _cache_composition(copy, composed, rows)
    await session.commit()
    await session.refresh(copy)
    return _public(copy, rows, composed, is_owner=True, author_name=user.display_name)


@router.post("/{recipe_id}/log", response_model=MealLogPublic, status_code=201)
async def log_recipe(
    recipe_id: str,
    payload: RecipeLogRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> MealLogPublic:
    """Log a portion of a recipe as a meal.

    Snapshots nutrition exactly like `/api/meals/log` does, and for the same
    reason: the author editing the recipe tomorrow must not rewrite what the
    user ate today.
    """
    recipe, _ = await _load_visible(session, recipe_id, user)
    rows = await _ingredients(session, recipe.id)
    composed = _compose(recipe, rows)

    if not rows:
        raise HTTPException(status_code=422, detail="This recipe has no ingredients.")

    try:
        panel, grams, label = rx.portion(
            composed, servings=payload.servings, grams=payload.grams
        )
    except rx.YieldUnknown as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    entry = MealLog(
        user_id=user.id,
        food_item_id=None,
        display_name=recipe.name,
        grams=grams,
        serving_label=label,
        calories=panel.calories,
        protein_g=panel.protein_g,
        carbs_g=panel.carbs_g,
        fat_g=panel.fat_g,
        fiber_g=panel.fiber_g,
        # Nullable-not-zero, matching meals.py: "no sodium" and "we don't
        # know the sodium" must not render identically.
        sodium_mg=panel.sodium_mg or None,
        sugars_g=panel.sugar_g or None,
        meal_type=payload.meal_type,
        logged_at=payload.logged_at or datetime.now(UTC),
    )
    session.add(entry)
    await session.execute(
        update(Recipe)
        .where(Recipe.id == recipe.id)  # type: ignore[arg-type]
        .values(log_count=Recipe.log_count + 1)
    )
    await session.commit()
    await session.refresh(entry)
    return MealLogPublic.model_validate(entry, from_attributes=True)
