"""Briefing signatures route through the PEP core (Срез-1: attested mode),
while the briefing service contract stays unchanged."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.models import BriefingEntry, BriefingJournal, SignatureRequest
from app.modules.briefings.services import BriefingEntryService


async def _entry(session, data_factory):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session, name="BRF PEP")
    person = await data_factory.create_person(tenant=tenant, company=company, session=session)
    # BriefingEntry requires briefing_journal_id (NOT NULL FK) and briefing_date (NOT NULL)
    journal = BriefingJournal(
        tenant_id=tenant.id,
        code="BRF-PEP-J1",
        title="PEP Parity Journal",
        journal_type="workplace",
        status="active",
    )
    session.add(journal)
    await session.flush()
    entry = BriefingEntry(
        tenant_id=tenant.id,
        person_id=person.id,
        briefing_journal_id=journal.id,
        briefing_type="primary",
        briefing_date=datetime.now(tz=timezone.utc),
        status="assigned",
    )
    session.add(entry)
    await session.flush()
    return tenant, person, entry


async def _pep_rows(session, tenant, entry):
    return (
        (
            await session.execute(
                select(SignatureRequest).where(
                    SignatureRequest.tenant_id == tenant.id,
                    SignatureRequest.purpose == "briefing",
                    SignatureRequest.object_id == entry.id,
                )
            )
        )
        .scalars()
        .all()
    )


@pytest.mark.asyncio
async def test_sign_creates_pep_record_and_links_it(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, entry = await _entry(session, data_factory)
        sig = await BriefingEntryService().sign(session, entry, "employee", None)
        await session.commit()

        pep = await _pep_rows(session, tenant, entry)
        assert len(pep) == 1
        assert pep[0].status == "signed"
        assert pep[0].signer_person_id == person.id
        assert pep[0].signature_type == "pep"
        assert sig.signature_payload.get("pep_request_id") == pep[0].id
        # контракт briefing не сломан
        assert entry.status == "signed_employee"


@pytest.mark.asyncio
async def test_repeated_sign_does_not_duplicate_pep(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, entry = await _entry(session, data_factory)
        await BriefingEntryService().sign(session, entry, "employee", None)
        await BriefingEntryService().sign(session, entry, "employee", None)
        pep = await _pep_rows(session, tenant, entry)
        assert len(pep) == 1


@pytest.mark.asyncio
async def test_instructor_sign_pep_uses_user_signer(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, entry = await _entry(session, data_factory)
        await BriefingEntryService().sign(session, entry, "instructor", "user-42")
        pep = await _pep_rows(session, tenant, entry)
        assert len(pep) == 1
        assert pep[0].signer_user_id == "user-42"
        assert pep[0].signer_person_id is None
        assert pep[0].result_json["attested_by"] == "user-42"
