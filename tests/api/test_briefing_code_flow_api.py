"""HTTP contract: BriefingTemplate.require_signature_code CRUD + code-flow cycle."""
from __future__ import annotations

import itertools
from datetime import datetime, timezone

import pytest

from app.models.models import BriefingEntry, BriefingJournal, BriefingTemplate, RoleEnum, SignatureRequest

_counter = itertools.count(1)


async def _entry_with_template(session, data_factory, *, require_code: bool):
    n = next(_counter)
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session, name="BRF CF API")
    person = await data_factory.create_person(tenant=tenant, company=company, session=session)
    template = BriefingTemplate(
        tenant_id=tenant.id, code=f"BRF-CF-API-T-{n}", title="CF", briefing_type="primary",
        require_signature_code=require_code,
    )
    journal = BriefingJournal(
        tenant_id=tenant.id, code=f"BRF-CF-API-J-{n}", title="CF", journal_type="workplace", status="active"
    )
    session.add_all([template, journal])
    await session.flush()
    entry = BriefingEntry(
        tenant_id=tenant.id, person_id=person.id, briefing_journal_id=journal.id,
        briefing_template_id=template.id, briefing_type="primary",
        briefing_date=datetime.now(tz=timezone.utc), status="assigned",
    )
    session.add(entry)
    await session.commit()
    return tenant, person, entry


@pytest.mark.asyncio
async def test_template_require_signature_code_roundtrip(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    created = await async_client.post(
        "/api/v1/briefings/templates",
        json={
            "code": "BRF-CODE-T1",
            "title": "Вводный с кодом",
            "briefing_type": "primary",
            "require_signature_code": True,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["require_signature_code"] is True

    # default остаётся false, когда поле не передано
    created2 = await async_client.post(
        "/api/v1/briefings/templates",
        json={"code": "BRF-CODE-T2", "title": "Без кода", "briefing_type": "primary"},
        headers=headers,
    )
    assert created2.status_code == 201, created2.text
    assert created2.json()["require_signature_code"] is False


@pytest.mark.asyncio
async def test_sign_employee_with_flag_returns_code_then_confirm(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant, _, entry = await _entry_with_template(session, data_factory, require_code=True)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    started = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/sign-employee", json={}, headers=headers
    )
    assert started.status_code == 200, started.text
    pending = started.json()["pending"]
    assert pending["status"] == "awaiting_code"
    assert len(pending["confirm_code"]) == 6

    confirmed = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/confirm-code",
        json={"code": pending["confirm_code"]},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["signature"]["signer_type"] == "employee"


@pytest.mark.asyncio
async def test_sign_employee_without_flag_signs_immediately(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant, _, entry = await _entry_with_template(session, data_factory, require_code=False)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    resp = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/sign-employee", json={}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "pending" not in body
    assert body["signature"]["signer_type"] == "employee"


@pytest.mark.asyncio
async def test_confirm_code_without_pending_returns_409(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant, _, entry = await _entry_with_template(session, data_factory, require_code=True)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    resp = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/confirm-code",
        json={"code": "123456"}, headers=headers,
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_confirm_code_wrong_code_returns_409_and_persists_attempt(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant, _, entry = await _entry_with_template(session, data_factory, require_code=True)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    started = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/sign-employee", json={}, headers=headers
    )
    assert started.status_code == 200, started.text
    pending = started.json()["pending"]

    wrong = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/confirm-code",
        json={"code": "000000"}, headers=headers,
    )
    assert wrong.status_code == 409, wrong.text

    # commit-on-conflict: инкремент попыток пережил 409
    async with sessionmaker() as s:
        req = await s.get(SignatureRequest, pending["pep_request_id"])
        assert req.confirm_attempts == 1
        assert req.status == "awaiting_code"

    # верный код после неверного всё ещё проходит
    ok = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/confirm-code",
        json={"code": pending["confirm_code"]}, headers=headers,
    )
    assert ok.status_code == 200, ok.text
