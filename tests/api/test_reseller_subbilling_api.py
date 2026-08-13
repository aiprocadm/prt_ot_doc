"""BIZ-52 срез-8: суб-биллинг по HTTP (разд. 52.4).

Закрепляется главное: партнёр ТЕПЕРЬ тарифицирует своих клиентов (ограничение
среза-2 снято), но не выше своего набора модулей; расход он видит только по
своим клиентам.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.models.models import RoleEnum, Tenant
from app.models.tenant_billing import TenantCounter
from app.modules.subscription import PLANS

BASE = "/api/v1/platform/tenants"


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
        RoleEnum.ADMIN, tenant=slug, email=f"admin-{slug}-billing@example.com"
    )


async def _platform_headers(make_auth_headers) -> dict[str, str]:
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant="test", email="admin-platform-billing@example.com"
    )


def _plan_with_features() -> str:
    """Код тарифа, у которого есть хотя бы один модуль."""

    for code, plan in PLANS.items():
        if plan.features:
            return code
    raise AssertionError("в каталоге нет тарифа с модулями — тест бессмыслен")


def _plan_without_features() -> str | None:
    for code, plan in PLANS.items():
        if not plan.features:
            return code
    return None


async def _write_usage(tenant_id: str, period: str, value: int) -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        session.add(
            TenantCounter(tenant_id=tenant_id, yyyymm=period, doc_generations=value)
        )
        await session.commit()


@pytest.mark.anyio
async def test_партнёр_без_набора_не_выдаёт_тариф_с_модулями(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Ограничение среза-2 сменилось потолком: отказ теперь по СОДЕРЖАНИЮ."""

    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['acme']}/plan",
        headers=await _partner_headers(make_auth_headers),
        json={"plan": _plan_with_features()},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "RESELLER_PLAN_EXCEEDS_OWN"
    # В сообщении названы конкретные модули, а не «нельзя».
    assert body["message"]


@pytest.mark.anyio
async def test_партнёр_выдаёт_тариф_в_пределах_своего_набора(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    plan_code = _plan_with_features()
    # Владелец платформы выдаёт партнёру тот же тариф — теперь набор есть.
    granted = await async_client.patch(
        f"{BASE}/{ids['beta']}/plan",
        headers=await _platform_headers(make_auth_headers),
        json={"plan": plan_code},
    )
    assert granted.status_code == 200, granted.text

    response = await async_client.patch(
        f"{BASE}/{ids['acme']}/plan",
        headers=await _partner_headers(make_auth_headers),
        json={"plan": plan_code},
    )

    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_партнёр_без_своего_тарифа_не_выдаёт_даже_бесплатный(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Следствие потолка, которое важно знать: даже «Бесплатный» несёт модули.

    Значит, партнёр обязан сперва САМ получить тариф от владельца платформы —
    перепродать можно только то, что купил. Отказ называет недостающие модули,
    поэтому причина видна сразу, а не выглядит поломкой.
    """

    assert _plan_without_features() is None, (
        "в каталоге появился тариф без модулей — правило «партнёр без тарифа "
        "ничего не выдаёт» перестало действовать, перепроверьте срез"
    )
    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['acme']}/plan",
        headers=await _partner_headers(make_auth_headers),
        json={"plan": "free"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "RESELLER_PLAN_EXCEEDS_OWN"


@pytest.mark.anyio
async def test_владельцу_платформы_потолок_не_мешает(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Он источник модулей: собственный набор его не ограничивает."""

    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['acme']}/plan",
        headers=await _platform_headers(make_auth_headers),
        json={"plan": _plan_with_features()},
    )

    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_чужой_клиент_по_прежнему_не_найден(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Потолок не должен подменить проверку области: чужой — 404, а не 403."""

    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['gamma']}/plan",
        headers=await _partner_headers(make_auth_headers),
        json={"plan": _plan_with_features()},
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_квоты_остались_за_владельцем_платформы(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Потолок по квотам — продуктовое решение владельца, срез его не выдумывает."""

    ids = await _shape_tree()

    response = await async_client.patch(
        f"{BASE}/{ids['acme']}/quotas",
        headers=await _partner_headers(make_auth_headers),
        json={"max_storage_mb": 999999},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FLEET_COMMERCIALS_PLATFORM_ONLY"


@pytest.mark.anyio
async def test_расход_партнёра_только_по_своим_клиентам(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    await _write_usage(ids["acme"], "202608", 10)
    await _write_usage(ids["gamma"], "202608", 99)

    response = await async_client.get(
        f"{BASE}/usage",
        headers=await _partner_headers(make_auth_headers),
        params={"period": "202608"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    slugs = {row["slug"] for row in body["items"]}
    assert slugs == {"acme"}
    # Итог считается по тем же строкам: чужой оборот в него не попадает.
    assert body["total_doc_generations"] == 10


@pytest.mark.anyio
async def test_владелец_платформы_видит_расход_всех(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    await _write_usage(ids["acme"], "202608", 10)
    await _write_usage(ids["gamma"], "202608", 99)

    response = await async_client.get(
        f"{BASE}/usage",
        headers=await _platform_headers(make_auth_headers),
        params={"period": "202608"},
    )

    body = response.json()
    assert {"acme", "gamma"} <= {row["slug"] for row in body["items"]}
    assert body["total_doc_generations"] >= 109


@pytest.mark.anyio
async def test_нулевой_расход_в_список_не_попадает(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Ноль в списке не отличим от «данных нет» — на вопрос отвечает итог."""

    ids = await _shape_tree()
    await _write_usage(ids["acme"], "202608", 0)

    response = await async_client.get(
        f"{BASE}/usage",
        headers=await _partner_headers(make_auth_headers),
        params={"period": "202608"},
    )

    assert response.json()["items"] == []


@pytest.mark.anyio
async def test_расход_обычному_арендатору_закрыт(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="acme", email="admin-acme-billing@example.com"
    )

    response = await async_client.get(f"{BASE}/usage", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FLEET_ACCESS_FORBIDDEN"


@pytest.mark.anyio
async def test_кривой_период_отвергается(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()

    response = await async_client.get(
        f"{BASE}/usage",
        headers=await _partner_headers(make_auth_headers),
        params={"period": "2026-08"},
    )

    assert response.status_code == 422
