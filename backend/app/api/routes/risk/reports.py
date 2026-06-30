"""Risk endpoints — risk cards, action plans, risk listing (ARCH-4 slice 6 split)."""

from __future__ import annotations

from datetime import date

from fastapi import HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.api.routes.risk._common import (
    ActionPlanItemOut,
    ActionPlanOut,
    EditorAccess,
    RiskCardOut,
    RiskReadAccess,
    SessionDep,
    TenantDep,
    _risk_level_filter,
    _risk_unprocessable,
    engine_router,
    router,
)
from app.models.models import (
    Site,
)
from app.models.risk import (
    Risk,
    RiskActionPlan,
    RiskCard,
)
from app.schemas.risk import RiskListResponse
from app.services.risk import RiskService


@engine_router.get("/cards", response_model=list[RiskCardOut])
async def list_risk_cards(
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    assessment_id: str | None = Query(default=None, alias="assessment_id"),
    company_id: str | None = Query(default=None, alias="company_id"),
    site_id: str | None = Query(default=None, alias="site_id"),
    workplace_id: str | None = Query(default=None, alias="workplace_id"),
    position_id: str | None = Query(default=None, alias="position_id"),
    employee_id: str | None = Query(default=None, alias="employee_id"),
) -> list[RiskCardOut] | Response:
    tenant_id = str(tenant.id)
    stmt = select(RiskCard).where(RiskCard.tenant_id == tenant_id)
    if assessment_id:
        stmt = stmt.where(RiskCard.assessment_id == assessment_id)
    if company_id:
        stmt = stmt.where(RiskCard.company_id == company_id)
    if site_id:
        stmt = stmt.where(RiskCard.site_id == site_id)
    if workplace_id:
        stmt = stmt.where(RiskCard.workplace_id == workplace_id)
    if position_id:
        stmt = stmt.where(RiskCard.position_id == position_id)
    if employee_id:
        stmt = stmt.where(RiskCard.employee_id == employee_id)
    records = list(
        (await session.execute(stmt.order_by(RiskCard.created_at.desc()))).scalars().all()
    )
    etag = compute_list_etag(
        tenant_id=tenant_id,
        items=records,
        scalars=[
            ("total", len(records)),
            ("kind", "cards"),
            ("assessment", assessment_id or ""),
            ("company", company_id or ""),
            ("site", site_id or ""),
            ("workplace", workplace_id or ""),
            ("position", position_id or ""),
            ("employee", employee_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return [
        RiskCardOut(
            id=record.id,
            assessment_id=record.assessment_id,
            company_id=record.company_id,
            site_id=record.site_id,
            workplace_id=record.workplace_id,
            position_id=record.position_id,
            employee_id=record.employee_id,
            methodology_id=record.methodology_id,
            methodology_version=record.methodology_version,
            summary=record.summary,
        )
        for record in records
    ]


@engine_router.get("/action-plans", response_model=list[ActionPlanOut])
async def list_action_plans(
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    assessment_id: str | None = Query(default=None, alias="assessment_id"),
    company_id: str | None = Query(default=None, alias="company_id"),
    site_id: str | None = Query(default=None, alias="site_id"),
    workplace_id: str | None = Query(default=None, alias="workplace_id"),
    position_id: str | None = Query(default=None, alias="position_id"),
    employee_id: str | None = Query(default=None, alias="employee_id"),
) -> list[ActionPlanOut] | Response:
    tenant_id = str(tenant.id)
    stmt = (
        select(RiskActionPlan)
        .where(RiskActionPlan.tenant_id == tenant_id)
        .options(selectinload(RiskActionPlan.items))
    )
    if assessment_id:
        stmt = stmt.where(RiskActionPlan.assessment_id == assessment_id)
    if company_id:
        stmt = stmt.where(RiskActionPlan.company_id == company_id)
    if site_id:
        stmt = stmt.where(RiskActionPlan.site_id == site_id)
    if workplace_id:
        stmt = stmt.where(RiskActionPlan.workplace_id == workplace_id)
    if position_id:
        stmt = stmt.where(RiskActionPlan.position_id == position_id)
    if employee_id:
        stmt = stmt.where(RiskActionPlan.employee_id == employee_id)

    records = list(
        (await session.execute(stmt.order_by(RiskActionPlan.created_at.desc()))).scalars().all()
    )
    etag = compute_list_etag(
        tenant_id=tenant_id,
        items=records,
        scalars=[
            ("total", len(records)),
            ("kind", "action_plans"),
            ("assessment", assessment_id or ""),
            ("company", company_id or ""),
            ("site", site_id or ""),
            ("workplace", workplace_id or ""),
            ("position", position_id or ""),
            ("employee", employee_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    result: list[ActionPlanOut] = []
    for record in records:
        items = sorted(record.items, key=lambda item: (item.due_date or date.min, item.id))
        result.append(
            ActionPlanOut(
                id=record.id,
                assessment_id=record.assessment_id,
                status=record.status,
                company_id=record.company_id,
                site_id=record.site_id,
                workplace_id=record.workplace_id,
                position_id=record.position_id,
                employee_id=record.employee_id,
                methodology_id=record.methodology_id,
                methodology_version=record.methodology_version,
                items=[
                    ActionPlanItemOut(
                        id=item.id,
                        hazard_id=item.hazard_id,
                        measure_text=item.measure_text,
                        owner_role=item.owner_role,
                        owner_id=item.owner_id,
                        due_date=item.due_date,
                        status=item.status,
                    )
                    for item in items
                ],
            )
        )
    return result


@router.get("/risks", response_model=RiskListResponse)
async def list_risks(
    session: SessionDep,
    tenant: TenantDep,
    access: RiskReadAccess,
    site_id: str | None = Query(default=None, alias="site_id"),
    risk_level: str | None = Query(default=None, alias="risk_level"),
) -> RiskListResponse:
    if site_id:
        try:
            await RiskService.ensure_site_belongs_to_tenant(session, tenant, site_id)
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        if site_id:
            site = await session.get(Site, site_id)
            if site is not None:
                access.ensure_site_access(site_id, site.company_id, action="read risks")

    if risk_level:
        access.ensure_risk_access(risk_level=risk_level, action="read risks")

    risks, report = await RiskService.list_by_site(session, tenant, site_id)
    if risk_level:
        try:
            minimum, maximum = _risk_level_filter(risk_level)
        except ValueError as exc:
            raise _risk_unprocessable(str(exc)) from exc
        filtered: list[Risk] = []
        for risk in risks:
            if minimum is not None and risk.level < minimum:
                continue
            if maximum is not None and risk.level > maximum:
                continue
            filtered.append(risk)
        risks = filtered
    return RiskListResponse.from_entities(risks, report)
