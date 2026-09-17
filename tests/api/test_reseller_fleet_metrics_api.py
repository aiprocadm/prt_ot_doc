"""BIZ-52 срез-13: кабинет партнёра показывает расход целиком (разд. 52.4).

Срез-8 дал одну метрику — генерации документов. ТЗ просит остальные: ЭДО,
хранилище, активные сотрудники. Здесь закрепляется, что показывается ровно то,
что СОБИРАЕТСЯ, а несобираемое названо вслух, а не показано нулём.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.models.models import RoleEnum, Tenant
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
                (
                    await session.execute(
                        select(Tenant).where(Tenant.slug.in_(["beta", "acme", "gamma"]))
                    )
                )
                .scalars()
                .all()
            )
        }
        rows["beta"].kind = RESELLER_KIND
        rows["acme"].parent_id = rows["beta"].id
        rows["gamma"].parent_id = None
        await session.commit()
        return {slug: record.id for slug, record in rows.items()}


async def _seed_generations(tenant_id: str, value: int, period: str = PERIOD) -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        session.add(TenantCounter(tenant_id=tenant_id, yyyymm=period, doc_generations=value))
        await session.commit()


async def _seed_billing_usage(
    tenant_id: str, *, storage: int = 0, workers: int = 0, period: str = PERIOD
) -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        session.add(
            BillingUsageCounter(
                tenant_id=tenant_id,
                period_yyyymm=int(period),
                s3_bytes_used=storage,
                active_workers=workers,
            )
        )
        await session.commit()


async def _partner_headers(make_auth_headers):
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-metrics@example.com"
    )


@pytest.mark.anyio
async def test_хранилище_и_сотрудники_видны_в_кабинете(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    await _seed_billing_usage(ids["acme"], storage=1_500_000, workers=42)

    response = await async_client.get(
        f"{BASE}/usage",
        params={"period": PERIOD},
        headers=await _partner_headers(make_auth_headers),
    )

    assert response.status_code == 200, response.text
    row = next(item for item in response.json()["items"] if item["slug"] == "acme")
    assert row["storage_bytes"] == 1_500_000
    assert row["active_workers"] == 42


@pytest.mark.anyio
async def test_клиент_без_генераций_но_с_данными_попадает_в_отчёт(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Правило «нулевой расход не показываем» было верным для ОДНОЙ метрики.

    Клиент, не сгенерировавший ни документа, но с полусотней сотрудников и
    гигабайтом файлов, услугу расходует — и партнёр обязан его видеть.
    """

    ids = await _shape_tree()
    await _seed_billing_usage(ids["acme"], storage=1_000_000, workers=50)

    response = await async_client.get(
        f"{BASE}/usage",
        params={"period": PERIOD},
        headers=await _partner_headers(make_auth_headers),
    )

    slugs = [item["slug"] for item in response.json()["items"]]
    assert "acme" in slugs


@pytest.mark.anyio
async def test_совсем_пустой_клиент_в_отчёт_не_попадает(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Ноль по ВСЕМ метрикам — шум в отчёте о расходе."""

    await _shape_tree()

    response = await async_client.get(
        f"{BASE}/usage",
        params={"period": PERIOD},
        headers=await _partner_headers(make_auth_headers),
    )

    assert response.json()["items"] == []


@pytest.mark.anyio
async def test_генерации_считаются_как_прежде(async_client: AsyncClient, make_auth_headers) -> None:
    """Источник генераций менять нельзя: числа не должны поменяться у партнёра."""

    ids = await _shape_tree()
    await _seed_generations(ids["acme"], 7)

    response = await async_client.get(
        f"{BASE}/usage",
        params={"period": PERIOD},
        headers=await _partner_headers(make_auth_headers),
    )

    row = next(item for item in response.json()["items"] if item["slug"] == "acme")
    assert row["doc_generations"] == 7


@pytest.mark.anyio
async def test_итоги_считаются_по_тем_же_строкам(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    await _seed_generations(ids["acme"], 3)
    await _seed_billing_usage(ids["acme"], storage=2_000, workers=5)
    # Чужой клиент: в итог партнёра попасть не должен.
    await _seed_billing_usage(ids["gamma"], storage=9_000_000, workers=99)

    body = (
        await async_client.get(
            f"{BASE}/usage",
            params={"period": PERIOD},
            headers=await _partner_headers(make_auth_headers),
        )
    ).json()

    assert body["total_doc_generations"] == 3
    assert body["total_storage_bytes"] == 2_000
    assert body["total_active_workers"] == 5


@pytest.mark.anyio
async def test_несобираемые_метрики_названы_а_не_показаны_нулём(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Счётчик ЭДО не увеличивает никто: провайдер отправки не реализован.

    Ноль в кабинете читался бы как «клиент не пользуется ЭДО» — это неправда.
    """

    await _shape_tree()

    body = (
        await async_client.get(
            f"{BASE}/usage",
            params={"period": PERIOD},
            headers=await _partner_headers(make_auth_headers),
        )
    ).json()

    assert any("ЭДО" in item for item in body["not_measured"])
    assert any("API" in item for item in body["not_measured"])


@pytest.mark.anyio
async def test_партнёр_не_видит_расход_чужого_клиента(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Область та же, что у списка: новые метрики её не расширяют."""

    ids = await _shape_tree()
    await _seed_billing_usage(ids["gamma"], storage=5_000_000, workers=77)

    body = (
        await async_client.get(
            f"{BASE}/usage",
            params={"period": PERIOD},
            headers=await _partner_headers(make_auth_headers),
        )
    ).json()

    assert [item["slug"] for item in body["items"]] == []
    assert body["total_storage_bytes"] == 0
