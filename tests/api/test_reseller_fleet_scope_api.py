"""BIZ-52 срез-2: кабинет партнёра ограничен его поддеревом (разд. 52.1, 52.4).

До этой волны весь флот был доступен ровно одному арендатору — управляющему, а
партнёру не был доступен вовсе. Тесты закрепляют обе новые границы: что партнёр
теперь ВИДИТ своих и что он НЕ видит и не трогает чужих.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.models.models import RoleEnum, Tenant

BASE = "/api/v1/platform/tenants"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _shape_tree() -> dict[str, str]:
    """Собрать дерево: два партнёра, у каждого свой клиент, плюс клиент платформы.

    `acme` → клиент партнёра `beta`; `gamma` → клиент партнёра `delta`;
    `zeta` остаётся прямым клиентом платформы.
    """

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        rows = {
            record.slug: record
            for record in (
                (
                    await session.execute(
                        select(Tenant).where(
                            Tenant.slug.in_(["beta", "delta", "acme", "gamma", "zeta"])
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        rows["beta"].kind = RESELLER_KIND
        rows["delta"].kind = RESELLER_KIND
        rows["acme"].parent_id = rows["beta"].id
        rows["gamma"].parent_id = rows["delta"].id
        rows["zeta"].parent_id = None
        await session.commit()
        return {slug: record.id for slug, record in rows.items()}


async def _partner_headers(make_auth_headers, slug: str = "beta") -> dict[str, str]:
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant=slug, email=f"admin-{slug}-fleet@example.com"
    )


async def _platform_headers(make_auth_headers) -> dict[str, str]:
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant="test", email="admin-platform-fleet@example.com"
    )


@pytest.mark.anyio
async def test_партнёр_видит_только_своих_клиентов(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()

    response = await async_client.get(BASE, headers=await _partner_headers(make_auth_headers))

    assert response.status_code == 200, response.text
    body = response.json()
    slugs = {item["tenant"]["slug"] for item in body["items"]}
    assert slugs == {"acme"}
    assert ids["gamma"] not in {item["tenant"]["id"] for item in body["items"]}


@pytest.mark.anyio
async def test_итог_считается_по_области_а_не_по_всей_таблице(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе над списком из одного клиента стояло бы «всего: 8»."""

    await _shape_tree()

    response = await async_client.get(BASE, headers=await _partner_headers(make_auth_headers))

    assert response.status_code == 200
    assert response.json()["total"] == 1


@pytest.mark.anyio
async def test_владелец_платформы_по_прежнему_видит_всех(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()

    response = await async_client.get(BASE, headers=await _platform_headers(make_auth_headers))

    assert response.status_code == 200
    slugs = {item["tenant"]["slug"] for item in response.json()["items"]}
    assert {"acme", "gamma", "zeta", "beta", "delta"} <= slugs


@pytest.mark.anyio
async def test_обычному_арендатору_кабинет_закрыт(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="acme", email="admin-acme-fleet@example.com"
    )

    response = await async_client.get(BASE, headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FLEET_ACCESS_FORBIDDEN"


@pytest.mark.anyio
async def test_партнёр_приостанавливает_своего_клиента(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['acme']}/status",
        headers=await _partner_headers(make_auth_headers),
        json={"is_active": False},
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False


@pytest.mark.anyio
async def test_чужой_клиент_отвечает_не_найдено_а_не_запрещено(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """403 подтвердил бы, что арендатор с таким id существует."""

    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['gamma']}/status",
        headers=await _partner_headers(make_auth_headers),
        json={"is_active": False},
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_клиент_платформы_партнёру_не_принадлежит(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['zeta']}/status",
        headers=await _partner_headers(make_auth_headers),
        json={"is_active": False},
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_партнёр_не_может_приостановить_сам_себя(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе одним запросом он запер бы собственный кабинет."""

    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['beta']}/status",
        headers=await _partner_headers(make_auth_headers),
        json={"is_active": False},
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_партнёр_не_может_приостановить_соседа(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['delta']}/status",
        headers=await _partner_headers(make_auth_headers),
        json={"is_active": False},
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_тариф_партнёру_закрыт_пока_нет_потолка(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Без «не выдай больше, чем есть у тебя» это раздача за чужой счёт."""

    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['acme']}/plan",
        headers=await _partner_headers(make_auth_headers),
        json={"plan": "pro"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FLEET_COMMERCIALS_PLATFORM_ONLY"


@pytest.mark.anyio
async def test_квоты_партнёру_тоже_закрыты(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['acme']}/quotas",
        headers=await _partner_headers(make_auth_headers),
        json={"max_storage_mb": 999999},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FLEET_COMMERCIALS_PLATFORM_ONLY"


@pytest.mark.anyio
async def test_пробный_доступ_партнёру_закрыт(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()

    response = await async_client.post(
        f"{BASE}/{ids['acme']}/modules/sout/trial",
        headers=await _partner_headers(make_auth_headers),
        json={"days": 14},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FLEET_COMMERCIALS_PLATFORM_ONLY"


@pytest.mark.anyio
async def test_права_проверяются_раньше_области(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Партнёр не должен по коду ответа отличать «чужой клиент» от «нет такого».

    На коммерческой ручке отказ обязан быть 403 «нельзя» ещё до поиска
    арендатора: иначе перебором id партнёр вычислил бы чужой контур по разнице
    между 403 и 404.
    """

    await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/несуществующий-id/plan",
        headers=await _partner_headers(make_auth_headers),
        json={"plan": "pro"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FLEET_COMMERCIALS_PLATFORM_ONLY"


@pytest.mark.anyio
async def test_справочник_тарифов_открыт_партнёру(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Без названий тарифов кабинет показывал бы пустую колонку."""

    await _shape_tree()

    response = await async_client.get(
        f"{BASE}/plans", headers=await _partner_headers(make_auth_headers)
    )

    assert response.status_code == 200
    assert response.json()["plans"]


@pytest.mark.anyio
async def test_партнёр_заводит_клиента_под_себя(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()

    response = await async_client.post(
        BASE,
        headers=await _partner_headers(make_auth_headers),
        json={
            "slug": "rs2-own-client",
            "name": "Клиент партнёра",
            "owner_email": "owner@rs2.example.com",
            "owner_password": "Secret123!",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["tenant"]["parent_id"] == ids["beta"]


@pytest.mark.anyio
async def test_партнёр_не_заводит_партнёра(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()

    response = await async_client.post(
        BASE,
        headers=await _partner_headers(make_auth_headers),
        json={
            "slug": "rs2-sub-partner",
            "name": "Суб-партнёр",
            "owner_email": "owner@rs2sub.example.com",
            "owner_password": "Secret123!",
            "kind": RESELLER_KIND,
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "RESELLER_CANNOT_CREATE_RESELLER"
