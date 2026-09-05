from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import abac
from app.db.session import rearm_session_tenant_context
from app.models.models import Tenant
from app.modules.analytics.breakdown import BREAKDOWN_DIMENSIONS, compute_breakdown
from app.modules.analytics.services import (
    AnalyticsAggregationService,
    DashboardFilters,
    KpiDashboardService,
)
from app.modules.projections.models import DashboardKpiSnapshot
from app.modules.projections.services import ProjectionOrchestrator
from app.schemas.discipline_reports import (
    DisciplineReportPage,
    DisciplineReportRead,
    DisciplineReportRunRead,
)
from app.services.discipline_report import list_reports, run_discipline_report


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


# Управленческие KPI: union прецедентов dashboard/operational/reports
# (_SUMMARY_ROLES + manager + ot_specialist). Worker/employee/client-роли не входят.
_ANALYTICS_READ_ROLES = [
    "admin",
    "owner",
    "hr",
    "ot_pb_lead",
    "line_manager",
    "ot_specialist",
    "manager",
]
_ANALYTICS_ADMIN_ROLES = ["admin", "owner"]

_ReadGuard = Depends(
    abac(_tenant_resource_id, required_roles=_ANALYTICS_READ_ROLES, action="read analytics")
)
_AdminGuard = Depends(
    abac(
        _tenant_resource_id,
        required_roles=_ANALYTICS_ADMIN_ROLES,
        action="recompute analytics",
    )
)

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[_ReadGuard])


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
        # rebuild committed — the transaction-local RLS GUCs are gone, re-arm
        # before the KPI reads below (SEC-65)
        await rearm_session_tenant_context(session)
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


@router.get("/dashboard/breakdown")
async def dashboard_breakdown(
    dimension: str = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    if dimension not in BREAKDOWN_DIMENSIONS:
        raise HTTPException(
            http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=api_problem_detail(
                code="breakdown_dimension_unknown",
                message=f"Unknown dimension: {dimension}",
                error_type="analytics",
            ),
        )
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=api_problem_detail(
                code="breakdown_window_invalid",
                message="date_from must not be after date_to",
                error_type="analytics",
            ),
        )
    return await compute_breakdown(
        session, str(tenant.id), dimension, date_from=date_from, date_to=date_to
    )


# Доп. №1 разд. 57.4 «авто-отчёты о состоянии по каждой дисциплине» (срез-50):
# отчёт арендатора о самом себе — снимок разреза «по дисциплинам» на дату и
# динамика к прошлому отчёту. Пишет еженедельный тик ``disciplines.report.tick``;
# «собрать сейчас» доступно тем же ролям, что читают дашборд: прогон
# идемпотентен по дате, второй отчёт за день не появится.
@router.get("/discipline-reports", response_model=DisciplineReportPage)
async def list_discipline_reports(
    limit: int = Query(default=12, ge=1, le=52),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> DisciplineReportPage:
    rows, total = await list_reports(session, str(tenant.id), limit=limit, offset=offset)
    return DisciplineReportPage(
        items=[DisciplineReportRead.model_validate(row) for row in rows], total=total
    )


@router.post("/discipline-reports/run", response_model=DisciplineReportRunRead)
@audit_operation("create", "discipline_status_report", id_attr="report")
async def run_discipline_report_now(
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> DisciplineReportRunRead:
    outcome = await run_discipline_report(session, str(tenant.id))
    await session.commit()
    return DisciplineReportRunRead(
        created=outcome.created,
        report=DisciplineReportRead.model_validate(outcome.report),
        notified=outcome.notified,
        mailed=outcome.mailed,
        summary=_run_summary(outcome.created, outcome.notified, outcome.mailed),
    )


def _recipients(count: int) -> str:
    tail = count % 100
    word = "получателю" if count % 10 == 1 and tail != 11 else "получателям"
    return f"{count} {word}"


def _run_summary(created: bool, notified: int, mailed: int = 0) -> str:
    if not created:
        return "Отчёт за сегодня уже есть — показан он, второй не пишется"
    if notified == 0 and mailed == 0:
        # Получателей нет (или все выключили оба канала) — это надо увидеть,
        # а не прочитать «собран» и решить, что директор уже в курсе.
        return "Отчёт собран, уведомление отправлять некому"
    # Срез-60: письмо — второй канал со своим согласием, поэтому итог по
    # каждому каналу свой. «Поставлено в очередь», а не «ушло»: отправляет
    # доставщик уведомлений, и без SMTP он честно пометит письмо пропущенным.
    card = (
        f"уведомление ушло {_recipients(notified)}"
        if notified
        else "уведомление в приложении отправлять некому"
    )
    letter = (
        f"письмо поставлено в очередь {_recipients(mailed)}"
        if mailed
        else "письмо никому не ушло: почта у получателей выключена"
    )
    return f"Отчёт собран, {card}, {letter}"


@router.post("/recompute", dependencies=[_AdminGuard])
async def recompute_dashboard(
    session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)
) -> dict:
    snapshot = await ProjectionOrchestrator(session, str(tenant.id)).rebuild_dashboard_snapshot(
        date.today()
    )
    return {"status": "ok", "payload": snapshot.payload}
