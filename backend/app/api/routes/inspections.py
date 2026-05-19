from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import compute_list_etag
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.incidents import add_inspection_result, register_inspection, update_inspection
from app.models.models import (
    Inspection,
    InspectionResult,
    InspectionStatus,
    InspectionType,
    Tenant,
    User,
)
from app.schemas.incidents import (
    InspectionCreate,
    InspectionPage,
    InspectionRead,
    InspectionResultCreate,
    InspectionResultRead,
    InspectionUpdate,
)
from app.services.audit import AuditService
from app.services.obligations import upsert_inspection_task
from app.services.outbox import OutboxService

router = APIRouter(tags=["inspections"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_INSPECTION_READ_ROLES = ["admin"]
_INSPECTION_WRITE_ROLES = ["admin"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_INSPECTION_READ_ROLES, action="read inspections")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_INSPECTION_WRITE_ROLES, action="manage inspections")),
]


def _inspection_bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_problem_detail(code="INSPECTION_VALIDATION_ERROR", message=message, error_type="inspections"),
    )


def _serialize_inspection(inspection: Inspection) -> InspectionRead:
    results = inspection.__dict__.get("results")
    serialized_results = (
        [InspectionResultRead.model_validate(result) for result in results]
        if results is not None
        else []
    )
    payload = {
        "id": inspection.id,
        "company_id": inspection.company_id,
        "site_id": inspection.site_id,
        "inspection_type": inspection.inspection_type,
        "responsible_id": inspection.responsible_id,
        "recurrence_rule": inspection.recurrence_rule,
        "authority": inspection.authority,
        "purpose": inspection.purpose,
        "scheduled_at": inspection.scheduled_at,
        "started_at": inspection.started_at,
        "finished_at": inspection.finished_at,
        "status": inspection.status,
        "result_summary": inspection.result_summary,
        "results": serialized_results,
    }
    return InspectionRead.model_validate(payload)


async def _get_inspection(session: AsyncSession, tenant: Tenant, inspection_id: str) -> Inspection:
    stmt = (
        select(Inspection)
        .options(selectinload(Inspection.results))
        .where(Inspection.id == inspection_id, Inspection.tenant_id == tenant.id, Inspection.deleted_at.is_(None))
    )
    inspection = (await session.execute(stmt)).scalar_one_or_none()
    if inspection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inspection not found")
    return inspection


@router.get("/inspections", response_model=InspectionPage)
async def list_inspections(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    company_id: str | None = Query(default=None, min_length=1, max_length=36),
    site_id: str | None = Query(default=None, min_length=1, max_length=36),
    status_filter: InspectionStatus | None = Query(default=None),
    inspection_type: InspectionType | None = Query(default=None),
    responsible_id: str | None = Query(default=None, min_length=1, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> InspectionPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Inspection).options(selectinload(Inspection.results)).where(
        Inspection.tenant_id == tenant.id, Inspection.deleted_at.is_(None)
    )
    if company_id:
        stmt = stmt.where(Inspection.company_id == company_id)
    if site_id:
        stmt = stmt.where(Inspection.site_id == site_id)
    if status_filter:
        stmt = stmt.where(Inspection.status == status_filter)
    if inspection_type:
        stmt = stmt.where(Inspection.inspection_type == inspection_type)
    if responsible_id:
        stmt = stmt.where(Inspection.responsible_id == responsible_id)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Inspection.scheduled_at.desc().nullslast(), Inspection.created_at.desc()).offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().unique().all())
    total = await session.scalar(total_stmt)
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[
            ("total", int(total or 0)),
            ("limit", limit),
            ("offset", offset),
            ("company", company_id or ""),
            ("site", site_id or ""),
            ("status", status_filter.value if status_filter else ""),
            ("type", inspection_type.value if inspection_type else ""),
            ("responsible", responsible_id or ""),
        ],
    )
    response.headers["ETag"] = etag
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    return InspectionPage(items=[_serialize_inspection(item) for item in items], total=int(total or 0))


@router.post("/inspections", response_model=InspectionRead, status_code=status.HTTP_201_CREATED)
async def create_inspection(
    request: Request,
    payload: InspectionCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> InspectionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    if payload.responsible_id:
        stmt = select(User).where(
            User.id == payload.responsible_id,
            User.tenant_id == tenant.id,
            User.deleted_at.is_(None),
        )
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Responsible user not found")
    try:
        inspection = await register_inspection(
            session,
            tenant_id=str(tenant.id),
            company_id=payload.company_id,
            site_id=payload.site_id,
            inspection_type=payload.inspection_type,
            responsible_id=payload.responsible_id,
            recurrence_rule=payload.recurrence_rule,
            authority=payload.authority,
            purpose=payload.purpose,
            scheduled_at=payload.scheduled_at,
            status=payload.status,
            started_at=payload.started_at,
        )
    except ValueError as exc:
        raise _inspection_bad_request(str(exc)) from exc

    await upsert_inspection_task(
        session,
        tenant_id=str(tenant.id),
        inspection=inspection,
        actor_id=getattr(access.user, "id", None),
    )
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="inspection",
        object_id=inspection.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"scheduled_at": inspection.scheduled_at, "status": inspection.status.value},
    )
    await OutboxService(session).enqueue(
        tenant_id=str(tenant.id),
        event_type="InspectionCreated",
        payload={
            "tenant_id": str(tenant.id),
            "inspection_id": inspection.id,
            "company_id": inspection.company_id,
            "site_id": inspection.site_id,
            "status": inspection.status.value,
            "inspection_type": inspection.inspection_type.value,
            "authority": inspection.authority,
            "actor_id": getattr(access.user, "id", None),
        },
    )
    await session.commit()
    await session.refresh(inspection)

    return _serialize_inspection(inspection)


@router.get("/inspections/{inspection_id}", response_model=InspectionRead)
async def get_inspection(
    inspection_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> InspectionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    inspection = await _get_inspection(session, tenant, inspection_id)
    return _serialize_inspection(inspection)


@router.patch("/inspections/{inspection_id}", response_model=InspectionRead)
async def patch_inspection(
    request: Request,
    inspection_id: str,
    payload: InspectionUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> InspectionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    inspection = await _get_inspection(session, tenant, inspection_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("responsible_id"):
        stmt = select(User).where(
            User.id == updates["responsible_id"],
            User.tenant_id == tenant.id,
            User.deleted_at.is_(None),
        )
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Responsible user not found")
    try:
        updated = await update_inspection(
            session,
            tenant_id=str(tenant.id),
            inspection=inspection,
            updates=updates,
        )
    except ValueError as exc:
        raise _inspection_bad_request(str(exc)) from exc
    await upsert_inspection_task(
        session,
        tenant_id=str(tenant.id),
        inspection=updated,
        actor_id=getattr(access.user, "id", None),
    )
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="inspection",
        object_id=updated.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"status": updated.status.value},
    )
    await session.commit()
    await session.refresh(updated)
    return _serialize_inspection(updated)


@router.post(
    "/inspections/{inspection_id}/results",
    response_model=InspectionResultRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_inspection_result_entry(
    request: Request,
    inspection_id: str,
    payload: InspectionResultCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> InspectionResultRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    inspection = await _get_inspection(session, tenant, inspection_id)
    try:
        result = await add_inspection_result(
            session,
            tenant_id=str(tenant.id),
            inspection=inspection,
            title=payload.title,
            outcome=payload.outcome,
            notes=payload.notes,
            issued_at=payload.issued_at,
            file_id=payload.file_id,
        )
    except ValueError as exc:
        raise _inspection_bad_request(str(exc)) from exc
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="inspection_result",
        object_id=result.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"inspection_id": inspection.id},
    )
    await session.commit()
    await session.refresh(result)
    return InspectionResultRead.model_validate(result)


@router.get("/inspections/{inspection_id}/results", response_model=list[InspectionResultRead])
async def list_inspection_results(
    inspection_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> list[InspectionResultRead]:
    TenantContextValidator.ensure_tenant_context(tenant)

    inspection = await _get_inspection(session, tenant, inspection_id)
    stmt = (
        select(InspectionResult)
        .where(InspectionResult.inspection_id == inspection.id, InspectionResult.tenant_id == tenant.id)
        .order_by(InspectionResult.created_at.asc())
    )
    records = list((await session.execute(stmt)).scalars().all())
    return [InspectionResultRead.model_validate(record) for record in records]
