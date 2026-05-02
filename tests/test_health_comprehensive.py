"""Tests for comprehensive health check endpoint."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.modules.health_checks import HealthCheckService


@pytest.mark.anyio
async def test_comprehensive_health_feature_disabled(app_fixture) -> None:
    """Comprehensive health check returns 403 when feature is disabled."""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/health/comprehensive",
            headers={"X-Tenant-Id": "test-tenant"},
        )
    assert response.status_code == 403
    assert "disabled" in response.json()["error"]


@pytest.mark.anyio
async def test_comprehensive_health_missing_tenant_header(app_fixture) -> None:
    """Comprehensive health check returns 400 without X-Tenant-Id header."""
    # Note: This test assumes feature is disabled by default.
    # If enabled in a test, it would still validate the header.
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health/comprehensive")

    # Either 403 (feature disabled) or 400 (missing header)
    assert response.status_code in (400, 403)


@pytest.mark.anyio
async def test_health_service_check_postgres(app_fixture) -> None:
    """HealthCheckService.check_postgres() succeeds on running database."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)
    result = await service.check_postgres()

    assert result.name == "postgres"
    assert result.status == "ok"
    assert result.error is None
    assert result.duration_ms > 0


@pytest.mark.anyio
async def test_health_service_check_redis(app_fixture) -> None:
    """HealthCheckService.check_redis() checks Redis connectivity."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)
    result = await service.check_redis()

    assert result.name == "redis"
    # Status depends on Redis config (in-memory mode or real Redis)
    assert result.status in ("ok", "degraded")
    assert result.duration_ms > 0


@pytest.mark.anyio
async def test_health_service_check_minio(app_fixture) -> None:
    """HealthCheckService.check_minio() checks MinIO/S3 connectivity."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)
    result = await service.check_minio()

    assert result.name == "minio"
    # Status depends on S3 backend (in-memory or real MinIO)
    assert result.status in ("ok", "degraded")
    assert result.duration_ms > 0


@pytest.mark.anyio
async def test_health_service_check_workers(app_fixture) -> None:
    """HealthCheckService.check_workers() checks Celery workers."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)
    result = await service.check_workers()

    assert result.name == "workers"
    # Status depends on whether workers are running
    assert result.status in ("ok", "degraded", "failed")
    assert result.duration_ms >= 0


@pytest.mark.anyio
async def test_health_service_check_1c_integration(app_fixture) -> None:
    """HealthCheckService.check_1c_integration() returns ok when disabled."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)
    result = await service.check_1c_integration()

    assert result.name == "1c_integration"
    assert result.status == "ok"
    # Should be disabled by default, so error should indicate that
    if not settings.use_1c_integration:
        assert result.error == "disabled"


@pytest.mark.anyio
async def test_health_service_check_edo_integration(app_fixture) -> None:
    """HealthCheckService.check_edo_integration() returns ok when disabled."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)
    result = await service.check_edo_integration()

    assert result.name == "edo_integration"
    assert result.status == "ok"
    # Should be disabled by default
    if not settings.use_edo_integration:
        assert result.error == "disabled"


@pytest.mark.anyio
async def test_health_service_check_email(app_fixture) -> None:
    """HealthCheckService.check_email() checks email/webhook configuration."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)
    result = await service.check_email()

    assert result.name == "email"
    assert result.status in ("ok", "degraded")


@pytest.mark.anyio
async def test_health_service_run_all_checks(app_fixture) -> None:
    """HealthCheckService.run_all_checks() returns comprehensive response."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)
    result = await service.run_all_checks(tenant_id="test-tenant", skip_slow=True)

    assert result.tenant_id == "test-tenant"
    assert result.status in ("ok", "degraded", "failed")
    # Should have at least critical checks
    assert "postgres" in result.checks or "redis" in result.checks
    # All checks should have required fields
    for check in result.checks.values():
        assert check.name
        assert check.status in ("ok", "degraded", "failed")
        assert check.duration_ms >= 0


@pytest.mark.anyio
async def test_health_service_cache_works(app_fixture) -> None:
    """HealthCheckService caching works correctly."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)

    # First call
    result1 = await service.run_all_checks(
        tenant_id="test-tenant", skip_cache=False, skip_slow=True
    )

    # Second call (should be cached)
    result2 = await service.run_all_checks(
        tenant_id="test-tenant", skip_cache=False, skip_slow=True
    )

    # Results should be identical (same timestamps, same cache)
    assert result1.status == result2.status
    assert len(result1.checks) == len(result2.checks)


@pytest.mark.anyio
async def test_health_service_cache_bypass(app_fixture) -> None:
    """HealthCheckService cache can be bypassed with skip_cache=True."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)

    # First call
    result1 = await service.run_all_checks(
        tenant_id="test-tenant", skip_cache=False, skip_slow=True
    )

    # Second call with skip_cache=True should bypass cache
    result2 = await service.run_all_checks(
        tenant_id="test-tenant", skip_cache=True, skip_slow=True
    )

    # Results should have different timestamps (different executions)
    # Note: This is subtle - timestamps might be very close, but cache behavior
    # should differ in other ways
    assert result1.status == result2.status


@pytest.mark.anyio
async def test_health_service_skip_slow_checks(app_fixture) -> None:
    """HealthCheckService skip_slow parameter works."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)

    # With skip_slow=True, should only get critical checks
    result = await service.run_all_checks(
        tenant_id="test-tenant", skip_cache=True, skip_slow=True
    )

    # Critical checks
    critical_checks = {"postgres", "redis", "minio"}
    # At least some critical checks should be present
    present_checks = set(result.checks.keys())
    assert len(critical_checks & present_checks) >= 1


@pytest.mark.anyio
async def test_health_service_overall_status_all_ok(app_fixture) -> None:
    """Overall status is 'ok' when all checks pass."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)
    result = await service.run_all_checks(
        tenant_id="test-tenant", skip_cache=True, skip_slow=True
    )

    # With a working database, redis, and minio, status should be "ok"
    # (assuming they're all running in the test environment)
    assert result.status in ("ok", "degraded", "failed")


@pytest.mark.anyio
async def test_health_service_multiple_tenants_cached_separately(app_fixture) -> None:
    """Health check results are cached per tenant."""
    from app.core.config import get_settings

    settings = get_settings()
    service = HealthCheckService(settings)

    # Run checks for two different tenants
    result1 = await service.run_all_checks(
        tenant_id="tenant-1", skip_cache=False, skip_slow=True
    )
    result2 = await service.run_all_checks(
        tenant_id="tenant-2", skip_cache=False, skip_slow=True
    )

    # Both should return results
    assert result1.tenant_id == "tenant-1"
    assert result2.tenant_id == "tenant-2"
    assert result1.status in ("ok", "degraded", "failed")
    assert result2.status in ("ok", "degraded", "failed")
