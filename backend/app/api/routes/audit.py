from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import AuditExportJob, AuditLog, Tenant
from app.celery.tasks.audit_export_job import export_audit_job
from app.services.file_storage import FileStorageService

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin", "owner", "auditor_ro"]))]


class AuditLogEntry(BaseModel):
    id: str
    ts: datetime
    actor_type: str
    actor_id: str | None = None
    actor_email: str | None = None
    action: str
    entity_type: str
    entity_id: str
    object_type: str
    object_id: str
    parent_type: str | None = None
    parent_id: str | None = None
    correlation_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    diff: dict[str, Any] = Field(default_factory=dict)


class AuditLogHistory(BaseModel):
    total: int
    items: list[AuditLogEntry]


class AuditExportCreate(BaseModel):
    filters: dict[str, Any] = Field(default_factory=dict)
    format: str = Field(pattern="^(csv|jsonl)$")


class AuditExportCreateResponse(BaseModel):
    export_job_id: str


class AuditExportRead(BaseModel):
    id: str
    status: str
    format: str
    signed_url: str | None = None
    expires_at: datetime | None = None
    error: str | None = None


def _to_entry(record: AuditLog) -> AuditLogEntry:
    return AuditLogEntry(
        id=record.id,
        ts=record.when,
        actor_type=record.actor_type,
        actor_id=record.user_id,
        actor_email=record.actor_email,
        action=record.action,
        entity_type=record.object_type,
        entity_id=record.object_id,
        object_type=record.object_type,
        object_id=record.object_id,
        parent_type=record.parent_type,
        parent_id=record.parent_id,
        correlation_id=record.correlation_id or record.request_id,
        meta={
            "ip": record.ip,
            "user_agent": record.user_agent,
            **(record.details or {}),
        },
        diff=record.changed_fields or {},
    )


@router.get("/logs", response_model=AuditLogHistory)
async def get_audit_history(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    actor_id: str | None = Query(None),
    action: str | None = Query(None),
    correlation_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    *,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
) -> AuditLogHistory:
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant.id)
    total_stmt = select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == tenant.id)
    if entity_type:
        stmt = stmt.where(AuditLog.object_type == entity_type)
        total_stmt = total_stmt.where(AuditLog.object_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.object_id == entity_id)
        total_stmt = total_stmt.where(AuditLog.object_id == entity_id)
    if actor_id:
        stmt = stmt.where(AuditLog.user_id == actor_id)
        total_stmt = total_stmt.where(AuditLog.user_id == actor_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
        total_stmt = total_stmt.where(AuditLog.action == action)
    if correlation_id:
        stmt = stmt.where(AuditLog.correlation_id == correlation_id)
        total_stmt = total_stmt.where(AuditLog.correlation_id == correlation_id)
    if from_:
        stmt = stmt.where(AuditLog.when >= from_)
        total_stmt = total_stmt.where(AuditLog.when >= from_)
    if to:
        stmt = stmt.where(AuditLog.when <= to)
        total_stmt = total_stmt.where(AuditLog.when <= to)

    rows = (await session.execute(stmt.order_by(AuditLog.when.desc()).limit(limit).offset(offset))).scalars().all()
    total = (await session.execute(total_stmt)).scalar_one()
    return AuditLogHistory(total=total, items=[_to_entry(item) for item in rows])


@router.get("/logs/{audit_id}", response_model=AuditLogEntry)
async def get_audit_log(audit_id: str, *, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> AuditLogEntry:
    row = await session.get(AuditLog, audit_id)
    if row is None or str(row.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit log not found")
    return _to_entry(row)


@router.post("/exports", response_model=AuditExportCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_export(payload: AuditExportCreate, *, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> AuditExportCreateResponse:
    job = AuditExportJob(tenant_id=str(tenant.id), filters=payload.filters, format=payload.format, status="queued")
    session.add(job)
    await session.flush()
    export_audit_job.delay(export_id=job.id, tenant_id=str(tenant.id))
    await session.commit()
    return AuditExportCreateResponse(export_job_id=job.id)




@router.get("/exports/{export_id}", response_model=AuditExportRead)
async def get_export(export_id: str, *, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> AuditExportRead:
    row = await session.get(AuditExportJob, export_id)
    if row is None or str(row.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export job not found")
    return AuditExportRead(
        id=row.id,
        status=row.status,
        format=row.format,
        signed_url=row.signed_url,
        expires_at=row.expires_at,
        error=row.error,
    )


@router.get("/exports/{export_id}/download")
async def download_export(export_id: str, *, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> StreamingResponse:
    row = await session.get(AuditExportJob, export_id)
    if row is None or str(row.tenant_id) != str(tenant.id) or not row.storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export file not found")
    body = FileStorageService.default().get(row.storage_key)
    media_type = "text/csv" if row.format == "csv" else "application/x-ndjson"
    return StreamingResponse(iter([body]), media_type=media_type)


@router.get("", response_model=AuditLogHistory)
async def backward_list(
    object_id: str | None = Query(None, min_length=1),
    object_type: str | None = Query(None, min_length=1),
    action: str | None = Query(None, min_length=1),
    *,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
) -> AuditLogHistory:
    if object_id is not None and not object_id.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "object_id must not be blank")
    if object_type is not None and not object_type.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "object_type must not be blank")
    if action is not None and not action.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "action must not be blank")

    return await get_audit_history(
        from_=None,
        to=None,
        entity_type=object_type,
        entity_id=object_id,
        actor_id=None,
        action=action,
        correlation_id=None,
        limit=100,
        offset=0,
        tenant=tenant,
        _=_,
        session=session,
    )


@router.get("/export")
async def backward_export(*, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> Response:
    raise HTTPException(status.HTTP_410_GONE, "use POST /v1/audit/exports")
