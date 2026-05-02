"""Operational dashboard service for aggregating critical alerts."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
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
            timestamp=datetime.utcnow(),
        )

    async def _get_overdue_alerts(
        self, tenant_id: str, db: AsyncSession
    ) -> list[AlertItem]:
        """Get alerts for overdue items (training, medical, PPE, SOÚT)."""
        alerts: list[AlertItem] = []

        from sqlalchemy import select, and_, func
        from app.domains.training.models import TrainingAssignment
        from app.domains.medical.models import MedicalExamSchedule
        from app.domains.ppe.models import PPEIssue
        from app.core.security import TenantContextValidator

        now = datetime.utcnow()

        try:
            for model_class, entity_type, check_field in [
                (TrainingAssignment, "training_assignment", "due_date"),
                (MedicalExamSchedule, "medical_exam", "exam_date"),
                (PPEIssue, "ppe_issue", "expiry_date"),
            ]:
                if check_field and hasattr(model_class, check_field):
                    try:
                        stmt = select(func.count(model_class.id)).where(
                            and_(
                                model_class.tenant_id == tenant_id,
                                getattr(model_class, check_field) < now,
                                getattr(model_class, "status", None)
                                != "completed",
                            )
                        )
                        result = await db.execute(stmt)
                        count = result.scalar_one_or_none() or 0

                        if count > 0:
                            alerts.append(
                                AlertItem(
                                    id=f"overdue_{entity_type}",
                                    category=AlertCategory.OVERDUE,
                                    severity=AlertSeverity.HIGH,
                                    title=f"{count} overdue {entity_type}(s)",
                                    description=f"{count} {entity_type} items are overdue",
                                    count=count,
                                    affected_entity_type=entity_type,
                                )
                            )
                    except Exception as e:
                        logger.debug(f"Error checking {entity_type} overdue: {e}")
                        continue

        except Exception as e:
            logger.exception("Error getting overdue alerts")

        return alerts

    async def _get_blocked_approval_alerts(
        self, tenant_id: str, db: AsyncSession
    ) -> list[AlertItem]:
        """Get alerts for documents blocked in approval."""
        alerts: list[AlertItem] = []

        try:
            from sqlalchemy import select, and_, func
            from app.domains.documents.models import Document

            stmt = select(func.count(Document.id)).where(
                and_(
                    Document.tenant_id == tenant_id,
                    Document.status == "approval_pending",
                )
            )
            result = await db.execute(stmt)
            count = result.scalar_one_or_none() or 0

            if count > 0:
                alerts.append(
                    AlertItem(
                        id="blocked_approvals",
                        category=AlertCategory.BLOCKED_APPROVAL,
                        severity=AlertSeverity.MEDIUM,
                        title=f"{count} document(s) awaiting approval",
                        description=f"{count} documents are blocked in approval stage",
                        count=count,
                        affected_entity_type="document",
                    )
                )
        except Exception as e:
            logger.debug(f"Error getting blocked approval alerts: {e}")

        return alerts

    async def _get_integration_error_alerts(
        self, tenant_id: str, db: AsyncSession
    ) -> list[AlertItem]:
        """Get alerts for integration errors (1C, EDO)."""
        alerts: list[AlertItem] = []

        try:
            from sqlalchemy import select, and_, func
            from app.domains.integrations.models import IntegrationLog

            stmt = select(func.count(IntegrationLog.id)).where(
                and_(
                    IntegrationLog.tenant_id == tenant_id,
                    IntegrationLog.status == "failed",
                    IntegrationLog.created_at
                    > datetime.utcnow() - timedelta(hours=24),
                )
            )
            result = await db.execute(stmt)
            count = result.scalar_one_or_none() or 0

            if count > 0:
                alerts.append(
                    AlertItem(
                        id="integration_errors",
                        category=AlertCategory.INTEGRATION_ERROR,
                        severity=AlertSeverity.HIGH,
                        title=f"{count} integration error(s) in last 24h",
                        description=f"{count} integration calls failed in the last 24 hours",
                        count=count,
                        affected_entity_type="integration",
                    )
                )
        except Exception as e:
            logger.debug(f"Error getting integration error alerts: {e}")

        return alerts

    async def _get_high_risk_alerts(
        self, tenant_id: str, db: AsyncSession
    ) -> list[AlertItem]:
        """Get alerts for high-risk items."""
        alerts: list[AlertItem] = []

        try:
            from sqlalchemy import select, and_, func
            from app.domains.risk.models import RiskAssessment

            stmt = select(func.count(RiskAssessment.id)).where(
                and_(
                    RiskAssessment.tenant_id == tenant_id,
                    RiskAssessment.severity == "critical",
                )
            )
            result = await db.execute(stmt)
            count = result.scalar_one_or_none() or 0

            if count > 0:
                alerts.append(
                    AlertItem(
                        id="high_risk_items",
                        category=AlertCategory.HIGH_RISK,
                        severity=AlertSeverity.CRITICAL,
                        title=f"{count} critical risk(s) identified",
                        description=f"{count} critical risks require immediate attention",
                        count=count,
                        affected_entity_type="risk_assessment",
                    )
                )
        except Exception as e:
            logger.debug(f"Error getting high risk alerts: {e}")

        return alerts

    async def _get_unassigned_task_alerts(
        self, tenant_id: str, db: AsyncSession
    ) -> list[AlertItem]:
        """Get alerts for unassigned tasks."""
        alerts: list[AlertItem] = []

        try:
            from sqlalchemy import select, and_, func
            from app.domains.tasks.models import Task

            stmt = select(func.count(Task.id)).where(
                and_(
                    Task.tenant_id == tenant_id,
                    Task.assigned_to == None,
                    Task.status.in_(["open", "pending"]),
                )
            )
            result = await db.execute(stmt)
            count = result.scalar_one_or_none() or 0

            if count > 0:
                alerts.append(
                    AlertItem(
                        id="unassigned_tasks",
                        category=AlertCategory.UNASSIGNED_TASK,
                        severity=AlertSeverity.MEDIUM,
                        title=f"{count} unassigned task(s)",
                        description=f"{count} tasks are unassigned and need attention",
                        count=count,
                        affected_entity_type="task",
                    )
                )
        except Exception as e:
            logger.debug(f"Error getting unassigned task alerts: {e}")

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
