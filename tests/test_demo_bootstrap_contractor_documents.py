"""Demo seed creates 3 contractor documents with valid/expiring/expired statuses."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.domains.contractors.documents import document_expiry_status
from app.domains.shared import ContingentItemStatus
from app.modules.contractors.models import ContractorDocument


@pytest.mark.asyncio
async def test_demo_seed_creates_three_documents(sessionmaker, data_factory):
    from app.services.demo_bootstrap import _seed_contractor_documents

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        from app.modules.contractors.models import ContractorEmployee, ContractorRegistry
        contractor = ContractorRegistry(tenant_id=tid, name="Seed Doc Contractor")
        session.add(contractor)
        await session.flush()
        emp = ContractorEmployee(tenant_id=tid, contractor_id=contractor.id, full_name="Seed Worker")
        session.add(emp)
        await session.flush()

        await _seed_contractor_documents(session, tid, contractor.id, emp.id)
        await session.commit()

        docs = list((await session.execute(
            select(ContractorDocument).where(ContractorDocument.tenant_id == tid)
        )).scalars().all())

    assert len(docs) == 3
    today = datetime.now(timezone.utc).date()
    statuses = {document_expiry_status(d.valid_until, today) for d in docs}
    assert ContingentItemStatus.OK in statuses
    assert ContingentItemStatus.DUE_SOON in statuses
    assert ContingentItemStatus.OVERDUE in statuses
