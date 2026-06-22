"""Health and readiness endpoints for infrastructure monitoring."""

from __future__ import annotations

import asyncio
import logging
import os
import socket

import redis.asyncio as redis_async
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.db.session import engine
from app.domains.files import s3
from app.modules.health_checks import HealthCheckService

logger = logging.getLogger("app.api.health")
router = APIRouter(tags=["service"], include_in_schema=False)


async def _ping_postgres(app: FastAPI) -> None:
    session_factory = getattr(app.state, "test_sessionmaker", None)
    if session_factory is not None:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        return

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def _ping_redis(app: FastAPI, settings: Settings) -> None:
    client = getattr(app.state, "redis_client", None)
    if client is not None:
        await asyncio.wait_for(client.ping(), timeout=5.0)
        return

    broker_url = settings.redis.broker_url
    if broker_url.startswith("memory://"):
        # Dockerless / in-memory mode; no real Redis to reach.
        return

    redis = redis_async.from_url(broker_url)
    try:
        await asyncio.wait_for(redis.ping(), timeout=5.0)
    finally:
        await redis.close()


def _ping_minio(settings: Settings) -> None:
    if settings.s3_backend == "memory":
        return
    s3.ensure_bucket()
    list_keys = getattr(s3, "list_keys", None)
    if callable(list_keys):
        list_keys(prefix="", max_keys=1)


def _ping_clamav(settings: Settings) -> bool:
    av_enabled = str(os.getenv("AV_ENABLED", "false")).lower() == "true"
    if not av_enabled:
        return True
    with socket.create_connection((settings.clamav_host, settings.clamav_port), timeout=2):
        return True


def _ping_libreoffice(settings: Settings) -> bool:
    return bool(settings.libreoffice_bin)


def _resolve_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ok"})


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    settings = _resolve_settings(request)
    trace_id = request.headers.get(settings.trace_header_name) or "generated"

    statuses: dict[str, bool] = {
        "postgres": False,
        "redis": False,
        "minio": False,
        "clamav": False,
        "libreoffice": False,
    }

    try:
        await _ping_postgres(request.app)
        statuses["postgres"] = True
    except (SQLAlchemyError, Exception):
        logger.exception("health.ready.postgres_failed")

    try:
        await _ping_redis(request.app, settings)
        statuses["redis"] = True
    except Exception:
        logger.exception("health.ready.redis_failed")

    try:
        _ping_minio(settings)
        statuses["minio"] = True
    except (ClientError, BotoCoreError, Exception):
        logger.exception("health.ready.minio_failed")

    try:
        statuses["clamav"] = _ping_clamav(settings)
    except Exception:
        logger.exception("health.ready.clamav_failed")

    try:
        statuses["libreoffice"] = _ping_libreoffice(settings)
    except Exception:
        logger.exception("health.ready.libreoffice_failed")

    required_ok = statuses["postgres"] and statuses["redis"] and statuses["minio"]
    content = {
        "status": "ok" if required_ok else "degraded",
        "postgres": statuses["postgres"],
        "redis": statuses["redis"],
        "minio": statuses["minio"],
        "clamav": statuses["clamav"],
        "libreoffice": statuses["libreoffice"],
        "dependencies": statuses,
        "correlation_id": trace_id,
    }
    code = status.HTTP_200_OK if required_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content=content)


@router.get("/healthz")
async def healthz() -> JSONResponse:
    return await health()


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    return await ready(request)


@router.get("/api/v1/health/comprehensive", tags=["health"])
async def health_comprehensive(
    request: Request,
    skip_cache: bool = False,
    skip_slow: bool = False,
) -> JSONResponse:
    """
    Comprehensive health check for tenant admins.

    Checks critical dependencies (postgres, redis, minio) and optional services
    (workers, integrations, email). Results are cached for 60s by default.

    Query parameters:
    - skip_cache: Force fresh check (bypass cache)
    - skip_slow: Skip optional/slow checks (workers, integrations)

    Required headers:
    - X-Tenant-Id: Tenant ID for scoping

    Returns:
    - 200 OK: All checks passed (status="ok")
    - 503 Service Unavailable: Critical check failed (status="failed")
    - 503 Service Unavailable: Optional check failed (status="degraded")
    - 400 Bad Request: Missing X-Tenant-Id header
    - 403 Forbidden: Comprehensive health checks disabled
    """
    settings = _resolve_settings(request)

    if not settings.health_check_comprehensive_enabled:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "comprehensive health checks disabled"},
        )

    tenant_id = request.headers.get("X-Tenant-Id")
    if not tenant_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "X-Tenant-Id header required"},
        )

    try:
        service = HealthCheckService(settings)
        result = await service.run_all_checks(
            tenant_id=tenant_id,
            skip_cache=skip_cache,
            skip_slow=skip_slow,
        )

        code = status.HTTP_200_OK if result.status == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(status_code=code, content=result.model_dump(mode="json"))
    except Exception as e:
        logger.exception("health.comprehensive_failed")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "health check failed", "detail": str(e)[:100]},
        )


__all__ = ["router", "_ping_postgres", "_ping_redis"]
