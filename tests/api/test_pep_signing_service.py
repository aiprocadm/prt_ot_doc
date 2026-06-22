"""PepSigningService: create/confirm/decline + builders (DB-level, no HTTP)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.domains.signing.pep import MAX_CONFIRM_ATTEMPTS, PepStatus
from app.models.models import Outbox, PPEIssue
from app.services.pep_signing import PepConflict, PepForbidden, PepNotFound, PepSigningService


async def _person_with_issue(session, data_factory, *, tag: str):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session, name=f"PEP {tag}")
    person = await data_factory.create_person(tenant=tenant, company=company, session=session)
    issue = PPEIssue(
        tenant_id=tenant.id,
        person_id=person.id,
        item_name=f"Каска {tag}",
        quantity=1,
        status="issued",
    )
    session.add(issue)
    await session.flush()
    return tenant, person, issue


@pytest.mark.asyncio
async def test_create_for_person_returns_one_time_code_and_awaits(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c1")
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue",
            object_id=issue.id,
            purpose="ppe_issue",
            signer_person_id=person.id,
            requested_by="user-1",
        )
        await session.commit()
        assert req.status == PepStatus.AWAITING_CODE.value
        assert code is not None and len(code) == 6 and code.isdigit()
        assert req.confirm_code_hash and req.confirm_code_hash != code
        assert req.content_hash and len(req.content_hash) == 64
        assert req.signature_type == "pep" and req.provider == "internal"
        assert req.purpose == "ppe_issue"


@pytest.mark.asyncio
async def test_confirm_with_valid_code_signs_and_snapshots_name(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c2")
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue",
            object_id=issue.id,
            purpose="ppe_issue",
            signer_person_id=person.id,
            requested_by="user-1",
        )
        signed = await svc.confirm(req.id, code=code)
        await session.commit()
        assert signed.status == PepStatus.SIGNED.value
        assert signed.signed_at is not None
        assert person.last_name in (signed.signer_name or "")


@pytest.mark.asyncio
async def test_confirm_wrong_code_5_times_declines(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c3")
        svc = PepSigningService(session, str(tenant.id))
        req, _code = await svc.create_request(
            object_type="ppe_issue",
            object_id=issue.id,
            purpose="ppe_issue",
            signer_person_id=person.id,
            requested_by="user-1",
        )
        for attempt in range(MAX_CONFIRM_ATTEMPTS):
            with pytest.raises(PepConflict):
                await svc.confirm(req.id, code="000000")
        assert req.status == PepStatus.DECLINED.value
        assert req.confirm_attempts == MAX_CONFIRM_ATTEMPTS


@pytest.mark.asyncio
async def test_confirm_expired_code_expires(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c4")
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue",
            object_id=issue.id,
            purpose="ppe_issue",
            signer_person_id=person.id,
            requested_by="user-1",
        )
        req.confirm_code_expires_at = req.confirm_code_expires_at - timedelta(minutes=60)
        with pytest.raises(PepConflict):
            await svc.confirm(req.id, code=code)
        assert req.status == PepStatus.EXPIRED.value


@pytest.mark.asyncio
async def test_duplicate_active_request_conflicts(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c5")
        svc = PepSigningService(session, str(tenant.id))
        await svc.create_request(
            object_type="ppe_issue",
            object_id=issue.id,
            purpose="ppe_issue",
            signer_person_id=person.id,
            requested_by="user-1",
        )
        with pytest.raises(PepConflict):
            await svc.create_request(
                object_type="ppe_issue",
                object_id=issue.id,
                purpose="ppe_issue",
                signer_person_id=person.id,
                requested_by="user-1",
            )


@pytest.mark.asyncio
async def test_user_signer_self_signs_instantly(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c6")
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue",
            object_id=issue.id,
            purpose="ppe_issue",
            signer_user_id="user-1",
            requested_by="user-1",
        )
        await session.commit()
        assert code is None
        assert req.status == PepStatus.SIGNED.value


@pytest.mark.asyncio
async def test_unknown_object_raises_not_found(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = PepSigningService(session, str(tenant.id))
        with pytest.raises(PepNotFound):
            await svc.create_request(
                object_type="ppe_issue",
                object_id="missing",
                purpose="ppe_issue",
                signer_user_id="user-1",
                requested_by="user-1",
            )


@pytest.mark.asyncio
async def test_decline_from_awaiting(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c7")
        svc = PepSigningService(session, str(tenant.id))
        req, _ = await svc.create_request(
            object_type="ppe_issue",
            object_id=issue.id,
            purpose="ppe_issue",
            signer_person_id=person.id,
            requested_by="user-1",
        )
        declined = await svc.decline(req.id, reason="отказ сотрудника")
        assert declined.status == PepStatus.DECLINED.value


@pytest.mark.asyncio
async def test_tenant_isolation_on_confirm(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c8")
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue",
            object_id=issue.id,
            purpose="ppe_issue",
            signer_person_id=person.id,
            requested_by="user-1",
        )
        foreign = PepSigningService(session, "00000000-0000-0000-0000-00000000dead")
        with pytest.raises(PepNotFound):
            await foreign.confirm(req.id, code=code)


@pytest.mark.asyncio
async def test_signed_enqueues_pep_signed_event(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="ev1")
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue",
            object_id=issue.id,
            purpose="ppe_issue",
            signer_person_id=person.id,
            requested_by="user-1",
        )
        await svc.confirm(req.id, code=code)
        await session.commit()

        outbox_entry = (
            await session.execute(
                select(Outbox).where(
                    Outbox.tenant_id == str(tenant.id),
                    Outbox.event_type == "PEPSigned",
                )
            )
        ).scalar_one_or_none()
        assert outbox_entry is not None
        assert outbox_entry.payload["signature_request_id"] == req.id


@pytest.mark.asyncio
async def test_declined_enqueues_pep_declined_event(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="ev2")
        svc = PepSigningService(session, str(tenant.id))
        req, _ = await svc.create_request(
            object_type="ppe_issue",
            object_id=issue.id,
            purpose="ppe_issue",
            signer_person_id=person.id,
            requested_by="user-1",
        )
        await svc.decline(req.id, reason="тест отклонения")
        await session.commit()

        outbox_entry = (
            await session.execute(
                select(Outbox).where(
                    Outbox.tenant_id == str(tenant.id),
                    Outbox.event_type == "PEPDeclined",
                )
            )
        ).scalar_one_or_none()
        assert outbox_entry is not None
        assert outbox_entry.payload["signature_request_id"] == req.id


@pytest.mark.asyncio
async def test_foreign_user_confirm_forbidden(sessionmaker, data_factory):
    """Чужой user-подписант получает PepForbidden (403-семантика), не PepConflict."""
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="f1")
        svc = PepSigningService(session, str(tenant.id))
        # signer_user_id="user-2", requested_by="user-1" → запрос остаётся created
        req, code = await svc.create_request(
            object_type="ppe_issue",
            object_id=issue.id,
            purpose="ppe_issue",
            signer_user_id="user-2",
            requested_by="user-1",
        )
        await session.commit()
        assert req.status == PepStatus.CREATED.value
        assert code is None

        # Чужой пользователь — PepForbidden
        with pytest.raises(PepForbidden):
            await svc.confirm(req.id, acting_user_id="user-3")

        # Назначенный подписант — успешная подпись
        signed = await svc.confirm(req.id, acting_user_id="user-2")
        await session.commit()
        assert signed.status == PepStatus.SIGNED.value
