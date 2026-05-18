"""Analytics aggregation service tests
(Phase 8.1 / vNext-ANALYTICS-02, Session 44).

Pins the contract for ``app.modules.analytics.services`` —
``AnalyticsAggregationService`` and ``KpiDashboardService`` — which power
every ``/api/v1/analytics/dashboard/*`` and ``/trends/*`` endpoint.

Before this session there were no direct service-layer tests; the only
analytics coverage was the end-to-end search/export center suite. These
tests exercise the aggregation logic directly against in-memory projection
read-models, which keeps the suite fast and deterministic.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.models import Tenant
from app.modules.analytics.services import (
    AnalyticsAggregationService,
    DashboardFilters,
    KpiDashboardService,
)
from app.modules.projections.models import (
    ContractorReadinessReadModel,
    PackageReadModel,
    PersonComplianceReadModel,
    SiteSafetyReadModel,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _seed_package(
    session,
    *,
    tenant_id: str,
    package_id: str = "pkg-1",
    status: str = "new",
    client_company_id: str | None = None,
    site_id: str | None = None,
) -> PackageReadModel:
    row = PackageReadModel(
        tenant_id=tenant_id,
        package_id=package_id,
        status=status,
        client_company_id=client_company_id,
        site_id=site_id,
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_person_compliance(
    session,
    *,
    tenant_id: str,
    person_id: str = "p-1",
    readiness_status: str = "ready",
    site_id: str | None = None,
    overdue_trainings: int = 0,
    overdue_briefings: int = 0,
) -> PersonComplianceReadModel:
    row = PersonComplianceReadModel(
        tenant_id=tenant_id,
        person_id=person_id,
        readiness_status=readiness_status,
        site_id=site_id,
        overdue_trainings=overdue_trainings,
        overdue_briefings=overdue_briefings,
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_site_safety(
    session,
    *,
    tenant_id: str,
    site_id: str = "s-1",
    open_incidents_count: int = 0,
    open_inspections_count: int = 0,
) -> SiteSafetyReadModel:
    row = SiteSafetyReadModel(
        tenant_id=tenant_id,
        site_id=site_id,
        open_incidents_count=open_incidents_count,
        open_inspections_count=open_inspections_count,
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_contractor_readiness(
    session,
    *,
    tenant_id: str,
    contractor_id: str = "c-1",
    active_packages_count: int = 0,
) -> ContractorReadinessReadModel:
    row = ContractorReadinessReadModel(
        tenant_id=tenant_id,
        contractor_id=contractor_id,
        active_packages_count=active_packages_count,
    )
    session.add(row)
    await session.flush()
    return row


async def _tenant_id(session) -> str:
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
    return str(tenant.id)


# =============================================================================
# base_counters
# =============================================================================


@pytest.mark.anyio
async def test_base_counters_returns_zeros_for_empty_tenant(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        service = AnalyticsAggregationService(session, tenant_id)
        counters = await service.base_counters(DashboardFilters())
    assert counters == {
        "packages_total": 0,
        "overdue_compliance_items": 0,
        "open_incidents": 0,
        "open_inspections": 0,
    }


@pytest.mark.anyio
async def test_base_counters_counts_packages(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_package(session, tenant_id=tenant_id, package_id="p1")
        await _seed_package(session, tenant_id=tenant_id, package_id="p2", status="active")
        await session.commit()

        counters = await AnalyticsAggregationService(session, tenant_id).base_counters(
            DashboardFilters()
        )
    assert counters["packages_total"] == 2


@pytest.mark.anyio
async def test_base_counters_filters_packages_by_status(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_package(session, tenant_id=tenant_id, package_id="p1", status="new")
        await _seed_package(session, tenant_id=tenant_id, package_id="p2", status="active")
        await _seed_package(session, tenant_id=tenant_id, package_id="p3", status="active")
        await session.commit()

        counters = await AnalyticsAggregationService(session, tenant_id).base_counters(
            DashboardFilters(status="active")
        )
    assert counters["packages_total"] == 2


@pytest.mark.anyio
async def test_base_counters_filters_packages_by_company_id(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_package(session, tenant_id=tenant_id, package_id="p1", client_company_id="co-A")
        await _seed_package(session, tenant_id=tenant_id, package_id="p2", client_company_id="co-B")
        await session.commit()

        counters = await AnalyticsAggregationService(session, tenant_id).base_counters(
            DashboardFilters(company_id="co-A")
        )
    assert counters["packages_total"] == 1


@pytest.mark.anyio
async def test_base_counters_filters_packages_by_site_id(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_package(session, tenant_id=tenant_id, package_id="p1", site_id="s-A")
        await _seed_package(session, tenant_id=tenant_id, package_id="p2", site_id="s-B")
        await session.commit()

        counters = await AnalyticsAggregationService(session, tenant_id).base_counters(
            DashboardFilters(site_id="s-A")
        )
    assert counters["packages_total"] == 1


@pytest.mark.anyio
async def test_base_counters_overdue_compliance_counts_blocked_only(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_person_compliance(
            session, tenant_id=tenant_id, person_id="p-blocked", readiness_status="blocked"
        )
        await _seed_person_compliance(
            session, tenant_id=tenant_id, person_id="p-ready", readiness_status="ready"
        )
        await _seed_person_compliance(
            session, tenant_id=tenant_id, person_id="p-also-blocked", readiness_status="blocked"
        )
        await session.commit()

        counters = await AnalyticsAggregationService(session, tenant_id).base_counters(
            DashboardFilters()
        )
    assert counters["overdue_compliance_items"] == 2


@pytest.mark.anyio
async def test_base_counters_overdue_compliance_filtered_by_site(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_person_compliance(
            session, tenant_id=tenant_id, person_id="p1",
            readiness_status="blocked", site_id="s-A",
        )
        await _seed_person_compliance(
            session, tenant_id=tenant_id, person_id="p2",
            readiness_status="blocked", site_id="s-B",
        )
        await session.commit()

        counters = await AnalyticsAggregationService(session, tenant_id).base_counters(
            DashboardFilters(site_id="s-A")
        )
    assert counters["overdue_compliance_items"] == 1


@pytest.mark.anyio
async def test_base_counters_sums_open_incidents_across_sites(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_site_safety(
            session, tenant_id=tenant_id, site_id="s1",
            open_incidents_count=2, open_inspections_count=3,
        )
        await _seed_site_safety(
            session, tenant_id=tenant_id, site_id="s2",
            open_incidents_count=5, open_inspections_count=1,
        )
        await session.commit()

        counters = await AnalyticsAggregationService(session, tenant_id).base_counters(
            DashboardFilters()
        )
    assert counters["open_incidents"] == 7
    assert counters["open_inspections"] == 4


@pytest.mark.anyio
async def test_base_counters_tenant_isolation(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_package(session, tenant_id=tenant_id, package_id="own-pkg")
        other = await data_factory.ensure_tenant(slug="analytics-other", session=session)
        await _seed_package(session, tenant_id=str(other.id), package_id="foreign-pkg")
        await session.commit()

        own = await AnalyticsAggregationService(session, tenant_id).base_counters(DashboardFilters())
        foreign = await AnalyticsAggregationService(session, str(other.id)).base_counters(
            DashboardFilters()
        )
    assert own["packages_total"] == 1
    assert foreign["packages_total"] == 1


# =============================================================================
# trend_series
# =============================================================================


@pytest.mark.anyio
async def test_trend_series_default_points_is_12(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await AnalyticsAggregationService(session, tenant_id).trend_series("incidents")
    assert result["metric"] == "incidents"
    assert result["period"] == "daily"
    assert len(result["series"]) == 12


@pytest.mark.anyio
async def test_trend_series_explicit_points(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await AnalyticsAggregationService(session, tenant_id).trend_series(
            "packages", points=5
        )
    assert len(result["series"]) == 5


@pytest.mark.anyio
async def test_trend_series_weekly_period(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await AnalyticsAggregationService(session, tenant_id).trend_series(
            "compliance", period="weekly", points=3
        )
    assert result["period"] == "weekly"
    assert len(result["series"]) == 3
    # ISO dates monotonically increase across the series.
    dates = [point["date"] for point in result["series"]]
    assert dates == sorted(dates)


@pytest.mark.anyio
async def test_trend_series_monthly_period(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await AnalyticsAggregationService(session, tenant_id).trend_series(
            "inspections", period="monthly", points=2
        )
    assert result["period"] == "monthly"
    assert len(result["series"]) == 2


@pytest.mark.anyio
async def test_trend_series_incidents_uses_open_incidents_count(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_site_safety(
            session, tenant_id=tenant_id, site_id="s1",
            open_incidents_count=4, open_inspections_count=0,
        )
        await session.commit()
        result = await AnalyticsAggregationService(session, tenant_id).trend_series(
            "incidents", points=1
        )
    assert result["series"][0]["value"] == 4


@pytest.mark.anyio
async def test_trend_series_packages_metric(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        for n in range(3):
            await _seed_package(session, tenant_id=tenant_id, package_id=f"pk-{n}")
        await session.commit()
        result = await AnalyticsAggregationService(session, tenant_id).trend_series(
            "packages", points=1
        )
    assert result["series"][0]["value"] == 3


@pytest.mark.anyio
async def test_trend_series_trainings_metric(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_person_compliance(
            session, tenant_id=tenant_id, person_id="p1", overdue_trainings=5
        )
        await _seed_person_compliance(
            session, tenant_id=tenant_id, person_id="p2", overdue_trainings=3
        )
        await session.commit()
        result = await AnalyticsAggregationService(session, tenant_id).trend_series(
            "trainings", points=1
        )
    assert result["series"][0]["value"] == 8


@pytest.mark.anyio
async def test_trend_series_compliance_metric_sums_trainings_and_briefings(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_person_compliance(
            session, tenant_id=tenant_id, person_id="p1",
            overdue_trainings=2, overdue_briefings=3,
        )
        await session.commit()
        result = await AnalyticsAggregationService(session, tenant_id).trend_series(
            "compliance", points=1
        )
    assert result["series"][0]["value"] == 5


@pytest.mark.anyio
async def test_trend_series_unknown_metric_falls_back_to_contractor_packages(sessionmaker) -> None:
    """The else-branch in trend_series sums ``active_packages_count`` from
    ContractorReadinessReadModel for any unrecognized metric."""
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_contractor_readiness(
            session, tenant_id=tenant_id, contractor_id="c1", active_packages_count=7
        )
        await session.commit()
        result = await AnalyticsAggregationService(session, tenant_id).trend_series(
            "ppe", points=1
        )
    assert result["series"][0]["value"] == 7


# =============================================================================
# detailed_counters — counters wired to the live tables
# =============================================================================


@pytest.mark.anyio
async def test_detailed_counters_returns_all_eleven_keys(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        counters = await AnalyticsAggregationService(session, tenant_id).detailed_counters(
            DashboardFilters()
        )
    assert set(counters) == {
        "trainings_overdue",
        "ppe_overdue",
        "incidents_open",
        "inspections_open",
        "prescriptions_overdue",
        "workflow_open",
        "workflow_sla_breached",
        "plan_tasks_overdue",
        "integration_errors",
        "edo_status_changes",
        "failed_notifications",
    }
    # All zero on an empty tenant.
    assert all(value == 0 for value in counters.values())


# =============================================================================
# KpiDashboardService — every dashboard returns name + widgets
# =============================================================================


@pytest.mark.anyio
async def test_executive_dashboard_returns_base_counter_widgets(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await KpiDashboardService(session, tenant_id).executive(DashboardFilters())
    assert result["name"] == "executive"
    assert set(result["widgets"]) >= {
        "packages_total",
        "overdue_compliance_items",
        "open_incidents",
        "open_inspections",
    }


@pytest.mark.anyio
async def test_safety_dashboard_uses_base_counters(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await KpiDashboardService(session, tenant_id).safety(DashboardFilters())
    assert result["name"] == "safety"
    assert "open_incidents" in result["widgets"]


@pytest.mark.anyio
async def test_training_dashboard_uses_base_counters(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await KpiDashboardService(session, tenant_id).training(DashboardFilters())
    assert result["name"] == "training"
    assert "packages_total" in result["widgets"]


@pytest.mark.anyio
async def test_ppe_dashboard_uses_base_counters(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await KpiDashboardService(session, tenant_id).ppe(DashboardFilters())
    assert result["name"] == "ppe"


@pytest.mark.anyio
async def test_client_delivery_dashboard_includes_detailed_counters(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await KpiDashboardService(session, tenant_id).client_delivery(DashboardFilters())
    assert result["name"] == "client-delivery"
    # Has both base + detailed counter keys.
    assert "packages_total" in result["widgets"]
    assert "workflow_open" in result["widgets"]
    assert "integration_errors" in result["widgets"]


@pytest.mark.anyio
async def test_incidents_dashboard_picks_specific_widgets(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await KpiDashboardService(session, tenant_id).incidents(DashboardFilters())
    assert result["name"] == "incidents"
    assert set(result["widgets"]) == {
        "incidents_open",
        "workflow_open",
        "integration_errors",
        "failed_notifications",
        "packages_total",
    }


@pytest.mark.anyio
async def test_inspections_dashboard_picks_specific_widgets(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await KpiDashboardService(session, tenant_id).inspections(DashboardFilters())
    assert result["name"] == "inspections"
    assert set(result["widgets"]) == {
        "inspections_open",
        "plan_tasks_overdue",
        "workflow_sla_breached",
        "open_incidents",
    }


@pytest.mark.anyio
async def test_prescriptions_dashboard_widgets(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await KpiDashboardService(session, tenant_id).prescriptions(DashboardFilters())
    assert result["name"] == "prescriptions"
    assert set(result["widgets"]) == {
        "prescriptions_overdue",
        "workflow_open",
        "workflow_sla_breached",
        "plan_tasks_overdue",
    }


@pytest.mark.anyio
async def test_overdue_dashboard_widgets(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await KpiDashboardService(session, tenant_id).overdue(DashboardFilters())
    assert result["name"] == "overdue"
    assert set(result["widgets"]) == {
        "overdue_compliance_items",
        "trainings_overdue",
        "ppe_overdue",
        "prescriptions_overdue",
        "plan_tasks_overdue",
    }


@pytest.mark.anyio
async def test_sla_load_dashboard_widgets(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await KpiDashboardService(session, tenant_id).sla_load(DashboardFilters())
    assert result["name"] == "sla-load"
    assert set(result["widgets"]) == {
        "workflow_open",
        "workflow_sla_breached",
        "plan_tasks_overdue",
    }


@pytest.mark.anyio
async def test_edo_dashboard_widgets(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        result = await KpiDashboardService(session, tenant_id).edo(DashboardFilters())
    assert result["name"] == "edo"
    assert set(result["widgets"]) == {
        "edo_status_changes",
        "integration_errors",
        "failed_notifications",
    }


# =============================================================================
# HTTP wiring — at least one dashboard endpoint smoke-test
# =============================================================================


@pytest.mark.anyio
async def test_executive_dashboard_endpoint_returns_snapshot_and_dashboard(
    async_client, make_auth_headers, sessionmaker
) -> None:
    """The endpoint should return a snapshot_date plus the dashboard payload."""
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        await _seed_package(session, tenant_id=tenant_id, package_id="pk-end")
        await session.commit()

    headers = await make_auth_headers()
    response = await async_client.get("/api/v1/analytics/dashboard/executive", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "snapshot_date" in body
    assert "dashboard" in body
    assert body["dashboard"]["name"] == "executive"


@pytest.mark.anyio
async def test_safety_dashboard_endpoint_returns_widgets(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.get("/api/v1/analytics/dashboard/safety", headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "safety"


@pytest.mark.anyio
async def test_trends_endpoint_returns_series(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers()
    response = await async_client.get(
        "/api/v1/analytics/trends/incidents?period=daily", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metric"] == "incidents"
    assert body["period"] == "daily"
    assert len(body["series"]) == 12


@pytest.mark.anyio
async def test_trends_endpoint_rejects_invalid_period(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers()
    response = await async_client.get(
        "/api/v1/analytics/trends/incidents?period=yearly", headers=headers
    )
    assert response.status_code == 422
