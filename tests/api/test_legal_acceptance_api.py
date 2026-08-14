"""BIZ-52 срез-11: принятие юридических текстов по HTTP (разд. 52.2).

Срез-5 научил партнёра публиковать оферту. Кто её принял — не записывалось
нигде. Здесь закрепляется главное: подписывает КОНКРЕТНЫЙ человек, принимается
ровно та редакция, которую ему показали, а новая редакция снова требует подписи.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domains.reseller import RESELLER_KIND
from app.domains.reseller.legal_acceptance import document_fingerprint
from app.models.legal_acceptance import TenantLegalAcceptance
from app.models.models import RoleEnum, Tenant

OWN = "/api/v1/platform/legal"
ACCEPT = "/api/v1/legal/acceptance"


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
        RoleEnum.ADMIN, tenant="beta", email="admin-beta-accept@example.com"
    )


async def _client_headers(make_auth_headers, email: str = "user-acme@example.com"):
    return await make_auth_headers(RoleEnum.EMPLOYEE, tenant="acme", email=email)


async def _publish_offer(async_client, headers, body: str = "Условия оказания услуг."):
    return await async_client.put(
        f"{OWN}/offer", headers=headers, json={"title": "Оферта партнёра", "body": body}
    )


@pytest.mark.anyio
async def test_принятие_записывает_редакцию_и_человека(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    await _publish_offer(async_client, await _partner_headers(make_auth_headers))

    response = await async_client.post(
        f"{ACCEPT}/offer", headers=await _client_headers(make_auth_headers)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["doc_version"] == 1
    # Клиент принял оферту ПАРТНЁРА — это должно быть видно в записи, иначе
    # номер редакции неоднозначен: у клиента и партнёра свои нумерации.
    assert body["source"] == "reseller"


@pytest.mark.anyio
async def test_состояние_показывает_что_ждёт_подписи(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()
    await _publish_offer(async_client, await _partner_headers(make_auth_headers))
    headers = await _client_headers(make_auth_headers)

    before = await async_client.get(ACCEPT, headers=headers)
    await async_client.post(f"{ACCEPT}/offer", headers=headers)
    after = await async_client.get(ACCEPT, headers=headers)

    assert before.status_code == 200, before.text
    assert "offer" in before.json()["pending"]
    assert after.json()["pending"] == []


@pytest.mark.anyio
async def test_новая_редакция_снова_требует_подписи(
    async_client: AsyncClient, make_auth_headers
) -> None:
    # Иначе публикация новых условий молча считалась бы принятой всеми.
    await _shape_tree()
    partner = await _partner_headers(make_auth_headers)
    await _publish_offer(async_client, partner)
    headers = await _client_headers(make_auth_headers)
    await async_client.post(f"{ACCEPT}/offer", headers=headers)

    await _publish_offer(async_client, partner, body="Новые условия.")
    state = await async_client.get(ACCEPT, headers=headers)

    offer = next(item for item in state.json()["items"] if item["kind"] == "offer")
    assert offer["accepted"] is False
    # «Условия изменились» — не то же, что «примите оферту».
    assert offer["outdated"] is True
    assert offer["accepted_version"] == 1
    assert offer["current_version"] == 2


@pytest.mark.anyio
async def test_повторное_принятие_не_плодит_записей(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Двойное нажатие кнопки — обычное дело, 409 выглядел бы как поломка."""

    await _shape_tree()
    await _publish_offer(async_client, await _partner_headers(make_auth_headers))
    headers = await _client_headers(make_auth_headers)

    first = await async_client.post(f"{ACCEPT}/offer", headers=headers)
    second = await async_client.post(f"{ACCEPT}/offer", headers=headers)

    assert second.status_code == 201, second.text
    # Время сохраняется ПЕРВОЕ: «когда согласился» — это когда согласился впервые.
    assert second.json()["accepted_at"] == first.json()["accepted_at"]


@pytest.mark.anyio
async def test_записан_отпечаток_принятого_текста(
    async_client: AsyncClient, make_auth_headers
) -> None:
    # Одной ссылки на редакцию мало: строку можно поправить в обход
    # версионирования, и «принята редакция 1» указывала бы на текст, которого
    # человек не видел.
    await _shape_tree()
    await _publish_offer(async_client, await _partner_headers(make_auth_headers))
    await async_client.post(f"{ACCEPT}/offer", headers=await _client_headers(make_auth_headers))

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        row = (
            await session.execute(
                select(TenantLegalAcceptance).where(TenantLegalAcceptance.kind == "offer")
            )
        ).scalar_one()

    assert row.body_sha256 == document_fingerprint("Условия оказания услуг.")


@pytest.mark.anyio
async def test_принятие_одного_не_считается_за_другого(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Подписывает человек, а не арендатор."""

    await _shape_tree()
    await _publish_offer(async_client, await _partner_headers(make_auth_headers))
    first = await _client_headers(make_auth_headers, email="one-acme@example.com")
    second = await _client_headers(make_auth_headers, email="two-acme@example.com")

    await async_client.post(f"{ACCEPT}/offer", headers=first)
    state = await async_client.get(ACCEPT, headers=second)

    assert "offer" in state.json()["pending"]


@pytest.mark.anyio
async def test_неопубликованный_текст_принять_нельзя(
    async_client: AsyncClient, make_auth_headers
) -> None:
    await _shape_tree()

    response = await async_client.post(
        f"{ACCEPT}/privacy", headers=await _client_headers(make_auth_headers)
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_рядовой_сотрудник_видит_состояние(
    async_client: AsyncClient, make_auth_headers
) -> None:
    # Закрой ручку ролью — и рядовой сотрудник не узнает, что от него ждут
    # подписи (грабля BIZ-61 среза-5: признаки всегда пустые у обычного
    # пользователя, и не скрывалось ничего).
    await _shape_tree()
    await _publish_offer(async_client, await _partner_headers(make_auth_headers))

    response = await async_client.get(
        ACCEPT, headers=await _client_headers(make_auth_headers, email="rank@example.com")
    )

    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_без_токена_принять_нельзя(async_client: AsyncClient) -> None:
    await _shape_tree()

    response = await async_client.post(f"{ACCEPT}/offer", headers={"x-tenant": "acme"})

    assert response.status_code in (401, 403)


@pytest.mark.anyio
async def test_прямой_клиент_платформы_без_текстов_не_держат_на_подписи(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """`zeta` — прямой клиент платформы: оферты партнёра его не касаются."""

    await _shape_tree()
    await _publish_offer(async_client, await _partner_headers(make_auth_headers))
    headers = await make_auth_headers(
        RoleEnum.EMPLOYEE, tenant="zeta", email="user-zeta@example.com"
    )

    state = await async_client.get(ACCEPT, headers=headers)

    assert state.json()["pending"] == []
