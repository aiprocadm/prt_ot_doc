"""BIZ-52 срез-16: перенос конфигурации между клиентами (разд. 52.3).

Закрепляется главное: партнёр снимает слепок с настроенного клиента и применяет
его к новому, перенос ДОБАВЛЯЕТ (не стирает чужое), а чужой арендатор недоступен
ни на выгрузку, ни на применение.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.models.master_data import Company, Position
from app.models.models import RoleEnum, Tenant
from app.models.safety_core import Hazard

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


async def _seed_reference(tenant_id: str, *, positions=(), hazards=()) -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        company_id = (
            await session.execute(select(Company.id).where(Company.tenant_id == tenant_id))
        ).scalar_one_or_none()
        if company_id is None and positions:
            company = Company(tenant_id=tenant_id, name="ООО Тест", legal_address="TBD")
            session.add(company)
            await session.flush()
            company_id = company.id
        for name in positions:
            session.add(Position(tenant_id=tenant_id, company_id=company_id, name=name))
        for name in hazards:
            session.add(Hazard(tenant_id=tenant_id, name=name))
        await session.commit()


async def _names_of(tenant_id: str, model) -> list[str]:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        return list(
            (
                await session.execute(select(model.name).where(model.tenant_id == tenant_id))
            ).scalars()
        )


async def _partner_headers(make_auth_headers):
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-config@example.com"
    )


@pytest.mark.anyio
async def test_выгрузка_собирает_справочники_клиента(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    await _seed_reference(ids["acme"], positions=["Мастер"], hazards=["Пожар"])

    response = await async_client.get(
        f"{BASE}/{ids['acme']}/config", headers=await _partner_headers(make_auth_headers)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reference_data"]["positions"] == ["Мастер"]
    assert body["reference_data"]["hazards"] == ["Пожар"]
    # Через месяц человек спросит «откуда этот файл».
    assert body["exported_from"] == "acme"


@pytest.mark.anyio
async def test_перенос_создаёт_справочники_у_другого_клиента(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    await _seed_reference(ids["acme"], positions=["Мастер"], hazards=["Пожар"])
    headers = await _partner_headers(make_auth_headers)
    exported = (await async_client.get(f"{BASE}/{ids['acme']}/config", headers=headers)).json()

    # Заводим второго клиента того же партнёра.
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        target = Tenant(
            slug="acme2",
            name="ООО Акме 2",
            contact_email="owner@acme2.example",
            parent_id=ids["beta"],
        )
        session.add(target)
        await session.commit()
        target_id = target.id

    response = await async_client.post(
        f"{BASE}/{target_id}/config",
        headers=headers,
        json={"reference_data": exported["reference_data"]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["applied"] is True
    assert "Пожар" in await _names_of(target_id, Hazard)


@pytest.mark.anyio
async def test_перенос_добавляет_а_не_стирает(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Клиент мог завести своё; «применить конфигурацию» ≠ «стереть чужое»."""

    ids = await _shape_tree()
    await _seed_reference(ids["acme"], hazards=["Своя опасность"])
    headers = await _partner_headers(make_auth_headers)

    await async_client.post(
        f"{BASE}/{ids['acme']}/config",
        headers=headers,
        json={"reference_data": {"hazards": ["Принесённая опасность"]}},
    )

    names = await _names_of(ids["acme"], Hazard)
    assert "Своя опасность" in names
    assert "Принесённая опасность" in names


@pytest.mark.anyio
async def test_повторный_перенос_не_удваивает(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()
    headers = await _partner_headers(make_auth_headers)
    body = {"reference_data": {"hazards": ["Пожар"]}}

    await async_client.post(f"{BASE}/{ids['acme']}/config", headers=headers, json=body)
    await async_client.post(f"{BASE}/{ids['acme']}/config", headers=headers, json=body)

    assert (await _names_of(ids["acme"], Hazard)).count("Пожар") == 1


@pytest.mark.anyio
async def test_проба_показывает_и_ничего_не_меняет(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Перенос вслепую на чужой арендатор — не то, что делают на ощупь."""

    ids = await _shape_tree()

    response = await async_client.post(
        f"{BASE}/{ids['acme']}/config",
        headers=await _partner_headers(make_auth_headers),
        json={"reference_data": {"hazards": ["Пожар"]}, "dry_run": True},
    )

    assert response.json()["applicable"] == {"hazards": 1}
    assert response.json()["applied"] is False
    assert await _names_of(ids["acme"], Hazard) == []


@pytest.mark.anyio
async def test_неприменимые_виды_названы(
    async_client: AsyncClient, make_auth_headers
) -> None:
    # Молчание о пропущенном читается как потеря данных.
    ids = await _shape_tree()

    body = (
        await async_client.post(
            f"{BASE}/{ids['acme']}/config",
            headers=await _partner_headers(make_auth_headers),
            json={
                "reference_data": {"hazards": ["Пожар"], "briefing_types": ["Вводный"]},
                "dry_run": True,
            },
        )
    ).json()

    assert "briefing_types" in body["skipped"]


@pytest.mark.anyio
async def test_чужой_клиент_не_выгружается(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Та же граница, что у остального кабинета: чужой — 404, а не 403."""

    ids = await _shape_tree()

    response = await async_client.get(
        f"{BASE}/{ids['gamma']}/config", headers=await _partner_headers(make_auth_headers)
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_на_чужого_клиента_ничего_не_переносится(
    async_client: AsyncClient, make_auth_headers
) -> None:
    ids = await _shape_tree()

    response = await async_client.post(
        f"{BASE}/{ids['gamma']}/config",
        headers=await _partner_headers(make_auth_headers),
        json={"reference_data": {"hazards": ["Чужое"]}},
    )

    assert response.status_code == 404
    assert await _names_of(ids["gamma"], Hazard) == []
