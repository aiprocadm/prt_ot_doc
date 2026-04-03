from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.tenant_row_http import enforce_row_belongs_to_tenant
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, rbac
from app.models.job_engine import OutboxEvent, OutboxEventStatus
from app.models.models import Outbox, OutboxStatus, Tenant

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin"]))]


class OutboxEntry(BaseModel):
    id: str
    tenant_id: str
    event_type: str
    destination: str
    status: OutboxStatus
    attempts: int
    next_attempt_at: str | None
    sent_at: str | None
    created_at: str
    updated_at: str
    last_error: dict[str, Any] | None = None


class OutboxListResponse(BaseModel):
    total: int
    items: list[OutboxEntry]


class RetryResponse(BaseModel):
    outbox_id: str
    status: OutboxStatus
    attempts: int
    next_attempt_at: str | None


class OutboxEventEntry(BaseModel):
    id: str
    tenant_id: str
    event_id: str
    event_type: str
    status: OutboxEventStatus
    attempts: int
    next_attempt_at: str | None
    created_at: str
    last_error: str | None = None


class OutboxEventListResponse(BaseModel):
    total: int
    items: list[OutboxEventEntry]


@router.get("", response_model=OutboxListResponse)
async def list_outbox(
    *,
    tenant: TenantDep,
    access: AdminAccess,
    session: SessionDep,
    status_filter: OutboxStatus | None = Query(None, alias="status"),
    event_type: str | None = Query(None, min_length=1),
    created_from: datetime | None = Query(None),
    created_to: datetime | None = Query(None),
) -> OutboxListResponse:
    _ = access
    stmt = select(Outbox).where(Outbox.tenant_id == tenant.id)
    if status_filter:
        stmt = stmt.where(Outbox.status == status_filter)
    if event_type:
        stmt = stmt.where(Outbox.event_type == event_type)
    if created_from:
        stmt = stmt.where(Outbox.created_at >= created_from)
    if created_to:
        stmt = stmt.where(Outbox.created_at <= created_to)

    stmt = stmt.order_by(Outbox.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()

    items = [
        OutboxEntry(
            id=entry.id,
            tenant_id=entry.tenant_id,
            event_type=entry.event_type,
            destination=entry.destination,
            status=entry.status,
            attempts=entry.attempts,
            next_attempt_at=entry.next_attempt_at.isoformat()
            if entry.next_attempt_at
            else None,
            sent_at=entry.sent_at.isoformat() if entry.sent_at else None,
            created_at=entry.created_at.isoformat(),
            updated_at=entry.updated_at.isoformat(),
            last_error=entry.last_error,
        )
        for entry in rows
    ]
    return OutboxListResponse(total=len(items), items=items)


@router.get("/{outbox_id}", response_model=OutboxEntry)
async def get_outbox_entry(
    outbox_id: str,
    *,
    tenant: TenantDep,
    access: AdminAccess,
    session: SessionDep,
) -> OutboxEntry:
    _ = access
    entry = await session.get(Outbox, outbox_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outbox entry not found")
    enforce_row_belongs_to_tenant(
        session,
        entry,
        tenant_id=str(tenant.id),
        mismatch_event="api.outbox_admin.get_entry.tenant_scope_mismatch",
        detail="Outbox entry not found",
    )

    return OutboxEntry(
        id=entry.id,
        tenant_id=entry.tenant_id,
        event_type=entry.event_type,
        destination=entry.destination,
        status=entry.status,
        attempts=entry.attempts,
        next_attempt_at=entry.next_attempt_at.isoformat() if entry.next_attempt_at else None,
        sent_at=entry.sent_at.isoformat() if entry.sent_at else None,
        created_at=entry.created_at.isoformat(),
        updated_at=entry.updated_at.isoformat(),
        last_error=entry.last_error,
    )


@router.post("/{outbox_id}/retry", response_model=RetryResponse)
@audit_operation("retry", "outbox_entry")
async def retry_outbox_entry(
    outbox_id: str,
    *,
    tenant: TenantDep,
    access: AdminAccess,
    session: SessionDep,
) -> RetryResponse:
    _ = access
    entry = await session.get(Outbox, outbox_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outbox entry not found")
    enforce_row_belongs_to_tenant(
        session,
        entry,
        tenant_id=str(tenant.id),
        mismatch_event="api.outbox_admin.retry_entry.tenant_scope_mismatch",
        detail="Outbox entry not found",
    )

    if entry.status not in {OutboxStatus.DEAD, OutboxStatus.FAILED}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only FAILED or DEAD outbox entries can be retried",
        )

    entry.status = OutboxStatus.PENDING
    entry.attempts = 0
    entry.next_attempt_at = datetime.now(tz=timezone.utc)
    entry.last_error = None

    await session.commit()

    return RetryResponse(
        outbox_id=entry.id,
        status=entry.status,
        attempts=entry.attempts,
        next_attempt_at=entry.next_attempt_at.isoformat() if entry.next_attempt_at else None,
    )


@router.get("/events", response_model=OutboxEventListResponse)
async def list_outbox_events(
    *,
    tenant: TenantDep,
    access: AdminAccess,
    session: SessionDep,
    status_filter: OutboxEventStatus | None = Query(None, alias="status"),
    event_type: str | None = Query(None, min_length=1),
) -> OutboxEventListResponse:
    _ = access
    stmt = select(OutboxEvent).where(OutboxEvent.tenant_id == tenant.id)
    if status_filter:
        stmt = stmt.where(OutboxEvent.status == status_filter.value)
    if event_type:
        stmt = stmt.where(OutboxEvent.event_type == event_type)
    rows = (await session.execute(stmt.order_by(OutboxEvent.created_at.desc()))).scalars().all()
    items = [
        OutboxEventEntry(
            id=item.id,
            tenant_id=item.tenant_id,
            event_id=item.event_id,
            event_type=item.event_type,
            status=OutboxEventStatus(item.status),
            attempts=item.attempts,
            next_attempt_at=item.next_attempt_at.isoformat() if item.next_attempt_at else None,
            created_at=item.created_at.isoformat(),
            last_error=item.last_error,
        )
        for item in rows
    ]
    return OutboxEventListResponse(total=len(items), items=items)


@router.post("/events/{event_id}/requeue", response_model=OutboxEventEntry)
@audit_operation("requeue", "outbox_event")
async def requeue_outbox_event(
    event_id: str,
    *,
    tenant: TenantDep,
    access: AdminAccess,
    session: SessionDep,
) -> OutboxEventEntry:
    _ = access
    event = await session.get(OutboxEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outbox event not found")
    enforce_row_belongs_to_tenant(
        session,
        event,
        tenant_id=str(tenant.id),
        mismatch_event="api.outbox_admin.requeue_event.tenant_scope_mismatch",
        detail="Outbox event not found",
    )

    if event.status not in {OutboxEventStatus.POISONED.value, OutboxEventStatus.FAILED.value}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only FAILED or DEAD events can be requeued")

    event.status = OutboxEventStatus.PENDING.value
    event.attempts = 0
    event.last_error = None
    event.next_attempt_at = datetime.now(tz=timezone.utc)
    await session.commit()

    return OutboxEventEntry(
        id=event.id,
        tenant_id=event.tenant_id,
        event_id=event.event_id,
        event_type=event.event_type,
        status=OutboxEventStatus(event.status),
        attempts=event.attempts,
        next_attempt_at=event.next_attempt_at.isoformat() if event.next_attempt_at else None,
        created_at=event.created_at.isoformat(),
        last_error=event.last_error,
    )
