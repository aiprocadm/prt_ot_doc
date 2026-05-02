"""Operational dashboard service for Command Center."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_core import DocumentStatus, PipelineRun, PipelineRunStatus
from app.models.models import Incident, IncidentStatus, TrainingPlan
from app.models.obligations import Task, TaskPriority, TaskStatus
from app.modules.operational_dashboard.schemas import (
    AlertItem,
    OperationalDashboardMetrics,
    OperationalDashboardResponse,
)

logger = logging.getLogger("app.modules.operational_dashboard")


class OperationalDashboardService:
    """Service for aggregating operational dashboard data."""

    def __init__(self):
        self.max_alerts = 20

    async def get_dashboard(
        self, session: AsyncSession, tenant_id: str
    ) -> OperationalDashboardResponse:
        """Get comprehensive operational dashboard."""
        alerts: list[AlertItem] = []
        now = datetime.now(timezone.utc)

        # Collect overdue items
        overdue_alerts = await self._collect_overdue_alerts(session, tenant_id, now)
        alerts.extend(overdue_alerts)

        # Collect blocked approvals
        blocked_alerts = await self._collect_blocked_approval_alerts(
            session, tenant_id
        )
        alerts.extend(blocked_alerts)

        # Collect critical incidents
        incident_alerts = await self._collect_incident_alerts(session, tenant_id)
        alerts.extend(incident_alerts)

        # Collect unassigned tasks
        unassigned_alerts = await self._collect_unassigned_task_alerts(
            session, tenant_id
        )
        alerts.extend(unassigned_alerts)

        # Sort by severity and creation time
        alerts = self._sort_alerts(alerts)[: self.max_alerts]

        # Calculate metrics
        metrics = await self._calculate_metrics(session, tenant_id, alerts)

        # Determine overall status
        overall_status = self._determine_status(metrics)

        response = OperationalDashboardResponse(
            tenant_id=tenant_id,
            status=overall_status,
            metrics=metrics,
            alerts=alerts,
        )

        return response

    async def _collect_overdue_alerts(
        self, session: AsyncSession, tenant_id: str, now: datetime
    ) -> list[AlertItem]:
        """Collect alerts for overdue tasks and items."""
        alerts = []

        # Overdue tasks
        stmt = (
            select(Task)
            .where(
                Task.tenant_id == tenant_id,
                Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
                Task.due_at.is_not(None),
                Task.due_at < now,
            )
            .limit(5)
        )
        tasks = await session.execute(stmt)
        for task in tasks.scalars():
            days_overdue = (now - task.due_at).days
            alerts.append(
                AlertItem(
                    id=str(task.id),
                    type="overdue",
                    severity="high" if days_overdue > 7 else "medium",
                    title=f"Overdue: {task.title}",
                    description=f"Due {days_overdue} days ago",
                    entity_type="task",
                    entity_id=str(task.id),
                    created_at=task.created_at,
                    action_url=f"/tasks/{task.id}",
                )
            )

        return alerts

    async def _collect_blocked_approval_alerts(
        self, session: AsyncSession, tenant_id: str
    ) -> list[AlertItem]:
        """Collect alerts for documents blocked in approval."""
        alerts = []

        # Documents in approval for > 3 days
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
        stmt = (
            select(PipelineRun)
            .where(
                PipelineRun.tenant_id == tenant_id,
                PipelineRun.status == PipelineRunStatus.WAITING_APPROVAL,
                PipelineRun.created_at < three_days_ago,
            )
            .limit(5)
        )
        blocked = await session.execute(stmt)
        for run in blocked.scalars():
            alerts.append(
                AlertItem(
                    id=str(run.id),
                    type="approval_blocked",
                    severity="high",
                    title=f"Document blocked in approval: {run.document_title or 'N/A'}",
                    description=f"Waiting for approval since {run.created_at.isoformat()}",
                    entity_type="document",
                    entity_id=str(run.document_id),
                    created_at=run.created_at,
                    action_url=f"/documents/{run.document_id}",
                )
            )

        return alerts

    async def _collect_incident_alerts(
        self, session: AsyncSession, tenant_id: str
    ) -> list[AlertItem]:
        """Collect alerts for critical incidents."""
        alerts = []

        # Recent critical incidents not closed
        stmt = (
            select(Incident)
            .where(
                Incident.tenant_id == tenant_id,
                Incident.status != IncidentStatus.CLOSED,
                Incident.severity.in_(["critical", "high"]),
            )
            .limit(3)
        )
        incidents = await session.execute(stmt)
        for incident in incidents.scalars():
            alerts.append(
                AlertItem(
                    id=str(incident.id),
                    type="critical_incident",
                    severity="critical" if incident.severity == "critical" else "high",
                    title=f"Incident: {incident.title or 'No title'}",
                    description=incident.description,
                    entity_type="incident",
                    entity_id=str(incident.id),
                    created_at=incident.created_at,
                    action_url=f"/incidents/{incident.id}",
                )
            )

        return alerts

    async def _collect_unassigned_task_alerts(
        self, session: AsyncSession, tenant_id: str
    ) -> list[AlertItem]:
        """Collect alerts for unassigned critical tasks."""
        alerts = []

        stmt = (
            select(Task)
            .where(
                Task.tenant_id == tenant_id,
                Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
                Task.assigned_to.is_(None),
                Task.priority.in_([TaskPriority.HIGH, TaskPriority.CRITICAL]),
            )
            .limit(5)
        )
        tasks = await session.execute(stmt)
        for task in tasks.scalars():
            alerts.append(
                AlertItem(
                    id=str(task.id),
                    type="unassigned_task",
                    severity="high",
                    title=f"Unassigned: {task.title}",
                    description=f"Priority: {task.priority}",
                    entity_type="task",
                    entity_id=str(task.id),
                    created_at=task.created_at,
                    action_url=f"/tasks/{task.id}",
                )
            )

        return alerts

    def _sort_alerts(self, alerts: list[AlertItem]) -> list[AlertItem]:
        """Sort alerts by severity (critical > high > medium > low) and recency."""
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(
            alerts,
            key=lambda a: (
                severity_order.get(a.severity, 4),
                -a.created_at.timestamp(),
            ),
        )

    async def _calculate_metrics(
        self,
        session: AsyncSession,
        tenant_id: str,
        alerts: list[AlertItem],
    ) -> OperationalDashboardMetrics:
        """Calculate high-level metrics."""
        now = datetime.now(timezone.utc)

        # Count overdue items
        overdue_stmt = select(func.count()).select_from(Task).where(
            Task.tenant_id == tenant_id,
            Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
            Task.due_at.is_not(None),
            Task.due_at < now,
        )
        overdue_count = int(await session.scalar(overdue_stmt) or 0)

        # Count blocked approvals
        blocked_stmt = select(func.count()).select_from(PipelineRun).where(
            PipelineRun.tenant_id == tenant_id,
            PipelineRun.status == PipelineRunStatus.WAITING_APPROVAL,
        )
        blocked_count = int(await session.scalar(blocked_stmt) or 0)

        # Count critical alerts and unassigned
        critical_count = sum(
            1 for a in alerts if a.severity == "critical"
        )
        unassigned_count = sum(
            1 for a in alerts if a.type == "unassigned_task"
        )

        return OperationalDashboardMetrics(
            overdue_items=overdue_count,
            blocked_approvals=blocked_count,
            critical_alerts=critical_count,
            degraded_services=0,  # Would come from health checks in future
            unassigned_tasks=unassigned_count,
        )

    def _determine_status(self, metrics: OperationalDashboardMetrics) -> str:
        """Determine overall dashboard status based on metrics."""
        if metrics.critical_alerts > 0:
            return "critical"
        if (
            metrics.blocked_approvals > 3
            or metrics.overdue_items > 5
            or metrics.degraded_services > 0
        ):
            return "degraded"
        return "ok"
