from __future__ import annotations

import pytest
from app.models.models import RoleEnum

BASE = "/api/v1/work-permits"


async def _make_permit(async_client, headers) -> str:
    r = await async_client.post(
        BASE, headers=headers, json={"work_type": "height", "zone_text": "z"}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _add_member(async_client, headers, wp_id, person_id, role) -> None:
    r = await async_client.post(
        f"{BASE}/{wp_id}/members", headers=headers, json={"person_id": person_id, "role": role}
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_permit_signature_attested_then_listed(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    wp_id = await _make_permit(async_client, headers)
    person = await data_factory.create_person()
    pid = str(person.id)
    await _add_member(async_client, headers, wp_id, pid, "foreman")

    r = await async_client.post(
        f"{BASE}/{wp_id}/signatures", headers=headers, json={"person_id": pid, "mode": "attested"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "signed"
    assert r.json()["stream"] == "permit"

    lst = await async_client.get(f"{BASE}/{wp_id}/signatures", headers=headers)
    assert lst.status_code == 200
    assert any(s["status"] == "signed" and s["signer_person_id"] == pid for s in lst.json())


@pytest.mark.asyncio
async def test_permit_signature_code_flow(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    wp_id = await _make_permit(async_client, headers)
    person = await data_factory.create_person()
    pid = str(person.id)
    await _add_member(async_client, headers, wp_id, pid, "supervisor")

    r = await async_client.post(
        f"{BASE}/{wp_id}/signatures", headers=headers, json={"person_id": pid, "mode": "code"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "awaiting_code"
    code = body["confirm_code"]
    assert code and len(code) == 6

    confirm = await async_client.post(
        f"/api/v1/sign/pep/requests/{body['id']}/confirm",
        headers=headers,
        json={"code": code},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "signed"


@pytest.mark.asyncio
async def test_permit_signature_rejects_non_member(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    wp_id = await _make_permit(async_client, headers)
    person = await data_factory.create_person()
    pid = str(person.id)
    # person is NOT in brigade
    r = await async_client.post(
        f"{BASE}/{wp_id}/signatures", headers=headers, json={"person_id": pid, "mode": "attested"}
    )
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_briefing_signature_attested(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    wp_id = await _make_permit(async_client, headers)
    person = await data_factory.create_person()
    pid = str(person.id)
    await _add_member(async_client, headers, wp_id, pid, "member")

    br = await async_client.post(
        f"{BASE}/{wp_id}/briefing", headers=headers, json={"topics_text": "t"}
    )
    assert br.status_code == 201, br.text
    bid = br.json()["id"]

    r = await async_client.post(
        f"{BASE}/{wp_id}/briefing/{bid}/signatures",
        headers=headers,
        json={"person_id": pid, "mode": "attested"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "signed"
    assert r.json()["stream"] == "briefing"
