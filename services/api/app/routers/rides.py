"""Rides: attach a GPS track to an activity, and draw where you have been.

WHAT THE CLIENT GETS AND WHY IT IS ALREADY PROJECTED
The coverage endpoint returns polylines in a 0..1 square, not lat/lon. The
projection needs the bounds of EVERY ride to put them in one frame, and it
needs a cos(latitude) correction or the shapes come out stretched. Doing that
on the server means one implementation instead of one per platform, and means
the phone renders an SVG path rather than doing trigonometry on 10,000 points
during a scroll.

NO MAP TILES. The coverage map draws the rider's own routes on the app's own
canvas. That is a deliberate choice, not a missing feature -- see the note on
`coverage()` below.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db import get_session
from ..models import ExternalWorkout, RideTrack, User
from ..schemas import (
    CoverageResponse,
    RideDetail,
    RideSummaryOut,
    RideTrackRequest,
    TrackBounds,
)
from ..services import routes as rt
from .auth import current_user

router = APIRouter(prefix="/api/rides", tags=["rides"])

#: Sports whose tracks belong on the coverage map. Anything that covers
#: ground under its own power; a treadmill run has GPS-shaped data and no
#: ground truth, so it is excluded.
OUTDOOR_SPORTS = frozenset(
    {
        "cycling",
        "cycling_leisure",
        "cycling_fast",
        "mountain_biking",
        "running",
        "trail_running",
        "walking",
        "power_walking",
        "hiking",
        "rucking",
        "skating",
        "skiing",
        "kayaking",
        "rowing",
    }
)

#: Above this the payload stops being worth what it costs to draw.
MAX_TRACKS_ON_MAP = 400


def _to_points(raw: list) -> list[rt.Point]:
    """Stored [[lat, lon, alt], ...] -> Points, skipping anything malformed.

    Defensive because this data arrives from a device SDK via a client. One
    bad triple in a 7,000-point ride must not 500 the map.
    """
    out: list[rt.Point] = []
    for item in raw or []:
        try:
            lat, lon = float(item[0]), float(item[1])
            alt = float(item[2]) if len(item) > 2 and item[2] is not None else None
        except (TypeError, ValueError, IndexError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            out.append(rt.Point(lat, lon, alt))
    return out


@router.post("/{workout_id}/track", response_model=RideDetail, status_code=201)
async def attach_track(
    workout_id: str,
    payload: RideTrackRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> RideDetail:
    """Attach (or replace) the GPS track for one activity.

    Accepts either an encoded polyline or raw points. Strava and Google hand
    out polylines; HealthKit and Health Connect hand out sample arrays, and
    only the latter carries altitude -- which is why a polyline-only ride
    reports its elevation as unknown rather than as zero.
    """
    workout = await session.get(ExternalWorkout, workout_id)
    if workout is None or workout.user_id != user.id:
        raise HTTPException(status_code=404, detail="Activity not found.")

    points = (
        _to_points(payload.points)
        if payload.points
        else rt.decode_polyline(payload.polyline or "")
    )
    if len(points) < 2:
        raise HTTPException(
            status_code=422, detail="A track needs at least two valid points."
        )

    # ORDER MATTERS: elevation off the FULL track, simplification after.
    # Simplifying first would throw away the intermediate fixes the altitude
    # profile is made of, and the climb figure would collapse.
    elev = rt.elevation(points)
    distance = rt.track_distance_km(points)
    drawable = rt.simplify(points)

    existing = await session.scalar(
        select(RideTrack).where(RideTrack.workout_id == workout_id)
    )
    track = existing or RideTrack(
        user_id=user.id, workout_id=workout_id, started_at=workout.started_at
    )
    track.sport = workout.activity_type
    track.started_at = workout.started_at
    track.points = [[p.lat, p.lon, p.alt] for p in drawable]
    track.point_count = len(drawable)
    track.raw_point_count = len(points)
    track.track_distance_km = distance
    # Nullable, not zeroed: a ride with no altitude data is not a flat ride.
    track.gain_m = elev.gain_m if elev.known else None
    track.loss_m = elev.loss_m if elev.known else None
    track.max_alt_m = elev.max_m
    track.min_alt_m = elev.min_m
    track.altitude_samples = elev.samples

    if existing is None:
        session.add(track)
    await session.commit()
    await session.refresh(track)

    return _detail(track, workout)


def _detail(track: RideTrack, workout: ExternalWorkout) -> RideDetail:
    points = _to_points(track.points)
    summary = rt.summarise(
        points,
        duration_minutes=workout.duration_minutes,
        device_distance_km=workout.distance_km,
    )
    projected = rt.project([points])
    return RideDetail(
        id=track.id,
        workout_id=track.workout_id,
        sport=track.sport,
        started_at=track.started_at,
        duration_minutes=workout.duration_minutes,
        distance_km=summary.distance_km,
        distance_from_device=summary.distance_from_device,
        avg_speed_kmh=summary.avg_speed_kmh,
        elevation_known=track.gain_m is not None,
        gain_m=track.gain_m,
        loss_m=track.loss_m,
        max_alt_m=track.max_alt_m,
        min_alt_m=track.min_alt_m,
        avg_gradient_pct=summary.avg_gradient_pct,
        # The altitude series, already thinned, so the client draws a profile
        # without a second round trip.
        altitude_profile=[p.alt for p in points if p.alt is not None],
        polyline=projected[0] if projected else [],
        point_count=track.point_count,
        raw_point_count=track.raw_point_count,
    )


@router.get("/{workout_id}/track", response_model=RideDetail)
async def get_track(
    workout_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> RideDetail:
    track = await session.scalar(
        select(RideTrack).where(
            RideTrack.workout_id == workout_id, RideTrack.user_id == user.id
        )
    )
    if track is None:
        raise HTTPException(status_code=404, detail="No track for that activity.")
    workout = await session.get(ExternalWorkout, workout_id)
    if workout is None:
        raise HTTPException(status_code=404, detail="Activity not found.")
    return _detail(track, workout)


@router.get("/coverage", response_model=CoverageResponse)
async def coverage(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
    days: int = Query(default=365, ge=1, le=3650),
    sport: Optional[str] = Query(default=None, description="e.g. 'cycling'"),
) -> CoverageResponse:
    """Everything the coverage map needs, in one round trip.

    GROUND COVERED IS REPORTED SEPARATELY FROM DISTANCE, and that distinction
    is the point of the screen. Riding the same 8 km commute 200 times is
    1,600 km of distance across about 4 km2 of ground. Both numbers are true;
    only one of them means "I have been somewhere".

    The map is drawn from the rider's own routes with no basemap underneath.
    A tile layer would need a keyed third-party service, would send every
    ride's location to it, and would look nothing like the rest of the app.
    The lines alone are legible -- a city's road network is recognisable from
    the routes you have ridden through it.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(RideTrack, ExternalWorkout)
        .join(ExternalWorkout, ExternalWorkout.id == RideTrack.workout_id)  # type: ignore[arg-type]
        .where(RideTrack.user_id == user.id, RideTrack.started_at >= since)
        .order_by(RideTrack.started_at.desc())  # type: ignore[union-attr]
        .limit(MAX_TRACKS_ON_MAP)
    )
    if sport:
        stmt = stmt.where(RideTrack.sport == sport)
    else:
        stmt = stmt.where(RideTrack.sport.in_(OUTDOOR_SPORTS))  # type: ignore[attr-defined]

    rows = (await session.execute(stmt)).all()

    tracks: list[list[rt.Point]] = []
    rides: list[rt.RideInput] = []
    summaries: list[RideSummaryOut] = []

    for track, workout in rows:
        points = _to_points(track.points)
        tracks.append(points)
        rides.append(
            rt.RideInput(
                distance_km=workout.distance_km,
                points=points,
                gain_m=track.gain_m,
                highest_m=track.max_alt_m,
            )
        )
        summaries.append(
            RideSummaryOut(
                id=track.id,
                workout_id=track.workout_id,
                sport=track.sport,
                started_at=track.started_at,
                distance_km=workout.distance_km or track.track_distance_km,
                duration_minutes=workout.duration_minutes,
                gain_m=track.gain_m,
                max_alt_m=track.max_alt_m,
            )
        )

    # Rides logged without a track still count toward distance and climb --
    # they just cannot be drawn. Counting them keeps the headline honest.
    trackless = (
        await session.execute(
            select(ExternalWorkout).where(
                ExternalWorkout.user_id == user.id,
                ExternalWorkout.started_at >= since,
                ExternalWorkout.activity_type.in_(  # type: ignore[attr-defined]
                    [sport] if sport else list(OUTDOOR_SPORTS)
                ),
                ExternalWorkout.id.notin_(  # type: ignore[attr-defined]
                    select(RideTrack.workout_id).where(RideTrack.user_id == user.id)
                ),
            )
        )
    ).scalars().all()
    rides.extend(rt.RideInput(distance_km=w.distance_km) for w in trackless)

    agg = rt.coverage(rides)
    projected = rt.project(tracks) if tracks else []

    return CoverageResponse(
        rides=agg.rides,
        rides_drawn=len(tracks),
        total_distance_km=agg.total_distance_km,
        total_gain_m=agg.total_gain_m,
        ground_km2=agg.ground_km2,
        cell_km=rt.COVERAGE_CELL_KM,
        highest_m=agg.highest_m,
        longest_ride_km=agg.longest_ride_km,
        biggest_climb_m=agg.biggest_climb_m,
        span_km=list(agg.span_km) if agg.span_km else None,
        bounds=(
            TrackBounds(
                min_lat=agg.bounds.min_lat,
                max_lat=agg.bounds.max_lat,
                min_lon=agg.bounds.min_lon,
                max_lon=agg.bounds.max_lon,
            )
            if agg.bounds
            else None
        ),
        polylines=projected,
        recent=summaries[:20],
    )
