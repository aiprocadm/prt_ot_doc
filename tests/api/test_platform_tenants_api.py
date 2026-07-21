"""HTTP contract for the managing-tenant fleet API (/platform/tenants).

The privilege boundary is the point of these tests: exactly one tenant may provision and
suspend the others, and a provisioned tenant must come out usable (owner can log in).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.models import RoleEnum, Tenant

BASE = "/api/v1/platform/tenants"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    """Make the default test tenant ("test") the managing tenant."""

    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _fetch_tenant(slug: str) -> Tenant | None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False
    ) as session:
        return (
            await session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()


@pytest.mark.anyio
async def test_list_requires_authentication(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    anonymous = {"x-tenant": headers["x-tenant"]}

    response = await async_client.get(BASE, headers=anonymous)

    assert response.status_code == 401


@pytest.mark.anyio
async def test_list_rejects_non_admin_role(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get(BASE, headers=headers)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_managing_admin_lists_every_tenant(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="othertenant", session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get(BASE, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["managing_tenant_slug"] == "test"
    slugs = {item["tenant"]["slug"] for item in body["items"]}
    # The whole point of the endpoint: foreign tenants are visible here and nowhere else.
    assert {"test", "othertenant"} <= slugs


@pytest.mark.anyio
async def test_non_managing_tenant_admin_is_forbidden(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="outsider", session=session)
        await session.commit()
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="outsider", email="admin-outsider@example.com"
    )

    response = await async_client.get(BASE, headers=headers)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_provision_creates_usable_tenant_with_owner_login(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = {
        "slug": "newco",
        "name": "ООО Ньюко",
        "owner_email": "owner@newco.ru",
        "owner_password": "OwnerPass123",
        "kind": "customer",
        "demo_data": False,
    }

    response = await async_client.post(BASE, json=payload, headers=headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["tenant"]["slug"] == "newco"
    assert body["tenant"]["is_active"] is True
    assert "owner_user" in body["created"]

    created = await _fetch_tenant("newco")
    assert created is not None

    # A tenant nobody can sign into would be a useless tenant — prove the owner can.
    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "owner@newco.ru", "password": "OwnerPass123"},
        headers={"x-tenant": str(created.id)},
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


@pytest.mark.anyio
async def test_provision_rejects_duplicate_slug(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = {
        "slug": "duplicate",
        "name": "Первый",
        "owner_email": "first@example.com",
        "owner_password": "OwnerPass123",
        "kind": "customer",
        "demo_data": False,
    }
    first = await async_client.post(BASE, json=payload, headers=headers)
    assert first.status_code == 201, first.text

    second = await async_client.post(BASE, json=payload, headers=headers)

    assert second.status_code == 409


@pytest.mark.anyio
@pytest.mark.parametrize(
    "slug",
    ["Acme", "9acme", "a", "acme space", "acme;drop", "tenant_" + "x" * 40],
)
async def test_provision_rejects_unsafe_slug(
    async_client: AsyncClient, make_auth_headers, slug: str
) -> None:
    """The slug becomes a DB schema name, so the alphabet is locked down."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = {
        "slug": slug,
        "name": "Тест",
        "owner_email": "owner@example.com",
        "owner_password": "OwnerPass123",
        "kind": "customer",
        "demo_data": False,
    }

    response = await async_client.post(BASE, json=payload, headers=headers)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_provision_rejects_short_owner_password(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = {
        "slug": "weakpass",
        "name": "Тест",
        "owner_email": "owner@example.com",
        "owner_password": "short",
        "kind": "customer",
        "demo_data": False,
    }

    response = await async_client.post(BASE, json=payload, headers=headers)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_suspend_and_restore_tenant_access(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    async with sessionmaker() as session:
        target = await data_factory.ensure_tenant(slug="suspendme", session=session)
        await session.commit()
        target_id = target.id
    headers = await make_auth_headers(RoleEnum.ADMIN)

    suspended = await async_client.patch(
        f"{BASE}/{target_id}/status", json={"is_active": False}, headers=headers
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["is_active"] is False

    restored = await async_client.patch(
        f"{BASE}/{target_id}/status", json={"is_active": True}, headers=headers
    )
    assert restored.status_code == 200
    assert restored.json()["is_active"] is True


@pytest.mark.anyio
async def test_managing_tenant_cannot_suspend_itself(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Suspending the managing tenant would lock everyone out of fleet management."""

    managing = await _fetch_tenant("test")
    assert managing is not None
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.patch(
        f"{BASE}/{managing.id}/status", json={"is_active": False}, headers=headers
    )

    assert response.status_code == 409


@pytest.mark.anyio
async def test_status_patch_returns_404_for_unknown_tenant(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.patch(
        f"{BASE}/does-not-exist/status", json={"is_active": False}, headers=headers
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_quota_patch_updates_subscription_limits(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    provision = await async_client.post(
        BASE,
        json={
            "slug": "quotatenant",
            "name": "Квоты",
            "owner_email": "owner@quota.ru",
            "owner_password": "OwnerPass123",
            "kind": "customer",
            "demo_data": False,
        },
        headers=headers,
    )
    assert provision.status_code == 201, provision.text
    tenant_id = provision.json()["tenant"]["id"]

    response = await async_client.patch(
        f"{BASE}/{tenant_id}/quotas",
        json={"max_storage_mb": 777, "enforce_billing_gate": True},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["max_storage_mb"] == 777
    assert body["enforce_billing_gate"] is True
