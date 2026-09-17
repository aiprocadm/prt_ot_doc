"""BIZ-52 срез-4: бренд приложения по HTTP (разд. 52.2).

Закрепляется главное: бренд отдаётся БЕЗ токена (иначе экран входа успел бы
показать вендора), клиент партнёра получает бренд партнёра, а править чужой
бренд нельзя.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.domains.reseller.white_label import DEFAULT_APP_NAME
from app.models.models import RoleEnum, Tenant

PUBLIC = "/api/v1/public/branding"
OWN = "/api/v1/platform/branding"


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
                (
                    await session.execute(
                        select(Tenant).where(Tenant.slug.in_(["beta", "acme", "zeta"]))
                    )
                )
                .scalars()
                .all()
            )
        }
        rows["beta"].kind = RESELLER_KIND
        rows["acme"].parent_id = rows["beta"].id
        rows["zeta"].parent_id = None
        await session.commit()
        return {slug: record.id for slug, record in rows.items()}


async def _partner_headers(make_auth_headers) -> dict[str, str]:
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-brand@example.com"
    )


@pytest.mark.anyio
async def test_бренд_отдаётся_без_токена(async_client: AsyncClient, make_auth_headers) -> None:
    """Экран входа обязан быть уже в бренде — токена там ещё нет."""

    await _shape_tree()

    response = await async_client.get(PUBLIC, headers={"x-tenant": "acme"})

    assert response.status_code == 200, response.text
    assert response.json()["app_name"]


@pytest.mark.anyio
async def test_без_настроек_действует_бренд_платформы(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()

    response = await async_client.get(PUBLIC, headers={"x-tenant": "zeta"})

    body = response.json()
    assert body["app_name"] == DEFAULT_APP_NAME
    assert body["source"] == "platform"


@pytest.mark.anyio
async def test_клиент_партнёра_видит_бренд_партнёра(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    saved = await async_client.put(
        OWN,
        headers=await _partner_headers(make_auth_headers),
        json={"app_name": "Охрана труда «Партнёр»", "primary_color": "210 90% 40%"},
    )
    assert saved.status_code == 200, saved.text

    response = await async_client.get(PUBLIC, headers={"x-tenant": "acme"})

    body = response.json()
    assert body["app_name"] == "Охрана труда «Партнёр»"
    assert body["primary_color"] == "210 90% 40%"
    assert body["source"] == "reseller"


@pytest.mark.anyio
async def test_соседний_арендатор_бренд_партнёра_не_получает(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """`zeta` — прямой клиент платформы, партнёрский бренд его не касается."""

    await _shape_tree()
    await async_client.put(
        OWN,
        headers=await _partner_headers(make_auth_headers),
        json={"app_name": "Охрана труда «Партнёр»"},
    )

    response = await async_client.get(PUBLIC, headers={"x-tenant": "zeta"})

    assert response.json()["app_name"] == DEFAULT_APP_NAME


@pytest.mark.anyio
async def test_очистка_поля_возвращает_наследование(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Пустое имя — это «не задано», а не «приложение без названия»."""

    await _shape_tree()
    headers = await _partner_headers(make_auth_headers)
    await async_client.put(OWN, headers=headers, json={"app_name": "Временное"})

    await async_client.put(OWN, headers=headers, json={"app_name": None})
    response = await async_client.get(PUBLIC, headers={"x-tenant": "acme"})

    assert response.json()["app_name"] == DEFAULT_APP_NAME


@pytest.mark.anyio
async def test_повторная_правка_не_плодит_строк(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Вторая строка сделала бы ответ ручки неопределённым (грабля BIZ-61)."""

    ids = await _shape_tree()
    headers = await _partner_headers(make_auth_headers)
    await async_client.put(OWN, headers=headers, json={"app_name": "Раз"})
    await async_client.put(OWN, headers=headers, json={"app_name": "Два"})

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        from app.models.white_label import TenantBranding

        rows = (
            (
                await session.execute(
                    select(TenantBranding).where(TenantBranding.tenant_id == ids["beta"])
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].app_name == "Два"


@pytest.mark.anyio
async def test_обычный_арендатор_бренд_не_правит(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="acme", email="admin-acme-brand@example.com"
    )

    response = await async_client.put(OWN, headers=headers, json={"app_name": "Чужое"})

    assert response.status_code == 403
    assert response.json()["code"] == "FLEET_ACCESS_FORBIDDEN"


@pytest.mark.anyio
async def test_правка_без_токена_отклоняется(async_client: AsyncClient, make_auth_headers) -> None:
    """Публично только ЧТЕНИЕ бренда."""

    await _shape_tree()

    response = await async_client.put(
        OWN, headers={"x-tenant": "beta"}, json={"app_name": "Аноним"}
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_цвет_проверяется_по_формату(async_client: AsyncClient, make_auth_headers) -> None:
    """Формат тот же, что у CSS-переменной: иначе тема молча не применится."""

    await _shape_tree()

    response = await async_client.put(
        OWN,
        headers=await _partner_headers(make_auth_headers),
        json={"primary_color": "#ff0000"},
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_своя_настройка_показывает_и_унаследованное(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """По одной своей настройке нельзя понять, что увидит пользователь."""

    await _shape_tree()
    headers = await _partner_headers(make_auth_headers)
    await async_client.put(OWN, headers=headers, json={"app_name": "Партнёр"})

    response = await async_client.get(OWN, headers=headers)

    body = response.json()
    assert body["app_name"] == "Партнёр"
    assert body["primary_color"] is None
    # Цвет не задан — в действующем бренде он платформенный, а не пустой.
    assert body["effective"]["primary_color"]
    assert body["effective"]["source"] == "self"
