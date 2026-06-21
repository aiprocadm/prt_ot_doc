"""Ф3b API: акт закрытия + подписи + гейт close + tenant-isolation."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.domains.permits import service as permit_svc
from app.models.models import Company, RoleEnum, Tenant

BASE = "/api/v1/work-permits"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_permit(async_client, headers) -> str:
    r = await async_client.post(
        BASE, headers=headers, json={"work_type": "height", "zone_text": "z"}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _add_member(async_client, headers, wp_id, person_id, role) -> None:
    r = await async_client.post(
        f"{BASE}/{wp_id}/members", headers=headers,
        json={"person_id": person_id, "role": role},
    )
    assert r.status_code == 201, r.text


async def _make_two_persons_with_permits(data_factory, sessionmaker):
    """Создаёт foreman и supervisor в одном тенанте с активными персональными допусками (height).

    Грабля: data_factory.create_person() создаёт компанию «ACME Corp», которая unique
    по (tenant_id, name). Поэтому вторую персону создаём с той же company.
    """
    foreman = await data_factory.create_person(first_name="Foreman", last_name="Closing")
    # Получаем тенант/компанию по ID (Person не хранит ссылочный объект)
    async with sessionmaker() as session:
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == str(foreman.tenant_id))
        )).scalar_one()
        company = (await session.execute(
            select(Company).where(Company.id == str(foreman.company_id))
        )).scalar_one()

    supervisor = await data_factory.create_person(
        first_name="Supervisor", last_name="Closing",
        tenant=tenant, company=company,
    )

    # Создаём персональные допуски (height) — обязательное условие для issue (brigade-readiness)
    async with sessionmaker() as session:
        for person in (foreman, supervisor):
            await permit_svc.create_permit(
                session, tenant_id=str(person.tenant_id), person_id=str(person.id),
                permit_type="height", issued_at=date.today(),
                valid_until=date.today() + timedelta(days=30),
            )
        await session.commit()

    return foreman, supervisor, tenant, company


async def _issued_permit(async_client, headers, foreman_id: str, supervisor_id: str) -> str:
    """Создаёт наряд work_type=height, добавляет foreman+supervisor и переводит в issued."""
    wp_id = await _make_permit(async_client, headers)
    await _add_member(async_client, headers, wp_id, foreman_id, "foreman")
    await _add_member(async_client, headers, wp_id, supervisor_id, "supervisor")
    r = await async_client.post(f"{BASE}/{wp_id}/issue", headers=headers, json={})
    assert r.status_code == 200, r.text
    return wp_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_closing_act_and_summary(async_client, make_auth_headers, data_factory, sessionmaker):
    """POST /closing сохраняет акт; GET /closing возвращает сводку с can_close=False."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    foreman, supervisor, _t, _c = await _make_two_persons_with_permits(data_factory, sessionmaker)
    wp_id = await _issued_permit(async_client, headers, str(foreman.id), str(supervisor.id))

    r = await async_client.post(
        f"{BASE}/{wp_id}/closing", headers=headers,
        json={"completion_text": "место сдано"},
    )
    assert r.status_code == 200, r.text

    s = (await async_client.get(f"{BASE}/{wp_id}/closing", headers=headers)).json()
    assert s["completion_text"] == "место сдано"
    assert s["can_close"] is False
    assert "handover_signature" in s["missing"]
    assert "acceptance_signature" in s["missing"]


@pytest.mark.asyncio
async def test_close_gate_then_success(async_client, make_auth_headers, data_factory, sessionmaker):
    """close без подписей → 409; с актом+обеими подписями → 200 closed."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    foreman, supervisor, _t, _c = await _make_two_persons_with_permits(data_factory, sessionmaker)
    foreman_id = str(foreman.id)
    supervisor_id = str(supervisor.id)

    wp_id = await _issued_permit(async_client, headers, foreman_id, supervisor_id)

    await async_client.post(
        f"{BASE}/{wp_id}/closing", headers=headers,
        json={"completion_text": "готово"},
    )

    # close до подписей → 409 с missing-списком
    blocked = await async_client.post(f"{BASE}/{wp_id}/close", headers=headers, json={})
    assert blocked.status_code == 409, blocked.text
    detail = blocked.json()["detail"]
    assert "missing" in detail.get("details", detail)

    # подписи сдал+принял (attested)
    for pid in (foreman_id, supervisor_id):
        rs = await async_client.post(
            f"{BASE}/{wp_id}/closing/signatures", headers=headers,
            json={"person_id": pid, "mode": "attested"},
        )
        assert rs.status_code == 201, rs.text
        assert rs.json()["status"] == "signed"

    # теперь can_close = True
    s = (await async_client.get(f"{BASE}/{wp_id}/closing", headers=headers)).json()
    assert s["can_close"] is True

    ok = await async_client.post(f"{BASE}/{wp_id}/close", headers=headers, json={})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_closing_act_locked_after_signature_409(async_client, make_auth_headers, data_factory, sessionmaker):
    """Правка акта окончания после первой SIGNED-подписи закрытия → 409 (защита подписи)."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    foreman, supervisor, _t, _c = await _make_two_persons_with_permits(data_factory, sessionmaker)
    wp_id = await _issued_permit(async_client, headers, str(foreman.id), str(supervisor.id))

    r = await async_client.post(
        f"{BASE}/{wp_id}/closing", headers=headers, json={"completion_text": "готово"}
    )
    assert r.status_code == 200, r.text

    rs = await async_client.post(
        f"{BASE}/{wp_id}/closing/signatures", headers=headers,
        json={"person_id": str(foreman.id), "mode": "attested"},
    )
    assert rs.status_code == 201, rs.text

    # правка акта после подписи → 409
    blocked = await async_client.post(
        f"{BASE}/{wp_id}/closing", headers=headers, json={"completion_text": "новый текст"}
    )
    assert blocked.status_code == 409, blocked.text

    # акт не изменился
    s = (await async_client.get(f"{BASE}/{wp_id}/closing", headers=headers)).json()
    assert s["completion_text"] == "готово"


@pytest.mark.asyncio
async def test_closing_signature_non_member_4xx(async_client, make_auth_headers, data_factory, sessionmaker):
    """Подпись закрытия от не-члена бригады → 4xx."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    foreman, supervisor, tenant, company = await _make_two_persons_with_permits(data_factory, sessionmaker)
    outsider = await data_factory.create_person(
        first_name="Outsider", last_name="Closing",
        tenant=tenant, company=company,
    )

    wp_id = await _issued_permit(async_client, headers, str(foreman.id), str(supervisor.id))

    r = await async_client.post(
        f"{BASE}/{wp_id}/closing/signatures", headers=headers,
        json={"person_id": str(outsider.id), "mode": "attested"},
    )
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_closing_completion_text_empty_422(async_client, make_auth_headers, data_factory, sessionmaker):
    """Пустой completion_text → 422 (pydantic-валидация)."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    foreman, supervisor, _t, _c = await _make_two_persons_with_permits(data_factory, sessionmaker)
    wp_id = await _issued_permit(async_client, headers, str(foreman.id), str(supervisor.id))

    for bad_text in ("", "   "):
        r = await async_client.post(
            f"{BASE}/{wp_id}/closing", headers=headers,
            json={"completion_text": bad_text},
        )
        assert r.status_code == 422, f"expected 422 for {bad_text!r}, got {r.status_code}: {r.text}"


@pytest.mark.asyncio
async def test_closing_signature_draft_status_409(async_client, make_auth_headers, data_factory, sessionmaker):
    """Подпись закрытия на наряде в статусе draft → 409 (статус-гейт)."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    foreman, supervisor, tenant, company = await _make_two_persons_with_permits(data_factory, sessionmaker)

    # Создаём наряд, добавляем foreman, но НЕ вызываем issue — остаётся draft
    wp_id = await _make_permit(async_client, headers)
    await _add_member(async_client, headers, wp_id, str(foreman.id), "foreman")

    r = await async_client.post(
        f"{BASE}/{wp_id}/closing/signatures", headers=headers,
        json={"person_id": str(foreman.id), "mode": "attested"},
    )
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_closing_tenant_isolation(async_client, make_auth_headers, data_factory, sessionmaker):
    """Наряд тенанта A недоступен для тенанта B."""
    # Tenant A (slug "test")
    headers_a = await make_auth_headers(
        RoleEnum.ADMIN, tenant="test", email="admin-a-closing-iso@example.com"
    )
    foreman_a, supervisor_a, _t, _c = await _make_two_persons_with_permits(data_factory, sessionmaker)
    wp_id = await _issued_permit(async_client, headers_a, str(foreman_a.id), str(supervisor_a.id))

    # Tenant B (slug "acme") пытается открыть closing наряда тенанта A
    headers_b = await make_auth_headers(
        RoleEnum.ADMIN, tenant="acme", email="admin-b-closing-iso@example.com"
    )
    r = await async_client.get(f"{BASE}/{wp_id}/closing", headers=headers_b)
    assert r.status_code == 404, r.text
