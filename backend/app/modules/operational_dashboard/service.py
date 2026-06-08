"""Operational dashboard service for aggregating critical alerts."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import SessionLocal
from app.modules.operational_dashboard.schemas import (
    AlertCategory,
    AlertItem,
    AlertSeverity,
    OperationalDashboardResponse,
)

logger = logging.getLogger("app.modules.operational_dashboard")


class OperationalDashboardService:
    """Service for aggregating operational dashboard alerts."""

    def __init__(self, settings: Settings):
        """Initialize service."""
        self.settings = settings

    async def get_dashboard(
        self, tenant_id: str, db: AsyncSession | None = None
    ) -> OperationalDashboardResponse:
        """
        Get operational dashboard with all critical alerts.

        Args:
            tenant_id: Tenant ID
            db: Database session (creates one if None)

        Returns:
            OperationalDashboardResponse with aggregated alerts
        """
        if db is None:
            async with SessionLocal() as db:
                return await self.get_dashboard(tenant_id, db)

        alerts: list[AlertItem] = []

        alerts.extend(await self._get_overdue_alerts(tenant_id, db))
        alerts.extend(await self._get_blocked_approval_alerts(tenant_id, db))
        alerts.extend(await self._get_integration_error_alerts(tenant_id, db))
        alerts.extend(await self._get_high_risk_alerts(tenant_id, db))
        alerts.extend(await self._get_unassigned_task_alerts(tenant_id, db))

        alert_count = self._count_alerts_by_severity(alerts)
        overall_status = self._determine_overall_status(alert_count)

        return OperationalDashboardResponse(
            tenant_id=tenant_id,
            status=overall_status,
            alerts=alerts,
            alert_count=alert_count,
            timestamp=datetime.now(tz=timezone.utc),
        )

    async def _get_overdue_alerts(
        self, tenant_id: str, db: AsyncSession
    ) -> list[AlertItem]:
        """Get alerts for overdue items (training enrollments, medical, PPE)."""
        alerts: list[AlertItem] = []
        now = datetime.now(tz=timezone.utc)
        today = date.today()

        try:
            from sqlalchemy import and_, func, select
            from app.models.models import (
                MedicalExam,
                MedicalSuspension,
                MedicalSuspensionStatus,
                PPEIssue,
                PPEIssueStatus,
                TrainingEnrollment,
            )
        except ImportError:
            logger.debug("overdue aggregates: model import failed", exc_info=True)
            return alerts

        async def _add_count(stmt, entity_type: str) -> None:
            result = await db.execute(stmt)
            count = int(result.scalar_one_or_none() or 0)
            if count > 0:
                alerts.append(
                    AlertItem(
                        id=f"overdue_{entity_type}",
                        category=AlertCategory.OVERDUE,
                        severity=AlertSeverity.HIGH,
                        title=f"{count} overdue {entity_type}(s)",
                        description=f"{count} items are overdue for tenant scope",
                        count=count,
                        affected_entity_type=entity_type,
                    )
                )

        try:
            await _add_count(
                select(func.count())
                .select_from(TrainingEnrollment)
                .where(
                    TrainingEnrollment.tenant_id == tenant_id,
                    TrainingEnrollment.deleted_at.is_(None),
                    TrainingEnrollment.status.in_(["assigned", "in_progress"]),
                    TrainingEnrollment.due_at.is_not(None),
                    TrainingEnrollment.due_at < now,
                ),
                "training_enrollment",
            )
            await _add_count(
                select(func.count())
                .select_from(MedicalExam)
                .where(
                    MedicalExam.tenant_id == tenant_id,
                    MedicalExam.deleted_at.is_(None),
                    MedicalExam.valid_until < today,
                ),
                "medical_exam",
            )
            await _add_count(
                select(func.count())
                .select_from(PPEIssue)
                .where(
                    PPEIssue.tenant_id == tenant_id,
                    PPEIssue.deleted_at.is_(None),
                    PPEIssue.status == PPEIssueStatus.ISSUED,
                    PPEIssue.expires_at.is_not(None),
                    PPEIssue.expires_at < now,
                ),
                "ppe_issue",
            )
            await _add_count(
                select(func.count())
                .select_from(MedicalSuspension)
                .where(
                    MedicalSuspension.tenant_id == tenant_id,
                    MedicalSuspension.deleted_at.is_(None),
                    MedicalSuspension.status == MedicalSuspensionStatus.ACTIVE,
                ),
                "medical_suspension",
            )
        except Exception:
            logger.debug("overdue aggregates failed", exc_info=True)

        return alerts

    async def _get_blocked_approval_alerts(
        self, tenant_id: str, db: AsyncSession
    ) -> list[AlertItem]:
        """Documents awaiting approval (REVIEW lifecycle state)."""
        alerts: list[AlertItem] = []

        try:
            from sqlalchemy import and_, func, select
            from app.models.document import Document, DocumentStatus
        except ImportError:
            return alerts

        try:
            stmt = select(func.count(Document.id)).where(
                and_(Document.tenant_id == tenant_id, Document.status == DocumentStatus.REVIEW)
            )
            result = await db.execute(stmt)
            count = int(result.scalar_one_or_none() or 0)

            if count > 0:
                alerts.append(
                    AlertItem(
                        id="blocked_approvals",
                        category=AlertCategory.BLOCKED_APPROVAL,
                        severity=AlertSeverity.MEDIUM,
                        title=f"{count} document(s) in review",
                        description=f"{count} documents remain in REVIEW awaiting approval/sign-off",
                        count=count,
                        affected_entity_type="document",
                    )
                )
        except Exception:
            logger.debug("blocked approval aggregate failed", exc_info=True)

        return alerts

    async def _get_integration_error_alerts(
        self, tenant_id: str, db: AsyncSession
    ) -> list[AlertItem]:
        """Integration telemetry (stub — persisted integration log schema not wired here)."""
        return []

    async def _get_high_risk_alerts(
        self, tenant_id: str, db: AsyncSession
    ) -> list[AlertItem]:
        """Escalations from risk register severity/level composites."""
        alerts: list[AlertItem] = []

        try:
            from sqlalchemy import and_, func, select
            from app.models.risk import Risk
        except ImportError:
            return alerts

        try:
            stmt = select(func.count(Risk.id)).where(
                and_(
                    Risk.tenant_id == tenant_id,
                    Risk.level >= 15,
                )
            )
            result = await db.execute(stmt)
            count = int(result.scalar_one_or_none() or 0)

            if count > 0:
                alerts.append(
                    AlertItem(
                        id="high_risk_register_items",
                        category=AlertCategory.HIGH_RISK,
                        severity=AlertSeverity.HIGH,
                        title=f"{count} elevated risk register entr(y/ies)",
                        description=f"{count} workplace risks flagged with composite level ≥ 15",
                        count=count,
                        affected_entity_type="risk_register",
                    )
                )
        except Exception:
            logger.debug("risk register aggregation failed", exc_info=True)

        return alerts

    async def _get_unassigned_task_alerts(
        self, tenant_id: str, db: AsyncSession
    ) -> list[AlertItem]:
        """Obligations tasks lacking an assignee."""
        alerts: list[AlertItem] = []

        try:
            from sqlalchemy import and_, func, select
            from app.models.obligations import Task, TaskStatus
        except ImportError:
            return alerts

        try:
            stmt = select(func.count(Task.id)).where(
                and_(
                    Task.tenant_id == tenant_id,
                    Task.assignee_id.is_(None),
                    Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
                )
            )
            result = await db.execute(stmt)
            count = int(result.scalar_one_or_none() or 0)

            if count > 0:
                alerts.append(
                    AlertItem(
                        id="unassigned_tasks",
                        category=AlertCategory.UNASSIGNED_TASK,
                        severity=AlertSeverity.MEDIUM,
                        title=f"{count} unassigned task(s)",
                        description=f"{count} open tasks lack an explicit assignee",
                        count=count,
                        affected_entity_type="task",
                    )
                )
        except Exception:
            logger.debug("unassigned obligations aggregate failed", exc_info=True)

        return alerts

    def _count_alerts_by_severity(
        self, alerts: list[AlertItem]
    ) -> dict[AlertSeverity, int]:
        """Count alerts grouped by severity."""
        count: dict[AlertSeverity, int] = defaultdict(int)
        for alert in alerts:
            count[alert.severity] += 1
        return dict(count)

    def _determine_overall_status(
        self, alert_count: dict[AlertSeverity, int]
    ) -> str:
        """Determine overall dashboard status based on alert counts."""
        if alert_count.get(AlertSeverity.CRITICAL, 0) > 0:
            return "critical"
        if alert_count.get(AlertSeverity.HIGH, 0) > 0:
            return "warning"
        if alert_count.get(AlertSeverity.MEDIUM, 0) > 0:
            return "caution"
        return "ok"
