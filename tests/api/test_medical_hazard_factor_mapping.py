"""Runtime CRUD привязки hazard→фактор 29н: PUT/GET + валидация + e2e влияние на список."""

from __future__ import annotations

import pytest
from fastapi import status

from app.models.models import RoleEnum

MAP = "/api/v1/medical/hazards/{hid}/factor"
LIST = "/api/v1/medical/hazard-factors"


async def _seed_hazard(sessionmaker, data_factory, *, tenant=None, factor=True):
    from app.models.models import MedicalFactor
    from app.models.risk import RiskHazard

    async with sessionmaker() as session:
        t = tenant or await data_factory.ensure_tenant(session=session)
        hazard = RiskHazard(tenant_id=t.id, code="noise", title="Шум производственный")
        session.add(hazard)
        if factor:
            session.add(
                MedicalFactor(
                    tenant_id=t.id, code="4.4", name="Шум",
                    exam_kinds=["periodic"], periodicity_months=12,
                )
            )
        await session.flush()
        hid = hazard.id
        await session.commit()
    return t, hid


@pytest.mark.asyncio
async def test_put_sets_mapping_and_get_lists_it(async_client, sessionmaker, data_factory, make_auth_headers):
    _t, hid = await _seed_hazard(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.put(MAP.format(hid=hid), headers=headers, json={"factor_code": "4.4"})
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["factor_code"] == "4.4"
    assert body["factor_name"] == "Шум"
    assert body["hazard_id"] == hid

    lst = await async_client.get(LIST, headers=headers)
    assert lst.status_code == status.HTTP_200_OK, lst.text
    assert any(it["hazard_id"] == hid and it["factor_code"] == "4.4" for it in lst.json()["items"])


@pytest.mark.asyncio
async def test_put_unknown_factor_422(async_client, sessionmaker, data_factory, make_auth_headers):
    _t, hid = await _seed_hazard(sessionmaker, data_factory, factor=False)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.put(MAP.format(hid=hid), headers=headers, json={"factor_code": "9.9"})
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text


@pytest.mark.asyncio
async def test_put_unknown_hazard_404(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.put(MAP.format(hid="missing-id"), headers=headers, json={"factor_code": None})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text


@pytest.mark.asyncio
async def test_put_null_clears_mapping(async_client, sessionmaker, data_factory, make_auth_headers):
    _t, hid = await _seed_hazard(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.put(MAP.format(hid=hid), headers=headers, json={"factor_code": "4.4"})
    resp = await async_client.put(MAP.format(hid=hid), headers=headers, json={"factor_code": None})
    assert resp.status_code == status.HTTP_200_OK, resp.text
    assert resp.json()["factor_code"] is None


@pytest.mark.asyncio
async def test_mapping_affects_named_list_e2e(async_client, sessionmaker, data_factory, make_auth_headers):
    from app.models.models import Position, PositionHazardLink

    t, hid = await _seed_hazard(sessionmaker, data_factory)
    async with sessionmaker() as session:
        company = await data_factory.create_company(tenant=t, session=session)
        pos = Position(tenant_id=t.id, company_id=company.id, name="Сварщик")
        session.add(pos)
        await session.flush()
        session.add(PositionHazardLink(tenant_id=t.id, position_id=pos.id, hazard_id=hid))
        await data_factory.create_person(
            tenant=t, company=company, session=session, position_id=pos.id,
            first_name="Иван", last_name="Петров",
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    # До привязки — поименный список пуст (немапленный hazard).
    before = await async_client.get("/api/v1/medical/named-list", headers=headers)
    assert before.status_code == 200
    assert all(r["full_name"] != "Петров Иван" for r in before.json()["items"])

    # Привязываем фактор → работник появляется factor-driven путём.
    await async_client.put(MAP.format(hid=hid), headers=headers, json={"factor_code": "4.4"})
    after = await async_client.get("/api/v1/medical/named-list", headers=headers)
    assert any(r["full_name"] == "Петров Иван" for r in after.json()["items"]), after.text


@pytest.mark.asyncio
async def test_cross_tenant_hazard_404(async_client, sessionmaker, data_factory, make_auth_headers):
    ta = await data_factory.ensure_tenant(slug="med-map-ta")
    await data_factory.ensure_tenant(slug="med-map-tb")
    _t, hid = await _seed_hazard(sessionmaker, data_factory, tenant=ta)
    headers_b = await make_auth_headers(
        RoleEnum.ADMIN, tenant="med-map-tb", email="admin-med-map-tb@example.com"
    )
    resp = await async_client.put(MAP.format(hid=hid), headers=headers_b, json={"factor_code": None})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text
