from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.models import Outbox
from app.services.outbox import OutboxService
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_outbox_enqueue_is_idempotent(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        outbox = OutboxService(session)
        payload = {
            "tenant_id": str(tenant.id),
            "actor_id": "tester",
            "occurred_at": datetime.now(tz=timezone.utc),
            "document_id": "doc-1",
            "document_version_id": "ver-1",
            "template_id": "tmpl-1",
            "template_version_id": "tmpl-ver-1",
            "company_id": "comp-1",
            "person_id": None,
            "storage_key": "s3/key",
            "status": "generated",
        }
        await outbox.enqueue(
            tenant_id=str(tenant.id),
            event_type="DocumentCreated",
            payload=payload,
            destination="https://example.test/hooks",
        )
        await outbox.enqueue(
            tenant_id=str(tenant.id),
            event_type="DocumentCreated",
            payload=payload,
            destination="https://example.test/hooks",
        )
        await session.commit()

    async with sessionmaker() as session:
        entries = (
            await session.execute(
                select(Outbox).where(
                    Outbox.tenant_id == str(tenant.id),
                    Outbox.event_type == "DocumentCreated",
                )
            )
        ).scalars().all()
        assert len(entries) == 1


@pytest.mark.asyncio
async def test_outbox_enqueue_rolls_back_with_transaction(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        outbox = OutboxService(session)
        payload = {
            "tenant_id": str(tenant.id),
            "actor_id": "tester",
            "occurred_at": datetime.now(tz=timezone.utc),
            "document_id": "doc-rollback",
            "document_version_id": "ver-rollback",
            "template_id": "tmpl-rollback",
            "template_version_id": "tmpl-ver-rollback",
            "company_id": "comp-rollback",
            "person_id": None,
            "storage_key": "s3/key-rollback",
            "status": "generated",
        }
        await outbox.enqueue(
            tenant_id=str(tenant.id),
            event_type="DocumentCreated",
            payload=payload,
            destination="https://example.test/hooks",
        )
        await session.rollback()

    async with sessionmaker() as session:
        entry = (
            await session.execute(
                select(Outbox).where(
                    Outbox.tenant_id == str(tenant.id),
                    Outbox.event_type == "DocumentCreated",
                    Outbox.idempotency_key == "doc-rollback:ver-rollback",
                )
            )
        ).scalar_one_or_none()
        assert entry is None
