"""Security decision audit helpers."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import SecurityAuditLog


async def log_security_decision(
    *,
    session: AsyncSession,
    request: Request,
    tenant_id: str,
    user_id: str | None,
    action: str,
    resource_type: str,
    decision: str,
    reason_code: str | None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> SecurityAuditLog:
    entry = SecurityAuditLog(
        tenant_id=str(tenant_id),
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        decision=decision,
        reason_code=reason_code,
        ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent"),
        correlation_id=getattr(request.state, "trace_id", None),
        details=details or {},
    )
    session.add(entry)
    await session.flush()
    return entry
