"""Dashboard summary endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.models.models import Incident, IncidentStatus, Tenant, TrainingPlan
from app.models.obligations import Task, TaskPriority, TaskStatus
from app.models.risk import RiskAssessment
from app.schemas.dashboard import DashboardSummary, DashboardTrainingSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)

_SUMMARY_ROLES = ["admin", "owner", "line_manager", "hr", "ot_pb_lead"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


SummaryAccess = Depends(
    abac(_tenant_resource_id, required_roles=_SUMMARY_ROLES, action="read dashboard")
)


async def _scalar(session: AsyncSession, stmt) -> int:
    value = await session.scalar(stmt)
    return int(value or 0)


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    _: AccessContext = SummaryAccess,
) -> DashboardSummary:
    now = datetime.now(timezone.utc)
    today = date.today()
    due_soon_date = today + timedelta(days=14)
    open_statuses = [TaskStatus.OPEN, TaskStatus.IN_PROGRESS]

    overdue_tasks_stmt = select(func.count()).select_from(Task).where(
        Task.tenant_id == tenant.id,
        Task.status.in_(open_statuses),
        Task.due_at.is_not(None),
        Task.due_at < now,
    )
    critical_obligations_stmt = select(func.count()).select_from(Task).where(
        Task.tenant_id == tenant.id,
        Task.status.in_(open_statuses),
        Task.priority.in_([TaskPriority.HIGH, TaskPriority.CRITICAL]),
        Task.due_at.is_not(None),
        Task.due_at <= now + timedelta(days=7),
    )
    incidents_open_stmt = select(func.count()).select_from(Incident).where(
        Incident.tenant_id == tenant.id,
        Incident.status.notin_([IncidentStatus.CLOSED, IncidentStatus.CANCELLED]),
    )
    risks_total_stmt = select(func.count()).select_from(RiskAssessment).where(
        RiskAssessment.tenant_id == tenant.id
    )
    training_total_stmt = select(func.count()).select_from(TrainingPlan).where(
        TrainingPlan.tenant_id == tenant.id
    )
    training_overdue_stmt = select(func.count()).select_from(TrainingPlan).where(
        TrainingPlan.tenant_id == tenant.id,
        TrainingPlan.due_date.is_not(None),
        TrainingPlan.due_date < today,
    )
    training_due_soon_stmt = select(func.count()).select_from(TrainingPlan).where(
        TrainingPlan.tenant_id == tenant.id,
        TrainingPlan.due_date.is_not(None),
        TrainingPlan.due_date >= today,
        TrainingPlan.due_date <= due_soon_date,
    )

    overdue_tasks = await _scalar(session, overdue_tasks_stmt)
    critical_obligations = await _scalar(session, critical_obligations_stmt)
    incidents_open = await _scalar(session, incidents_open_stmt)
    risks_total = await _scalar(session, risks_total_stmt)
    training_total = await _scalar(session, training_total_stmt)
    training_overdue = await _scalar(session, training_overdue_stmt)
    training_due_soon = await _scalar(session, training_due_soon_stmt)

    if training_overdue > 0:
        training_status = "critical"
    elif training_due_soon > 0:
        training_status = "warning"
    else:
        training_status = "ok"

    return DashboardSummary(
        overdue_tasks=overdue_tasks,
        critical_obligations=critical_obligations,
        incidents_open=incidents_open,
        risks_total=risks_total,
        training=DashboardTrainingSummary(
            total=training_total,
            overdue=training_overdue,
            due_soon=training_due_soon,
            status=training_status,
        ),
        generated_at=now.isoformat(),
    )
