"""BIZ-51 срез-1: лента изменений у клиента по HTTP (Доп. №1 разд. 51.1).

Закрепляется главное: изменение фиксируется вместе с подсказками «что теперь
делать», запись НИЧЕГО не создаёт сама, разбор виден и обратим, а чужой клиент
недоступен.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.client_changes import ClientChange
from app.models.managed_clients import ManagedClient
from app.models.models import RoleEnum, Tenant

BASE = "/api/v1/managed-clients"


@pytest.fixture(autouse=True)
def _module_on(monkeypatch: pytest.MonkeyPatch):
    """Модуль аутсорсера включён: лента живёт в его кабинете."""

    from unittest.mock import AsyncMock

    from app.api import dependencies_managed_client as deps
    from app.api.routes import managed_clients as routes

    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(deps, "is_module_enabled", AsyncMock(return_value=True), raising=False)


async def _tenant_id(slug: str = "test") -> str:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        return (await session.execute(select(Tenant.id).where(Tenant.slug == slug))).scalar_one()


async def _client(tenant_id: str, name: str = "ООО Ромашка") -> str:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        row = ManagedClient(
            tenant_id=tenant_id,
            name=name,
            mode=ManagedClientMode.LIGHTWEIGHT,
            contract_status=ContractStatus.ACTIVE,
        )
        session.add(row)
        await session.commit()
        return row.id


def _change(**extra) -> dict:
    base = {
        "kind": "employee_hired",
        "happened_on": "2026-08-14",
        "summary": "Принят слесарь Иванов",
    }
    base.update(extra)
    return base


@pytest.mark.anyio
async def test_изменение_записывается_с_подсказками(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Список «что теперь делать» и есть смысл ленты."""

    mcid = await _client(await _tenant_id())
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(f"{BASE}/{mcid}/changes", json=_change(), headers=headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind_title"] == "Принят новый сотрудник"
    assert "Направление на медосмотр" in body["suggestions"]
    assert body["status"] == "new"


@pytest.mark.anyio
async def test_запись_ничего_не_создаёт_сама(async_client: AsyncClient, make_auth_headers) -> None:
    """ТЗ говорит «предложить/сделать», но начинать с «сделать» нельзя.

    Одна загрузка штатки на сто человек породила бы сотни задач, разгребать
    которые пришлось бы вручную.
    """

    from app.models.obligations import Task

    tenant_id = await _tenant_id()
    mcid = await _client(tenant_id)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    await async_client.post(f"{BASE}/{mcid}/changes", json=_change(), headers=headers)

    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        tasks = (await session.execute(select(Task).where(Task.tenant_id == tenant_id))).all()
    assert tasks == []


@pytest.mark.anyio
async def test_лента_показывает_свежие_сверху(async_client: AsyncClient, make_auth_headers) -> None:
    mcid = await _client(await _tenant_id())
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post(
        f"{BASE}/{mcid}/changes",
        json=_change(happened_on="2026-08-01", summary="Старое"),
        headers=headers,
    )
    await async_client.post(
        f"{BASE}/{mcid}/changes",
        json=_change(happened_on="2026-08-14", summary="Свежее"),
        headers=headers,
    )

    body = (await async_client.get(f"{BASE}/{mcid}/changes", headers=headers)).json()

    assert [item["summary"] for item in body["items"]] == ["Свежее", "Старое"]


@pytest.mark.anyio
async def test_сводка_называет_сколько_требует_внимания(
    async_client: AsyncClient, make_auth_headers
) -> None:
    mcid = await _client(await _tenant_id())
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post(f"{BASE}/{mcid}/changes", json=_change(), headers=headers)

    body = (await async_client.get(f"{BASE}/{mcid}/changes", headers=headers)).json()

    assert body["summary"] == "Требуют внимания: 1 из 1"


@pytest.mark.anyio
async def test_пустая_лента_объясняется_словами(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """«Пусто» и «всё разобрано» — разные ответы."""

    mcid = await _client(await _tenant_id())

    body = (
        await async_client.get(
            f"{BASE}/{mcid}/changes", headers=await make_auth_headers(RoleEnum.ADMIN)
        )
    ).json()

    assert body["items"] == []
    assert body["summary"] == "Изменений не зафиксировано"


@pytest.mark.anyio
async def test_разбор_фиксирует_кто_и_когда(async_client: AsyncClient, make_auth_headers) -> None:
    tenant_id = await _tenant_id()
    mcid = await _client(tenant_id)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = (
        await async_client.post(f"{BASE}/{mcid}/changes", json=_change(), headers=headers)
    ).json()

    response = await async_client.patch(
        f"{BASE}/{mcid}/changes/{created['id']}", json={"status": "handled"}, headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["handled_at"] is not None
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as session:
        row = (
            await session.execute(select(ClientChange).where(ClientChange.id == created["id"]))
        ).scalar_one()
    # «Кем разобрано» — первый вопрос при разборе жалобы клиента.
    assert row.handled_by is not None


@pytest.mark.anyio
async def test_отклонение_убирает_из_требующих_внимания(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Часть изменений действий не требует; без «отклонить» лента копит долги."""

    mcid = await _client(await _tenant_id())
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = (
        await async_client.post(f"{BASE}/{mcid}/changes", json=_change(), headers=headers)
    ).json()

    await async_client.patch(
        f"{BASE}/{mcid}/changes/{created['id']}", json={"status": "dismissed"}, headers=headers
    )
    body = (await async_client.get(f"{BASE}/{mcid}/changes", headers=headers)).json()

    assert body["summary"] == "Все изменения разобраны: 1"


@pytest.mark.anyio
async def test_возврат_в_новое_стирает_след_разбора(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе запись выглядела бы разобранной кем-то, хотя ждёт работы."""

    mcid = await _client(await _tenant_id())
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = (
        await async_client.post(f"{BASE}/{mcid}/changes", json=_change(), headers=headers)
    ).json()
    await async_client.patch(
        f"{BASE}/{mcid}/changes/{created['id']}", json={"status": "handled"}, headers=headers
    )

    response = await async_client.patch(
        f"{BASE}/{mcid}/changes/{created['id']}", json={"status": "new"}, headers=headers
    )

    assert response.json()["handled_at"] is None


@pytest.mark.anyio
async def test_счётчик_внимания_не_зависит_от_фильтра(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе фильтр «разобранные» показывал бы ноль новых и успокаивал зря."""

    mcid = await _client(await _tenant_id())
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = (
        await async_client.post(f"{BASE}/{mcid}/changes", json=_change(), headers=headers)
    ).json()
    await async_client.post(
        f"{BASE}/{mcid}/changes", json=_change(summary="Второе"), headers=headers
    )
    await async_client.patch(
        f"{BASE}/{mcid}/changes/{created['id']}", json={"status": "handled"}, headers=headers
    )

    body = (
        await async_client.get(
            f"{BASE}/{mcid}/changes", params={"status": "handled"}, headers=headers
        )
    ).json()

    assert body["total"] == 1
    assert body["summary"] == "Требуют внимания: 1 из 2"


@pytest.mark.anyio
async def test_чужой_клиент_недоступен(async_client: AsyncClient, make_auth_headers) -> None:
    """Та же граница, что у остального кабинета аутсорсера."""

    other_tenant = await _tenant_id("acme")
    foreign = await _client(other_tenant, name="ООО Чужой")

    response = await async_client.post(
        f"{BASE}/{foreign}/changes",
        json=_change(),
        headers=await make_auth_headers(RoleEnum.ADMIN),
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_выдуманный_вид_изменения_отклоняется(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Список закрыт: «прочее» без последствий превратило бы ленту в свалку."""

    mcid = await _client(await _tenant_id())

    response = await async_client.post(
        f"{BASE}/{mcid}/changes",
        json=_change(kind="выдуманное"),
        headers=await make_auth_headers(RoleEnum.ADMIN),
    )

    assert response.status_code == 422
