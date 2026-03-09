from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projections.models import (
    ContractorReadinessReadModel,
    PackageReadModel,
    PersonComplianceReadModel,
    SiteSafetyReadModel,
)


@dataclass(slots=True)
class DashboardFilters:
    company_id: str | None = None
    site_id: str | None = None
    contractor_id: str | None = None
    status: str | None = None
    risk_level: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class AnalyticsAggregationService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def base_counters(self, filters: DashboardFilters) -> dict[str, int]:
        package_stmt = select(func.count()).select_from(PackageReadModel).where(PackageReadModel.tenant_id == self.tenant_id)
        if filters.status:
            package_stmt = package_stmt.where(PackageReadModel.status == filters.status)
        if filters.company_id:
            package_stmt = package_stmt.where(PackageReadModel.client_company_id == filters.company_id)
        if filters.site_id:
            package_stmt = package_stmt.where(PackageReadModel.site_id == filters.site_id)

        overdue_stmt = select(func.count()).select_from(PersonComplianceReadModel).where(
            PersonComplianceReadModel.tenant_id == self.tenant_id,
            PersonComplianceReadModel.readiness_status == "blocked",
        )
        if filters.site_id:
            overdue_stmt = overdue_stmt.where(PersonComplianceReadModel.site_id == filters.site_id)

        incidents_stmt = select(func.sum(SiteSafetyReadModel.open_incidents_count)).where(SiteSafetyReadModel.tenant_id == self.tenant_id)
        inspections_stmt = select(func.sum(SiteSafetyReadModel.open_inspections_count)).where(SiteSafetyReadModel.tenant_id == self.tenant_id)

        return {
            "packages_total": int(await self.session.scalar(package_stmt) or 0),
            "overdue_compliance_items": int(await self.session.scalar(overdue_stmt) or 0),
            "open_incidents": int(await self.session.scalar(incidents_stmt) or 0),
            "open_inspections": int(await self.session.scalar(inspections_stmt) or 0),
        }

    async def trend_series(self, metric: str, period: str = "daily", points: int = 12) -> dict[str, Any]:
        today = date.today()
        step_days = 1 if period == "daily" else 7 if period == "weekly" else 30
        values: list[dict[str, Any]] = []
        for idx in reversed(range(points)):
            point_date = today - timedelta(days=idx * step_days)
            if metric == "incidents":
                value = int(
                    await self.session.scalar(
                        select(func.sum(SiteSafetyReadModel.open_incidents_count)).where(SiteSafetyReadModel.tenant_id == self.tenant_id)
                    )
                    or 0
                )
            elif metric == "inspections":
                value = int(
                    await self.session.scalar(
                        select(func.sum(SiteSafetyReadModel.open_inspections_count)).where(SiteSafetyReadModel.tenant_id == self.tenant_id)
                    )
                    or 0
                )
            elif metric == "packages":
                value = int(
                    await self.session.scalar(
                        select(func.count()).select_from(PackageReadModel).where(PackageReadModel.tenant_id == self.tenant_id)
                    )
                    or 0
                )
            elif metric == "trainings":
                value = int(
                    await self.session.scalar(
                        select(func.sum(PersonComplianceReadModel.overdue_trainings)).where(
                            PersonComplianceReadModel.tenant_id == self.tenant_id
                        )
                    )
                    or 0
                )
            elif metric == "compliance":
                value = int(
                    await self.session.scalar(
                        select(func.sum(PersonComplianceReadModel.overdue_trainings + PersonComplianceReadModel.overdue_briefings)).where(
                            PersonComplianceReadModel.tenant_id == self.tenant_id
                        )
                    )
                    or 0
                )
            else:
                value = int(
                    await self.session.scalar(
                        select(func.sum(ContractorReadinessReadModel.active_packages_count)).where(
                            ContractorReadinessReadModel.tenant_id == self.tenant_id
                        )
                    )
                    or 0
                )
            values.append({"date": point_date.isoformat(), "value": value})
        return {"metric": metric, "period": period, "series": values}


class KpiDashboardService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.agg = AnalyticsAggregationService(session, tenant_id)

    async def executive(self, filters: DashboardFilters) -> dict[str, Any]:
        counters = await self.agg.base_counters(filters)
        return {"name": "executive", "widgets": counters}

    async def safety(self, filters: DashboardFilters) -> dict[str, Any]:
        counters = await self.agg.base_counters(filters)
        return {"name": "safety", "widgets": counters}

    async def training(self, filters: DashboardFilters) -> dict[str, Any]:
        counters = await self.agg.base_counters(filters)
        return {"name": "training", "widgets": counters}

    async def ppe(self, filters: DashboardFilters) -> dict[str, Any]:
        counters = await self.agg.base_counters(filters)
        return {"name": "ppe", "widgets": counters}

    async def client_delivery(self, filters: DashboardFilters) -> dict[str, Any]:
        counters = await self.agg.base_counters(filters)
        return {"name": "client-delivery", "widgets": counters}
