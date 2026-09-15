"""Сравнение редакций через ручку: B.18 разд. 19.4 (срез-202).

Разбор самого сравнения — в ``tests/test_npa_revision_diff.py`` (без базы).
Здесь проверяется МЕСТО ПОДКЛЮЧЕНИЯ: что текст редакции доезжает до базы, что
ручка отдаёт его обратно, что чужую редакцию сравнить нельзя и что честный
отказ доживает до ответа, а не превращается по дороге в пустой список.

Урок среза-187 записан прямо здесь: **тесты шва не заменяют теста места
подключения.** Там десять проверок службы ЭДО были зелёными, а ручка падала
дважды.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/api/test_npa_revision_compare.py -v``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.domains.npa.revision_diff import NO_TEXT_REASON
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


async def _revision(
    client: AsyncClient,
    headers: dict[str, str],
    act_id: str,
    code: str,
    clauses: list[dict[str, str]] | None,
) -> str:
    payload: dict = {
        "revision_code": code,
        "title": f"Редакция {code}",
        "effective_from": "2026-02-01",
    }
    if clauses is not None:
        payload["clauses"] = clauses
    response = await client.post(f"{NPA}/{act_id}/revisions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.anyio
async def test_текст_редакции_доезжает_до_базы_и_обратно(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, headers)

    created = await async_client.post(
        f"{NPA}/{act_id}/revisions",
        json={
            "revision_code": "ред-1",
            "title": "Первая",
            "effective_from": "2026-02-01",
            "clauses": [
                {"code": "п. 1", "text": "Общие положения"},
                {"code": "п. 4", "text": "Обучение раз в год"},
            ],
        },
        headers=headers,
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["has_text"] is True
    assert [c["code"] for c in body["clauses"]] == ["п. 1", "п. 4"]


@pytest.mark.anyio
async def test_редакция_без_текста_так_и_говорит(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Редакцию часто заводят заранее, зная только дату. Это законное
    состояние, и оно названо, а не замаскировано пустым списком."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, headers)
    revision_id = await _revision(async_client, headers, act_id, "ред-пусто", None)

    detail = await async_client.get(f"{NPA}/{act_id}", headers=headers)
    by_id = {r["id"]: r for r in detail.json()["revisions"]}
    assert by_id[revision_id]["has_text"] is False


@pytest.mark.anyio
async def test_сравнение_показывает_что_изменилось(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, headers)
    first = await _revision(
        async_client,
        headers,
        act_id,
        "ред-1",
        [
            {"code": "п. 1", "text": "Общие положения"},
            {"code": "п. 4", "text": "Обучение раз в год"},
            {"code": "п. 9", "text": "Исключат"},
        ],
    )
    second = await _revision(
        async_client,
        headers,
        act_id,
        "ред-2",
        [
            {"code": "п. 1", "text": "Общие положения"},
            {"code": "п. 4", "text": "Обучение раз в полгода"},
            {"code": "п. 10", "text": "Новое требование"},
        ],
    )

    response = await async_client.get(
        f"{NPA}/{act_id}/revisions/diff",
        params={"base": first, "target": second},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["comparable"] is True
    assert body["summary"] == {"added": 1, "removed": 1, "modified": 1, "unchanged": 1}
    by_code = {row["code"]: row for row in body["changes"]}
    assert by_code["п. 4"]["before"] == "Обучение раз в год"
    assert by_code["п. 4"]["after"] == "Обучение раз в полгода"
    # Подпись словами приходит с сервера.
    assert by_code["п. 10"]["change_title"] == "Пункт добавлен"
    # Обе редакции названы в ответе: экран не должен искать их отдельно.
    assert body["base"]["revision_code"] == "ред-1"
    assert body["target"]["revision_code"] == "ред-2"


@pytest.mark.anyio
async def test_редакция_без_текста_даёт_отказ_а_не_пустой_дифф(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """ГЛАВНАЯ ПРОВЕРКА СРЕЗА НА ЖИВОЙ РУЧКЕ.

    У всех редакций, заведённых до среза-202, текста нет. Ответ «изменений нет»
    здесь означал бы, что закон не менялся, — и человек не стал бы пересматривать
    документы.
    """

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, headers)
    empty = await _revision(async_client, headers, act_id, "ред-старая", None)
    full = await _revision(
        async_client, headers, act_id, "ред-новая", [{"code": "п. 1", "text": "Текст"}]
    )

    response = await async_client.get(
        f"{NPA}/{act_id}/revisions/diff",
        params={"base": empty, "target": full},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["comparable"] is False
    assert body["reason"] == NO_TEXT_REASON
    assert body["changes"] == []
    # И «всё добавлено» тоже не отвечаем: что было раньше — неизвестно.
    assert body["summary"]["added"] == 0


@pytest.mark.anyio
async def test_порядок_редакций_не_подставляется_за_человека(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """«Что стало при переходе от A к B» и «от B к A» — разные вопросы:
    добавленный пункт в обратную сторону становится исключённым."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, headers)
    first = await _revision(async_client, headers, act_id, "ред-1", [{"code": "п. 1", "text": "А"}])
    second = await _revision(
        async_client,
        headers,
        act_id,
        "ред-2",
        [{"code": "п. 1", "text": "А"}, {"code": "п. 2", "text": "Б"}],
    )

    forward = await async_client.get(
        f"{NPA}/{act_id}/revisions/diff",
        params={"base": first, "target": second},
        headers=headers,
    )
    backward = await async_client.get(
        f"{NPA}/{act_id}/revisions/diff",
        params={"base": second, "target": first},
        headers=headers,
    )

    assert forward.json()["changes"][0]["change"] == "added"
    assert backward.json()["changes"][0]["change"] == "removed"


@pytest.mark.anyio
async def test_редакция_чужого_акта_не_сравнивается(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе по коду ответа можно было бы перебирать идентификаторы редакций."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first_act = await _act(async_client, headers)
    other_act = await _act(async_client, headers)
    mine = await _revision(async_client, headers, first_act, "ред-1", [{"code": "1", "text": "А"}])
    alien = await _revision(async_client, headers, other_act, "ред-1", [{"code": "1", "text": "Б"}])

    response = await async_client.get(
        f"{NPA}/{first_act}/revisions/diff",
        params={"base": mine, "target": alien},
        headers=headers,
    )

    assert response.status_code == 404, response.text


@pytest.mark.anyio
async def test_чужой_локальный_акт_не_сравнивается(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """Срез-201 закрыл акты арендатора фильтром видимости. Новая ручка обязана
    идти через тот же фильтр — иначе она стала бы десятой дырой."""

    owner = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, owner)
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="outsider202", session=session)
        await session.commit()
    stranger = await make_auth_headers(
        RoleEnum.ADMIN, tenant="outsider202", email="admin-outsider202@example.com"
    )
    own = await async_client.post(
        NPA,
        json={
            "scope": "own",
            "code": "ПР-202",
            "title": "Приказ организации",
            "edition": "ред. 1",
            "clauses": [],
        },
        headers=stranger,
    )
    assert own.status_code == 201, own.text
    alien_revision = await _revision(
        async_client, stranger, own.json()["id"], "ред-1", [{"code": "1", "text": "секрет"}]
    )
    mine = await _revision(async_client, owner, act_id, "ред-1", [{"code": "1", "text": "А"}])

    response = await async_client.get(
        f"{NPA}/{act_id}/revisions/diff",
        params={"base": mine, "target": alien_revision},
        headers=owner,
    )

    assert response.status_code == 404, response.text


@pytest.mark.anyio
async def test_повторный_код_пункта_в_редакции_отвергается(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Дифф сопоставляет пункты ПО КОДУ. Два «п. 4» в одном снимке означали бы,
    что сравнение молча берёт любой из них."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act_id = await _act(async_client, headers)

    response = await async_client.post(
        f"{NPA}/{act_id}/revisions",
        json={
            "revision_code": "ред-1",
            "title": "Первая",
            "clauses": [{"code": "п. 4", "text": "А"}, {"code": "п. 4", "text": "Б"}],
        },
        headers=headers,
    )

    assert response.status_code == 422, response.text
