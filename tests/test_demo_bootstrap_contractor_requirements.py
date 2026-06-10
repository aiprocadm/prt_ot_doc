"""Demo bootstrap seeds tenant document requirements (sro/company, medical_cert/employee)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.modules.contractors.models import ContractorDocumentRequirement


@pytest.mark.asyncio
async def test_seed_requirements_idempotent(sessionmaker, data_factory):
    from app.services.demo_bootstrap import _seed_contractor_requirements

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        await _seed_contractor_requirements(session, tid)
        await session.commit()
        # second call must not duplicate
        await _seed_contractor_requirements(session, tid)
        await session.commit()

        rows = (await session.execute(
            select(ContractorDocumentRequirement).where(
                ContractorDocumentRequirement.tenant_id == tid,
                ContractorDocumentRequirement.deleted_at.is_(None),
            )
        )).scalars().all()

    pairs = {(r.doc_type, r.scope) for r in rows}
    assert ("sro", "company") in pairs
    assert ("medical_cert", "employee") in pairs
    assert len(rows) == 2  # idempotent — no duplicates
