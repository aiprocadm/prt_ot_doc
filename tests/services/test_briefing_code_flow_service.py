"""Two-phase briefing code-flow at the service layer (Срез-3)."""
from __future__ import annotations

import itertools
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.domains.signing.pep import PepStatus
from app.models.models import (
    BriefingEntry,
    BriefingJournal,
    BriefingSignature,
    BriefingTemplate,
    SignatureRequest,
)
from app.modules.briefings.services import (
    BriefingEntryService,
    NoPendingCodeRequest,
)
from app.services.pep_signing import PepConflict

_counter = itertools.count(1)


async def _world(session, data_factory, *, require_code: bool, with_person: bool = True):
    n = next(_counter)
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session, name=f"BRF CF {n}")
    person = (
        await data_factory.create_person(tenant=tenant, company=company, session=session)
        if with_person
        else None
    )
    template = BriefingTemplate(
        tenant_id=tenant.id,
        code=f"BRF-CF-T-{n}",
        title="CF",
        briefing_type="primary",
        require_signature_code=require_code,
    )
    journal = BriefingJournal(
        tenant_id=tenant.id, code=f"BRF-CF-J-{n}", title="CF", journal_type="workplace", status="active"
    )
    session.add_all([template, journal])
    await session.flush()
    entry = BriefingEntry(
        tenant_id=tenant.id,
        person_id=person.id if person else None,
        briefing_journal_id=journal.id,
        briefing_template_id=template.id,
        briefing_type="primary",
        briefing_date=datetime.now(tz=timezone.utc),
        status="assigned",
    )
    session.add(entry)
    await session.flush()
    return tenant, person, template, entry


@pytest.mark.asyncio
async def test_requires_code_true_only_when_flag_and_person(sessionmaker, data_factory):
    async with sessionmaker() as session:
        _, _, _, entry = await _world(session, data_factory, require_code=True)
        assert await BriefingEntryService().requires_signature_code(session, entry) is True

        _, _, _, entry_off = await _world(session, data_factory, require_code=False)
        assert await BriefingEntryService().requires_signature_code(session, entry_off) is False

        _, _, _, entry_noperson = await _world(
            session, data_factory, require_code=True, with_person=False
        )
        assert await BriefingEntryService().requires_signature_code(session, entry_noperson) is False


@pytest.mark.asyncio
async def test_start_then_confirm_creates_signature(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, _, entry = await _world(session, data_factory, require_code=True)
        svc = BriefingEntryService()
        req, code = await svc.start_employee_signature(session, entry, "user-1")
        await session.commit()

        assert req.status == PepStatus.AWAITING_CODE.value
        assert code is not None and len(code) == 6
        sigs = (await session.execute(
            select(BriefingSignature).where(BriefingSignature.briefing_entry_id == entry.id)
        )).scalars().all()
        assert sigs == []
        assert entry.status == "assigned"

        sig = await svc.confirm_code(session, entry, code)
        await session.commit()

        assert sig.signer_person_id == person.id
        assert sig.signature_payload["pep_request_id"] == req.id
        assert entry.status == "signed_employee"
        refreshed = await session.get(SignatureRequest, req.id)
        assert refreshed.status == PepStatus.SIGNED.value


@pytest.mark.asyncio
async def test_wrong_code_raises_and_attempts_increment_survive_commit(sessionmaker, data_factory):
    async with sessionmaker() as session:
        _, _, _, entry = await _world(session, data_factory, require_code=True)
        svc = BriefingEntryService()
        req, _ = await svc.start_employee_signature(session, entry, "user-1")
        await session.commit()

        with pytest.raises(PepConflict):
            await svc.confirm_code(session, entry, "000000")
        await session.commit()  # commit-on-conflict: счётчик попыток сохраняется

        refreshed = await session.get(SignatureRequest, req.id)
        assert refreshed.confirm_attempts == 1
        assert refreshed.status == PepStatus.AWAITING_CODE.value


@pytest.mark.asyncio
async def test_confirm_without_pending_request_raises(sessionmaker, data_factory):
    async with sessionmaker() as session:
        _, _, _, entry = await _world(session, data_factory, require_code=True)
        with pytest.raises(NoPendingCodeRequest):
            await BriefingEntryService().confirm_code(session, entry, "123456")
