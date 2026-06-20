"""Endpoints for personal permits (личные допуски): CRUD + lifecycle operations."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.permits import (
    create_permit,
    extend_permit,
    revoke_permit,
    update_permit,
)
from app.domains.permits import lifecycle as lc
from app.models.models import Permit, Person, Position
from app.models.tenanting import Tenant
from app.schemas.permit import (
    PermitCreate,
    PermitExtend,
    PermitPage,
    PermitRead,
    PermitUpdate,
)

router = APIRouter(prefix="/permits")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


_PERMIT_READ_ROLES = ["admin"]
_PERMIT_WRITE_ROLES = ["admin"]

ReaderAccess = Annotated[
    AccessContext, Depends(abac(_tenant_resource_id, required_roles=_PERMIT_READ_ROLES))
]
WriterAccess = Annotated[
    AccessContext, Depends(abac(_tenant_resource_id, required_roles=_PERMIT_WRITE_ROLES))
]


def _transition_conflict(exc: lc.PermitTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="PERMIT_TRANSITION_INVALID", message=str(exc), error_type="permit"
        ),
    )


def _permit_schema(permit: Permit) -> PermitRead:
    return PermitRead(
        id=str(permit.id),
        person_id=str(permit.person_id),
        position_id=str(permit.position_id) if permit.position_id else None,
        permit_type=permit.permit_type,
        issued_at=permit.issued_at,
        valid_until=permit.valid_until,
        status=str(permit.status),
        is_expired=lc.is_expired(str(permit.status), permit.valid_until, date.today()),
        created_at=permit.created_at,
        updated_at=permit.updated_at,
    )


async def _get_permit_or_404(session: AsyncSession, tenant: Tenant, permit_id: str) -> Permit:
    stmt = select(Permit).where(Permit.id == permit_id, Permit.tenant_id == tenant.id)
    permit = (await session.execute(stmt)).scalar_one_or_none()
    if permit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permit not found")
    return permit


async def _ensure_person(session: AsyncSession, tenant: Tenant, person_id: str) -> None:
    stmt = select(Person.id).where(
        Person.id == person_id, Person.tenant_id == tenant.id, Person.deleted_at.is_(None)
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "person not found")


async def _ensure_position(session: AsyncSession, tenant: Tenant, position_id: str) -> None:
    stmt = select(Position.id).where(
        Position.id == position_id, Position.tenant_id == tenant.id, Position.deleted_at.is_(None)
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "position not found")


@router.get("", response_model=PermitPage)
async def list_permits(
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
    person_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    expired_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PermitPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    if status_filter and expired_only:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "status filter and expired_only are mutually exclusive",
        )
    stmt = select(Permit).where(Permit.tenant_id == tenant.id)
    count_stmt = select(func.count()).select_from(Permit).where(Permit.tenant_id == tenant.id)
    if person_id:
        stmt = stmt.where(Permit.person_id == person_id)
        count_stmt = count_stmt.where(Permit.person_id == person_id)
    if status_filter:
        stmt = stmt.where(Permit.status == status_filter)
        count_stmt = count_stmt.where(Permit.status == status_filter)
    if expired_only:
        stmt = stmt.where(Permit.status == lc.PERMIT_STATUS_EXPIRED)
        count_stmt = count_stmt.where(Permit.status == lc.PERMIT_STATUS_EXPIRED)
    stmt = stmt.order_by(Permit.issued_at.desc()).limit(limit).offset(offset)
    permits = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return PermitPage(items=[_permit_schema(p) for p in permits], total=total)


@router.post("", response_model=PermitRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "permit")
async def create_permit_endpoint(
    payload: PermitCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> PermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _ensure_person(session, tenant, payload.person_id)
    if payload.position_id:
        await _ensure_position(session, tenant, payload.position_id)
    permit = await create_permit(
        session, tenant_id=tenant.id, person_id=payload.person_id,
        permit_type=payload.permit_type, issued_at=payload.issued_at,
        valid_until=payload.valid_until, position_id=payload.position_id,
    )
    return _permit_schema(permit)


@router.get("/{permit_id}", response_model=PermitRead)
async def get_permit(
    permit_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess
) -> PermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return _permit_schema(await _get_permit_or_404(session, tenant, permit_id))


@router.patch("/{permit_id}", response_model=PermitRead)
@audit_operation("update", "permit")
async def update_permit_endpoint(
    permit_id: str, payload: PermitUpdate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> PermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_permit_or_404(session, tenant, permit_id)  # fast-fail before any other work
    fields = payload.model_dump(exclude_unset=True)
    new_position_id = fields.get("position_id")
    if new_position_id is not None:
        await _ensure_position(session, tenant, new_position_id)
    try:
        permit = await update_permit(
            session, tenant_id=tenant.id, permit_id=permit_id,
            permit_type=fields.get("permit_type"),
            valid_until=fields.get("valid_until"),
            position_id=fields.get("position_id"),
            valid_until_set="valid_until" in fields,
            position_id_set="position_id" in fields,
        )
    except lc.PermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if permit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permit not found")
    return _permit_schema(permit)


@router.post("/{permit_id}/extend", response_model=PermitRead)
@audit_operation("update", "permit")
async def extend_permit_endpoint(
    permit_id: str, payload: PermitExtend, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> PermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        permit = await extend_permit(
            session, tenant_id=tenant.id, permit_id=permit_id, valid_until=payload.valid_until
        )
    except lc.PermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if permit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permit not found")
    return _permit_schema(permit)


@router.post("/{permit_id}/revoke", response_model=PermitRead)
@audit_operation("update", "permit")
async def revoke_permit_endpoint(
    permit_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> PermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        permit = await revoke_permit(session, tenant_id=tenant.id, permit_id=permit_id)
    except lc.PermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if permit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permit not found")
    return _permit_schema(permit)
