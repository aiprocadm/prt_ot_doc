"""Health and readiness endpoints for infrastructure monitoring."""

from __future__ import annotations

import logging

import redis.asyncio as redis_async
from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.db.session import engine

logger = logging.getLogger("app.api.health")
router = APIRouter(tags=["service"], include_in_schema=False)


async def _ping_postgres(app: FastAPI) -> None:
    """Perform a lightweight database connectivity check."""

    session_factory = getattr(app.state, "test_sessionmaker", None)
    if session_factory is not None:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        return

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def _ping_redis(app: FastAPI, settings: Settings) -> None:
    """Ensure Redis is reachable for readiness probes."""

    client = getattr(app.state, "redis_client", None)
    if client is not None:
        await client.ping()
        return

    redis = redis_async.from_url(settings.redis.broker_url)
    try:
        await redis.ping()
    finally:
        await redis.close()


def _resolve_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


@router.get("/health")
async def health() -> JSONResponse:
    """Return service liveness information."""

    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ok"})


async def _check_postgres(request: Request) -> bool:
    try:
        await _ping_postgres(request.app)
    except SQLAlchemyError:
        logger.exception("health.ready.postgres_failed")
        return False
    except Exception:  # noqa: BLE001 - defensive logging
        logger.exception("health.ready.postgres_unexpected")
        return False
    return True


async def _check_redis(request: Request, settings: Settings) -> bool:
    try:
        await _ping_redis(request.app, settings)
    except Exception:  # noqa: BLE001 - defensive logging
        logger.exception("health.ready.redis_failed")
        return False
    return True


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Return readiness information for dependent services."""

    settings = _resolve_settings(request)
    postgres_ok = await _check_postgres(request)
    redis_ok = await _check_redis(request, settings)
    ok = postgres_ok and redis_ok
    payload = {
        "status": "ok" if ok else "degraded",
        "postgres": postgres_ok,
        "redis": redis_ok,
    }
    status_code = status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/healthz")
async def healthz() -> JSONResponse:
    return await health()


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    return await ready(request)


__all__ = ["router", "_ping_postgres", "_ping_redis"]
