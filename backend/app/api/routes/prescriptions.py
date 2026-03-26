"""Prescription endpoints for inspection follow-ups."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Incident, Inspection, Prescription, PrescriptionStatus, User
from app.models.tenanting import Tenant
from app.schemas.prescriptions import (
    PrescriptionCreate,
    PrescriptionPage,
    PrescriptionRead,
    PrescriptionUpdate,
)
from app.services.audit import AuditService

router = APIRouter(tags=["prescriptions"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_PRESCRIPTION_READ_ROLES = ["admin", "owner", "hr", "line_manager"]
_PRESCRIPTION_WRITE_ROLES = ["admin", "owner", "hr", "line_manager"]


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_PRESCRIPTION_READ_ROLES, action="read prescriptions")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_PRESCRIPTION_WRITE_ROLES, action="manage prescriptions")),
]


async def _get_inspection(session: AsyncSession, tenant_id: str, inspection_id: str) -> Inspection:
    stmt = select(Inspection).where(
        Inspection.id == inspection_id,
        Inspection.tenant_id == tenant_id,
        Inspection.deleted_at.is_(None),
    )
    inspection = (await session.execute(stmt)).scalar_one_or_none()
    if inspection is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error_detail("inspection_not_found", "Inspection not found"),
        )
    return inspection


async def _get_incident(session: AsyncSession, tenant_id: str, incident_id: str) -> Incident:
    stmt = select(Incident).where(
        Incident.id == incident_id,
        Incident.tenant_id == tenant_id,
        Incident.deleted_at.is_(None),
    )
    incident = (await session.execute(stmt)).scalar_one_or_none()
    if incident is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error_detail("incident_not_found", "Incident not found"),
        )
    return incident


async def _get_user(session: AsyncSession, tenant_id: str, user_id: str) -> User:
    stmt = select(User).where(User.id == user_id, User.tenant_id == tenant_id, User.deleted_at.is_(None))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error_detail("user_not_found", "User not found"),
        )
    return user


async def _get_prescription(
    session: AsyncSession, tenant_id: str, prescription_id: str
) -> Prescription:
    stmt = select(Prescription).where(
        Prescription.id == prescription_id,
        Prescription.tenant_id == tenant_id,
        Prescription.deleted_at.is_(None),
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error_detail("prescription_not_found", "Prescription not found"),
        )
    return record


@router.get("/prescriptions", response_model=PrescriptionPage)
async def list_prescriptions(
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    inspection_id: str | None = Query(default=None, min_length=1, max_length=36),
    incident_id: str | None = Query(default=None, min_length=1, max_length=36),
    status_filter: PrescriptionStatus | None = Query(default=None, alias="status"),
    assignee_id: str | None = Query(default=None, min_length=1, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PrescriptionPage:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Prescription).where(
        Prescription.tenant_id == tenant.id, Prescription.deleted_at.is_(None)
    )
    if inspection_id:
        stmt = stmt.where(Prescription.inspection_id == inspection_id)
    if incident_id:
        stmt = stmt.where(Prescription.incident_id == incident_id)
    if status_filter:
        stmt = stmt.where(Prescription.status == status_filter)
    if assignee_id:
        stmt = stmt.where(Prescription.assignee_id == assignee_id)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Prescription.due_at.desc().nullslast(), Prescription.created_at.desc())
    stmt = stmt.offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    return PrescriptionPage(
        items=[PrescriptionRead.model_validate(item) for item in items],
        total=int(total or 0),
    )


@router.post("/prescriptions", response_model=PrescriptionRead, status_code=status.HTTP_201_CREATED)
async def create_prescription(
    request: Request,
    payload: PrescriptionCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PrescriptionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    await _get_inspection(session, str(tenant.id), payload.inspection_id)
    if payload.incident_id:
        await _get_incident(session, str(tenant.id), payload.incident_id)
    if payload.assignee_id:
        await _get_user(session, str(tenant.id), payload.assignee_id)

    record = Prescription(
        tenant_id=str(tenant.id),
        inspection_id=payload.inspection_id,
        incident_id=payload.incident_id,
        description=payload.description,
        due_at=payload.due_at,
        status=payload.status,
        assignee_id=payload.assignee_id,
    )
    session.add(record)
    await session.flush()
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="prescription",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"inspection_id": record.inspection_id},
    )
    await session.commit()
    await session.refresh(record)
    return PrescriptionRead.model_validate(record)


@router.get("/prescriptions/{prescription_id}", response_model=PrescriptionRead)
async def get_prescription(
    prescription_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> PrescriptionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    record = await _get_prescription(session, str(tenant.id), prescription_id)
    return PrescriptionRead.model_validate(record)


@router.patch("/prescriptions/{prescription_id}", response_model=PrescriptionRead)
async def update_prescription(
    request: Request,
    prescription_id: str,
    payload: PrescriptionUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PrescriptionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    record = await _get_prescription(session, str(tenant.id), prescription_id)
    updates = payload.model_dump(exclude_unset=True)
    if "inspection_id" in updates and updates["inspection_id"]:
        await _get_inspection(session, str(tenant.id), str(updates["inspection_id"]))
    if "incident_id" in updates and updates["incident_id"]:
        await _get_incident(session, str(tenant.id), str(updates["incident_id"]))
    if "assignee_id" in updates and updates["assignee_id"]:
        await _get_user(session, str(tenant.id), str(updates["assignee_id"]))

    for key, value in updates.items():
        setattr(record, key, value)

    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="prescription",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"status": record.status.value},
    )
    await session.commit()
    await session.refresh(record)
    return PrescriptionRead.model_validate(record)
