"""BIZ-52 срез-12: отрасль при заведении клиента (разд. 52.3).

Закрепляется главное: отрасль определяет, ЧТО получит новый арендатор в
справочниках, а неизвестный код — отказ до создания, а не общий набор под видом
отраслевого.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.master_data import Position
from app.models.models import RoleEnum, Tenant
from app.models.safety_core import Hazard

BASE = "/api/v1/platform/tenants"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


def _payload(slug: str, **extra) -> dict:
    base = {
        "slug": slug,
        "name": f"ООО {slug}",
        "owner_email": f"owner@{slug}.ru",
        "owner_password": "OwnerPass123",
        "kind": "customer",
        "demo_data": False,
    }
    base.update(extra)
    return base


async def _hazards_of(slug: str) -> list[str]:
    """Опасности нового арендатора — то, ради чего отрасль и выбирают."""

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    select(Hazard.name).where(Hazard.tenant_id == tenant.id)
                )
            )
            .scalars()
            .all()
        )
    return list(rows)


async def _positions_of(slug: str) -> list[str]:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    select(Position.name).where(Position.tenant_id == tenant.id)
                )
            )
            .scalars()
            .all()
        )
    return list(rows)


@pytest.mark.anyio
async def test_список_отраслей_отдаёт_сервер(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Зашитая копия списка на фронте разошлась бы при первой новой отрасли."""

    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get(f"{BASE}/industries", headers=headers)

    assert response.status_code == 200, response.text
    codes = [item["code"] for item in response.json()["items"]]
    assert "construction" in codes
    # Общая идёт первой: она подходит любому.
    assert codes[0] == "general"


@pytest.mark.anyio
async def test_отраслевой_набор_доезжает_до_справочников(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(
        BASE, json=_payload("stroyco", industry="construction"), headers=headers
    )

    assert response.status_code == 201, response.text
    hazards = await _hazards_of("stroyco")
    # Не «набор применён», а именно отраслевые строки: срез-7 научил, что отчёт
    # об успехе может врать.
    assert "Обрушение конструкций и грунта" in hazards
    assert "Производитель работ (прораб)" in await _positions_of("stroyco")


@pytest.mark.anyio
async def test_должности_не_пропускаются_при_заведении_через_api(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Страж дефекта, найденного этим срезом.

    В сессиях приложения `autoflush=False`, поэтому только что созданная
    организация не была видна следующему запросу, и должности эталона молча
    пропускались с пометкой «у арендатора нет организации» — при том что сама
    организация числилась созданной. Существующие тесты посева этого не
    показывали: они работают в тестовой сессии, где autoflush включён, то есть
    боевой путь не воспроизводили.
    """

    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(BASE, json=_payload("flushco"), headers=headers)

    warnings = response.json()["warnings"]
    assert not [item for item in warnings if item.startswith("starter_pack_skipped:positions")]
    assert await _positions_of("flushco")


@pytest.mark.anyio
async def test_разные_отрасли_дают_разное_наполнение(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post(
        BASE, json=_payload("energoco", industry="energy"), headers=headers
    )
    await async_client.post(
        BASE, json=_payload("transco", industry="transport"), headers=headers
    )

    energy = await _hazards_of("energoco")
    transport = await _hazards_of("transco")

    assert "Воздействие электрической дуги" in energy
    assert "Воздействие электрической дуги" not in transport
    assert "Дорожно-транспортное происшествие" in transport


@pytest.mark.anyio
async def test_без_отрасли_прежнее_поведение(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Клиенты, заведённые как раньше, получают тот же общий набор."""

    headers = await make_auth_headers(RoleEnum.ADMIN)

    await async_client.post(BASE, json=_payload("plainco"), headers=headers)

    assert "Падение с высоты" in await _hazards_of("plainco")


@pytest.mark.anyio
async def test_неизвестная_отрасль_отклоняется_до_создания(
    async_client: AsyncClient, make_auth_headers
) -> None:
    # Проверка стоит ДО выдачи: упади она на середине bootstrap — за собой
    # осталась бы схема в базе и половина справочников.
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(
        BASE, json=_payload("mineco", industry="mining"), headers=headers
    )

    assert response.status_code == 400, response.text
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        leftover = (
            await session.execute(select(Tenant).where(Tenant.slug == "mineco"))
        ).scalar_one_or_none()
    assert leftover is None


@pytest.mark.anyio
async def test_отказ_называет_доступные_отрасли(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе исправить опечатку можно только чтением исходников."""

    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(
        BASE, json=_payload("badco", industry="mining"), headers=headers
    )

    assert "construction" in response.text
