"""Health check service for operational diagnostics."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta

import redis.asyncio as redis_async
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.db.session import engine
from app.domains.files import s3
from app.modules.health_checks.schemas import (
    HealthCheckComprehensiveResponse,
    HealthCheckItem,
)
from app.services.celery_app import celery_app

logger = logging.getLogger("app.modules.health_checks")


class HealthCheckCache:
    """Simple in-memory cache for health check results."""

    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self.cache: dict[str, tuple[datetime, HealthCheckComprehensiveResponse]] = {}

    def get(self, tenant_id: str) -> HealthCheckComprehensiveResponse | None:
        """Get cached result if not expired."""
        if tenant_id not in self.cache:
            return None
        stored_time, result = self.cache[tenant_id]
        if datetime.utcnow() - stored_time > timedelta(seconds=self.ttl):
            del self.cache[tenant_id]
            return None
        return result

    def set(
        self, tenant_id: str, result: HealthCheckComprehensiveResponse
    ) -> None:
        """Cache a result."""
        self.cache[tenant_id] = (datetime.utcnow(), result)

    def clear(self, tenant_id: str | None = None) -> None:
        """Clear cache (optionally for a specific tenant)."""
        if tenant_id:
            self.cache.pop(tenant_id, None)
        else:
            self.cache.clear()


class HealthCheckService:
    """Service for comprehensive health checks."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache = HealthCheckCache(settings.health_check_cache_ttl_seconds)
        self.timeout = settings.health_check_timeout_per_check_seconds

    async def check_postgres(self) -> HealthCheckItem:
        """Check PostgreSQL connectivity."""
        start = time.time()
        try:
            async with asyncio.timeout(self.timeout):
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="postgres",
                status="ok",
                duration_ms=round(duration, 2),
            )
        except asyncio.TimeoutError:
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="postgres",
                status="failed",
                error="timeout",
                duration_ms=round(duration, 2),
            )
        except (SQLAlchemyError, Exception) as e:
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="postgres",
                status="failed",
                error=str(e)[:100],
                duration_ms=round(duration, 2),
            )

    async def check_redis(self) -> HealthCheckItem:
        """Check Redis connectivity."""
        start = time.time()
        try:
            broker_url = self.settings.redis.broker_url
            if broker_url.startswith("memory://"):
                duration = (time.time() - start) * 1000
                return HealthCheckItem(
                    name="redis",
                    status="ok",
                    error="in-memory mode",
                    duration_ms=round(duration, 2),
                )

            redis = redis_async.from_url(broker_url)
            try:
                async with asyncio.timeout(self.timeout):
                    await redis.ping()
                duration = (time.time() - start) * 1000
                return HealthCheckItem(
                    name="redis",
                    status="ok",
                    duration_ms=round(duration, 2),
                )
            finally:
                await redis.close()
        except asyncio.TimeoutError:
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="redis",
                status="failed",
                error="timeout",
                duration_ms=round(duration, 2),
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="redis",
                status="failed",
                error=str(e)[:100],
                duration_ms=round(duration, 2),
            )

    async def check_minio(self) -> HealthCheckItem:
        """Check MinIO/S3 connectivity."""
        start = time.time()
        try:
            if self.settings.s3_backend == "memory":
                duration = (time.time() - start) * 1000
                return HealthCheckItem(
                    name="minio",
                    status="ok",
                    error="in-memory mode",
                    duration_ms=round(duration, 2),
                )

            async with asyncio.timeout(self.timeout):
                s3.ensure_bucket()
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="minio",
                status="ok",
                duration_ms=round(duration, 2),
            )
        except asyncio.TimeoutError:
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="minio",
                status="failed",
                error="timeout",
                duration_ms=round(duration, 2),
            )
        except (ClientError, BotoCoreError, Exception) as e:
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="minio",
                status="failed",
                error=str(e)[:100],
                duration_ms=round(duration, 2),
            )

    async def check_workers(self) -> HealthCheckItem:
        """Check Celery workers status."""
        start = time.time()
        try:
            async with asyncio.timeout(self.timeout):
                inspector = celery_app.control.inspect()
                active_workers = inspector.active()
                worker_count = len(active_workers) if active_workers else 0

                if worker_count == 0:
                    duration = (time.time() - start) * 1000
                    return HealthCheckItem(
                        name="workers",
                        status="degraded",
                        error="no active workers",
                        duration_ms=round(duration, 2),
                    )

                duration = (time.time() - start) * 1000
                return HealthCheckItem(
                    name="workers",
                    status="ok",
                    error=f"{worker_count} active",
                    duration_ms=round(duration, 2),
                )
        except asyncio.TimeoutError:
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="workers",
                status="failed",
                error="timeout",
                duration_ms=round(duration, 2),
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="workers",
                status="failed",
                error=str(e)[:100],
                duration_ms=round(duration, 2),
            )

    async def check_1c_integration(self) -> HealthCheckItem:
        """Check 1С integration status."""
        start = time.time()
        try:
            if not self.settings.use_1c_integration:
                duration = (time.time() - start) * 1000
                return HealthCheckItem(
                    name="1c_integration",
                    status="ok",
                    error="disabled",
                    duration_ms=round(duration, 2),
                )
            # For now, just check if enabled
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="1c_integration",
                status="ok",
                duration_ms=round(duration, 2),
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="1c_integration",
                status="failed",
                error=str(e)[:100],
                duration_ms=round(duration, 2),
            )

    async def check_edo_integration(self) -> HealthCheckItem:
        """Check EDO integration status."""
        start = time.time()
        try:
            if not self.settings.use_edo_integration:
                duration = (time.time() - start) * 1000
                return HealthCheckItem(
                    name="edo_integration",
                    status="ok",
                    error="disabled",
                    duration_ms=round(duration, 2),
                )
            # For now, just check if enabled
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="edo_integration",
                status="ok",
                duration_ms=round(duration, 2),
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="edo_integration",
                status="failed",
                error=str(e)[:100],
                duration_ms=round(duration, 2),
            )

    async def check_email(self) -> HealthCheckItem:
        """Check email/webhook configuration."""
        start = time.time()
        try:
            # Simple check: verify webhook URLs are configured
            if not self.settings.webhook_notification_url:
                duration = (time.time() - start) * 1000
                return HealthCheckItem(
                    name="email",
                    status="ok",
                    error="not configured",
                    duration_ms=round(duration, 2),
                )

            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="email",
                status="ok",
                duration_ms=round(duration, 2),
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckItem(
                name="email",
                status="failed",
                error=str(e)[:100],
                duration_ms=round(duration, 2),
            )

    async def run_all_checks(
        self,
        tenant_id: str,
        skip_cache: bool = False,
        skip_slow: bool = False,
    ) -> HealthCheckComprehensiveResponse:
        """Run all health checks and return comprehensive response."""
        # Check cache first
        if not skip_cache:
            cached = self.cache.get(tenant_id)
            if cached:
                return cached

        # Run all checks in parallel
        results = {}

        # Critical checks (always run)
        critical_tasks = [
            self.check_postgres(),
            self.check_redis(),
            self.check_minio(),
        ]

        # Optional checks (skip if skip_slow is True)
        optional_tasks = [
            self.check_workers(),
            self.check_1c_integration(),
            self.check_edo_integration(),
            self.check_email(),
        ]

        tasks_to_run = critical_tasks + ([] if skip_slow else optional_tasks)

        # Execute all checks in parallel
        check_results = await asyncio.gather(*tasks_to_run, return_exceptions=False)

        for check_result in check_results:
            if isinstance(check_result, HealthCheckItem):
                results[check_result.name] = check_result

        # Determine overall status
        # Failed critical checks → "failed"
        # Failed optional checks → "degraded"
        # All ok → "ok"
        has_failed_critical = any(
            results.get(check, HealthCheckItem(name="", status="unknown", duration_ms=0.0)).status
            == "failed"
            for check in ["postgres", "redis", "minio"]
        )

        has_failed_optional = any(
            results.get(check, HealthCheckItem(name="", status="unknown", duration_ms=0.0)).status
            == "failed"
            for check in results.keys()
            if check not in ["postgres", "redis", "minio"]
        )

        if has_failed_critical:
            overall_status = "failed"
        elif has_failed_optional:
            overall_status = "degraded"
        else:
            overall_status = "ok"

        response = HealthCheckComprehensiveResponse(
            status=overall_status,
            checks=results,
            tenant_id=tenant_id,
        )

        # Cache the result
        self.cache.set(tenant_id, response)

        return response
