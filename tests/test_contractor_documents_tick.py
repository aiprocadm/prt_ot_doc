"""contractors.documents.tick: drives notify_document_expiry across active tenants."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.contractors.models import ContractorDocument, ContractorRegistry

TODAY = datetime.now(timezone.utc).date()


@pytest.mark.asyncio
async def test_documents_tick_enqueues(sessionmaker, data_factory):
    from app.tasks._core import _contractors_documents_tick

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        contractor = ContractorRegistry(tenant_id=tid, name="Tick Contractor")
        session.add(contractor)
        await session.flush()
        session.add(ContractorDocument(
            tenant_id=tid, contractor_id=contractor.id, doc_type="medical_cert", title="Soon",
            valid_until=TODAY + timedelta(days=10),
        ))
        await session.commit()

    total = await _contractors_documents_tick()
    assert total >= 1
