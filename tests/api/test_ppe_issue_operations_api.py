"""Issue lifecycle operations: return/writeoff/replace + FSM 409 + outbox."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import Outbox, PPEItem, RoleEnum

ISSUES = "/api/v1/ppe/issues"


async def _seed_issue(async_client, headers, sessionmaker, data_factory) -> tuple[str, str]:
    """Create item + person + issue via API; return (issue_id, person_id)."""
    tenant = await data_factory.ensure_tenant(slug="test")
    person = await data_factory.create_person(tenant=tenant)
    async with sessionmaker() as session:
        item = PPEItem(tenant_id=tenant.id, name=f"Перчатки-{person.id[:8]}", default_wear_days=90)
        session.add(item)
        await session.commit()
        item_id = str(item.id)
    resp = await async_client.post(
        ISSUES,
        headers=headers,
        json={
            "person_id": str(person.id),
            "item_id": item_id,
            "quantity": 1,
            "certificate_no": "ЕАЭС RU С-RU.АБ12.В.00001/26",
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    assert resp.json()["certificate_no"] == "ЕАЭС RU С-RU.АБ12.В.00001/26"
    return resp.json()["id"], str(person.id)


@pytest.mark.asyncio
async def test_return_operation(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issue_id, _ = await _seed_issue(async_client, headers, sessionmaker, data_factory)

    resp = await async_client.post(
        f"{ISSUES}/{issue_id}/return",
        headers=headers,
        json={
            "return_wear_percent": 50,
            "signature_doc_ref": "ведомость МБ-7 №12",
        },
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["status"] == "returned"
    assert body["return_wear_percent"] == 50
    assert body["returned_at"] is not None

    # terminal: second operation must 409
    again = await async_client.post(f"{ISSUES}/{issue_id}/return", headers=headers, json={})
    assert again.status_code == status.HTTP_409_CONFLICT, again.text


@pytest.mark.asyncio
async def test_writeoff_operation_emits_event(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issue_id, _ = await _seed_issue(async_client, headers, sessionmaker, data_factory)

    resp = await async_client.post(
        f"{ISSUES}/{issue_id}/writeoff",
        headers=headers,
        json={
            "writeoff_reason": "механическое повреждение",
        },
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    assert resp.json()["status"] == "written_off"
    assert resp.json()["writeoff_reason"] == "механическое повреждение"

    async with sessionmaker() as session:
        rows = (
            (await session.execute(select(Outbox).where(Outbox.event_type == "PPEWrittenOff")))
            .scalars()
            .all()
        )
        assert any(issue_id in str(r.payload) for r in rows)


@pytest.mark.asyncio
async def test_replace_operation_links_new_issue(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issue_id, person_id = await _seed_issue(async_client, headers, sessionmaker, data_factory)

    resp = await async_client.post(
        f"{ISSUES}/{issue_id}/replace",
        headers=headers,
        json={
            "quantity": 1,
            "certificate_no": "ЕАЭС RU С-RU.АБ12.В.00002/26",
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    new_issue = resp.json()
    assert new_issue["replaces_issue_id"] == issue_id
    assert new_issue["status"] == "issued"
    assert new_issue["person_id"] == person_id

    old = await async_client.get(f"{ISSUES}/{issue_id}", headers=headers)
    assert old.json()["status"] == "replaced"


@pytest.mark.asyncio
async def test_legacy_patch_respects_fsm(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issue_id, _ = await _seed_issue(async_client, headers, sessionmaker, data_factory)

    ok = await async_client.patch(
        f"{ISSUES}/{issue_id}", headers=headers, json={"status": "returned"}
    )
    assert ok.status_code == status.HTTP_200_OK, ok.text

    bad = await async_client.patch(f"{ISSUES}/{issue_id}", headers=headers, json={"status": "lost"})
    assert bad.status_code == status.HTTP_409_CONFLICT, bad.text


@pytest.mark.asyncio
async def test_replace_with_unknown_item_returns_400(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issue_id, _ = await _seed_issue(async_client, headers, sessionmaker, data_factory)

    resp = await async_client.post(
        f"{ISSUES}/{issue_id}/replace",
        headers=headers,
        json={
            "item_id": "no-such-item",
        },
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.text
