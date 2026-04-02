from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import AuditService

from .diff import field_diff


async def write_audit_event(
    *,
    session: AsyncSession,
    request: Request,
    tenant_id: str,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    meta: dict[str, Any] | None = None,
):
    diff = field_diff(before, after)
    audit = AuditService(session)
    return await audit.log_event(
        tenant_id=tenant_id,
        action=action,
        object_type=resource_type,
        object_id=resource_id,
        user_id=actor_id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        changed_fields=diff,
        details={
            "before_json": before or {},
            "after_json": after or {},
            "diff_json": diff,
            "meta_json": meta or {},
            "correlation_id": getattr(request.state, "trace_id", None),
        },
    )
