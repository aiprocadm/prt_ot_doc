from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.models import Outbox, Tenant
from app.services.outbox import OutboxProcessor


class DummyDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def dispatch(self, *, event_type: str, tenant_id: str, payload: dict) -> None:
        self.calls.append(
            {"event_type": event_type, "tenant_id": tenant_id, "payload": payload}
        )
        if payload.get("fail"):
            raise RuntimeError("boom")


@pytest.mark.anyio
async def test_outbox_processor_dispatches_entries(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry = Outbox(
            tenant_id=tenant.id,
            event_type="DocumentGenerated",
            payload={"document_id": "doc-1"},
        )
        session.add(entry)
        await session.commit()
        entry_id = entry.id

    dispatcher = DummyDispatcher()
    async with sessionmaker() as session:
        processor = OutboxProcessor(session, dispatcher=dispatcher)
        processed = await processor.process_once()

    assert processed == 1
    assert dispatcher.calls
    assert dispatcher.calls[0]["event_type"] == "DocumentGenerated"

    async with sessionmaker() as session:
        refreshed = await session.get(Outbox, entry_id)
        assert refreshed is not None
        assert refreshed.processed_at is not None
        assert refreshed.attempts == 1
        assert refreshed.last_error is None


@pytest.mark.anyio
async def test_outbox_processor_retries_failed_entries(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry = Outbox(
            tenant_id=tenant.id,
            event_type="Signed",
            payload={"document_id": "doc-2", "fail": True},
        )
        session.add(entry)
        await session.commit()
        entry_id = entry.id

    dispatcher = DummyDispatcher()
    async with sessionmaker() as session:
        processor = OutboxProcessor(session, dispatcher=dispatcher)
        processed = await processor.process_once()

    assert processed == 0
    assert dispatcher.calls

    async with sessionmaker() as session:
        refreshed = await session.get(Outbox, entry_id)
        assert refreshed is not None
        assert refreshed.processed_at is None
        assert refreshed.attempts == 1
        assert refreshed.last_error
