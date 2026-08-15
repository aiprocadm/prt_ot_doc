"""BIZ-52 срез-15: партнёр видит свои лимиты и свой расход (разд. 52.4).

Партнёр не входит в собственную область (решение среза-2), поэтому в списке
клиентов и в отчёте о расходе его нет. Свои квоты он не видел вовсе — здесь
закрепляется, что теперь видит, и что чужие лимиты через эту ручку не достать.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.models.models import RoleEnum, Tenant, TenantQuota
from app.models.tenant_billing import BillingUsageCounter, TenantCounter

BASE = "/api/v1/platform/tenants"
PERIOD = "202608"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _shape_tree() -> dict[str, str]:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        rows = {
            record.slug: record
            for record in (
                (await session.execute(select(Tenant).where(Tenant.slug.in_(["beta", "acme"]))))
                .scalars()
                .all()
            )
        }
        rows["beta"].kind = RESELLER_KIND
        rows["acme"].parent_id = rows["beta"].id
        await session.commit()
        return {slug: record.id for slug, record in rows.items()}


async def _set_quota(tenant_id: str, **values) -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        quota = (
            await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant_id))
        ).scalar_one_or_none()
        if quota is None:
            quota = TenantQuota(tenant_id=tenant_id)
            session.add(quota)
        for key, value in values.items():
            setattr(quota, key, value)
        await session.commit()


async def _set_usage(tenant_id: str, *, generations: int = 0, storage: int = 0) -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        session.add(
            TenantCounter(tenant_id=tenant_id, yyyymm=PERIOD, doc_generations=generations)
        )
        session.add(
            BillingUsageCounter(
                tenant_id=tenant_id, period_yyyymm=int(PERIOD), s3_bytes_used=storage
            )
        )
        await session.commit()


async def _partner_headers(make_auth_headers):
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-limits@example.com"
    )


@pytest.mark.anyio
async def test_партнёр_видит_свои_лимиты_и_расход(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    await _set_quota(ids["beta"], max_doc_generations_per_month=100, max_storage_mb=10)
    await _set_usage(ids["beta"], generations=80, storage=5 * 1024 * 1024)

    response = await async_client.get(
        f"{BASE}/me/limits",
        params={"period": PERIOD},
        headers=await _partner_headers(make_auth_headers),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tenant_slug"] == "beta"
    docs = next(item for item in body["items"] if item["code"] == "doc_generations")
    assert docs["limit"] == 100
    assert docs["used"] == 80
    assert docs["remaining"] == 20


@pytest.mark.anyio
async def test_расход_чужого_клиента_сюда_не_попадает(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Ручка про СВОЙ арендатор: расход клиента не должен подмешиваться."""

    ids = await _shape_tree()
    await _set_quota(ids["beta"], max_doc_generations_per_month=100)
    await _set_usage(ids["acme"], generations=999)

    body = (
        await async_client.get(
            f"{BASE}/me/limits",
            params={"period": PERIOD},
            headers=await _partner_headers(make_auth_headers),
        )
    ).json()

    docs = next(item for item in body["items"] if item["code"] == "doc_generations")
    assert docs["used"] == 0


@pytest.mark.anyio
async def test_несчитаемый_расход_приходит_пустым_а_не_нулём(
    async_client: AsyncClient, make_auth_headers
) -> None:
    # Ноль читался бы как «ЭДО не пользуются», а правда — «мы это не считаем».
    ids = await _shape_tree()
    await _set_quota(ids["beta"], monthly_edo_outgoing=50)

    body = (
        await async_client.get(
            f"{BASE}/me/limits",
            params={"period": PERIOD},
            headers=await _partner_headers(make_auth_headers),
        )
    ).json()

    edo = next(item for item in body["items"] if item["code"] == "edo_outgoing")
    assert edo["limit"] == 50
    assert edo["used"] is None


@pytest.mark.anyio
async def test_исчерпанный_предел_виден_признаком(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    await _set_quota(ids["beta"], max_doc_generations_per_month=10)
    await _set_usage(ids["beta"], generations=10)

    body = (
        await async_client.get(
            f"{BASE}/me/limits",
            params={"period": PERIOD},
            headers=await _partner_headers(make_auth_headers),
        )
    ).json()

    docs = next(item for item in body["items"] if item["code"] == "doc_generations")
    assert docs["exhausted"] is True
    assert docs["remaining"] == 0


@pytest.mark.anyio
async def test_владелец_платформы_тоже_видит_свои_лимиты(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Кабинет один; у владельца платформы квоты тоже есть."""

    await _shape_tree()

    response = await async_client.get(
        f"{BASE}/me/limits", headers=await make_auth_headers(RoleEnum.ADMIN)
    )

    assert response.status_code == 200, response.text
    assert response.json()["tenant_slug"] == "test"


@pytest.mark.anyio
async def test_клиенту_кабинет_лимитов_закрыт(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Та же граница, что у остального кабинета флота: клиент сюда не ходит."""

    await _shape_tree()
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="acme", email="admin-acme-limits@example.com"
    )

    response = await async_client.get(f"{BASE}/me/limits", headers=headers)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_путь_me_не_принимается_за_идентификатор(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """`/{tenant_id}` объявлен ниже: иначе `me` уехал бы в него как id."""

    await _shape_tree()

    response = await async_client.get(
        f"{BASE}/me/limits", headers=await _partner_headers(make_auth_headers)
    )

    assert response.status_code == 200
    assert "items" in response.json()
