"""notify_document_expiry: enqueue only for DUE_SOON/OVERDUE, idempotent per day."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.contractors.models import ContractorDocument, ContractorRegistry

TODAY = date.today()


async def _seed(session, tenant_id: str) -> str:
    contractor = ContractorRegistry(tenant_id=tenant_id, name="Notif Contractor")
    session.add(contractor)
    await session.flush()
    # OK (future) — skipped
    session.add(ContractorDocument(
        tenant_id=tenant_id, contractor_id=contractor.id, doc_type="license", title="Future",
        valid_until=TODAY + timedelta(days=90),
    ))
    # open-ended — skipped
    session.add(ContractorDocument(
        tenant_id=tenant_id, contractor_id=contractor.id, doc_type="other", title="Open",
    ))
    # DUE_SOON — enqueued
    session.add(ContractorDocument(
        tenant_id=tenant_id, contractor_id=contractor.id, doc_type="medical_cert", title="Soon",
        valid_until=TODAY + timedelta(days=10),
    ))
    # OVERDUE — enqueued
    session.add(ContractorDocument(
        tenant_id=tenant_id, contractor_id=contractor.id, doc_type="access_permit", title="Past",
        valid_until=TODAY - timedelta(days=3),
    ))
    await session.commit()
    return contractor.id


@pytest.mark.asyncio
async def test_notify_enqueues_due_soon_and_overdue_only(sessionmaker, data_factory):
    from app.services.contractor_documents import notify_document_expiry

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        await _seed(session, tid)
        count = await notify_document_expiry(session, tenant_id=tid)
        await session.commit()
    assert count == 2, f"Expected 2 (DUE_SOON + OVERDUE), got {count}"


@pytest.mark.asyncio
async def test_notify_is_idempotent_same_day(sessionmaker, data_factory):
    from app.services.contractor_documents import notify_document_expiry

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        await _seed(session, tid)
        first = await notify_document_expiry(session, tenant_id=tid)
        await session.commit()
        second = await notify_document_expiry(session, tenant_id=tid)
        await session.commit()
    assert first == 2
    assert second == 0, "Same-day re-run must not duplicate events"
