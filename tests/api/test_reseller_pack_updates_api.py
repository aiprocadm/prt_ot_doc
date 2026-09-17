"""BIZ-52 срез-17: приём обновлений эталона по HTTP (разд. 52.3).

Закрепляется главное: клиенту предлагаются только ДОБАВЛЕНИЯ новой редакции,
удалённое им не воскресает, а после приёма то же обновление не предлагается
второй раз.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.models.models import RoleEnum, Tenant
from app.models.safety_core import Hazard
from app.services.tenants.bootstrap.service import STARTER_PACK_ROOT

BASE = "/api/v1/platform/tenants"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


def _current_pack() -> dict:
    return json.loads((STARTER_PACK_ROOT / "v1" / "default.json").read_text(encoding="utf-8"))


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


async def _set_applied_pack(tenant_id: str, payload: dict | None) -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        row = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        settings = dict(row.settings or {})
        if payload is None:
            settings.pop("starter_pack", None)
        else:
            settings["starter_pack"] = payload
        row.settings = settings
        await session.commit()


async def _hazards_of(tenant_id: str) -> list[str]:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        return list(
            (
                await session.execute(select(Hazard.name).where(Hazard.tenant_id == tenant_id))
            ).scalars()
        )


async def _partner_headers(make_auth_headers):
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-packs@example.com"
    )


def _stale_pack() -> dict:
    """Слепок «старой редакции»: та же основа, но без части опасностей."""

    applied = json.loads(json.dumps(_current_pack()))
    applied["revision"] = 1
    applied["reference_data"]["hazards"] = applied["reference_data"]["hazards"][:1]
    return applied


@pytest.mark.anyio
async def test_показывает_чего_не_хватает(async_client: AsyncClient, make_auth_headers) -> None:
    ids = await _shape_tree()
    await _set_applied_pack(ids["acme"], _stale_pack())

    response = await async_client.get(
        f"{BASE}/{ids['acme']}/pack-update", headers=await _partner_headers(make_auth_headers)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["additions"]["hazards"]
    assert body["applied_unknown"] is False


@pytest.mark.anyio
async def test_приём_создаёт_только_новые_строки(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    await _set_applied_pack(ids["acme"], _stale_pack())
    headers = await _partner_headers(make_auth_headers)

    response = await async_client.post(f"{BASE}/{ids['acme']}/pack-update", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["applied"] is True
    names = await _hazards_of(ids["acme"])
    assert "Электротравма" in names


@pytest.mark.anyio
async def test_после_приёма_то_же_не_предлагается(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе кнопка «принять» никогда не гасла бы."""

    ids = await _shape_tree()
    await _set_applied_pack(ids["acme"], _stale_pack())
    headers = await _partner_headers(make_auth_headers)

    await async_client.post(f"{BASE}/{ids['acme']}/pack-update", headers=headers)
    after = await async_client.get(f"{BASE}/{ids['acme']}/pack-update", headers=headers)

    assert after.json()["additions"] == {}
    assert "Обновлений нет" in after.json()["summary"]


@pytest.mark.anyio
async def test_удалённое_клиентом_не_воскресает(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Строку из применённой редакции клиент мог удалить осознанно."""

    ids = await _shape_tree()
    # Слепок = текущий набор: новинок нет, значит и предлагать нечего, даже
    # если справочники у клиента пусты.
    await _set_applied_pack(ids["acme"], _current_pack())
    headers = await _partner_headers(make_auth_headers)

    response = await async_client.post(f"{BASE}/{ids['acme']}/pack-update", headers=headers)

    assert response.json()["applied"] is False
    assert await _hazards_of(ids["acme"]) == []


@pytest.mark.anyio
async def test_без_слепка_предлагается_весь_набор(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    await _set_applied_pack(ids["acme"], None)

    body = (
        await async_client.get(
            f"{BASE}/{ids['acme']}/pack-update",
            headers=await _partner_headers(make_auth_headers),
        )
    ).json()

    assert body["applied_unknown"] is True
    # Человек должен понимать, что предложена не разница, а весь набор.
    assert "неизвестна" in body["summary"]


@pytest.mark.anyio
async def test_повторный_приём_ничего_не_удваивает(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    await _set_applied_pack(ids["acme"], _stale_pack())
    headers = await _partner_headers(make_auth_headers)

    await async_client.post(f"{BASE}/{ids['acme']}/pack-update", headers=headers)
    await async_client.post(f"{BASE}/{ids['acme']}/pack-update", headers=headers)

    names = await _hazards_of(ids["acme"])
    assert names.count("Электротравма") == 1


@pytest.mark.anyio
async def test_чужой_клиент_недоступен(async_client: AsyncClient, make_auth_headers) -> None:
    ids = await _shape_tree()

    preview = await async_client.get(
        f"{BASE}/{ids['gamma']}/pack-update", headers=await _partner_headers(make_auth_headers)
    )
    applied = await async_client.post(
        f"{BASE}/{ids['gamma']}/pack-update", headers=await _partner_headers(make_auth_headers)
    )

    assert preview.status_code == 404
    assert applied.status_code == 404


@pytest.mark.anyio
async def test_отраслевому_клиенту_предлагается_его_набор(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе стройке подсунули бы строки общего набора."""

    ids = await _shape_tree()
    construction = json.loads(
        (STARTER_PACK_ROOT / "v1" / "construction.json").read_text(encoding="utf-8")
    )
    stale = json.loads(json.dumps(construction))
    stale["reference_data"]["hazards"] = stale["reference_data"]["hazards"][:1]
    await _set_applied_pack(ids["acme"], stale)

    body = (
        await async_client.get(
            f"{BASE}/{ids['acme']}/pack-update",
            headers=await _partner_headers(make_auth_headers),
        )
    ).json()

    assert body["pack"] == "construction"
    assert "Обрушение конструкций и грунта" in body["additions"]["hazards"]
