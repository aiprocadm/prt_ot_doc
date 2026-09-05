from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Incident,
    Inspection,
    InspectionStatus,
    PPEIssue,
    PPEIssueStatus,
    Prescription,
    TrainingPlan,
)
from app.models.notifications import (
    Notification,
    NotificationStatus,
    NotificationType,
    PlanTask,
    PlanTaskStatus,
)
from app.modules.projections.models import (
    ContractorReadinessReadModel,
    DashboardKpiSnapshot,
    PackageReadModel,
    PersonComplianceReadModel,
    SiteSafetyReadModel,
)
from app.modules.workflow.models import WorkflowTask, WorkflowTaskStatus
from app.services.discipline_incidents import open_incidents_where


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
        package_stmt = (
            select(func.count())
            .select_from(PackageReadModel)
            .where(PackageReadModel.tenant_id == self.tenant_id)
        )
        if filters.status:
            package_stmt = package_stmt.where(PackageReadModel.status == filters.status)
        if filters.company_id:
            package_stmt = package_stmt.where(
                PackageReadModel.client_company_id == filters.company_id
            )
        if filters.site_id:
            package_stmt = package_stmt.where(PackageReadModel.site_id == filters.site_id)

        overdue_stmt = (
            select(func.count())
            .select_from(PersonComplianceReadModel)
            .where(
                PersonComplianceReadModel.tenant_id == self.tenant_id,
                PersonComplianceReadModel.readiness_status == "blocked",
            )
        )
        if filters.site_id:
            overdue_stmt = overdue_stmt.where(PersonComplianceReadModel.site_id == filters.site_id)

        incidents_stmt = select(func.sum(SiteSafetyReadModel.open_incidents_count)).where(
            SiteSafetyReadModel.tenant_id == self.tenant_id
        )
        inspections_stmt = select(func.sum(SiteSafetyReadModel.open_inspections_count)).where(
            SiteSafetyReadModel.tenant_id == self.tenant_id
        )

        return {
            "packages_total": int(await self.session.scalar(package_stmt) or 0),
            "overdue_compliance_items": int(await self.session.scalar(overdue_stmt) or 0),
            "open_incidents": int(await self.session.scalar(incidents_stmt) or 0),
            "open_inspections": int(await self.session.scalar(inspections_stmt) or 0),
        }

    _TREND_SNAPSHOT_KEY = {
        "incidents": "incidents_open",
        "inspections": "inspections_open",
        "packages": "packages_total",
        "trainings": "overdue_trainings",
        "compliance": "overdue_compliance",
    }

    async def _current_metric_value(self, metric: str) -> int:
        """Live value of a trend metric from the read models (the same figures the
        dashboard shows)."""
        if metric == "incidents":
            stmt = select(func.sum(SiteSafetyReadModel.open_incidents_count)).where(
                SiteSafetyReadModel.tenant_id == self.tenant_id
            )
        elif metric == "inspections":
            stmt = select(func.sum(SiteSafetyReadModel.open_inspections_count)).where(
                SiteSafetyReadModel.tenant_id == self.tenant_id
            )
        elif metric == "packages":
            stmt = (
                select(func.count())
                .select_from(PackageReadModel)
                .where(PackageReadModel.tenant_id == self.tenant_id)
            )
        elif metric == "trainings":
            stmt = select(func.sum(PersonComplianceReadModel.overdue_trainings)).where(
                PersonComplianceReadModel.tenant_id == self.tenant_id
            )
        elif metric == "compliance":
            stmt = select(
                func.sum(
                    PersonComplianceReadModel.overdue_trainings
                    + PersonComplianceReadModel.overdue_briefings
                )
            ).where(PersonComplianceReadModel.tenant_id == self.tenant_id)
        else:
            stmt = select(func.sum(ContractorReadinessReadModel.active_packages_count)).where(
                ContractorReadinessReadModel.tenant_id == self.tenant_id
            )
        return int(await self.session.scalar(stmt) or 0)

    async def trend_series(
        self, metric: str, period: str = "daily", points: int = 12
    ) -> dict[str, Any]:
        today = date.today()
        step_days = 1 if period == "daily" else 7 if period == "weekly" else 30
        # Real trend (#29): the latest bucket uses the live current value (robust even
        # before today's snapshot job runs), and each past bucket reads the most recent
        # daily DashboardKpiSnapshot on/before that date — instead of re-running the
        # same current aggregate for every bucket, which produced a flat line. Past
        # buckets read 0 until snapshots accumulate.
        snapshot_key = self._TREND_SNAPSHOT_KEY.get(metric, "contractors")
        current_value = await self._current_metric_value(metric)
        values: list[dict[str, Any]] = []
        for idx in reversed(range(points)):
            point_date = today - timedelta(days=idx * step_days)
            if point_date >= today:
                value = current_value
            else:
                payload = (
                    await self.session.execute(
                        select(DashboardKpiSnapshot.payload)
                        .where(
                            DashboardKpiSnapshot.tenant_id == self.tenant_id,
                            DashboardKpiSnapshot.scope_type == "tenant",
                            DashboardKpiSnapshot.scope_id.is_(None),
                            DashboardKpiSnapshot.snapshot_date <= point_date,
                        )
                        .order_by(DashboardKpiSnapshot.snapshot_date.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none() or {}
                value = int(payload.get(snapshot_key, 0) or 0)
            values.append({"date": point_date.isoformat(), "value": value})
        return {"metric": metric, "period": period, "series": values}

    async def detailed_counters(self, filters: DashboardFilters) -> dict[str, int]:
        today = date.today()
        trainings_overdue = int(
            await self.session.scalar(
                select(func.count())
                .select_from(TrainingPlan)
                .where(
                    TrainingPlan.tenant_id == self.tenant_id,
                    TrainingPlan.due_date.is_not(None),
                    TrainingPlan.due_date < today,
                )
            )
            or 0
        )
        ppe_overdue = int(
            await self.session.scalar(
                select(func.count())
                .select_from(PPEIssue)
                .where(
                    PPEIssue.tenant_id == self.tenant_id,
                    PPEIssue.deleted_at.is_(None),
                    PPEIssue.status == PPEIssueStatus.ISSUED,
                    PPEIssue.expires_at.is_not(None),
                    func.date(PPEIssue.expires_at) < today,
                )
            )
            or 0
        )
        incidents_open = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Incident)
                .where(*open_incidents_where(self.tenant_id))
            )
            or 0
        )
        inspections_open = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Inspection)
                .where(
                    Inspection.tenant_id == self.tenant_id,
                    Inspection.deleted_at.is_(None),
                    Inspection.status.notin_(
                        [InspectionStatus.COMPLETED, InspectionStatus.CANCELLED]
                    ),
                )
            )
            or 0
        )
        prescriptions_overdue = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Prescription)
                .where(
                    Prescription.tenant_id == self.tenant_id,
                    Prescription.deleted_at.is_(None),
                    Prescription.due_at.is_not(None),
                    Prescription.due_at < today,
                )
            )
            or 0
        )
        workflow_open = int(
            await self.session.scalar(
                select(func.count())
                .select_from(WorkflowTask)
                .where(
                    WorkflowTask.tenant_id == self.tenant_id,
                    WorkflowTask.status == WorkflowTaskStatus.OPEN,
                    WorkflowTask.deleted_at.is_(None),
                )
            )
            or 0
        )
        workflow_sla_breached = int(
            await self.session.scalar(
                select(func.count())
                .select_from(WorkflowTask)
                .where(
                    WorkflowTask.tenant_id == self.tenant_id,
                    WorkflowTask.status == WorkflowTaskStatus.OPEN,
                    WorkflowTask.due_at.is_not(None),
                    WorkflowTask.due_at < func.now(),
                    WorkflowTask.deleted_at.is_(None),
                )
            )
            or 0
        )
        plan_overdue = int(
            await self.session.scalar(
                select(func.count())
                .select_from(PlanTask)
                .where(
                    PlanTask.tenant_id == self.tenant_id,
                    PlanTask.status.in_([PlanTaskStatus.OPEN, PlanTaskStatus.OVERDUE]),
                    PlanTask.due_at.is_not(None),
                    PlanTask.due_at < func.now(),
                    PlanTask.deleted_at.is_(None),
                )
            )
            or 0
        )
        notifications_integration_errors = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.tenant_id == self.tenant_id,
                    Notification.type == NotificationType.INTEGRATION_ERROR,
                    Notification.deleted_at.is_(None),
                )
            )
            or 0
        )
        notifications_edo_changes = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.tenant_id == self.tenant_id,
                    Notification.type == NotificationType.EDO_STATUS_CHANGED,
                    Notification.deleted_at.is_(None),
                )
            )
            or 0
        )
        notifications_failed = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.tenant_id == self.tenant_id,
                    Notification.status == NotificationStatus.FAILED,
                    Notification.deleted_at.is_(None),
                )
            )
            or 0
        )
        return {
            "trainings_overdue": trainings_overdue,
            "ppe_overdue": ppe_overdue,
            "incidents_open": incidents_open,
            "inspections_open": inspections_open,
            "prescriptions_overdue": prescriptions_overdue,
            "workflow_open": workflow_open,
            "workflow_sla_breached": workflow_sla_breached,
            "plan_tasks_overdue": plan_overdue,
            "integration_errors": notifications_integration_errors,
            "edo_status_changes": notifications_edo_changes,
            "failed_notifications": notifications_failed,
        }


class KpiDashboardService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id
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
        counters.update(await self.agg.detailed_counters(filters))
        return {"name": "client-delivery", "widgets": counters}

    async def incidents(self, filters: DashboardFilters) -> dict[str, Any]:
        counters = await self.agg.base_counters(filters)
        detailed = await self.agg.detailed_counters(filters)
        return {
            "name": "incidents",
            "widgets": {
                k: detailed[k]
                for k in [
                    "incidents_open",
                    "workflow_open",
                    "integration_errors",
                    "failed_notifications",
                ]
            }
            | {"packages_total": counters["packages_total"]},
        }

    async def inspections(self, filters: DashboardFilters) -> dict[str, Any]:
        counters = await self.agg.base_counters(filters)
        detailed = await self.agg.detailed_counters(filters)
        return {
            "name": "inspections",
            "widgets": {
                k: detailed[k]
                for k in ["inspections_open", "plan_tasks_overdue", "workflow_sla_breached"]
            }
            | {"open_incidents": counters["open_incidents"]},
        }

    async def prescriptions(self, filters: DashboardFilters) -> dict[str, Any]:
        detailed = await self.agg.detailed_counters(filters)
        return {
            "name": "prescriptions",
            "widgets": {
                k: detailed[k]
                for k in [
                    "prescriptions_overdue",
                    "workflow_open",
                    "workflow_sla_breached",
                    "plan_tasks_overdue",
                ]
            },
        }

    async def overdue(self, filters: DashboardFilters) -> dict[str, Any]:
        counters = await self.agg.base_counters(filters)
        detailed = await self.agg.detailed_counters(filters)
        return {
            "name": "overdue",
            "widgets": {
                "overdue_compliance_items": counters["overdue_compliance_items"],
                "trainings_overdue": detailed["trainings_overdue"],
                "ppe_overdue": detailed["ppe_overdue"],
                "prescriptions_overdue": detailed["prescriptions_overdue"],
                "plan_tasks_overdue": detailed["plan_tasks_overdue"],
            },
        }

    async def sla_load(self, filters: DashboardFilters) -> dict[str, Any]:
        detailed = await self.agg.detailed_counters(filters)
        return {
            "name": "sla-load",
            "widgets": {
                "workflow_open": detailed["workflow_open"],
                "workflow_sla_breached": detailed["workflow_sla_breached"],
                "plan_tasks_overdue": detailed["plan_tasks_overdue"],
            },
        }

    async def edo(self, filters: DashboardFilters) -> dict[str, Any]:
        detailed = await self.agg.detailed_counters(filters)
        return {
            "name": "edo",
            "widgets": {
                "edo_status_changes": detailed["edo_status_changes"],
                "integration_errors": detailed["integration_errors"],
                "failed_notifications": detailed["failed_notifications"],
            },
        }
