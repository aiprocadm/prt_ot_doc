"""Attestation endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Attestation, AttestationStatus, Person, Position, Tenant, User
from app.schemas.attestations import (
    AttestationCreate,
    AttestationPage,
    AttestationRead,
    AttestationUpdate,
)
from app.services.audit import AuditService
from app.services.obligations import upsert_attestation_task

router = APIRouter(tags=["attestations"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_ATTESTATION_READ_ROLES = ["admin", "owner", "hr", "line_manager"]
_ATTESTATION_WRITE_ROLES = ["admin", "owner", "hr", "line_manager"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_ATTESTATION_READ_ROLES, action="read attestations")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_ATTESTATION_WRITE_ROLES, action="manage attestations")),
]


async def _get_person(session: AsyncSession, tenant_id: str, person_id: str) -> Person:
    stmt = select(Person).where(
        Person.id == person_id, Person.tenant_id == tenant_id, Person.deleted_at.is_(None)
    )
    person = (await session.execute(stmt)).scalar_one_or_none()
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    return person


async def _get_position(session: AsyncSession, tenant_id: str, position_id: str) -> Position:
    stmt = select(Position).where(
        Position.id == position_id, Position.tenant_id == tenant_id, Position.deleted_at.is_(None)
    )
    position = (await session.execute(stmt)).scalar_one_or_none()
    if position is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Position not found")
    return position


async def _get_user(session: AsyncSession, tenant_id: str, user_id: str) -> User:
    stmt = select(User).where(User.id == user_id, User.tenant_id == tenant_id, User.deleted_at.is_(None))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


async def _get_attestation(
    session: AsyncSession, tenant_id: str, attestation_id: str
) -> Attestation:
    stmt = select(Attestation).where(
        Attestation.id == attestation_id,
        Attestation.tenant_id == tenant_id,
        Attestation.deleted_at.is_(None),
    )
    attestation = (await session.execute(stmt)).scalar_one_or_none()
    if attestation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attestation not found")
    return attestation


@router.get("/attestations", response_model=AttestationPage)
async def list_attestations(
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    person_id: str | None = Query(default=None, min_length=1, max_length=36),
    status_filter: AttestationStatus | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AttestationPage:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Attestation).where(
        Attestation.tenant_id == tenant.id, Attestation.deleted_at.is_(None)
    )
    if person_id:
        stmt = stmt.where(Attestation.person_id == person_id)
    if status_filter:
        stmt = stmt.where(Attestation.status == status_filter)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Attestation.expires_at.desc().nullslast(), Attestation.created_at.desc())
    stmt = stmt.offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    return AttestationPage(items=[AttestationRead.model_validate(item) for item in items], total=int(total or 0))


@router.post("/attestations", response_model=AttestationRead, status_code=status.HTTP_201_CREATED)
async def create_attestation(
    request: Request,
    payload: AttestationCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> AttestationRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    person = await _get_person(session, str(tenant.id), payload.person_id)
    if payload.position_id:
        await _get_position(session, str(tenant.id), payload.position_id)
    if payload.responsible_id:
        await _get_user(session, str(tenant.id), payload.responsible_id)

    record = Attestation(
        tenant_id=str(tenant.id),
        person_id=person.id,
        position_id=payload.position_id,
        name=payload.name,
        issued_at=payload.issued_at,
        expires_at=payload.expires_at,
        status=payload.status,
        responsible_id=payload.responsible_id,
        notes=payload.notes,
    )
    session.add(record)
    await session.flush()
    await upsert_attestation_task(
        session,
        tenant_id=str(tenant.id),
        attestation=record,
        actor_id=getattr(access.user, "id", None),
    )
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="attestation",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"person_id": record.person_id, "expires_at": record.expires_at},
    )
    await session.commit()
    await session.refresh(record)
    return AttestationRead.model_validate(record)


@router.get("/attestations/{attestation_id}", response_model=AttestationRead)
async def get_attestation(
    attestation_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> AttestationRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    attestation = await _get_attestation(session, str(tenant.id), attestation_id)
    return AttestationRead.model_validate(attestation)


@router.patch("/attestations/{attestation_id}", response_model=AttestationRead)
async def update_attestation(
    request: Request,
    attestation_id: str,
    payload: AttestationUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> AttestationRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    record = await _get_attestation(session, str(tenant.id), attestation_id)
    updates = payload.model_dump(exclude_unset=True)
    if "person_id" in updates and updates["person_id"]:
        await _get_person(session, str(tenant.id), str(updates["person_id"]))
    if "position_id" in updates and updates["position_id"]:
        await _get_position(session, str(tenant.id), str(updates["position_id"]))
    if "responsible_id" in updates and updates["responsible_id"]:
        await _get_user(session, str(tenant.id), str(updates["responsible_id"]))

    for key, value in updates.items():
        setattr(record, key, value)

    await upsert_attestation_task(
        session,
        tenant_id=str(tenant.id),
        attestation=record,
        actor_id=getattr(access.user, "id", None),
    )
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="attestation",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"status": record.status.value},
    )
    await session.commit()
    await session.refresh(record)
    return AttestationRead.model_validate(record)
