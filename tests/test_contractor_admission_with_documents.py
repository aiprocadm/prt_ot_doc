"""evaluate_with_documents: tenant isolation + company/employee scope routing + gating."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.contractors.lifecycle import ReadinessStatus
from app.modules.contractors.models import (
    ComplianceStatus,
    ContractorDocument,
    ContractorDocumentRequirement,
    ContractorEmployee,
    ContractorRegistry,
)

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


async def _seed_ready_employee(session, tenant_id: str) -> ContractorEmployee:
    contractor = ContractorRegistry(tenant_id=tenant_id, name="WD Contractor")
    session.add(contractor)
    await session.flush()
    emp = ContractorEmployee(
        tenant_id=tenant_id, contractor_id=contractor.id, full_name="WD Worker",
        access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID, last_training_at=NOW,
        next_medical_at=NOW + timedelta(days=200),
    )
    session.add(emp)
    await session.flush()
    return emp


@pytest.mark.asyncio
async def test_missing_mandatory_employee_doc_blocks(sessionmaker, data_factory):
    from app.services.contractor_admission import evaluate_with_documents

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        emp = await _seed_ready_employee(session, tid)
        session.add(ContractorDocumentRequirement(
            tenant_id=tid, doc_type="medical_cert", scope="employee", mandatory=True,
        ))
        await session.commit()
        verdicts = await evaluate_with_documents(session, employees=[emp])

    assert verdicts[0].status is ReadinessStatus.BLOCKED
    assert "document:medical_cert" in verdicts[0].violations


@pytest.mark.asyncio
async def test_company_doc_satisfies_company_rule(sessionmaker, data_factory):
    from app.services.contractor_admission import evaluate_with_documents

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        emp = await _seed_ready_employee(session, tid)
        session.add(ContractorDocumentRequirement(
            tenant_id=tid, doc_type="sro", scope="company", mandatory=True,
        ))
        # company-level doc: employee_id is None, same contractor
        session.add(ContractorDocument(
            tenant_id=tid, contractor_id=emp.contractor_id, doc_type="sro",
            title="СРО", valid_until=TODAY + timedelta(days=90), status="active",
        ))
        await session.commit()
        verdicts = await evaluate_with_documents(session, employees=[emp])

    assert verdicts[0].status is ReadinessStatus.ALLOWED


@pytest.mark.asyncio
async def test_inactive_document_does_not_satisfy(sessionmaker, data_factory):
    from app.services.contractor_admission import evaluate_with_documents

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        emp = await _seed_ready_employee(session, tid)
        session.add(ContractorDocumentRequirement(
            tenant_id=tid, doc_type="sro", scope="company", mandatory=True,
        ))
        session.add(ContractorDocument(
            tenant_id=tid, contractor_id=emp.contractor_id, doc_type="sro",
            title="СРО (archived)", valid_until=TODAY + timedelta(days=90), status="archived",
        ))
        await session.commit()
        verdicts = await evaluate_with_documents(session, employees=[emp])

    assert verdicts[0].status is ReadinessStatus.BLOCKED  # archived doc ignored → MISSING
