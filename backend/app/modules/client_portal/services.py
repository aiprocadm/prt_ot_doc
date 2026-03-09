from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projections.models import ClientPortalReadModel


class SafePortalPayloadService:
    """Strip internal/sensitive fields for client cabinet payloads."""

    _BLOCKED_KEYS = {
        "internal_notes",
        "audit_payload",
        "raw_attempts",
        "raw_answers",
        "risk_formula",
        "system_error",
        "policy_payload",
    }

    @classmethod
    def sanitize(cls, payload: dict | None) -> dict:
        """Return a deep-copied payload without blocked keys."""

        if not payload:
            return {}
        return cls._sanitize_value(payload)

    @classmethod
    def _sanitize_value(cls, value: object) -> object:
        if isinstance(value, dict):
            return {
                key: cls._sanitize_value(item)
                for key, item in value.items()
                if key not in cls._BLOCKED_KEYS
            }
        if isinstance(value, list):
            return [cls._sanitize_value(item) for item in value]
        return value


class ClientPortalService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def list_items(self, *, client_company_id: str | None = None, item_type: str | None = None) -> list[ClientPortalReadModel]:
        stmt = select(ClientPortalReadModel).where(ClientPortalReadModel.tenant_id == self.tenant_id)
        if client_company_id:
            stmt = stmt.where(ClientPortalReadModel.client_company_id == client_company_id)
        if item_type:
            stmt = stmt.where(ClientPortalReadModel.item_type == item_type)
        rows = (await self.session.execute(stmt.order_by(ClientPortalReadModel.last_event_at.desc().nullslast()))).scalars().all()
        for row in rows:
            row.safe_payload = SafePortalPayloadService.sanitize(row.safe_payload)
        return rows
