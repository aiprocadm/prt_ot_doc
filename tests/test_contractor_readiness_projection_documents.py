"""Projection fills missing_docs_count from document-requirement violations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.modules.contractors.models import (
    ComplianceStatus,
    ContractorDocumentRequirement,
    ContractorEmployee,
    ContractorRegistry,
)
from app.modules.projections.models import ContractorReadinessReadModel
from app.modules.projections.services import ContractorReadinessProjectionService

NOW = datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_missing_docs_count_reflects_document_violations(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        contractor = ContractorRegistry(tenant_id=tid, name="Proj Contractor")
        session.add(contractor)
        await session.flush()
        session.add(
            ContractorEmployee(
                tenant_id=tid,
                contractor_id=contractor.id,
                full_name="Proj Worker",
                access_status=ComplianceStatus.VALID,
                training_status=ComplianceStatus.VALID,
                medical_status=ComplianceStatus.VALID,
                last_training_at=NOW,
                next_medical_at=NOW + timedelta(days=200),
            )
        )
        session.add(
            ContractorDocumentRequirement(
                tenant_id=tid,
                doc_type="medical_cert",
                scope="employee",
                mandatory=True,
            )
        )
        await session.commit()

        await ContractorReadinessProjectionService(session, tid).rebuild()

        row = (
            await session.execute(
                select(ContractorReadinessReadModel).where(
                    ContractorReadinessReadModel.tenant_id == tid,
                    ContractorReadinessReadModel.contractor_id == contractor.id,
                )
            )
        ).scalar_one()
        assert row.missing_docs_count == 1
        assert row.readiness_status == "blocked"
        # the document violation also folds into the aggregate overdue/violations counter
        assert row.overdue_items_count >= 1
