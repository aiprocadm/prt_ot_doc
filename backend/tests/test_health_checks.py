"""Tests for health check module (Phase 2.2)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import Settings
from app.modules.health_checks.schemas import (
    HealthCheckComprehensiveResponse,
    HealthCheckItem,
)
from app.modules.health_checks.service import HealthCheckCache, HealthCheckService


@pytest.fixture
def settings():
    """Mock settings for tests."""
    return Settings(
        health_check_comprehensive_enabled=True,
        health_check_cache_ttl_seconds=60,
        health_check_timeout_per_check_seconds=5,
        use_1c_integration=True,
        use_edo_integration=True,
        webhook_notification_url="http://example.com/webhook",
        s3_backend="s3",
        redis_broker_url="redis://localhost",
    )


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


class TestHealthCheckCache:
    """Tests for HealthCheckCache."""

    def test_cache_set_and_get(self):
        """Test setting and getting cached result."""
        cache = HealthCheckCache(ttl_seconds=60)
        item = HealthCheckItem(name="test", status="ok", duration_ms=10.0)
        response = HealthCheckComprehensiveResponse(
            status="ok",
            checks={"test": item},
            tenant_id="tenant-1",
        )

        cache.set("tenant-1", response)
        result = cache.get("tenant-1")

        assert result is not None
        assert result.tenant_id == "tenant-1"
        assert result.status == "ok"

    def test_cache_expiration(self):
        """Test cache expiration after TTL."""
        cache = HealthCheckCache(ttl_seconds=1)  # 1 second TTL
        item = HealthCheckItem(name="test", status="ok", duration_ms=10.0)
        response = HealthCheckComprehensiveResponse(
            status="ok",
            checks={"test": item},
            tenant_id="tenant-1",
        )

        cache.set("tenant-1", response)
        assert cache.get("tenant-1") is not None

        # Wait for expiration
        import time
        time.sleep(1.1)
        assert cache.get("tenant-1") is None

    def test_cache_clear_all(self):
        """Test clearing all cache entries."""
        cache = HealthCheckCache(ttl_seconds=60)
        item = HealthCheckItem(name="test", status="ok", duration_ms=10.0)
        response = HealthCheckComprehensiveResponse(
            status="ok",
            checks={"test": item},
            tenant_id="tenant-1",
        )

        cache.set("tenant-1", response)
        cache.set("tenant-2", response)
        assert cache.get("tenant-1") is not None
        assert cache.get("tenant-2") is not None

        cache.clear()
        assert cache.get("tenant-1") is None
        assert cache.get("tenant-2") is None

    def test_cache_clear_single(self):
        """Test clearing single cache entry."""
        cache = HealthCheckCache(ttl_seconds=60)
        item = HealthCheckItem(name="test", status="ok", duration_ms=10.0)
        response = HealthCheckComprehensiveResponse(
            status="ok",
            checks={"test": item},
            tenant_id="tenant-1",
        )

        cache.set("tenant-1", response)
        cache.set("tenant-2", response)
        cache.clear("tenant-1")

        assert cache.get("tenant-1") is None
        assert cache.get("tenant-2") is not None


class TestHealthCheckService:
    """Tests for HealthCheckService."""

    @pytest.mark.asyncio
    async def test_check_postgres_success(self, settings):
        """Test successful PostgreSQL check."""
        service = HealthCheckService(settings)
        with patch("app.modules.health_checks.service.engine") as mock_engine:
            mock_connection = AsyncMock()
            mock_engine.connect = MagicMock()
            mock_engine.connect.return_value.__aenter__ = AsyncMock(
                return_value=mock_connection
            )
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_connection.execute = AsyncMock()

            result = await service.check_postgres()
            assert result.name == "postgres"
            assert result.status == "ok"
            assert result.error is None
            assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_check_redis_success(self, settings):
        """Test successful Redis check (in-memory mode)."""
        settings.redis.broker_url = "memory://"
        service = HealthCheckService(settings)
        result = await service.check_redis()

        assert result.name == "redis"
        assert result.status == "ok"
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_check_minio_success(self, settings):
        """Test successful MinIO check (in-memory mode)."""
        settings.s3_backend = "memory"
        service = HealthCheckService(settings)
        result = await service.check_minio()

        assert result.name == "minio"
        assert result.status == "ok"
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_check_1c_integration_disabled(self, settings):
        """Test 1C integration check when disabled."""
        settings.use_1c_integration = False
        service = HealthCheckService(settings)
        result = await service.check_1c_integration()

        assert result.name == "1c_integration"
        assert result.status == "ok"
        assert result.error == "disabled"

    @pytest.mark.asyncio
    async def test_check_edo_integration_disabled(self, settings):
        """Test EDO integration check when disabled."""
        settings.use_edo_integration = False
        service = HealthCheckService(settings)
        result = await service.check_edo_integration()

        assert result.name == "edo_integration"
        assert result.status == "ok"
        assert result.error == "disabled"

    @pytest.mark.asyncio
    async def test_check_email_not_configured(self, settings):
        """Test email check when not configured."""
        settings.webhook_notification_url = None
        service = HealthCheckService(settings)
        result = await service.check_email()

        assert result.name == "email"
        assert result.status == "ok"
        assert result.error == "not configured"

    @pytest.mark.asyncio
    async def test_run_all_checks_success(self, settings):
        """Test running all checks successfully."""
        settings.s3_backend = "memory"
        settings.redis.broker_url = "memory://"
        service = HealthCheckService(settings)

        with patch("app.modules.health_checks.service.engine") as mock_engine:
            mock_connection = AsyncMock()
            mock_engine.connect = MagicMock()
            mock_engine.connect.return_value.__aenter__ = AsyncMock(
                return_value=mock_connection
            )
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_connection.execute = AsyncMock()

            result = await service.run_all_checks(tenant_id="test-tenant")
            assert result.status == "ok"
            assert result.tenant_id == "test-tenant"
            assert len(result.checks) >= 3  # At least postgres, redis, minio

    @pytest.mark.asyncio
    async def test_run_all_checks_skip_slow(self, settings):
        """Test running checks with skip_slow=True."""
        settings.s3_backend = "memory"
        settings.redis.broker_url = "memory://"
        service = HealthCheckService(settings)

        with patch("app.modules.health_checks.service.engine") as mock_engine:
            mock_connection = AsyncMock()
            mock_engine.connect = MagicMock()
            mock_engine.connect.return_value.__aenter__ = AsyncMock(
                return_value=mock_connection
            )
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_connection.execute = AsyncMock()

            result = await service.run_all_checks(
                tenant_id="test-tenant", skip_slow=True
            )
            assert result.status == "ok"
            assert "postgres" in result.checks
            assert "redis" in result.checks
            assert "minio" in result.checks
            # Optional checks should not be present
            assert len(result.checks) == 3

    @pytest.mark.asyncio
    async def test_run_all_checks_cache(self, settings):
        """Test caching of health check results."""
        settings.s3_backend = "memory"
        settings.redis.broker_url = "memory://"
        service = HealthCheckService(settings)

        with patch("app.modules.health_checks.service.engine") as mock_engine:
            mock_connection = AsyncMock()
            mock_engine.connect = MagicMock()
            mock_engine.connect.return_value.__aenter__ = AsyncMock(
                return_value=mock_connection
            )
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_connection.execute = AsyncMock()

            # First call - should execute all checks
            result1 = await service.run_all_checks(tenant_id="test-tenant")
            first_timestamp = result1.timestamp

            # Second call - should return cached result
            result2 = await service.run_all_checks(tenant_id="test-tenant")
            assert result2.timestamp == first_timestamp  # Same timestamp = cached

            # Third call with skip_cache - should be different
            result3 = await service.run_all_checks(
                tenant_id="test-tenant", skip_cache=True
            )
            assert result3.timestamp > first_timestamp  # Different timestamp

    @pytest.mark.asyncio
    async def test_run_all_checks_degraded_status(self, settings):
        """Test degraded status when optional check fails."""
        settings.s3_backend = "memory"
        settings.redis.broker_url = "memory://"
        service = HealthCheckService(settings)

        with patch("app.modules.health_checks.service.engine") as mock_engine:
            mock_connection = AsyncMock()
            mock_engine.connect = MagicMock()
            mock_engine.connect.return_value.__aenter__ = AsyncMock(
                return_value=mock_connection
            )
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_connection.execute = AsyncMock()

            with patch.object(
                service, "check_workers", new_callable=AsyncMock
            ) as mock_workers:
                mock_workers.return_value = HealthCheckItem(
                    name="workers", status="failed", error="no workers"
                )

                result = await service.run_all_checks(tenant_id="test-tenant")
                # Critical checks pass, optional fails → degraded
                assert result.status == "degraded"


class TestHealthCheckEndpoint:
    """Tests for /api/v1/health/comprehensive endpoint."""

    def test_health_comprehensive_missing_tenant_header(self, client):
        """Test endpoint returns 400 when X-Tenant-Id header is missing."""
        response = client.get("/api/v1/health/comprehensive")
        assert response.status_code == 400
        assert "X-Tenant-Id header required" in response.text

    def test_health_comprehensive_disabled(self, client):
        """Test endpoint returns 403 when feature is disabled."""
        with patch("app.api.routes.health.get_settings") as mock_settings:
            mock_settings.return_value.health_check_comprehensive_enabled = False
            response = client.get(
                "/api/v1/health/comprehensive",
                headers={"X-Tenant-Id": "test-tenant"},
            )
            assert response.status_code == 403
            assert "disabled" in response.text

    def test_health_comprehensive_success(self, client):
        """Test successful health comprehensive endpoint call."""
        with patch("app.api.routes.health.HealthCheckService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            item = HealthCheckItem(name="postgres", status="ok", duration_ms=10.0)
            response_obj = HealthCheckComprehensiveResponse(
                status="ok",
                checks={"postgres": item},
                tenant_id="test-tenant",
            )
            mock_service.run_all_checks = AsyncMock(return_value=response_obj)

            response = client.get(
                "/api/v1/health/comprehensive",
                headers={"X-Tenant-Id": "test-tenant"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["tenant_id"] == "test-tenant"

    def test_health_comprehensive_skip_cache(self, client):
        """Test skip_cache query parameter."""
        with patch("app.api.routes.health.HealthCheckService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            item = HealthCheckItem(name="postgres", status="ok", duration_ms=10.0)
            response_obj = HealthCheckComprehensiveResponse(
                status="ok",
                checks={"postgres": item},
                tenant_id="test-tenant",
            )
            mock_service.run_all_checks = AsyncMock(return_value=response_obj)

            response = client.get(
                "/api/v1/health/comprehensive?skip_cache=true",
                headers={"X-Tenant-Id": "test-tenant"},
            )
            assert response.status_code == 200
            # Verify skip_cache was passed
            mock_service.run_all_checks.assert_called_once()
            call_kwargs = mock_service.run_all_checks.call_args[1]
            assert call_kwargs["skip_cache"] is True
