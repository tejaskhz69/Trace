"""Trace API entrypoint.

Railway deployment checklist baked in here:
  * Binds 0.0.0.0:$PORT (see run() at the bottom and the Dockerfile CMD).
  * /health returns 200 without touching the database, so Railway's healthcheck
    passes even during a DB blip and doesn't kill an otherwise-fine container.
  * /healthz/db separately verifies the database, for your own monitoring.
  * Startup failures are logged loudly rather than swallowed -- a container
    that boots but can't reach Postgres is the most confusing failure mode
    there is.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from .db import engine, init_db
from .routers import (
    adjudication,
    auth,
    chat,
    foods,
    insights,
    meals,
    onboarding,
    preparations,
    programming,
    recipes,
    recognition,
    weight,
    workouts,
)

# Aliased: the liveness endpoint below is also called `health`, and a bare
# `health` import would be shadowed by it at include_router() time.
from .routers import health as health_router
from .services import programming as programming_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("trace")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Trace API (env=%s)", settings.ENV)
    try:
        await init_db()
        log.info("Database ready")
    except Exception:
        # Do NOT swallow this. If the DB is unreachable you want it in the
        # Railway logs in giant letters, not a mysterious 500 an hour later.
        log.exception("DATABASE INITIALISATION FAILED")
        raise
    yield
    await engine.dispose()
    log.info("Shutdown complete")


app = FastAPI(
    title="Trace API",
    description="AI nutrition + strength tracking. Know if it's working.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

# CORS only matters for Expo Web / the browser. A native React Native fetch
# sends no Origin header and is never subject to CORS -- so if your device
# login fails, CORS is not your bug. See docs/04-fix-expo-railway-auth.md.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.is_production else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def timing_and_logging(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong on our end."},
        )
    took_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Response-Time-ms"] = f"{took_ms:.1f}"
    if took_ms > 500:
        log.warning("SLOW %s %s took %.0fms", request.method, request.url.path, took_ms)
    return response


# --- Health ---------------------------------------------------------------


@app.get("/health", tags=["ops"])
async def health() -> dict:
    """Liveness. Deliberately does not touch the database."""
    return {"status": "ok", "env": settings.ENV, "version": app.version}


@app.get("/healthz/db", tags=["ops"])
async def health_db() -> dict:
    """Readiness. Use this when debugging a Railway deploy.

    ALSO REPORTS UNFILLED PROGRAMME SLOTS, against the live database rather
    than the seed. The test suite has a guard for the same property, but it
    reads the curated constant `seed_movements` writes -- so it proves the
    SEED is coherent, not that production is. If `exercise_attributes` ever
    drifts from the seed, that test stays green while real programmes come
    back short.

    `unfilled` names slots the generator asks for and this database cannot
    fill. `carry` is expected there today (see KNOWN_EMPTY_PATTERNS);
    anything else appearing is drift and means somebody is being
    under-prescribed right now.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            rows = (
                await conn.execute(
                    text(
                        "SELECT movement_pattern, is_isolation, classified_by "
                        "FROM exercise_attributes"
                    )
                )
            ).all()
    except Exception as exc:
        return JSONResponse(
            status_code=503, content={"database": "unreachable", "error": str(exc)}
        )

    pairs = [(pattern, bool(isolation)) for pattern, isolation, _by in rows]

    # The two guards are mirror images and neither is sufficient alone.
    # `unfilled_slots` catches a template asking for something the catalogue
    # cannot supply. `unrequested_patterns` catches the quieter failure: the
    # catalogue supplying something no template will ever ask for, which has
    # no error, no empty day and no log line. `lunge` and `core` sat in that
    # blind spot -- unreachable, with this endpoint reporting green.
    unfilled = programming_service.unfilled_slots(pairs)
    unexpected = sorted(unfilled - programming_service.KNOWN_EMPTY_PATTERNS)
    unrequested = programming_service.unrequested_patterns(pairs)
    unexpected_unrequested = sorted(
        unrequested - programming_service.KNOWN_UNUSED_PATTERNS
    )

    # How much of the catalogue anyone actually stands behind. A bare count
    # of classified rows says nothing about whether a person has read them.
    human = sum(1 for _p, _i, by in rows if by == "human")

    return {
        "database": "ok",
        "classified_movements": len(rows),
        "human_reviewed": human,
        "engine_derived": len(rows) - human,
        "unfilled_slots": sorted(unfilled),
        "unexpected_unfilled_slots": unexpected,
        "unrequested_patterns": sorted(unrequested),
        "unexpected_unrequested_patterns": unexpected_unrequested,
    }


@app.get("/", tags=["ops"])
async def root() -> dict:
    return {
        "service": "trace-api",
        "docs": "/docs" if not settings.is_production else "disabled in production",
        "health": "/health",
    }


# --- Routers --------------------------------------------------------------

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(foods.router)
app.include_router(insights.router)
app.include_router(health_router.router)
app.include_router(onboarding.router)
app.include_router(preparations.router)
app.include_router(meals.router)
app.include_router(recipes.router)
app.include_router(recognition.router)
app.include_router(weight.router)
app.include_router(workouts.router)
# Same /api/workouts prefix, separate module: the recording endpoints in
# routers/workouts.py are left untouched.
app.include_router(programming.router)
app.include_router(adjudication.router)


def run() -> None:
    import uvicorn

    # Railway injects PORT. Reading it here (not just from Settings) means a
    # stale .env can never override the platform's value.
    port = int(os.getenv("PORT", settings.PORT))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run()
