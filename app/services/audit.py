from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tracing import get_trace_id
from app.models.models import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Persist audit trail entries for security-sensitive actions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log_event(
        self,
        *,
        tenant_id: str,
        action: str,
        object_type: str,
        object_id: str,
        user_id: str | None,
        ip: str,
        request_id: str | None = None,
        session_id: str | None = None,
        user_agent: str | None = None,
        changed_fields: Mapping[str, Any] | None = None,
        when: datetime | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> AuditLog:
        """Create and persist a new audit log entry."""

        payload = dict(details or {})
        entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            ip=ip or "unknown",
            request_id=request_id or get_trace_id(),
            session_id=session_id,
            user_agent=user_agent,
            changed_fields=dict(changed_fields or {}),
            when=when or datetime.now(tz=timezone.utc),
            details=payload,
        )
        self.session.add(entry)
        await self.session.flush()
        logger.info(
            "audit.log",
            extra={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
            },
        )
        return entry

    async def log(
        self,
        *,
        actor_id: str | None,
        action: str,
        entity: str,
        entity_id: str,
        diff: Mapping[str, Any] | None = None,
        ip: str = "system",
        request_id: str | None = None,
        session_id: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        """Backward-compatible wrapper for logging audit events."""

        tenant_id = str(
            self.session.info.get("tenant_id")
            or self.session.info.get("tenant")
            or ""
        )
        return await self.log_event(
            tenant_id=tenant_id,
            action=action,
            object_type=entity,
            object_id=entity_id,
            user_id=actor_id,
            ip=ip,
            request_id=request_id,
            session_id=session_id,
            user_agent=user_agent,
            changed_fields=diff,
            details=diff,
        )
