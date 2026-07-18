"""Tests for PEP signing _build_content branches: work_permit + work_permit_briefing."""

import pytest

from app.domains.work_permits import add_member, create_briefing, create_work_permit
from app.domains.work_permits.signing import (
    WorkPermitSignerError,
    sign_briefing,
    sign_permit,
)
from app.services.pep_signing import PepConflict, PepNotFound, PepSigningService


@pytest.mark.asyncio
async def test_build_content_work_permit(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="фасад",
            number="НД-7",
            content_text="монтаж",
        )
        svc = PepSigningService(session, str(person.tenant_id))
        content = await svc._build_content("work_permit", wp.id)
        assert content["work_permit_id"] == wp.id
        assert content["number"] == "НД-7"
        assert content["work_type"] == "height"
        assert content["members"] == []


@pytest.mark.asyncio
async def test_build_content_unknown_permit_raises(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        svc = PepSigningService(session, str(person.tenant_id))
        with pytest.raises(PepNotFound):
            await svc._build_content("work_permit", "missing-id")


@pytest.mark.asyncio
async def test_sign_permit_attested_marks_signed(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="z",
        )
        await add_member(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            person_id=person.id,
            role="foreman",
        )
        req, code = await sign_permit(
            session,
            tenant_id=str(person.tenant_id),
            work_permit_id=wp.id,
            person_id=person.id,
            mode="attested",
            requested_by="u1",
        )
        assert code is None
        assert req.status == "signed"
        assert req.object_type == "work_permit"


@pytest.mark.asyncio
async def test_sign_permit_code_mode_returns_code(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="z",
        )
        await add_member(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            person_id=person.id,
            role="supervisor",
        )
        req, code = await sign_permit(
            session,
            tenant_id=str(person.tenant_id),
            work_permit_id=wp.id,
            person_id=person.id,
            mode="code",
            requested_by="u1",
        )
        assert code is not None and len(code) == 6
        assert req.status == "awaiting_code"


@pytest.mark.asyncio
async def test_sign_permit_rejects_non_responsible(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="z",
        )
        # роль member НЕ входит в класс ответственных
        await add_member(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            person_id=person.id,
            role="member",
        )
        with pytest.raises(WorkPermitSignerError):
            await sign_permit(
                session,
                tenant_id=str(person.tenant_id),
                work_permit_id=wp.id,
                person_id=person.id,
                mode="attested",
                requested_by="u1",
            )


@pytest.mark.asyncio
async def test_sign_permit_blocks_double_sign(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="z",
        )
        await add_member(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            person_id=person.id,
            role="issuer",
        )
        await sign_permit(
            session,
            tenant_id=str(person.tenant_id),
            work_permit_id=wp.id,
            person_id=person.id,
            mode="attested",
            requested_by="u1",
        )
        with pytest.raises(PepConflict):
            await sign_permit(
                session,
                tenant_id=str(person.tenant_id),
                work_permit_id=wp.id,
                person_id=person.id,
                mode="attested",
                requested_by="u1",
            )


@pytest.mark.asyncio
async def test_sign_briefing_attested(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="z",
        )
        await add_member(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            person_id=person.id,
            role="member",
        )
        br = await create_briefing(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            topics_text="t",
        )
        req, code = await sign_briefing(
            session,
            tenant_id=str(person.tenant_id),
            briefing_id=br.id,
            person_id=person.id,
            mode="attested",
            requested_by="u1",
        )
        assert code is None and req.status == "signed"
        assert req.object_type == "work_permit_briefing"
