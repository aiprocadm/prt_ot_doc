"""Reporting endpoints (MVP KPI aggregates)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.core.screen_access import screen_roles
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import (
    Incident,
    PPEIssue,
    Prescription,
    PrescriptionStatus,
    Tenant,
    TrainingPlan,
)
from app.models.risk import RiskAssessmentItem
from app.services.discipline_incidents import open_incidents_where
from app.services.discipline_risks import high_risk_item_where
from app.services.person_scope import employed_record_where

router = APIRouter(prefix="/reports", tags=["reports"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

# Роли берутся из единой карты прав экрана (core/screen_access): пункт меню
# виден ровно тем, кого пускает ручка — иначе человек видит раздел и получает
# 403 (docs/audit/ACCESS_MENU_VS_API.md, сторож tests/test_menu_matches_api.py).
_REPORT_ROLES = list(screen_roles("reports.view"))


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
async def get_kpi(
    tenant: TenantDep,
    session: SessionDep,
    _: ReportAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> dict[str, int]:
    TenantContextValidator.ensure_tenant_context(tenant)

    today = date.today()

    # Формула «высокий риск» одна на продукт (срез-131): её же берут разрез
    # аналитики и Командный центр — раньше каждый считал по-своему, и один из
    # них по мёртвой таблице.
    risks_high_stmt = (
        select(func.count())
        .select_from(RiskAssessmentItem)
        .where(*high_risk_item_where(str(tenant.id)))
    )
    # «Уволенный не в счёт» (срез-127) — тот же счётчик, что на сводке и в
    # аналитике (срез-96); KPI обязан совпадать с ними число в число.
    trainings_overdue_stmt = (
        select(func.count())
        .select_from(TrainingPlan)
        .where(
            TrainingPlan.tenant_id == tenant.id,
            TrainingPlan.due_date.is_not(None),
            TrainingPlan.due_date < today,
            employed_record_where(TrainingPlan, str(tenant.id)),
        )
    )
    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)

    ppe_issues_month_stmt = (
        select(func.count())
        .select_from(PPEIssue)
        .where(
            PPEIssue.tenant_id == tenant.id,
            PPEIssue.issued_at >= month_start,
            PPEIssue.issued_at < next_month,
        )
    )
    # «Открытое» — одна формула на платформу (срез-69): удалённые не считаются
    incidents_open_stmt = (
        select(func.count()).select_from(Incident).where(*open_incidents_where(str(tenant.id)))
    )
    prescriptions_overdue_stmt = (
        select(func.count())
        .select_from(Prescription)
        .where(
            Prescription.tenant_id == tenant.id,
            Prescription.status.in_([PrescriptionStatus.OPEN, PrescriptionStatus.IN_PROGRESS]),
            Prescription.due_at.is_not(None),
            Prescription.due_at < today,
        )
    )

    return {
        "risks_high": await _scalar(session, risks_high_stmt),
        "trainings_overdue": await _scalar(session, trainings_overdue_stmt),
        "ppe_issues_month": await _scalar(session, ppe_issues_month_stmt),
        "incidents_open": await _scalar(session, incidents_open_stmt),
        "prescriptions_overdue": await _scalar(session, prescriptions_overdue_stmt),
    }
