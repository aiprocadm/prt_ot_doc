from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from app.modules.analytics.services import (
    AnalyticsAggregationService,
    DashboardFilters,
    KpiDashboardService,
)
from app.modules.projections.models import DashboardKpiSnapshot
from app.modules.projections.services import ProjectionOrchestrator

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _filters(
    company_id: str | None = Query(default=None),
    site_id: str | None = Query(default=None),
    contractor_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> DashboardFilters:
    return DashboardFilters(
        company_id=company_id,
        site_id=site_id,
        contractor_id=contractor_id,
        status=status,
        risk_level=risk_level,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/dashboard/executive")
async def executive_dashboard(
    filters: DashboardFilters = Depends(_filters),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    today = date.today()
    snapshot = (
        await session.execute(
            select(DashboardKpiSnapshot).where(
                DashboardKpiSnapshot.tenant_id == str(tenant.id),
                DashboardKpiSnapshot.scope_type == "tenant",
                DashboardKpiSnapshot.snapshot_date == today,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = await ProjectionOrchestrator(session, str(tenant.id)).rebuild_dashboard_snapshot(
            today
        )
    payload = await KpiDashboardService(session, str(tenant.id)).executive(filters)
    return {"snapshot_date": today, "widgets": snapshot.payload, "dashboard": payload}


@router.get("/dashboard/safety")
async def safety_dashboard(
    filters: DashboardFilters = Depends(_filters),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await KpiDashboardService(session, str(tenant.id)).safety(filters)


@router.get("/dashboard/client-delivery")
async def client_delivery_dashboard(
    filters: DashboardFilters = Depends(_filters),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await KpiDashboardService(session, str(tenant.id)).client_delivery(filters)


@router.get("/dashboard/incidents")
async def incidents_dashboard(
    filters: DashboardFilters = Depends(_filters),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await KpiDashboardService(session, str(tenant.id)).incidents(filters)


@router.get("/dashboard/inspections")
async def inspections_dashboard(
    filters: DashboardFilters = Depends(_filters),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await KpiDashboardService(session, str(tenant.id)).inspections(filters)


@router.get("/dashboard/prescriptions")
async def prescriptions_dashboard(
    filters: DashboardFilters = Depends(_filters),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await KpiDashboardService(session, str(tenant.id)).prescriptions(filters)


@router.get("/dashboard/overdue")
async def overdue_dashboard(
    filters: DashboardFilters = Depends(_filters),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await KpiDashboardService(session, str(tenant.id)).overdue(filters)


@router.get("/dashboard/sla-load")
async def sla_load_dashboard(
    filters: DashboardFilters = Depends(_filters),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await KpiDashboardService(session, str(tenant.id)).sla_load(filters)


@router.get("/dashboard/edo")
async def edo_dashboard(
    filters: DashboardFilters = Depends(_filters),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await KpiDashboardService(session, str(tenant.id)).edo(filters)


@router.get("/dashboard/ppe")
async def ppe_dashboard(
    filters: DashboardFilters = Depends(_filters),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await KpiDashboardService(session, str(tenant.id)).ppe(filters)


@router.get("/dashboard/training")
async def training_dashboard(
    filters: DashboardFilters = Depends(_filters),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await KpiDashboardService(session, str(tenant.id)).training(filters)


@router.get("/trends/incidents")
async def incidents_trends(
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await AnalyticsAggregationService(session, str(tenant.id)).trend_series(
        "incidents", period
    )


@router.get("/trends/compliance")
async def compliance_trends(
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await AnalyticsAggregationService(session, str(tenant.id)).trend_series(
        "compliance", period
    )


@router.get("/trends/packages")
async def packages_trends(
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await AnalyticsAggregationService(session, str(tenant.id)).trend_series(
        "packages", period
    )


@router.get("/trends/trainings")
async def trainings_trends(
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await AnalyticsAggregationService(session, str(tenant.id)).trend_series(
        "trainings", period
    )


@router.get("/trends/inspections")
async def inspections_trends(
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await AnalyticsAggregationService(session, str(tenant.id)).trend_series(
        "inspections", period
    )


@router.get("/trends/ppe")
async def ppe_trends(
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    return await AnalyticsAggregationService(session, str(tenant.id)).trend_series("ppe", period)


@router.post("/recompute")
async def recompute_dashboard(
    session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)
) -> dict:
    snapshot = await ProjectionOrchestrator(session, str(tenant.id)).rebuild_dashboard_snapshot(
        date.today()
    )
    return {"status": "ok", "payload": snapshot.payload}
