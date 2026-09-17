"""BIZ-61 срез-3 — ручки временного доступа в консоли платформы (разд. 61.2)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.models.models import RoleEnum

BASE = "/api/v1/platform/tenants"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _provision(async_client: AsyncClient, headers, slug: str) -> str:
    response = await async_client.post(
        BASE,
        json={
            "slug": slug,
            "name": f"Компания {slug}",
            "owner_email": f"owner@{slug}.ru",
            "owner_password": "OwnerPass123",
            "kind": "customer",
            "demo_data": False,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["tenant"]["id"]


def _feature(item: dict, code: str) -> dict:
    return next(entry for entry in item["features"] if entry["code"] == code)


@pytest.mark.anyio
async def test_grant_shows_up_in_the_fleet_with_its_end_date(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """«Включено» и «включено до 24 августа» — разные ответы клиенту."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant_id = await _provision(async_client, headers, "trialapi")

    granted = await async_client.post(
        f"{BASE}/{tenant_id}/modules/sout/trial", json={"days": 14}, headers=headers
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["trial_until"], "срок не назван — значит его негде показать"

    fleet = await async_client.get(f"{BASE}?limit=200", headers=headers)
    assert fleet.status_code == 200, fleet.text
    item = next(row for row in fleet.json()["items"] if row["tenant"]["id"] == tenant_id)
    sout = _feature(item, "sout")
    assert sout["on"] is True
    assert sout["trial_until"] == granted.json()["trial_until"]


@pytest.mark.anyio
async def test_trial_does_not_relabel_the_plan(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Демонстрация не должна превращать тариф клиента в «свой набор».

    Тариф вычисляется сравнением набора включённых модулей с набором плана.
    Попади пробный доступ в этот набор — клиент с «Бесплатным» перестал бы
    совпадать с любым тарифом, и это увидели бы и менеджер, и счёт.
    """

    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant_id = await _provision(async_client, headers, "trialplan")

    assigned = await async_client.patch(
        f"{BASE}/{tenant_id}/plan", json={"plan": "free"}, headers=headers
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["plan"] == "free"

    await async_client.post(
        f"{BASE}/{tenant_id}/modules/sout/trial", json={"days": 30}, headers=headers
    )

    fleet = await async_client.get(f"{BASE}?limit=200", headers=headers)
    item = next(row for row in fleet.json()["items"] if row["tenant"]["id"] == tenant_id)
    assert item["plan"] == "free", "пробный доступ переименовал тариф"
    assert _feature(item, "sout")["on"] is True, "а доступ-то выдан"


@pytest.mark.anyio
async def test_revoke_closes_access(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant_id = await _provision(async_client, headers, "trialrevoke")

    await async_client.post(
        f"{BASE}/{tenant_id}/modules/sout/trial", json={"days": 7}, headers=headers
    )
    revoked = await async_client.delete(f"{BASE}/{tenant_id}/modules/sout/trial", headers=headers)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["trial_until"] is None

    fleet = await async_client.get(f"{BASE}?limit=200", headers=headers)
    item = next(row for row in fleet.json()["items"] if row["tenant"]["id"] == tenant_id)
    assert _feature(item, "sout")["on"] is False

    # Второй отзыв — честный 404, а не «сделано».
    again = await async_client.delete(f"{BASE}/{tenant_id}/modules/sout/trial", headers=headers)
    assert again.status_code == 404


@pytest.mark.anyio
async def test_bad_requests_are_refused(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant_id = await _provision(async_client, headers, "trialbad")

    absurd = await async_client.post(
        f"{BASE}/{tenant_id}/modules/sout/trial", json={"days": 4000}, headers=headers
    )
    assert absurd.status_code == 422

    core = await async_client.post(
        f"{BASE}/{tenant_id}/modules/documents/trial", json={"days": 7}, headers=headers
    )
    assert core.status_code == 422, "ядро и так включено — «пробный доступ» к нему бессмыслен"

    missing = await async_client.post(
        f"{BASE}/00000000-0000-0000-0000-000000000000/modules/sout/trial",
        json={"days": 7},
        headers=headers,
    )
    assert missing.status_code == 404


@pytest.mark.anyio
async def test_only_the_managing_tenant_may_grant(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе клиент выдаёт себе модули сам — это не «пробный доступ», а дыра."""

    admin_headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant_id = await _provision(async_client, admin_headers, "trialauth")

    anonymous = await async_client.post(f"{BASE}/{tenant_id}/modules/sout/trial", json={"days": 7})
    assert anonymous.status_code >= 400, "выдать модуль удалось без предъявления прав"
    assert anonymous.status_code < 500, anonymous.text
