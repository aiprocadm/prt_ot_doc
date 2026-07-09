from __future__ import annotations

import pytest
from fastapi import status

from app.models.models import RoleEnum


@pytest.mark.asyncio
async def test_activity_type_crud_and_duplicate(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = {"code": "height", "name": "Работы на высоте", "interval_days": 1825}
    r = await async_client.post(
        "/api/v1/medical/psychiatric/activity-types", headers=headers, json=body
    )
    assert r.status_code == status.HTTP_201_CREATED, r.text
    aid = r.json()["id"]

    dup = await async_client.post(
        "/api/v1/medical/psychiatric/activity-types", headers=headers, json=body
    )
    assert dup.status_code == status.HTTP_409_CONFLICT

    lst = await async_client.get("/api/v1/medical/psychiatric/activity-types", headers=headers)
    assert lst.status_code == status.HTTP_200_OK
    assert any(a["code"] == "height" for a in lst.json()["items"])

    patched = await async_client.patch(
        f"/api/v1/medical/psychiatric/activity-types/{aid}",
        headers=headers, json={"interval_days": 1095},
    )
    assert patched.status_code == status.HTTP_200_OK and patched.json()["interval_days"] == 1095

    deleted = await async_client.delete(
        f"/api/v1/medical/psychiatric/activity-types/{aid}", headers=headers
    )
    assert deleted.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_seed_defaults_idempotent_endpoint(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r1 = await async_client.post(
        "/api/v1/medical/psychiatric/activity-types/seed-defaults", headers=headers
    )
    assert r1.status_code == status.HTTP_200_OK and r1.json()["count"] >= 8
    r2 = await async_client.post(
        "/api/v1/medical/psychiatric/activity-types/seed-defaults", headers=headers
    )
    assert r2.status_code == status.HTTP_200_OK and r2.json()["count"] == 0


@pytest.mark.asyncio
async def test_set_position_activities_and_validation(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    from app.models.models import Position

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Крановщик")
        session.add(pos)
        await session.commit()
        pos_id = pos.id
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post(
        "/api/v1/medical/psychiatric/activity-types/seed-defaults", headers=headers
    )
    # unknown code → 422
    bad = await async_client.put(
        f"/api/v1/medical/psychiatric/positions/{pos_id}/activities",
        headers=headers, json={"activity_codes": ["ghost"]},
    )
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # valid set → 200, and read reflects it
    ok = await async_client.put(
        f"/api/v1/medical/psychiatric/positions/{pos_id}/activities",
        headers=headers, json={"activity_codes": ["height", "transport"]},
    )
    assert ok.status_code == status.HTTP_200_OK
    assert set(ok.json()["activity_codes"]) == {"height", "transport"}
    # replace semantics: setting a smaller set removes the rest
    ok2 = await async_client.put(
        f"/api/v1/medical/psychiatric/positions/{pos_id}/activities",
        headers=headers, json={"activity_codes": ["height"]},
    )
    assert set(ok2.json()["activity_codes"]) == {"height"}


@pytest.mark.asyncio
async def test_activity_types_require_write_role(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    r = await async_client.post(
        "/api/v1/medical/psychiatric/activity-types",
        headers=headers, json={"code": "x", "name": "y"},
    )
    assert r.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


@pytest.mark.asyncio
async def test_create_psychiatric_exam_persists_new_fields(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session,
            first_name="Марк", last_name="Лев",
        )
        await session.commit()
        pid = person.id
    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = {
        "person_id": pid,
        "exam_kind": "psychiatric",
        "exam_date": "2026-01-01",
        "fitness": "fit",
        "medical_org_name": "ВК № 7",
        "psychiatric_protocol_no": "ПРО-99",
        "psychiatric_activity_codes": ["height"],
    }
    r = await async_client.post("/api/v1/medical/exams", headers=headers, json=body)
    assert r.status_code == status.HTTP_201_CREATED, r.text
    data = r.json()
    assert data["psychiatric_protocol_no"] == "ПРО-99"
    assert data["psychiatric_activity_codes"] == ["height"]


@pytest.mark.asyncio
async def test_set_position_activities_unknown_position_404(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post(
        "/api/v1/medical/psychiatric/activity-types/seed-defaults", headers=headers
    )
    r = await async_client.put(
        "/api/v1/medical/psychiatric/positions/does-not-exist/activities",
        headers=headers, json={"activity_codes": ["height"]},
    )
    assert r.status_code == status.HTTP_404_NOT_FOUND, r.text
    # the _error(...) code is promoted to the top-level machine code in the error contract
    assert r.json()["code"] == "position_not_found"


@pytest.mark.asyncio
async def test_activity_type_cross_tenant_isolation(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session, slug="psy-tenant-a")
        await data_factory.ensure_tenant(session=session, slug="psy-tenant-b")
        await session.commit()
    # distinct email per tenant (cross-tenant workaround documented in conftest)
    headers_a = await make_auth_headers(
        RoleEnum.ADMIN, tenant="psy-tenant-a", email="admin-psy-a@example.com"
    )
    headers_b = await make_auth_headers(
        RoleEnum.ADMIN, tenant="psy-tenant-b", email="admin-psy-b@example.com"
    )
    created = await async_client.post(
        "/api/v1/medical/psychiatric/activity-types",
        headers=headers_a, json={"code": "height", "name": "Работы на высоте"},
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    aid = created.json()["id"]
    # tenant B must not see tenant A's activity type by id
    got = await async_client.get(
        f"/api/v1/medical/psychiatric/activity-types/{aid}", headers=headers_b
    )
    assert got.status_code == status.HTTP_404_NOT_FOUND
    # ... nor in its list
    lst = await async_client.get(
        "/api/v1/medical/psychiatric/activity-types", headers=headers_b
    )
    assert lst.status_code == status.HTTP_200_OK
    assert all(a["id"] != aid for a in lst.json()["items"])
