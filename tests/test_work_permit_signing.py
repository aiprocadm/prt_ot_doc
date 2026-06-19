"""Tests for PEP signing _build_content branches: work_permit + work_permit_briefing."""
import pytest

from app.domains.work_permits import create_work_permit
from app.services.pep_signing import PepNotFound, PepSigningService


@pytest.mark.asyncio
async def test_build_content_work_permit(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session, tenant_id=person.tenant_id, work_type="height", zone_text="фасад",
            number="НД-7", content_text="монтаж",
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
