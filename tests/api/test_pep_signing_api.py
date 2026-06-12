"""PEP signing HTTP contract: full person-code cycle, errors, journal, acknowledgements."""
from __future__ import annotations

import pytest

from app.models.models import PPEIssue, RoleEnum


async def _issue_world(session, data_factory):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session, name="PEP API")
    person = await data_factory.create_person(tenant=tenant, company=company, session=session)
    issue = PPEIssue(
        tenant_id=tenant.id, person_id=person.id,
        item_name="Каска api", quantity=1, status="issued",
    )
    session.add(issue)
    await session.commit()
    return tenant, person, issue


@pytest.mark.asyncio
async def test_full_person_cycle_via_http(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:
        tenant, person, issue = await _issue_world(session, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    created = await async_client.post(
        "/api/v1/sign/pep/requests",
        json={
            "object_type": "ppe_issue", "object_id": issue.id,
            "purpose": "ppe_issue", "signer_person_id": person.id,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "awaiting_code"
    assert len(body["confirm_code"]) == 6  # единственный момент видимости кода
    rid = body["id"]

    confirmed = await async_client.post(
        f"/api/v1/sign/pep/requests/{rid}/confirm", json={"code": body["confirm_code"]}, headers=headers
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "signed"
    assert "confirm_code" not in confirmed.json()

    verify = await async_client.get(f"/api/v1/sign/pep/requests/{rid}/verify", headers=headers)
    assert verify.status_code == 200
    assert verify.json()["match"] is True

    journal = await async_client.get(
        "/api/v1/sign/pep/requests",
        params={"object_type": "ppe_issue", "object_id": issue.id},
        headers=headers,
    )
    assert journal.status_code == 200
    assert any(item["id"] == rid for item in journal.json()["items"])


@pytest.mark.asyncio
async def test_wrong_code_409_persists_attempts(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:
        tenant, person, issue = await _issue_world(session, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    created = await async_client.post(
        "/api/v1/sign/pep/requests",
        json={
            "object_type": "ppe_issue", "object_id": issue.id,
            "purpose": "ppe_issue", "signer_person_id": person.id,
        },
        headers=headers,
    )
    rid = created.json()["id"]
    wrong = await async_client.post(
        f"/api/v1/sign/pep/requests/{rid}/confirm", json={"code": "000000"}, headers=headers
    )
    assert wrong.status_code == 409

    # КРИТИЧНО: инкремент попыток должен пережить 409 (commit-on-conflict)
    from sqlalchemy import select
    from app.models.models import SignatureRequest
    async with sessionmaker() as session:
        row = (
            await session.execute(select(SignatureRequest).where(SignatureRequest.id == rid))
        ).scalar_one()
        assert row.confirm_attempts == 1


@pytest.mark.asyncio
async def test_unknown_object_404(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:
        tenant, person, _ = await _issue_world(session, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)
    missing = await async_client.post(
        "/api/v1/sign/pep/requests",
        json={
            "object_type": "ppe_issue", "object_id": "no-such",
            "purpose": "ppe_issue", "signer_person_id": person.id,
        },
        headers=headers,
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_acknowledgements_journal(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="ACK API")
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        doc, ver = await data_factory.create_document(tenant=tenant, session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    created = await async_client.post(
        "/api/v1/sign/pep/requests",
        json={
            "object_type": "document_version", "object_id": ver.id,
            "purpose": "acknowledgement", "signer_person_id": person.id,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    code = created.json()["confirm_code"]
    rid = created.json()["id"]
    await async_client.post(f"/api/v1/sign/pep/requests/{rid}/confirm", json={"code": code}, headers=headers)

    acks = await async_client.get(
        "/api/v1/sign/acknowledgements", params={"document_version_id": ver.id}, headers=headers
    )
    assert acks.status_code == 200
    items = acks.json()["items"]
    assert len(items) == 1
    assert items[0]["signer_person_id"] == person.id
    assert items[0]["status"] == "signed"


@pytest.mark.asyncio
async def test_decline_endpoint(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:
        tenant, person, issue = await _issue_world(session, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)
    created = await async_client.post(
        "/api/v1/sign/pep/requests",
        json={
            "object_type": "ppe_issue", "object_id": issue.id,
            "purpose": "ppe_issue", "signer_person_id": person.id,
        },
        headers=headers,
    )
    rid = created.json()["id"]
    declined = await async_client.post(
        f"/api/v1/sign/pep/requests/{rid}/decline", json={"reason": "отказ"}, headers=headers
    )
    assert declined.status_code == 200
    assert declined.json()["status"] == "declined"
