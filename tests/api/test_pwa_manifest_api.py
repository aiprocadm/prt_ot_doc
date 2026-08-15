"""BIZ-52 срез-14: манифест PWA по HTTP (разд. 52.2).

Главное здесь: манифест браузер грузит САМ, без заголовков приложения. Поэтому
арендатор берётся из адреса, а ответ обязан остаться валидным манифестом даже
на мусорном слаге — иначе браузер ругается на весь ярлык, а не на одно поле.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.models.models import RoleEnum, Tenant

MANIFEST = "/api/v1/public/manifest.webmanifest"
OWN_BRAND = "/api/v1/platform/branding"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _shape_tree() -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        rows = {
            record.slug: record
            for record in (
                (
                    await session.execute(select(Tenant).where(Tenant.slug.in_(["beta", "acme"])))
                )
                .scalars()
                .all()
            )
        }
        rows["beta"].kind = RESELLER_KIND
        rows["acme"].parent_id = rows["beta"].id
        await session.commit()


async def _publish_brand(async_client, make_auth_headers, name: str = "Охрана труда Партнёр"):
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-manifest@example.com"
    )
    return await async_client.put(
        OWN_BRAND,
        headers=headers,
        json={"app_name": name, "primary_color": "10 80% 50%", "support_email": None},
    )


@pytest.mark.anyio
async def test_манифест_отдаётся_без_токена(async_client: AsyncClient) -> None:
    """Браузер грузит манифест до всякого входа."""

    await _shape_tree()

    response = await async_client.get(MANIFEST, headers={"x-tenant": "acme"})

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/manifest+json")


@pytest.mark.anyio
async def test_арендатор_берётся_из_адреса(
    async_client: AsyncClient, make_auth_headers
) -> None:
    # Заголовок арендатора в такой запрос не поставить — браузер шлёт его сам.
    await _shape_tree()
    await _publish_brand(async_client, make_auth_headers)

    response = await async_client.get(MANIFEST, params={"tenant": "acme"})

    assert response.json()["name"] == "Охрана труда Партнёр"


@pytest.mark.anyio
async def test_клиент_партнёра_получает_имя_партнёра(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Ярлык на телефоне — самое заметное место, где 52.2 требует подмены."""

    await _shape_tree()
    await _publish_brand(async_client, make_auth_headers)

    body = (await async_client.get(MANIFEST, params={"tenant": "acme"})).json()

    assert body["name"] == "Охрана труда Партнёр"
    assert "PRT" not in body["name"]
    assert body["short_name"] == "Охрана"


@pytest.mark.anyio
async def test_цвет_темы_из_бренда(async_client: AsyncClient, make_auth_headers) -> None:
    await _shape_tree()
    await _publish_brand(async_client, make_auth_headers)

    body = (await async_client.get(MANIFEST, params={"tenant": "acme"})).json()

    # `10 80% 50%` — это #e63d0f; браузеру нужен именно HEX.
    assert body["theme_color"].startswith("#")
    assert body["theme_color"] != "#0f172a"


@pytest.mark.anyio
async def test_мусорный_слаг_даёт_валидный_манифест(async_client: AsyncClient) -> None:
    """404 или пустой ответ браузер ругает целиком, а не по одному полю."""

    await _shape_tree()

    response = await async_client.get(
        MANIFEST, params={"tenant": "нет-такого"}, headers={"x-tenant": "acme"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"]
    assert body["icons"]


@pytest.mark.anyio
async def test_без_слага_работает_прежний_способ(async_client: AsyncClient) -> None:
    """Заголовок арендатора остаётся рабочим: срез ничего не ломает."""

    await _shape_tree()

    response = await async_client.get(MANIFEST, headers={"x-tenant": "acme"})

    assert response.status_code == 200
    assert response.json()["start_url"] == "/"


@pytest.mark.anyio
async def test_логотип_отдаётся_по_слагу_из_адреса(async_client: AsyncClient) -> None:
    """Иконка манифеста тоже грузится браузером без заголовков.

    Ручка обязана понимать слаг из адреса, иначе иконка в ярлыке не появится.
    """

    await _shape_tree()

    response = await async_client.get(
        "/api/v1/public/branding/logo", params={"tenant": "acme"}
    )

    # Логотип не загружен — 404 это нормально; важно, что запрос БЕЗ заголовка
    # арендатора дошёл до обработчика, а не упал на резолвере.
    assert response.status_code in (200, 404)
