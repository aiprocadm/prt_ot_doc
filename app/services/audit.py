from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

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
