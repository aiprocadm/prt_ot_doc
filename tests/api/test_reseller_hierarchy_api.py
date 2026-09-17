"""BIZ-52 срез-1: кто кому может завести арендатора (Доп. №1 разд. 52.1).

До этой волны `POST /tenants` проверял ТОЛЬКО роль, а роль `owner`/`admin` есть
у каждого арендатора — админ любого клиента заводил на платформе новых
арендаторов со своей схемой в базе. Тесты ниже закрепляют границу уровней.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.models.models import RoleEnum, Tenant

BASE = "/api/v1/tenants"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    """Управляющим арендатором делаем `test` — как в тестах флота."""

    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _mark_as_reseller(slug: str) -> str:
    """Сделать посевного арендатора реселлером и вернуть его id."""

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        record = (await session.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one()
        record.kind = RESELLER_KIND
        await session.commit()
        return record.id


async def _tenant_id(slug: str) -> str:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False
    ) as session:
        return (await session.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one().id


def _body(slug: str, **extra: object) -> dict[str, object]:
    return {
        "slug": slug,
        "name": f"Арендатор {slug}",
        "contact_email": f"{slug}@example.com",
        **extra,
    }


@pytest.mark.anyio
async def test_админ_обычного_арендатора_больше_не_создаёт_арендаторов(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="acme", email="admin-acme-biz52@example.com"
    )

    response = await async_client.post(BASE, headers=headers, json=_body("rs-hole-check"))

    assert response.status_code == 403
    assert response.json()["code"] == "TENANT_CREATION_FORBIDDEN"


@pytest.mark.anyio
async def test_владелец_платформы_создаёт_реселлера_корнем(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="test", email="admin-platform-biz52@example.com"
    )

    response = await async_client.post(
        BASE, headers=headers, json=_body("rs-partner-1", kind=RESELLER_KIND)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == RESELLER_KIND
    assert body["parent_id"] is None


@pytest.mark.anyio
async def test_реселлеру_нельзя_дать_родителя(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="test", email="admin-platform-biz52@example.com"
    )
    reseller_id = await _mark_as_reseller("beta")

    response = await async_client.post(
        BASE,
        headers=headers,
        json=_body("rs-partner-nested", kind=RESELLER_KIND, parent_id=reseller_id),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "RESELLER_MUST_BE_ROOT"


@pytest.mark.anyio
async def test_владелец_платформы_отдаёт_клиента_реселлеру(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="test", email="admin-platform-biz52@example.com"
    )
    reseller_id = await _mark_as_reseller("beta")

    response = await async_client.post(
        BASE, headers=headers, json=_body("rs-client-of-partner", parent_id=reseller_id)
    )

    assert response.status_code == 201, response.text
    assert response.json()["parent_id"] == reseller_id


@pytest.mark.anyio
async def test_клиент_родителем_быть_не_может(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="test", email="admin-platform-biz52@example.com"
    )
    plain_client_id = await _tenant_id("gamma")

    response = await async_client.post(
        BASE, headers=headers, json=_body("rs-fourth-level", parent_id=plain_client_id)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "TENANT_PARENT_NOT_RESELLER"


@pytest.mark.anyio
async def test_опечатка_в_родителе_не_создаёт_корневого_арендатора(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Молчаливое «родителя не нашли — значит, под платформу» было бы хуже отказа."""

    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="test", email="admin-platform-biz52@example.com"
    )

    response = await async_client.post(
        BASE, headers=headers, json=_body("rs-typo-parent", parent_id="нет-такого-id")
    )

    assert response.status_code == 400
    assert response.json()["code"] == "TENANT_PARENT_NOT_FOUND"


@pytest.mark.anyio
async def test_реселлер_заводит_клиента_и_тот_ложится_под_него(
    async_client: AsyncClient, make_auth_headers
) -> None:
    reseller_id = await _mark_as_reseller("beta")
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-biz52@example.com"
    )

    response = await async_client.post(BASE, headers=headers, json=_body("rs-own-client"))

    assert response.status_code == 201, response.text
    body = response.json()
    # Родителя не просили — его подставили правила, а не тело запроса.
    assert body["parent_id"] == reseller_id
    assert body["kind"] == "customer"


@pytest.mark.anyio
async def test_реселлер_не_плодит_реселлеров(async_client: AsyncClient, make_auth_headers) -> None:
    await _mark_as_reseller("beta")
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-biz52@example.com"
    )

    response = await async_client.post(
        BASE, headers=headers, json=_body("rs-sub-partner", kind=RESELLER_KIND)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "RESELLER_CANNOT_CREATE_RESELLER"


@pytest.mark.anyio
async def test_реселлер_не_заводит_клиента_в_чужом_контуре(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _mark_as_reseller("beta")
    foreign_reseller_id = await _mark_as_reseller("delta")
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-biz52@example.com"
    )

    response = await async_client.post(
        BASE, headers=headers, json=_body("rs-foreign-client", parent_id=foreign_reseller_id)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "RESELLER_PARENT_MISMATCH"
