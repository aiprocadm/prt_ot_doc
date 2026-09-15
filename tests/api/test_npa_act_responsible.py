"""Ответственный за акт: B.18 разд. 19.1 «owner» (срез-203).

ЧТО ПОКАЗАЛА СВЕРКА. Разд. 19.1 перечисляет восемь пунктов, которые обязан
поддерживать реестр НПА: федеральные акты, локальные акты, редакции, даты
вступления, даты отмены, ссылки на процессы и сущности, **owner**, статус
актуальности. Семь были закрыты срезами 141–202, восьмой — нет.

Прошлая волна записала остаток одной фразой «federal/local и owner», то есть
читала owner как «чей акт», и срез-201 закрыл его вместе с принадлежностью.
**Это прочтение не выдерживает проверки:** «федеральные НПА» и «локальные НПА» —
уже два отдельных пункта того же списка, и третий про то же был бы повтором; а
разд. 19.2 рядом пишет «responsible owner» про человека. Значит, owner здесь —
кто в организации ВЕДЁТ этот акт.

ЗАЧЕМ ЭТО НА ДЕЛЕ. Задачи актуализации (разд. 19.4) доставались тому, кто нажал
кнопку, — то есть первому, кто открыл экран. «Пересмотреть документы после новой
редакции» должно попадать к тому, кто за акт отвечает.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/api/test_npa_act_responsible.py -v``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.models.models import RoleEnum

NPA = "/api/v1/npa"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _act(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        NPA,
        json={
            "code": f"{uuid4().hex[:6]}н",
            "title": "Приказ об обучении",
            "edition": "ред. 2026",
            "valid_from": "2026-01-01",
            "clauses": [{"code": "п. 1", "text": "Общие положения"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.anyio
async def test_ответственный_назначается_и_виден_словами(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, headers)

    options = await async_client.get(f"{NPA}/{act_id}/responsible", headers=headers)
    assert options.status_code == 200, options.text
    # Пока никого не назначили, это так и сказано — пустым ответственным.
    assert options.json()["responsible"] is None
    candidates = options.json()["candidates"]
    assert candidates, "некого назначить — справочник кандидатов пуст"

    chosen = candidates[0]["id"]
    saved = await async_client.put(
        f"{NPA}/{act_id}/responsible", json={"owner_user_id": chosen}, headers=headers
    )

    assert saved.status_code == 200, saved.text
    # Имя приходит С СЕРВЕРА: витрина не должна знать идентификаторы людей.
    assert saved.json()["responsible"]["user_id"] == chosen
    assert saved.json()["responsible"]["name"]
    assert saved.json()["responsible"]["name"] != chosen


@pytest.mark.anyio
async def test_снятие_ответственного_это_отдельное_действие(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """«Акт никто не ведёт» — честное состояние реестра, и выставляется оно
    явно, а не получается забывчивостью."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, headers)
    options = await async_client.get(f"{NPA}/{act_id}/responsible", headers=headers)
    chosen = options.json()["candidates"][0]["id"]
    await async_client.put(
        f"{NPA}/{act_id}/responsible", json={"owner_user_id": chosen}, headers=headers
    )

    cleared = await async_client.put(
        f"{NPA}/{act_id}/responsible", json={"owner_user_id": None}, headers=headers
    )

    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["responsible"] is None


@pytest.mark.anyio
async def test_ответственный_у_каждой_организации_свой(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """ГЛАВНАЯ ПРОВЕРКА СРЕЗА.

    Один приказ Минтруда действует на всех арендаторов, и ведут его в разных
    организациях разные люди. Колонка у общей строки реестра дала бы одного
    ответственного на всю платформу — ответ, верный максимум для одной из них.
    """

    platform = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, platform)
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="acme203", session=session)
        await session.commit()
    other = await make_auth_headers(
        RoleEnum.ADMIN, tenant="acme203", email="admin-acme203@example.com"
    )

    mine = (await async_client.get(f"{NPA}/{act_id}/responsible", headers=platform)).json()
    theirs = (await async_client.get(f"{NPA}/{act_id}/responsible", headers=other)).json()
    await async_client.put(
        f"{NPA}/{act_id}/responsible",
        json={"owner_user_id": mine["candidates"][0]["id"]},
        headers=platform,
    )
    await async_client.put(
        f"{NPA}/{act_id}/responsible",
        json={"owner_user_id": theirs["candidates"][0]["id"]},
        headers=other,
    )

    after_platform = (
        await async_client.get(f"{NPA}/{act_id}/responsible", headers=platform)
    ).json()
    after_other = (await async_client.get(f"{NPA}/{act_id}/responsible", headers=other)).json()
    assert after_platform["responsible"]["user_id"] != after_other["responsible"]["user_id"], (
        "назначение одной организации перезаписало ответственного другой — "
        "ответственный привязан к общей строке реестра, а не к арендатору"
    )


@pytest.mark.anyio
async def test_чужой_сотрудник_не_назначается(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """Иначе по коду ответа можно было бы перебирать сотрудников соседей."""

    platform = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, platform)
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="beta203", session=session)
        await session.commit()
    other = await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta203", email="admin-beta203@example.com"
    )
    alien = (await async_client.get(f"{NPA}/{act_id}/responsible", headers=other)).json()[
        "candidates"
    ][0]["id"]

    response = await async_client.put(
        f"{NPA}/{act_id}/responsible", json={"owner_user_id": alien}, headers=platform
    )

    assert response.status_code == 404, response.text


@pytest.mark.anyio
async def test_чужой_локальный_акт_не_получает_ответственного(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """Новая ручка обязана идти через тот же фильтр видимости, что и остальные
    девять мест (срез-201), — иначе она станет десятой дырой."""

    platform = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="gamma203", session=session)
        await session.commit()
    other = await make_auth_headers(
        RoleEnum.ADMIN, tenant="gamma203", email="admin-gamma203@example.com"
    )
    own = await async_client.post(
        NPA,
        json={
            "scope": "own",
            "code": "ПР-203",
            "title": "Приказ организации",
            "edition": "ред. 1",
            "clauses": [],
        },
        headers=other,
    )
    assert own.status_code == 201, own.text

    response = await async_client.get(f"{NPA}/{own.json()['id']}/responsible", headers=platform)

    assert response.status_code == 404, response.text


@pytest.mark.anyio
async def test_рядовая_роль_не_назначает_ответственного(
    async_client: AsyncClient, make_auth_headers
) -> None:
    admin = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, admin)
    worker = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.put(
        f"{NPA}/{act_id}/responsible", json={"owner_user_id": None}, headers=worker
    )

    assert response.status_code == 403, response.text


@pytest.mark.anyio
async def test_задача_актуализации_идёт_ответственному(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """РАДИ ЧЕГО СРЕЗ.

    До него задача доставалась тому, кто нажал кнопку, — то есть первому, кто
    открыл экран. «Пересмотреть документы после новой редакции» должно попадать
    к тому, кто за акт отвечает.
    """

    from sqlalchemy import select

    from app.models.notifications import PlanTask

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, headers)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        template = await data_factory.create_template(
            tenant=tenant, name=f"Инструкция {uuid4().hex[:4]}", session=session
        )
        company = await data_factory.create_company(
            tenant=tenant, name=f"ООО {uuid4().hex[:4]}", session=session
        )
        document, _ = await data_factory.create_document(
            tenant=tenant, template=template, company=company, session=session
        )
        await session.commit()
        document_id = document.id
    bound = await async_client.post(
        f"{NPA}/{act_id}/bindings",
        json={"entity_type": "document", "entity_id": document_id},
        headers=headers,
    )
    assert bound.status_code == 201, bound.text

    options = await async_client.get(f"{NPA}/{act_id}/responsible", headers=headers)
    # Берём кандидата, который ЗАВЕДОМО не тот, кто жмёт кнопку, если такой есть.
    chosen = options.json()["candidates"][-1]["id"]
    await async_client.put(
        f"{NPA}/{act_id}/responsible", json={"owner_user_id": chosen}, headers=headers
    )

    created = await async_client.post(f"{NPA}/{act_id}/impact/tasks", headers=headers)
    assert created.status_code in (200, 201), created.text

    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(PlanTask).where(
                        PlanTask.entity_type == "npa", PlanTask.entity_id == act_id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert rows, "задачи актуализации не завелись"
    assert all(
        row.assignee_id == chosen for row in rows
    ), "задача ушла не ответственному за акт, а тому, кто нажал кнопку"
