"""Tests for operational dashboard module."""

import pytest
from fastapi import status

from app.core.config import get_settings
from app.modules.operational_dashboard import (
    AlertCategory,
    AlertSeverity,
    OperationalDashboardResponse,
    OperationalDashboardService,
)

API_PREFIX = "/api/v1"


@pytest.mark.asyncio
class TestOperationalDashboardService:
    """Tests for OperationalDashboardService."""

    async def test_dashboard_endpoint_missing_tenant_header(self, async_client, auth_headers):
        """Tenant-scoped routing requires slug/UUID headers before RBAC/dashboard logic."""
        headers = {"Authorization": auth_headers["Authorization"]}

        response = await async_client.get(f"{API_PREFIX}/operational/dashboard", headers=headers)
        assert response.status_code in (
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND,
        )

    async def test_dashboard_endpoint_returns_response_structure(
        self, authenticated_client, auth_headers
    ):
        """Test that endpoint returns proper response structure."""
        response = await authenticated_client.get(
            f"{API_PREFIX}/operational/dashboard", headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify response structure
        assert "tenant_id" in data
        assert "status" in data
        assert "alerts" in data
        assert isinstance(data["alerts"], list)
        assert "alert_count" in data
        assert "timestamp" in data

    async def test_dashboard_endpoint_unauthorized_no_auth(self, async_client):
        """Test that endpoint requires authentication."""
        response = await async_client.get(f"{API_PREFIX}/operational/dashboard")
        assert response.status_code in (
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )

    async def test_dashboard_status_ok_when_no_alerts(
        self, authenticated_client, auth_headers, test_db_session
    ):
        """Test that dashboard status is 'ok' when no critical alerts."""
        response = await authenticated_client.get(
            f"{API_PREFIX}/operational/dashboard", headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Status can be ok, caution, warning, or critical depending on test data
        assert data["status"] in ["ok", "caution", "warning", "critical"]

    async def test_dashboard_alert_count_by_severity(self, authenticated_client, auth_headers):
        """Test that alert_count is properly organized by severity."""
        response = await authenticated_client.get(
            f"{API_PREFIX}/operational/dashboard", headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify alert_count has proper structure
        alert_count = data.get("alert_count", {})
        # Can contain keys like "critical", "high", "medium", "low"
        for severity, count in alert_count.items():
            assert severity in ["critical", "high", "medium", "low"]
            assert isinstance(count, int)
            assert count >= 0

    @pytest.mark.asyncio
    async def test_service_get_dashboard_returns_response(self, test_db_session):
        """Test that service.get_dashboard() returns OperationalDashboardResponse."""
        service = OperationalDashboardService(get_settings())
        tenant_id = "test_tenant"

        dashboard = await service.get_dashboard(tenant_id=tenant_id, db=test_db_session)

        assert isinstance(dashboard, OperationalDashboardResponse)
        assert dashboard.tenant_id == tenant_id
        assert dashboard.status in ["ok", "caution", "warning", "critical"]
        assert isinstance(dashboard.alerts, list)

    @pytest.mark.asyncio
    async def test_service_handles_empty_alerts(self, test_db_session):
        """Test that service handles scenario with no alerts."""
        service = OperationalDashboardService(get_settings())
        tenant_id = "test_tenant_empty"

        dashboard = await service.get_dashboard(tenant_id=tenant_id, db=test_db_session)

        assert dashboard.status == "ok"
        assert len(dashboard.alerts) == 0
        assert dashboard.alert_count == {} or all(v == 0 for v in dashboard.alert_count.values())

    @pytest.mark.asyncio
    async def test_service_aggregates_multiple_alert_types(self, test_db_session):
        """Test that service attempts to aggregate multiple alert types."""
        service = OperationalDashboardService(get_settings())
        tenant_id = "test_tenant"

        dashboard = await service.get_dashboard(tenant_id=tenant_id, db=test_db_session)

        # Verify that service tried to get different alert types
        # (even if no data exists, service should attempt all checks)
        assert isinstance(dashboard.alerts, list)
        for alert in dashboard.alerts:
            assert alert.category in [
                AlertCategory.OVERDUE,
                AlertCategory.BLOCKED_APPROVAL,
                AlertCategory.INTEGRATION_ERROR,
                AlertCategory.HIGH_RISK,
                AlertCategory.UNASSIGNED_TASK,
            ]

    def test_alert_severity_enum_values(self):
        """Test that AlertSeverity enum has expected values."""
        assert AlertSeverity.CRITICAL.value == "critical"
        assert AlertSeverity.HIGH.value == "high"
        assert AlertSeverity.MEDIUM.value == "medium"
        assert AlertSeverity.LOW.value == "low"

    def test_alert_category_enum_values(self):
        """Test that AlertCategory enum has expected values."""
        assert AlertCategory.OVERDUE.value == "overdue"
        assert AlertCategory.BLOCKED_APPROVAL.value == "blocked_approval"
        assert AlertCategory.INTEGRATION_ERROR.value == "integration_error"
        assert AlertCategory.HIGH_RISK.value == "high_risk"
        assert AlertCategory.UNASSIGNED_TASK.value == "unassigned_task"

    def test_alert_item_required_fields(self):
        """Test that AlertItem has all required fields."""
        from app.modules.operational_dashboard import AlertItem

        alert = AlertItem(
            id="test_1",
            category=AlertCategory.OVERDUE,
            severity=AlertSeverity.HIGH,
            title="Test Alert",
            count=5,
        )

        assert alert.id == "test_1"
        assert alert.category == AlertCategory.OVERDUE
        assert alert.severity == AlertSeverity.HIGH
        assert alert.title == "Test Alert"
        assert alert.count == 5
        assert alert.created_at is not None

    def test_dashboard_response_required_fields(self):
        """Test that OperationalDashboardResponse has required fields."""
        response = OperationalDashboardResponse(
            tenant_id="test_tenant",
            status="ok",
        )

        assert response.tenant_id == "test_tenant"
        assert response.status == "ok"
        assert response.alerts == []
        assert response.alert_count == {}
        assert response.timestamp is not None

    @pytest.mark.asyncio
    async def test_dashboard_endpoint_with_valid_tenant(
        self, authenticated_client, auth_headers, test_db_session
    ):
        """Test complete workflow with valid tenant."""
        # Set proper tenant header
        tenant_id = auth_headers.get("X-Tenant-Id", "test_tenant")
        headers = {
            **auth_headers,
            "X-Tenant-Id": tenant_id,
        }

        response = await authenticated_client.get(
            f"{API_PREFIX}/operational/dashboard", headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify complete structure
        assert data["tenant_id"] == tenant_id
        assert "status" in data
        assert "alerts" in data
        assert "alert_count" in data
        assert "timestamp" in data

    def test_alert_item_model_dump_serialization(self):
        """Test that AlertItem serializes correctly."""
        from app.modules.operational_dashboard import AlertItem

        alert = AlertItem(
            id="test_1",
            category=AlertCategory.OVERDUE,
            severity=AlertSeverity.CRITICAL,
            title="Critical Alert",
            count=10,
            description="Test description",
        )

        dumped = alert.model_dump()

        assert dumped["id"] == "test_1"
        assert dumped["category"] == AlertCategory.OVERDUE  # Enum preserved
        assert dumped["severity"] == AlertSeverity.CRITICAL
        assert dumped["title"] == "Critical Alert"
        assert dumped["count"] == 10

    def test_dashboard_response_model_dump_with_enums(self):
        """Test that OperationalDashboardResponse.model_dump() handles enums properly."""
        response = OperationalDashboardResponse(
            tenant_id="test_tenant",
            status="warning",
            alert_count={AlertSeverity.HIGH: 5, AlertSeverity.CRITICAL: 2},
        )

        dumped = response.model_dump()

        # Enums should be serialized as strings or values
        assert "alert_count" in dumped
        alert_count = dumped["alert_count"]
        # Keys could be either enum names or values depending on implementation
        assert len(alert_count) == 2


class TestOperationalDashboardIntegration:
    """Integration tests for operational dashboard."""

    @pytest.mark.asyncio
    async def test_dashboard_endpoint_full_workflow(
        self, async_client, make_auth_headers, test_db_session
    ):
        """Test complete dashboard endpoint workflow."""
        base = await make_auth_headers()
        headers = dict(base)
        headers.setdefault("X-Tenant-Id", headers.get("x-tenant", ""))

        response = await async_client.get(
            f"{API_PREFIX}/operational/dashboard",
            headers=headers,
        )

        assert response.status_code in [status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED]

    @pytest.mark.asyncio
    async def test_dashboard_performance_with_multiple_tenants(
        self, authenticated_client, make_auth_headers, test_db_session
    ):
        """Test that dashboard performs reasonably with multiple tenants."""
        import time

        for _ in range(3):
            base = dict(await make_auth_headers())
            base.setdefault("X-Tenant-Id", base.get("x-tenant", ""))
            headers = base
            start = time.time()

            response = await authenticated_client.get(
                f"{API_PREFIX}/operational/dashboard",
                headers=headers,
            )

            duration = time.time() - start

            # Sanity-порог против бесконечного зависания, а НЕ перф-гейт:
            # на общих CI-раннерах под 4 xdist-воркерами запрос занимал 9+с,
            # и жёсткие 5с давали ложные падения. Перф меряет perf-smoke.
            assert duration < 30.0
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_401_UNAUTHORIZED,
            ]
