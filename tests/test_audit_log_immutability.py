from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import AuditLog
from tests.utils.factories import TestDataFactory


@pytest.mark.anyio("asyncio")
async def test_audit_log_rejects_updates(
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        entry = AuditLog(
            tenant_id=tenant.id,
            user_id=None,
            action="created",
            object_type="document",
            object_id="doc-immutable",
            ip="127.0.0.1",
        )
        session.add(entry)
        await session.commit()
        entry_id = entry.id

    async with sessionmaker() as session:
        entry = await session.get(AuditLog, entry_id)
        assert entry is not None
        entry.action = "updated"
        with pytest.raises(RuntimeError, match="append-only"):
            await session.commit()
        await session.rollback()


@pytest.mark.anyio("asyncio")
async def test_audit_log_rejects_deletes(
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        entry = AuditLog(
            tenant_id=tenant.id,
            user_id=None,
            action="created",
            object_type="template",
            object_id="tpl-immutable",
            ip="127.0.0.1",
        )
        session.add(entry)
        await session.commit()
        entry_id = entry.id

    async with sessionmaker() as session:
        entry = await session.get(AuditLog, entry_id)
        assert entry is not None
        await session.delete(entry)
        with pytest.raises(RuntimeError, match="append-only"):
            await session.commit()
        await session.rollback()
