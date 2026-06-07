from __future__ import annotations

from datetime import date

import pytest
from fastapi import status

from app.models.models import RoleEnum


async def _seed_person(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()
        return person.id


@pytest.mark.asyncio
async def test_record_exam_unfit_blocks_then_fit_clears(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    person_id = await _seed_person(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    r = await async_client.post("/api/v1/medical/exams", headers=headers, json={
        "person_id": person_id, "exam_kind": "periodic",
        "exam_date": date(2026, 1, 1).isoformat(), "fitness": "unfit",
        "contraindications": ["asthma"]})
    assert r.status_code == status.HTTP_201_CREATED, r.text
    assert r.json()["fitness"] == "unfit"

    s = await async_client.get("/api/v1/medical/suspensions", headers=headers,
                               params={"person_id": person_id})
    assert s.status_code == status.HTTP_200_OK
    assert s.json()["total"] == 1

    r2 = await async_client.post("/api/v1/medical/exams", headers=headers, json={
        "person_id": person_id, "exam_kind": "periodic",
        "exam_date": date(2026, 2, 1).isoformat(), "fitness": "fit"})
    assert r2.status_code == status.HTTP_201_CREATED
    s2 = await async_client.get("/api/v1/medical/suspensions", headers=headers,
                                params={"person_id": person_id, "status": "active"})
    assert s2.json()["total"] == 0


@pytest.mark.asyncio
async def test_norm_crud(async_client, sessionmaker, data_factory, make_auth_headers):
    from app.models.models import Position
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Электрик")
        session.add(pos); await session.commit(); pos_id = pos.id
    headers = await make_auth_headers(RoleEnum.ADMIN)
    c = await async_client.post("/api/v1/medical/norms", headers=headers, json={
        "position_id": pos_id, "exam_kind": "periodic", "interval_days": 365})
    assert c.status_code == status.HTTP_201_CREATED, c.text
    norm_id = c.json()["id"]
    lst = await async_client.get("/api/v1/medical/norms", headers=headers)
    assert lst.status_code == status.HTTP_200_OK and lst.json()["total"] == 1
    etag = lst.headers["ETag"]
    hit = await async_client.get("/api/v1/medical/norms", headers={**headers, "If-None-Match": etag})
    assert hit.status_code == status.HTTP_304_NOT_MODIFIED
    pa = await async_client.patch(f"/api/v1/medical/norms/{norm_id}", headers=headers, json={"interval_days": 180})
    assert pa.status_code == status.HTTP_200_OK and pa.json()["interval_days"] == 180
    d = await async_client.delete(f"/api/v1/medical/norms/{norm_id}", headers=headers)
    assert d.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_referral_fsm(async_client, sessionmaker, data_factory, make_auth_headers):
    person_id = await _seed_person(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    c = await async_client.post("/api/v1/medical/referrals", headers=headers, json={
        "person_id": person_id, "exam_kind": "periodic", "due_at": date(2026, 7, 1).isoformat()})
    assert c.status_code == status.HTTP_201_CREATED, c.text
    rid = c.json()["id"]
    ok = await async_client.post(f"/api/v1/medical/referrals/{rid}/transition", headers=headers, json={"to": "scheduled"})
    assert ok.status_code == status.HTTP_200_OK
    bad = await async_client.post(f"/api/v1/medical/referrals/{rid}/transition", headers=headers, json={"to": "issued"})
    assert bad.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_contingent_and_generate(async_client, sessionmaker, data_factory, make_auth_headers):
    from app.models.models import MedicalNorm, Position
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Крановщик")
        session.add(pos); await session.flush()
        await data_factory.create_person(tenant=tenant, company=company, session=session, position_id=pos.id)
        session.add(MedicalNorm(tenant_id=tenant.id, position_id=pos.id, exam_kind="periodic", interval_days=365))
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    cont = await async_client.get("/api/v1/medical/contingent", headers=headers)
    assert cont.status_code == status.HTTP_200_OK
    assert any(i["status"] == "missing" for i in cont.json()["items"])
    gen = await async_client.post("/api/v1/medical/contingent/generate-referrals", headers=headers)
    assert gen.status_code == status.HTTP_200_OK and gen.json()["count"] == 1
    summ = await async_client.get("/api/v1/medical/summary", headers=headers)
    assert summ.json()["total"] >= 1
