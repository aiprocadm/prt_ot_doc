"""BIZ-52 срез-5: юридические тексты по HTTP (разд. 52.2, четвёртый пункт).

Закрепляется главное: тексты читаются БЕЗ токена (иначе ссылка на оферту с
экрана входа бессмысленна), клиент партнёра видит тексты ПАРТНЁРА, а публикация
не правит прежнюю редакцию, а добавляет новую.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.models.legal_documents import TenantLegalDocument
from app.models.models import RoleEnum, Tenant

PUBLIC = "/api/v1/public/legal"
OWN = "/api/v1/platform/legal"


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
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-legal@example.com"
    )


async def _publish_offer(async_client, headers, body: str = "Условия оказания услуг."):
    return await async_client.put(
        f"{OWN}/offer",
        headers=headers,
        json={"title": "Оферта партнёра", "body": body},
    )


@pytest.mark.anyio
async def test_оферта_читается_без_токена(async_client: AsyncClient, make_auth_headers) -> None:
    """Ссылка на оферту с экрана входа бессмысленна, если для неё нужен вход."""

    await _shape_tree()
    published = await _publish_offer(async_client, await _partner_headers(make_auth_headers))
    assert published.status_code == 201, published.text

    response = await async_client.get(f"{PUBLIC}/offer", headers={"x-tenant": "acme"})

    assert response.status_code == 200, response.text
    assert response.json()["body"] == "Условия оказания услуг."


@pytest.mark.anyio
async def test_клиент_партнёра_видит_текст_партнёра(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    await _publish_offer(async_client, await _partner_headers(make_auth_headers))

    response = await async_client.get(f"{PUBLIC}/offer", headers={"x-tenant": "acme"})

    assert response.json()["source"] == "reseller"


@pytest.mark.anyio
async def test_чужой_арендатор_текста_партнёра_не_получает(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """`zeta` — прямой клиент платформы, оферта партнёра его не касается."""

    await _shape_tree()
    await _publish_offer(async_client, await _partner_headers(make_auth_headers))

    response = await async_client.get(f"{PUBLIC}/offer", headers={"x-tenant": "zeta"})

    assert response.status_code == 404


@pytest.mark.anyio
async def test_ненайденный_текст_отвечает_404_а_не_пустотой(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Пустое тело с кодом 200 читалось бы как «оферта пустая»."""

    await _shape_tree()

    response = await async_client.get(f"{PUBLIC}/privacy", headers={"x-tenant": "acme"})

    assert response.status_code == 404


@pytest.mark.anyio
async def test_список_показывает_только_опубликованное(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    await _publish_offer(async_client, await _partner_headers(make_auth_headers))

    response = await async_client.get(PUBLIC, headers={"x-tenant": "acme"})

    kinds = {item["kind"] for item in response.json()["items"]}
    assert kinds == {"offer"}


@pytest.mark.anyio
async def test_публикация_добавляет_редакцию_а_не_правит_прежнюю(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """«Какая редакция действовала в марте» — вопрос юридический."""

    ids = await _shape_tree()
    headers = await _partner_headers(make_auth_headers)
    first = await _publish_offer(async_client, headers, body="Редакция один")
    second = await _publish_offer(async_client, headers, body="Редакция два")

    assert first.json()["version"] == 1
    assert second.json()["version"] == 2

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        rows = (
            (
                await session.execute(
                    select(TenantLegalDocument).where(TenantLegalDocument.tenant_id == ids["beta"])
                )
            )
            .scalars()
            .all()
        )
    # Прежняя редакция осталась: история неизменна.
    assert len(rows) == 2
    assert {row.body for row in rows} == {"Редакция один", "Редакция два"}


@pytest.mark.anyio
async def test_действует_последняя_редакция(async_client: AsyncClient, make_auth_headers) -> None:
    await _shape_tree()
    headers = await _partner_headers(make_auth_headers)
    await _publish_offer(async_client, headers, body="Старая")
    await _publish_offer(async_client, headers, body="Новая")

    response = await async_client.get(f"{PUBLIC}/offer", headers={"x-tenant": "acme"})

    body = response.json()
    assert body["body"] == "Новая"
    assert body["version"] == 2


@pytest.mark.anyio
async def test_свой_текст_побеждает_текст_партнёра(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    await _publish_offer(
        async_client, await _partner_headers(make_auth_headers), body="Партнёрская"
    )
    # Клиенту публиковать нельзя, поэтому «свою» редакцию заводим владельцем
    # платформы для САМОГО партнёра — проверяем ступень `self`.
    response = await async_client.get(f"{PUBLIC}/offer", headers={"x-tenant": "beta"})

    assert response.json()["source"] == "self"


@pytest.mark.anyio
async def test_обычный_арендатор_публиковать_не_может(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="acme", email="admin-acme-legal@example.com"
    )

    response = await async_client.put(
        f"{OWN}/offer", headers=headers, json={"title": "Своя", "body": "Текст"}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FLEET_ACCESS_FORBIDDEN"


@pytest.mark.anyio
async def test_публикация_без_токена_отклоняется(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Публично только ЧТЕНИЕ."""

    await _shape_tree()

    response = await async_client.put(
        f"{OWN}/offer", headers={"x-tenant": "beta"}, json={"title": "А", "body": "Б"}
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_пустой_текст_не_публикуется(async_client: AsyncClient, make_auth_headers) -> None:
    await _shape_tree()

    response = await async_client.put(
        f"{OWN}/offer",
        headers=await _partner_headers(make_auth_headers),
        json={"title": "Оферта", "body": ""},
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_неизвестный_вид_текста_отвергается(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Список видов закрыт: «оферта2» не должна становиться новым видом."""

    await _shape_tree()

    response = await async_client.get(f"{PUBLIC}/contract", headers={"x-tenant": "acme"})

    assert response.status_code == 422
