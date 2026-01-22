from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.domains.incidents import add_inspection_result, register_inspection, update_inspection
from app.models.models import Inspection, InspectionResult, InspectionStatus, Tenant
from app.schemas.incidents import (
    InspectionCreate,
    InspectionPage,
    InspectionRead,
    InspectionResultCreate,
    InspectionResultRead,
    InspectionUpdate,
)

router = APIRouter(tags=["inspections"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_manager_roles = ["admin"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_manager_roles, action="read inspections")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_manager_roles, action="manage inspections")),
]


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
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    company_id: str | None = Query(default=None, min_length=1, max_length=36),
    site_id: str | None = Query(default=None, min_length=1, max_length=36),
    status_filter: InspectionStatus | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> InspectionPage:
    stmt = select(Inspection).options(selectinload(Inspection.results)).where(
        Inspection.tenant_id == tenant.id, Inspection.deleted_at.is_(None)
    )
    if company_id:
        stmt = stmt.where(Inspection.company_id == company_id)
    if site_id:
        stmt = stmt.where(Inspection.site_id == site_id)
    if status_filter:
        stmt = stmt.where(Inspection.status == status_filter)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Inspection.scheduled_at.desc().nullslast(), Inspection.created_at.desc()).offset(offset).limit(limit)
    items = (await session.execute(stmt)).scalars().unique().all()
    total = await session.scalar(total_stmt)
    return InspectionPage(items=[_serialize_inspection(item) for item in items], total=int(total or 0))


@router.post("/inspections", response_model=InspectionRead, status_code=status.HTTP_201_CREATED)
async def create_inspection(
    payload: InspectionCreate,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
) -> InspectionRead:
    try:
        inspection = await register_inspection(
            session,
            tenant_id=str(tenant.id),
            company_id=payload.company_id,
            site_id=payload.site_id,
            authority=payload.authority,
            purpose=payload.purpose,
            scheduled_at=payload.scheduled_at,
            status=payload.status,
            started_at=payload.started_at,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return _serialize_inspection(inspection)


@router.get("/inspections/{inspection_id}", response_model=InspectionRead)
async def get_inspection(
    inspection_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> InspectionRead:
    inspection = await _get_inspection(session, tenant, inspection_id)
    return _serialize_inspection(inspection)


@router.patch("/inspections/{inspection_id}", response_model=InspectionRead)
async def patch_inspection(
    inspection_id: str,
    payload: InspectionUpdate,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
) -> InspectionRead:
    inspection = await _get_inspection(session, tenant, inspection_id)
    updates = payload.model_dump(exclude_unset=True)
    try:
        updated = await update_inspection(
            session,
            tenant_id=str(tenant.id),
            inspection=inspection,
            updates=updates,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _serialize_inspection(updated)


@router.post(
    "/inspections/{inspection_id}/results",
    response_model=InspectionResultRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_inspection_result_entry(
    inspection_id: str,
    payload: InspectionResultCreate,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
) -> InspectionResultRead:
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return InspectionResultRead.model_validate(result)


@router.get("/inspections/{inspection_id}/results", response_model=list[InspectionResultRead])
async def list_inspection_results(
    inspection_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> list[InspectionResultRead]:
    inspection = await _get_inspection(session, tenant, inspection_id)
    stmt = (
        select(InspectionResult)
        .where(InspectionResult.inspection_id == inspection.id, InspectionResult.tenant_id == tenant.id)
        .order_by(InspectionResult.created_at.asc())
    )
    records = list((await session.execute(stmt)).scalars().all())
    return [InspectionResultRead.model_validate(record) for record in records]
