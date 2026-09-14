"""Сторож: реестр требований листается, а счётчики считают ВСЁ (B.18, срез-195).

ЧТО БЫЛО. Строка B.18 сама называла остаток: «список не страничный». Сверка
подтвердила буквально: ручка отдавала ВСЮ таблицу требований арендатора на
каждое открытие экрана, а порядок считался в памяти ПОСЛЕ выборки — то есть
страницы были невозможны в принципе.

ГЛАВНОЕ, ЧТО ЗДЕСЬ ЗАКРЕПЛЕНО, — не сама разбивка, а ЧЕСТНОСТЬ СЧЁТЧИКОВ. На
экране написано «Всего · на контроле · просрочено». Посчитай их по выданной
странице — и человек, увидев «просрочено: 0» над первой страницей, сделает
ложный вывод, что просроченных нет вовсе. Этот класс в проекте ловили дважды
(отбор просеивал только текущую страницу), поэтому он под отдельной проверкой.

Второе по важности: ПОРЯДОК. Он должен быть устойчив между страницами, иначе
одна и та же строка попадёт на две страницы, а другая не попадёт ни на одну.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/api/test_compliance_requirements_paging.py -v``.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.models.models import RoleEnum

BASE = "/api/v1/compliance/requirements"
NPA = "/api/v1/npa"

PAST = date(2020, 1, 15)
FAR_FUTURE = date(2999, 1, 1)


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _act(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post(
        NPA,
        json={
            "code": f"{uuid4().hex[:6]}н",
            "title": "Приказ об обучении",
            "edition": "ред. 2026",
            "valid_from": "2026-01-01",
            "clauses": [{"code": "п. 1", "text": "Обучать ежегодно"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    payload = {
        "code": f"ОТ-{uuid4().hex[:8]}",
        "title": "Проводить обучение",
        "severity": "high",
        **fields,
    }
    response = await client.post(BASE, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.anyio
async def test_страница_ограничена_а_счётчики_считают_всю_выборку(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """ГЛАВНАЯ ПРОВЕРКА СРЕЗА.

    Просроченное требование лежит НЕ на первой странице по объёму, но
    «просрочено» обязано его посчитать: иначе человек решит, что всё в порядке.
    """

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    clause = act["clauses"][0]

    # Пять требований: одно просроченное, четыре со сроком в далёком будущем.
    await _create(
        async_client,
        headers,
        npa_id=act["id"],
        clause_id=clause["id"],
        next_due_at=PAST.isoformat(),
    )
    for _ in range(4):
        await _create(
            async_client,
            headers,
            npa_id=act["id"],
            clause_id=clause["id"],
            next_due_at=FAR_FUTURE.isoformat(),
        )

    page = await async_client.get(BASE, params={"limit": 2, "offset": 0}, headers=headers)
    assert page.status_code == 200, page.text
    body = page.json()

    assert len(body["items"]) == 2, "страница не ограничена — вернулось всё"
    # Счётчики — по ВСЕЙ выборке, а не по двум выданным строкам.
    assert body["total"] == 5
    assert body["active"] == 5
    assert body["overdue"] == 1
    assert body["limit"] == 2
    assert body["offset"] == 0


@pytest.mark.anyio
async def test_счётчик_просрочки_виден_даже_когда_просроченного_нет_на_странице(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Та же мысль с другой стороны: просроченное на ВТОРОЙ странице.

    Порядок ставит горящее первым, поэтому просроченное само уходит на первую
    страницу. Здесь мы смотрим вторую — и всё равно обязаны видеть «просрочено: 1».
    """

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    clause = act["clauses"][0]

    await _create(
        async_client, headers, npa_id=act["id"], clause_id=clause["id"],
        next_due_at=PAST.isoformat(),
    )
    for _ in range(3):
        await _create(
            async_client, headers, npa_id=act["id"], clause_id=clause["id"],
            next_due_at=FAR_FUTURE.isoformat(),
        )

    second = await async_client.get(BASE, params={"limit": 2, "offset": 2}, headers=headers)
    body = second.json()
    assert body["overdue"] == 1, "счётчик посчитан по странице — на второй просроченных нет"
    assert body["total"] == 4
    assert body["offset"] == 2


@pytest.mark.anyio
async def test_страницы_не_теряют_и_не_дублируют_строки(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Порядок обязан быть устойчив: иначе строка попадёт на две страницы,
    а соседняя — ни на одну."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    clause = act["clauses"][0]
    for _ in range(7):
        await _create(
            async_client, headers, npa_id=act["id"], clause_id=clause["id"],
            next_due_at=FAR_FUTURE.isoformat(),
        )

    seen: list[str] = []
    for offset in (0, 3, 6):
        response = await async_client.get(
            BASE, params={"limit": 3, "offset": offset}, headers=headers
        )
        seen.extend(item["id"] for item in response.json()["items"])

    assert len(seen) == 7, f"страницы отдали {len(seen)} строк вместо семи"
    assert len(set(seen)) == 7, "строка попала на две страницы"


@pytest.mark.anyio
async def test_счётчики_учитывают_фильтр(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """«Всего» при фильтре — это всего ПРИ ФИЛЬТРЕ.

    Иначе экран с фильтром по одному акту показывал бы число из другого мира.
    """

    headers = await make_auth_headers(RoleEnum.ADMIN)
    mine = await _act(async_client, headers)
    other = await _act(async_client, headers)
    await _create(
        async_client, headers, npa_id=mine["id"], clause_id=mine["clauses"][0]["id"],
        next_due_at=FAR_FUTURE.isoformat(),
    )
    for _ in range(3):
        await _create(
            async_client, headers, npa_id=other["id"], clause_id=other["clauses"][0]["id"],
            next_due_at=FAR_FUTURE.isoformat(),
        )

    response = await async_client.get(BASE, params={"npa_id": mine["id"]}, headers=headers)
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


@pytest.mark.anyio
async def test_размер_страницы_ограничен_сверху(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Потолок не даёт вернуть прежнюю выдачу «всё сразу» одним параметром."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    too_big = await async_client.get(BASE, params={"limit": 5000}, headers=headers)
    assert too_big.status_code == 422
    negative = await async_client.get(BASE, params={"offset": -1}, headers=headers)
    assert negative.status_code == 422


@pytest.mark.anyio
async def test_умолчание_не_режет_маленький_реестр(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """У кого требований немного — не должен заметить изменения вовсе."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    for _ in range(3):
        await _create(
            async_client, headers, npa_id=act["id"], clause_id=act["clauses"][0]["id"],
            next_due_at=FAR_FUTURE.isoformat(),
        )
    response = await async_client.get(BASE, headers=headers)
    body = response.json()
    assert len(body["items"]) == 3
    assert body["total"] == 3
