from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import AuditLog, Tenant

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin"]))]


class AuditLogEntry(BaseModel):
    when: str = Field(..., description="Timestamp in ISO 8601 format")
    user_id: str | None = Field(None, description="Identifier of the acting user")
    action: str
    object_type: str
    object_id: str
    ip: str
    details: dict[str, Any] = Field(default_factory=dict)


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
        )
        for record in rows
    ]
    return AuditLogHistory(total=len(items), items=items)
