"""Ф4 сервис рендера наряда: собирает данные из БД и отдаёт DOCX-байты."""
from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document

from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import service as svc
from app.domains.work_permits.signing import sign_closing
from app.services.work_permit_print import PdfRendererUnavailable, render_work_permit


async def _persons(data_factory, *names):
    tenant = await data_factory.ensure_tenant()
    company = await data_factory.create_company(tenant=tenant)
    people = []
    for i, nm in enumerate(names):
        people.append(await data_factory.create_person(
            tenant=tenant, company=company, first_name=nm, last_name=f"P{i}"))
    return tenant, people


def _docx_text(b: bytes) -> str:
    doc = Document(BytesIO(b))
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                parts.append(c.text)
    return "\n".join(parts)


@pytest.mark.asyncio
async def test_render_docx_includes_members_and_signature(sessionmaker, data_factory):
    tenant, (foreman, supervisor) = await _persons(data_factory, "Ivan", "Petr")
    tid = str(tenant.id)
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(session, tenant_id=tid, work_type="height",
                                          zone_text="фасад", number="НД-7")
        await svc.add_member(session, tenant_id=tid, work_permit_id=wp.id, person_id=foreman.id, role="foreman")
        await svc.add_member(session, tenant_id=tid, work_permit_id=wp.id, person_id=supervisor.id, role="supervisor")
        wp.status = lc.STATUS_ISSUED
        await session.flush()
        await svc.record_completion(session, tenant_id=tid, work_permit_id=wp.id,
                                    completion_text="работы окончены", actor_user_id="u1")
        await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                           person_id=foreman.id, mode="attested", requested_by="u1")
        rendered = await render_work_permit(session, tenant=tenant, permit_id=wp.id,
                                            fmt="docx", with_letterhead=False)
        assert rendered.media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert rendered.filename.endswith(".docx")
        text = _docx_text(rendered.content)
        assert "НД-7" in text
        assert "Ivan" in text                  # ФИО члена бригады зарезолвлено
        assert "работы окончены" in text


@pytest.mark.asyncio
async def test_render_unknown_permit_returns_none(sessionmaker, data_factory):
    tenant, _ = await _persons(data_factory, "Solo")
    async with sessionmaker() as session:
        rendered = await render_work_permit(session, tenant=tenant, permit_id="missing-id",
                                            fmt="docx", with_letterhead=False)
        assert rendered is None
