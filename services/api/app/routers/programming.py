"""Deterministic workout programming -- the "what should I lift today?" half.

This router is thin on purpose. Every decision about what belongs in a
programme lives in `services/programming.py` as pure functions; everything
here is loading rows, checking ownership, and writing the result.

IT SHARES THE `/api/workouts` PREFIX WITH `routers/workouts.py` AND CHANGES
NOTHING IN IT. The recording endpoints -- sessions, sets, next-set, finish,
voice -- are untouched and keep working with no programme, no profile and no
planned session. Programming is something the app offers; logging is something
it must never gate.

OWNERSHIP IS CHECKED ON EVERY PATH, AND MISSING IS INDISTINGUISHABLE FROM
NOT-YOURS. Every lookup returns 404 for a row that does not exist and 404 for
a row belonging to someone else, because a 403 would confirm the row exists --
which is itself the leak. Rows reached indirectly (a programme day, a
prescription) are joined back to their owning row and filtered there rather
than trusted from the path.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import (
    AIGeneration,  # noqa: F401 -- FK target; imported so metadata is complete
    Exercise,
    ExerciseAttributes,
    ExerciseSubstitution,
    PlannedSession,
    PrescribedExercise,
    ProgrammeDay,
    TrainingProfile,
    TrainingProgramme,
    User,
    WorkoutSession,
)
from ..schemas import (
    ExerciseEducationPublic,
    PlannedSessionPublic,
    PlannedSessionRequest,
    PlannedSessionStartPublic,
    PrescribedExercisePatch,
    PrescribedExercisePublic,
    ProgrammeDayPublic,
    ProgrammePublic,
    ProgrammeRequest,
    TrainingProfilePatch,
    TrainingProfilePublic,
    TrainingProfileRequest,
)
from ..services import programming
from .auth import current_user

router = APIRouter(prefix="/api/workouts", tags=["workouts"])

#: Cap on how many substitutions are offered per prescribed exercise. A list
#: of twenty alternatives is not a choice, it is a catalogue.
MAX_SUBSTITUTIONS = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today_for(user: User) -> date:
    """The user's local calendar day.

    A scheduled day has no timezone, but *which* day it is depends entirely on
    the user's. Falling back to UTC on an unrecognised zone is deliberate: a
    bad timezone string should not stop someone training.
    """
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(user.timezone or "UTC")).date()
    except Exception:
        return datetime.now(timezone.utc).date()


async def _load_profile(
    session: AsyncSession, user: User
) -> Optional[TrainingProfile]:
    return (
        await session.execute(
            select(TrainingProfile).where(TrainingProfile.user_id == user.id)
        )
    ).scalar_one_or_none()


async def _require_profile(session: AsyncSession, user: User) -> TrainingProfile:
    profile = await _load_profile(session, user)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="No training profile yet. Create one first.",
        )
    return profile


async def _owned_programme(
    session: AsyncSession, programme_id: str, user: User
) -> TrainingProgramme:
    programme = (
        await session.execute(
            select(TrainingProgramme).where(
                TrainingProgramme.id == programme_id,
                TrainingProgramme.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if programme is None:
        raise HTTPException(status_code=404, detail="Programme not found.")
    return programme


async def _owned_planned(
    session: AsyncSession, planned_id: str, user: User
) -> PlannedSession:
    planned = (
        await session.execute(
            select(PlannedSession).where(
                PlannedSession.id == planned_id,
                PlannedSession.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if planned is None:
        raise HTTPException(status_code=404, detail="Planned session not found.")
    return planned


async def _load_options(session: AsyncSession) -> list[programming.ExerciseOption]:
    """Every catalogue exercise that carries programming attributes.

    INNER JOIN, not outer. An exercise with no attributes row is not
    classified, and generation must refuse to prescribe it rather than invent
    a rep range -- so it never becomes an option in the first place.
    """
    rows = (
        await session.execute(
            select(Exercise, ExerciseAttributes).join(
                ExerciseAttributes,
                ExerciseAttributes.exercise_id == Exercise.id,
            )
        )
    ).all()
    return [
        programming.ExerciseOption(
            exercise_id=ex.id,
            name=ex.name,
            equipment=ex.equipment,
            muscle_group=ex.muscle_group,
            secondary_muscles=tuple(ex.secondary_muscles or ()),
            movement_pattern=attr.movement_pattern,
            exercise_class=attr.exercise_class,
            default_rep_min=attr.default_rep_min,
            default_rep_max=attr.default_rep_max,
            default_rest_seconds=attr.default_rest_seconds,
            fatigue_cost=attr.fatigue_cost,
            is_unilateral=attr.is_unilateral,
        )
        for ex, attr in rows
    ]


async def _substitutions_for(
    session: AsyncSession, exercise_ids: list[str]
) -> dict[str, list[str]]:
    """Ranked alternatives for many exercises in ONE query.

    Looping a query per prescribed exercise would be the N+1 this endpoint is
    most likely to grow, so it is done once up front.
    """
    if not exercise_ids:
        return {}
    rows = (
        await session.execute(
            select(
                ExerciseSubstitution.from_exercise_id,
                ExerciseSubstitution.to_exercise_id,
            )
            .where(ExerciseSubstitution.from_exercise_id.in_(exercise_ids))
            .order_by(
                ExerciseSubstitution.from_exercise_id,
                ExerciseSubstitution.rank,
                ExerciseSubstitution.to_exercise_id,
            )
        )
    ).all()
    out: dict[str, list[str]] = {}
    for src, dst in rows:
        bucket = out.setdefault(src, [])
        if len(bucket) < MAX_SUBSTITUTIONS:
            bucket.append(dst)
    return out


async def _planned_public(
    session: AsyncSession, planned: PlannedSession
) -> PlannedSessionPublic:
    """Render a planned session and everything under it.

    TWO QUERIES, INDEPENDENT OF EXERCISE COUNT: the prescriptions joined to
    their exercise and attributes, plus the programme day label. Rendering one
    row per prescription with its own lookup would be the obvious N+1 here,
    and a session with eight exercises would then cost nine round trips.
    """
    rows = (
        await session.execute(
            select(PrescribedExercise, Exercise, ExerciseAttributes)
            .join(Exercise, Exercise.id == PrescribedExercise.exercise_id)
            .outerjoin(
                ExerciseAttributes,
                ExerciseAttributes.exercise_id == Exercise.id,
            )
            .where(PrescribedExercise.planned_session_id == planned.id)
            .order_by(PrescribedExercise.order_index)
        )
    ).all()

    label: Optional[str] = None
    if planned.programme_day_id:
        label = (
            await session.execute(
                select(ProgrammeDay.label).where(
                    ProgrammeDay.id == planned.programme_day_id
                )
            )
        ).scalar_one_or_none()

    exercises: list[PrescribedExercisePublic] = []
    for presc, ex, attr in rows:
        education = None
        if attr is not None:
            # Education metadata is offered only where the catalogue actually
            # carries it -- an unclassified exercise gets no invented cue.
            edu = programming.education_for(
                programming.ExerciseOption(
                    exercise_id=ex.id,
                    name=ex.name,
                    equipment=ex.equipment,
                    muscle_group=ex.muscle_group,
                    secondary_muscles=tuple(ex.secondary_muscles or ()),
                    movement_pattern=attr.movement_pattern,
                    exercise_class=attr.exercise_class,
                    default_rep_min=attr.default_rep_min,
                    default_rep_max=attr.default_rep_max,
                    default_rest_seconds=attr.default_rest_seconds,
                    fatigue_cost=attr.fatigue_cost,
                    is_unilateral=attr.is_unilateral,
                )
            )
            education = ExerciseEducationPublic(
                primary_muscle=edu.primary_muscle,
                secondary_muscles=list(edu.secondary_muscles),
                movement_pattern=edu.movement_pattern,
                form_cue=edu.form_cue,
            )
        exercises.append(
            PrescribedExercisePublic(
                id=presc.id,
                exercise_id=presc.exercise_id,
                exercise_name=ex.name,
                equipment=ex.equipment,
                order_index=presc.order_index,
                sets=presc.sets,
                rep_min=presc.rep_min,
                rep_max=presc.rep_max,
                target_rir=presc.target_rir,
                rest_seconds=presc.rest_seconds,
                suggested_weight_kg=presc.suggested_weight_kg,
                progression_rule=presc.progression_rule,
                status=presc.status,
                replaced_with_exercise_id=presc.replaced_with_exercise_id,
                substitution_ids=list(presc.substitution_ids or []),
                education=education,
            )
        )

    return PlannedSessionPublic(
        id=planned.id,
        programme_day_id=planned.programme_day_id,
        programme_day_label=label,
        session_id=planned.session_id,
        scheduled_for=planned.scheduled_for,
        status=planned.status,
        estimated_minutes=planned.estimated_minutes,
        generated_by=planned.generated_by,
        notes=list(planned.notes or []),
        exercises=exercises,
    )


async def _programme_public(
    session: AsyncSession, programme: TrainingProgramme
) -> ProgrammePublic:
    days = (
        (
            await session.execute(
                select(ProgrammeDay)
                .where(ProgrammeDay.programme_id == programme.id)
                .order_by(ProgrammeDay.day_index)
            )
        )
        .scalars()
        .all()
    )
    return ProgrammePublic(
        id=programme.id,
        name=programme.name,
        split_type=programme.split_type,
        days_per_week=programme.days_per_week,
        status=programme.status,
        generated_by=programme.generated_by,
        started_at=programme.started_at,
        archived_at=programme.archived_at,
        days=[
            ProgrammeDayPublic(
                id=d.id,
                day_index=d.day_index,
                label=d.label,
                focus=list(d.focus or []),
                target_minutes=d.target_minutes,
            )
            for d in days
        ],
    )


# ---------------------------------------------------------------------------
# Training profile
# ---------------------------------------------------------------------------


@router.post("/training-profile", status_code=201, response_model=TrainingProfilePublic)
async def create_training_profile(
    body: TrainingProfileRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> TrainingProfilePublic:
    """Create the caller's profile. 409 if they already have one."""
    if await _load_profile(session, user) is not None:
        raise HTTPException(
            status_code=409,
            detail="A training profile already exists. Use PATCH to change it.",
        )
    profile = TrainingProfile(user_id=user.id, **body.model_dump())
    session.add(profile)
    try:
        await session.commit()
    except IntegrityError:
        # uq_training_profile_user, i.e. two concurrent creates. The database
        # settles it; we translate rather than surface a 500.
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="A training profile already exists."
        )
    await session.refresh(profile)
    return TrainingProfilePublic(**profile.model_dump())


@router.get("/training-profile", response_model=TrainingProfilePublic)
async def get_training_profile(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> TrainingProfilePublic:
    profile = await _require_profile(session, user)
    return TrainingProfilePublic(**profile.model_dump())


@router.patch("/training-profile", response_model=TrainingProfilePublic)
async def update_training_profile(
    body: TrainingProfilePatch,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> TrainingProfilePublic:
    """Partial update.

    `exclude_unset` is what makes this a real PATCH: a field the client did
    not send is left alone, while `"limitations": null` genuinely clears it.
    Without it every PATCH would silently reset the fields it omitted.
    """
    profile = await _require_profile(session, user)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(profile, field, value)
    profile.updated_at = datetime.now(timezone.utc)
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return TrainingProfilePublic(**profile.model_dump())


# ---------------------------------------------------------------------------
# Programmes
# ---------------------------------------------------------------------------


@router.post("/programmes", status_code=201, response_model=ProgrammePublic)
async def create_programme(
    body: ProgrammeRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> ProgrammePublic:
    """Generate and persist a programme from the caller's profile.

    ARCHIVES THE CURRENT ACTIVE PROGRAMME IN THE SAME TRANSACTION. A user ends
    up with exactly one active programme or the request fails; there is no
    window in which they have two, and none in which they have none because
    the old one was archived and the new one then failed to insert.
    """
    profile = await _require_profile(session, user)
    days_per_week = body.days_per_week or profile.days_per_week

    split_type, templates = programming.split_for(days_per_week)

    existing = (
        await session.execute(
            select(TrainingProgramme).where(
                TrainingProgramme.user_id == user.id,
                TrainingProgramme.status == "active",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.status = "archived"
        existing.archived_at = datetime.now(timezone.utc)
        existing.updated_at = existing.archived_at
        session.add(existing)

    programme = TrainingProgramme(
        user_id=user.id,
        name=programming.programme_name(split_type, days_per_week),
        split_type=split_type,
        days_per_week=days_per_week,
        status="active",
        generated_by="template",
    )
    session.add(programme)
    await session.flush()

    for index, template in enumerate(templates):
        session.add(
            ProgrammeDay(
                programme_id=programme.id,
                day_index=index,
                label=template.label,
                focus=list(template.focus),
                target_minutes=profile.preferred_minutes,
            )
        )

    try:
        await session.commit()
    except IntegrityError:
        # uq_active_programme_per_user under a concurrent create.
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="An active programme already exists. Archive it first.",
        )
    await session.refresh(programme)
    return await _programme_public(session, programme)


@router.get("/programmes/active", response_model=ProgrammePublic)
async def active_programme(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> ProgrammePublic:
    programme = (
        await session.execute(
            select(TrainingProgramme).where(
                TrainingProgramme.user_id == user.id,
                TrainingProgramme.status == "active",
            )
        )
    ).scalar_one_or_none()
    if programme is None:
        raise HTTPException(status_code=404, detail="No active programme.")
    return await _programme_public(session, programme)


@router.post("/programmes/{programme_id}/archive", response_model=ProgrammePublic)
async def archive_programme(
    programme_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> ProgrammePublic:
    """Archive, never delete.

    A programme is the explanation for every planned session beneath it, so
    there is no DELETE on this router at all. Archiving twice is a no-op
    rather than an error -- a retried request should not fail.
    """
    programme = await _owned_programme(session, programme_id, user)
    if programme.status != "archived":
        programme.status = "archived"
        programme.archived_at = datetime.now(timezone.utc)
        programme.updated_at = programme.archived_at
        session.add(programme)
        await session.commit()
        await session.refresh(programme)
    return await _programme_public(session, programme)


@router.get("/programmes/{programme_id}/days", response_model=list[ProgrammeDayPublic])
async def programme_days(
    programme_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> list[ProgrammeDayPublic]:
    """Days of one programme, always ordered by `day_index`.

    Ownership is checked on the PROGRAMME, not the days -- the days are then
    reachable only through a row already proven to belong to the caller.
    """
    programme = await _owned_programme(session, programme_id, user)
    full = await _programme_public(session, programme)
    return full.days


# ---------------------------------------------------------------------------
# Planned sessions
# ---------------------------------------------------------------------------


@router.post(
    "/planned-sessions", status_code=201, response_model=PlannedSessionPublic
)
async def materialise_planned_session(
    body: PlannedSessionRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> PlannedSessionPublic:
    """Materialise one dated session from the active programme.

    IDEMPOTENT on (user, date, programme day): asking twice returns the
    session that already exists rather than creating a second one. A client
    that double-taps, retries on a flaky connection, or re-opens the home
    screen must not end up with two plans for one day.
    """
    profile = await _require_profile(session, user)
    programme = (
        await session.execute(
            select(TrainingProgramme).where(
                TrainingProgramme.user_id == user.id,
                TrainingProgramme.status == "active",
            )
        )
    ).scalar_one_or_none()
    if programme is None:
        raise HTTPException(
            status_code=404, detail="No active programme. Create one first."
        )

    days = (
        (
            await session.execute(
                select(ProgrammeDay)
                .where(ProgrammeDay.programme_id == programme.id)
                .order_by(ProgrammeDay.day_index)
            )
        )
        .scalars()
        .all()
    )
    if not days:
        raise HTTPException(status_code=404, detail="Programme has no days.")

    scheduled_for = body.scheduled_for or _today_for(user)

    # IDEMPOTENCY IS CHECKED BEFORE THE ROTATION ADVANCES, and that ordering
    # is the whole correctness of this endpoint.
    #
    # "Give me today's session" must return today's session. Advancing the
    # rotation first and only then looking for an existing row means the
    # second call computes the NEXT day, finds nothing under it, and cheerfully
    # creates a second session for the same date -- which uq_planned_day does
    # not catch, because the day differs. A double-tap would silently produce
    # two plans for one day.
    if body.programme_day_id:
        day = next((d for d in days if d.id == body.programme_day_id), None)
        if day is None:
            # Belongs to another programme, or does not exist. Same answer
            # either way -- see the module docstring.
            raise HTTPException(status_code=404, detail="Programme day not found.")
        existing = (
            await session.execute(
                select(PlannedSession).where(
                    PlannedSession.user_id == user.id,
                    PlannedSession.scheduled_for == scheduled_for,
                    PlannedSession.programme_day_id == day.id,
                )
            )
        ).scalar_one_or_none()
    else:
        # No day named: any session already planned for this date under this
        # programme is the answer, whichever day it happens to be.
        existing = (
            await session.execute(
                select(PlannedSession)
                .join(ProgrammeDay, ProgrammeDay.id == PlannedSession.programme_day_id)
                .where(
                    PlannedSession.user_id == user.id,
                    PlannedSession.scheduled_for == scheduled_for,
                    ProgrammeDay.programme_id == programme.id,
                )
                .order_by(PlannedSession.id)
            )
        ).scalars().first()
        day = None

    if existing is not None:
        # Already materialised: 200, not 201, and emphatically not a second
        # row. A double-tap or a retry must be indistinguishable from one call.
        response.status_code = 200
        return await _planned_public(session, existing)

    if day is None:
        # Next in the rotation: how many sessions have already been planned
        # under this programme, modulo its length.
        planned_count = (
            await session.execute(
                select(func.count())
                .select_from(PlannedSession)
                .join(ProgrammeDay, ProgrammeDay.id == PlannedSession.programme_day_id)
                .where(
                    PlannedSession.user_id == user.id,
                    ProgrammeDay.programme_id == programme.id,
                )
            )
        ).scalar_one()
        day = days[planned_count % len(days)]

    options = await _load_options(session)
    if not options:
        raise HTTPException(
            status_code=422,
            detail=(
                "No exercises in the catalogue carry programming attributes "
                "yet, so no session can be generated."
            ),
        )

    template = programming.DayTemplate(
        label=day.label,
        focus=tuple(day.focus or ()),
        patterns=_patterns_for(day),
    )
    candidates = programming.eligible(
        options,
        equipment=programming.beginner_equipment(profile.equipment),
        disliked=profile.disliked_exercise_ids,
    )
    budget = programming.exercise_budget(
        day.target_minutes or profile.preferred_minutes
    )
    selected = programming.select_for_day(template, candidates, budget)
    if not selected:
        raise HTTPException(
            status_code=422,
            detail=(
                "No eligible exercises for this profile. Widen the available "
                "equipment or remove some exclusions."
            ),
        )
    prescriptions = programming.prescribe(selected)
    subs = await _substitutions_for(session, [o.exercise_id for o in selected])

    planned = PlannedSession(
        user_id=user.id,
        programme_day_id=day.id,
        scheduled_for=scheduled_for,
        status="planned",
        estimated_minutes=programming.estimated_minutes(prescriptions),
        generated_by="template",
        notes=list(programming.programme_notes(programme.days_per_week)),
    )
    session.add(planned)
    await session.flush()

    for p in prescriptions:
        session.add(
            PrescribedExercise(
                planned_session_id=planned.id,
                exercise_id=p.exercise_id,
                order_index=p.order_index,
                sets=p.sets,
                rep_min=p.rep_min,
                rep_max=p.rep_max,
                target_rir=p.target_rir,
                rest_seconds=p.rest_seconds,
                progression_rule=p.progression_rule,
                substitution_ids=subs.get(p.exercise_id, []),
            )
        )

    try:
        await session.commit()
    except IntegrityError:
        # uq_planned_day lost a race. The winner's row is the answer.
        await session.rollback()
        winner = (
            await session.execute(
                select(PlannedSession).where(
                    PlannedSession.user_id == user.id,
                    PlannedSession.scheduled_for == scheduled_for,
                    PlannedSession.programme_day_id == day.id,
                )
            )
        ).scalar_one_or_none()
        if winner is None:
            raise HTTPException(
                status_code=409, detail="Could not materialise this session."
            )
        response.status_code = 200
        return await _planned_public(session, winner)

    await session.refresh(planned)
    return await _planned_public(session, planned)


def _patterns_for(day: ProgrammeDay) -> tuple[str, ...]:
    """Recover the movement patterns a stored day was generated from.

    `programme_days` stores focus muscles, not patterns, because focus is what
    a user reads on the screen. Rather than denormalise a second list that
    could drift out of step with the generator, the day's template is looked
    back up by its label.

    If the label is unrecognised -- a future rename, or a day created by some
    later producer -- the global priority order is used. That still yields a
    sensible session rather than an error, which is the right failure mode for
    something purely advisory.
    """
    template = _TEMPLATES_BY_LABEL.get(day.label)
    return template.patterns if template else programming.PATTERN_PRIORITY


#: Every label any split can produce, mapped to its patterns. Built once at
#: import from the generator itself, so a new split type cannot be added
#: without this map picking it up.
_TEMPLATES_BY_LABEL: dict[str, programming.DayTemplate] = {
    template.label: template
    for days in range(1, 8)
    for template in programming.split_for(days)[1]
}


@router.get("/planned-sessions/{planned_id}", response_model=PlannedSessionPublic)
async def get_planned_session(
    planned_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> PlannedSessionPublic:
    planned = await _owned_planned(session, planned_id, user)
    return await _planned_public(session, planned)


@router.post(
    "/planned-sessions/{planned_id}/start",
    status_code=201,
    response_model=PlannedSessionStartPublic,
)
async def start_planned_session(
    planned_id: str,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> PlannedSessionStartPublic:
    """Create the performed session and hand off to the existing logger.

    THE HANDOFF IS THE POINT. This returns a real `WorkoutSession.id`, and
    from that moment the untouched `POST /sessions/{id}/sets` owns the
    workout. Programming does not wrap, proxy or re-implement set logging.

    IDEMPOTENT: starting twice returns the same session and creates no second
    one. It never overwrites an existing link, because a performed session is
    a record of something that happened and a retry is not new evidence.
    """
    planned = await _owned_planned(session, planned_id, user)

    if planned.session_id:
        # Already started. Return the SAME session -- a retry is not new
        # evidence that a second workout happened.
        response.status_code = 200
        return PlannedSessionStartPublic(
            planned_session_id=planned.id,
            session_id=planned.session_id,
            created=False,
        )

    routine_name: Optional[str] = None
    if planned.programme_day_id:
        routine_name = (
            await session.execute(
                select(ProgrammeDay.label).where(
                    ProgrammeDay.id == planned.programme_day_id
                )
            )
        ).scalar_one_or_none()

    # The performed session is a NEW row. Nothing existing is overwritten --
    # this is the first time this workout has been recorded.
    workout = WorkoutSession(user_id=user.id, routine_name=routine_name)
    session.add(workout)
    await session.flush()

    planned.session_id = workout.id
    planned.status = "active"
    planned.updated_at = datetime.now(timezone.utc)
    session.add(planned)
    await session.commit()

    return PlannedSessionStartPublic(
        planned_session_id=planned.id, session_id=workout.id, created=True
    )


# ---------------------------------------------------------------------------
# Prescribed exercises
# ---------------------------------------------------------------------------


@router.patch(
    "/prescribed-exercises/{prescribed_id}",
    response_model=PrescribedExercisePublic,
)
async def update_prescribed_exercise(
    prescribed_id: str,
    body: PrescribedExercisePatch,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> PrescribedExercisePublic:
    """Skip a prescribed exercise, or replace it with an offered alternative.

    SKIPPING SETS A STATUS, IT DOES NOT DELETE THE ROW. What was prescribed
    and declined is exactly the signal the deferred preference learning will
    need, and deleting it throws that away for no gain.

    A REPLACEMENT MUST BE ONE WE OFFERED. An arbitrary exercise id is rejected
    422 rather than accepted: the substitution list is the reviewed set, and
    accepting anything else would let a client write a prescription nobody
    checked -- the same class of trust failure as accepting an AI-invented id.
    """
    row = (
        await session.execute(
            select(PrescribedExercise, PlannedSession)
            .join(
                PlannedSession,
                PlannedSession.id == PrescribedExercise.planned_session_id,
            )
            .where(
                PrescribedExercise.id == prescribed_id,
                PlannedSession.user_id == user.id,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Prescribed exercise not found.")
    presc, _planned = row

    if body.status == "replaced":
        target = body.replaced_with_exercise_id
        if not target:
            raise HTTPException(
                status_code=422,
                detail="replaced_with_exercise_id is required to replace an exercise.",
            )
        exists = (
            await session.execute(select(Exercise.id).where(Exercise.id == target))
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=422, detail="Unknown exercise id.")

        offered = set(presc.substitution_ids or [])
        if target not in offered:
            allowed = (
                await session.execute(
                    select(ExerciseSubstitution.id).where(
                        ExerciseSubstitution.from_exercise_id == presc.exercise_id,
                        ExerciseSubstitution.to_exercise_id == target,
                    )
                )
            ).scalar_one_or_none()
            if allowed is None:
                raise HTTPException(
                    status_code=422,
                    detail="That exercise is not an offered substitution for this one.",
                )
        presc.status = "replaced"
        presc.replaced_with_exercise_id = target
    elif body.status == "skipped":
        presc.status = "skipped"
        presc.replaced_with_exercise_id = None
    else:
        # Undo: back to as-prescribed. ck_prescribed_replacement requires the
        # replacement to be cleared in lockstep with the status.
        presc.status = "prescribed"
        presc.replaced_with_exercise_id = None

    presc.updated_at = datetime.now(timezone.utc)
    session.add(presc)
    await session.commit()
    await session.refresh(presc)

    exercise = await session.get(Exercise, presc.exercise_id)
    return PrescribedExercisePublic(
        id=presc.id,
        exercise_id=presc.exercise_id,
        exercise_name=exercise.name if exercise else "",
        equipment=exercise.equipment if exercise else "",
        order_index=presc.order_index,
        sets=presc.sets,
        rep_min=presc.rep_min,
        rep_max=presc.rep_max,
        target_rir=presc.target_rir,
        rest_seconds=presc.rest_seconds,
        suggested_weight_kg=presc.suggested_weight_kg,
        progression_rule=presc.progression_rule,
        status=presc.status,
        replaced_with_exercise_id=presc.replaced_with_exercise_id,
        substitution_ids=list(presc.substitution_ids or []),
    )
