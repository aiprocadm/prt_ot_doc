from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog


@dataclass
class AuditDomainService:
    session: AsyncSession

    async def record(
        self,
        actor_id: str | None,
        action: str,
        entity: str,
        entity_id: str,
        details: dict[str, Any],
        *,
        ip: str = "system",
    ) -> AuditLog:
        entry = AuditLog(
            user_id=actor_id,
            action=action,
            object_type=entity,
            object_id=entity_id,
            details=dict(details),
            ip=ip,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry
