"""Reporting endpoints (MVP KPI aggregates)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import (
    Incident,
    IncidentStatus,
    PPEIssue,
    Prescription,
    PrescriptionStatus,
    Tenant,
    TrainingPlan,
)
from app.models.risk import RiskAssessmentItem

router = APIRouter(prefix="/reports", tags=["reports"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_REPORT_ROLES = ["admin", "owner", "ot_specialist", "line_manager"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ReportAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_REPORT_ROLES, action="read reports")),
]


async def _scalar(session: AsyncSession, stmt) -> int:
    value = await session.scalar(stmt)
    return int(value or 0)


@router.get("/kpi")
async def get_kpi(tenant: TenantDep, session: SessionDep, _: ReportAccess,
    correlation_id: str = Depends(get_correlation_id)) -> dict[str, int]:
    TenantContextValidator.ensure_tenant_context(tenant)

    today = date.today()

    risks_high_stmt = select(func.count()).select_from(RiskAssessmentItem).where(
        RiskAssessmentItem.tenant_id == tenant.id,
        RiskAssessmentItem.level.in_(["high", "crit"]),
    )
    trainings_overdue_stmt = select(func.count()).select_from(TrainingPlan).where(
        TrainingPlan.tenant_id == tenant.id,
        TrainingPlan.due_date.is_not(None),
        TrainingPlan.due_date < today,
    )
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)

    ppe_issues_month_stmt = select(func.count()).select_from(PPEIssue).where(
        PPEIssue.tenant_id == tenant.id,
        PPEIssue.issued_at >= month_start,
        PPEIssue.issued_at < next_month,
    )
    incidents_open_stmt = select(func.count()).select_from(Incident).where(
        Incident.tenant_id == tenant.id,
        Incident.status.notin_([IncidentStatus.CLOSED, IncidentStatus.CANCELLED]),
    )
    prescriptions_overdue_stmt = select(func.count()).select_from(Prescription).where(
        Prescription.tenant_id == tenant.id,
        Prescription.status.in_([PrescriptionStatus.OPEN, PrescriptionStatus.IN_PROGRESS]),
        Prescription.due_at.is_not(None),
        Prescription.due_at < today,
    )

    return {
        "risks_high": await _scalar(session, risks_high_stmt),
        "trainings_overdue": await _scalar(session, trainings_overdue_stmt),
        "ppe_issues_month": await _scalar(session, ppe_issues_month_stmt),
        "incidents_open": await _scalar(session, incidents_open_stmt),
        "prescriptions_overdue": await _scalar(session, prescriptions_overdue_stmt),
    }
