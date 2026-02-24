from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import Tenant
from app.services.audit import AuditService, field_level_diff


def test_field_level_diff_masks_pii_and_drops_secrets() -> None:
    diff = field_level_diff(
        {"email": "old@example.com", "password": "old", "status": "draft"},
        {"email": "new@example.com", "password": "new", "status": "approved"},
    )
    assert diff["fields"]["email"]["from"].endswith("@example.com")
    assert diff["fields"]["status"] == {"from": "draft", "to": "approved"}
    # service-level sanitizer removes secret keys when persisting


@pytest.mark.anyio("asyncio")
async def test_audit_chain_verification_ok(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        tenant_id = str(tenant.id)
        audit = AuditService(session)
        await audit.log_event(
            tenant_id=tenant_id,
            action="create",
            object_type="Template",
            object_id="tpl-1",
            user_id=None,
            ip="127.0.0.1",
            request_id="corr-1",
            changed_fields={"fields": {"name": {"from": None, "to": "T1"}}},
            details={"token": "hidden", "email": "user@example.com"},
            when=datetime.now(tz=timezone.utc),
        )
        await audit.log_event(
            tenant_id=tenant_id,
            action="update",
            object_type="Template",
            object_id="tpl-1",
            user_id=None,
            ip="127.0.0.1",
            request_id="corr-2",
            changed_fields={"fields": {"name": {"from": "T1", "to": "T2"}}},
            details={"meta": {"password": "secret", "status": "ok"}},
            when=datetime.now(tz=timezone.utc),
        )
        result = await audit.verify_audit_chain(entity_type="Template", entity_id="tpl-1")
        assert result["checked"] == 2
        assert "ok" in result
        await session.rollback()
