"""766н personal card: header+sizes, required-vs-issued, line statuses, timeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import Position, PPEIssue, PPEItem, PPENorm, RoleEnum
from app.models.risk import RiskHazard

CARD = "/api/v1/ppe/employees/{person_id}/card"
SIZES = "/api/v1/ppe/employees/{person_id}/sizes"

NOW = datetime.now(tz=timezone.utc)


async def _seed_card_world(sessionmaker, data_factory):
    """Person on a position with 2 norms; 1 active issue, 1 expired, covered/uncovered lines."""
    tenant = await data_factory.ensure_tenant(slug="test")
    company = await data_factory.create_company(tenant=tenant, name="Card Co")
    async with sessionmaker() as session:
        position = Position(tenant_id=tenant.id, company_id=company.id, name="Монтажник")
        hazard = RiskHazard(tenant_id=tenant.id, code="height", title="Работы на высоте")
        helmet = PPEItem(tenant_id=tenant.id, name="Каска защитная", default_wear_days=730)
        belt = PPEItem(tenant_id=tenant.id, name="Пояс страховочный", default_wear_days=365)
        session.add_all([position, hazard, helmet, belt])
        await session.flush()
        norm_helmet = PPENorm(
            tenant_id=tenant.id,
            position_id=position.id,
            hazard_id=hazard.id,
            item_id=helmet.id,
            item_name=helmet.name,
            quantity=1,
            interval_days=730,
        )
        norm_belt = PPENorm(
            tenant_id=tenant.id,
            position_id=position.id,
            hazard_id=hazard.id,
            item_id=belt.id,
            item_name=belt.name,
            quantity=1,
            interval_days=365,
        )
        session.add_all([norm_helmet, norm_belt])
        await session.commit()
        position_id, helmet_id, belt_id = str(position.id), str(helmet.id), str(belt.id)
        tenant_db_id = str(tenant.id)

    person = await data_factory.create_person(
        tenant=tenant,
        company=company,
        position_id=position_id,
        ppe_sizes={"height": 180, "headgear_size": "58"},
    )
    async with sessionmaker() as session:
        # активная выдача каски (далеко до истечения) → ok
        session.add(
            PPEIssue(
                tenant_id=tenant_db_id,
                person_id=person.id,
                item_id=helmet_id,
                item_name="Каска защитная",
                quantity=1,
                issued_at=NOW,
                expires_at=NOW + timedelta(days=400),
                status="issued",
                certificate_no="CERT-1",
            )
        )
        # активная, но истёкшая выдача пояса → overdue
        session.add(
            PPEIssue(
                tenant_id=tenant_db_id,
                person_id=person.id,
                item_id=belt_id,
                item_name="Пояс страховочный",
                quantity=1,
                issued_at=NOW - timedelta(days=400),
                expires_at=NOW - timedelta(days=35),
                status="issued",
            )
        )
        await session.commit()
    return str(person.id)


@pytest.mark.asyncio
async def test_card_full_shape(async_client, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    person_id = await _seed_card_world(sessionmaker, data_factory)

    resp = await async_client.get(CARD.format(person_id=person_id), headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    card = resp.json()

    assert card["person_id"] == person_id
    assert card["position_name"] == "Монтажник"
    assert card["sizes"] == {"height": 180, "headgear_size": "58"}

    lines = {line["item_name"]: line for line in card["required"]}
    assert lines["Каска защитная"]["status"] == "ok"
    assert lines["Пояс страховочный"]["status"] == "overdue"
    assert card["summary_status"] == "overdue"

    assert len(card["issues"]) == 2
    events = [e["event"] for e in card["timeline"]]
    assert events.count("issued") == 2


@pytest.mark.asyncio
async def test_card_missing_line_when_no_issue(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant = await data_factory.ensure_tenant(slug="test")
    company = await data_factory.create_company(tenant=tenant, name="Missing Co")
    async with sessionmaker() as session:
        position = Position(tenant_id=tenant.id, company_id=company.id, name="Лаборант")
        hazard = RiskHazard(tenant_id=tenant.id, code="chem", title="Химфактор")
        gloves = PPEItem(tenant_id=tenant.id, name="Перчатки КЩС", default_wear_days=30)
        session.add_all([position, hazard, gloves])
        await session.flush()
        session.add(
            PPENorm(
                tenant_id=tenant.id,
                position_id=position.id,
                hazard_id=hazard.id,
                item_id=gloves.id,
                item_name=gloves.name,
                quantity=2,
                interval_days=30,
            )
        )
        await session.commit()
        position_id = str(position.id)
    person = await data_factory.create_person(
        tenant=tenant, company=company, position_id=position_id
    )

    resp = await async_client.get(CARD.format(person_id=str(person.id)), headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    card = resp.json()
    assert card["required"][0]["status"] == "missing"
    assert card["summary_status"] == "missing"


@pytest.mark.asyncio
async def test_card_404_for_unknown_person(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(CARD.format(person_id="nope"), headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_put_sizes_validates_and_persists(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant = await data_factory.ensure_tenant(slug="test")
    person = await data_factory.create_person(tenant=tenant)

    resp = await async_client.put(
        SIZES.format(person_id=str(person.id)),
        headers=headers,
        json={
            "height": 175,
            "clothing_size": "52-54",
            "shoe_size": "43",
        },
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    assert resp.json()["sizes"]["clothing_size"] == "52-54"

    bad = await async_client.put(
        SIZES.format(person_id=str(person.id)),
        headers=headers,
        json={
            "height": 999,
        },
    )
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_legacy_norm_without_item_id_matches_catalog_issue(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    """Pre-sz01 norm (no item_id) must be satisfied by a catalog-issued item with the same name."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant = await data_factory.ensure_tenant(slug="test")
    company = await data_factory.create_company(tenant=tenant, name="Legacy Co")
    async with sessionmaker() as session:
        position = Position(tenant_id=tenant.id, company_id=company.id, name="Аппаратчик")
        hazard = RiskHazard(tenant_id=tenant.id, code="legacy", title="Legacy фактор")
        item = PPEItem(tenant_id=tenant.id, name="Респиратор У-2К", default_wear_days=180)
        session.add_all([position, hazard, item])
        await session.flush()
        session.add(
            PPENorm(  # legacy: item_id is None
                tenant_id=tenant.id,
                position_id=position.id,
                hazard_id=hazard.id,
                item_id=None,
                item_name="Респиратор У-2К",
                quantity=1,
                interval_days=180,
            )
        )
        await session.commit()
        position_id, item_id = str(position.id), str(item.id)
    person = await data_factory.create_person(
        tenant=tenant, company=company, position_id=position_id
    )
    async with sessionmaker() as session:
        session.add(
            PPEIssue(  # catalog issue WITH item_id
                tenant_id=str(tenant.id),
                person_id=person.id,
                item_id=item_id,
                item_name="Респиратор У-2К",
                quantity=1,
                issued_at=NOW,
                expires_at=NOW + timedelta(days=170),
                status="issued",
            )
        )
        await session.commit()

    resp = await async_client.get(CARD.format(person_id=str(person.id)), headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    card = resp.json()
    assert card["required"][0]["status"] == "ok", card["required"]
    assert card["summary_status"] == "ok"


@pytest.mark.asyncio
async def test_card_with_soft_deleted_position_renders(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant = await data_factory.ensure_tenant(slug="test")
    company = await data_factory.create_company(tenant=tenant, name="SoftDel Co")
    async with sessionmaker() as session:
        position = Position(tenant_id=tenant.id, company_id=company.id, name="Упразднённая")
        session.add(position)
        await session.flush()
        position_id = str(position.id)
        await session.commit()
    person = await data_factory.create_person(
        tenant=tenant, company=company, position_id=position_id
    )
    async with sessionmaker() as session:
        pos = (
            await session.execute(select(Position).where(Position.id == position_id))
        ).scalar_one()
        pos.deleted_at = datetime.now(timezone.utc)
        await session.commit()

    resp = await async_client.get(CARD.format(person_id=str(person.id)), headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    assert resp.json()["position_name"] is None
