from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import AuditLog, Tenant

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin", "owner"]))]


class AuditLogEntry(BaseModel):
    when: str = Field(..., description="Timestamp in ISO 8601 format")
    user_id: str | None = Field(None, description="Identifier of the acting user")
    action: str
    object_type: str
    object_id: str
    ip: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    session_id: str | None = None
    user_agent: str | None = None
    changed_fields: dict[str, Any] = Field(default_factory=dict)


class AuditLogHistory(BaseModel):
    total: int
    items: list[AuditLogEntry]


@router.get("", response_model=AuditLogHistory)
async def get_audit_history(
    object_id: str = Query(..., min_length=1),
    object_type: str | None = Query(None, min_length=1),
    action: str | None = Query(None, min_length=1),
    *,
    tenant: TenantDep,
    access: AdminAccess,
    session: SessionDep,
) -> AuditLogHistory:
    if not object_id.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "object_id must not be empty")

    stmt = select(AuditLog).where(
        AuditLog.tenant_id == tenant.id,
        AuditLog.object_id == object_id,
    )
    if object_type:
        stmt = stmt.where(AuditLog.object_type == object_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)

    stmt = stmt.order_by(AuditLog.when.desc())
    rows = (await session.execute(stmt)).scalars().all()

    items = [
        AuditLogEntry(
            when=record.when.isoformat(),
            user_id=record.user_id,
            action=record.action,
            object_type=record.object_type,
            object_id=record.object_id,
            ip=record.ip,
            details=record.details or {},
            request_id=record.request_id,
            session_id=record.session_id,
            user_agent=record.user_agent,
            changed_fields=record.changed_fields or {},
        )
        for record in rows
    ]
    return AuditLogHistory(total=len(items), items=items)


@router.get("/export")
async def export_audit_history(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    entity: str | None = Query(None),
    actor: str | None = Query(None),
    fmt: str = Query("jsonl", pattern="^(jsonl|csv)$"),
    *,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
) -> StreamingResponse:
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant.id)
    if entity:
        stmt = stmt.where(AuditLog.object_type == entity)
    if actor:
        stmt = stmt.where(AuditLog.user_id == actor)
    if from_:
        stmt = stmt.where(AuditLog.when >= datetime.fromisoformat(from_))
    if to:
        stmt = stmt.where(AuditLog.when <= datetime.fromisoformat(to))
    rows = (await session.execute(stmt.order_by(AuditLog.when.desc()))).scalars().all()

    if fmt == "csv":
        def _iter_csv():
            yield "when,user_id,action,object_type,object_id,ip,request_id\n"
            for row in rows:
                yield f"{row.when.isoformat()},{row.user_id or ''},{row.action},{row.object_type},{row.object_id},{row.ip},{row.request_id or ''}\n"

        return StreamingResponse(_iter_csv(), media_type="text/csv")

    def _iter_jsonl():
        import json

        for row in rows:
            payload = {
                "when": row.when.isoformat(),
                "user_id": row.user_id,
                "action": row.action,
                "entity_type": row.object_type,
                "entity_id": row.object_id,
                "ip": row.ip,
                "request_id": row.request_id,
                "changed_fields": row.changed_fields or {},
            }
            yield json.dumps(payload, ensure_ascii=False) + "\n"

    return StreamingResponse(_iter_jsonl(), media_type="application/x-ndjson")
