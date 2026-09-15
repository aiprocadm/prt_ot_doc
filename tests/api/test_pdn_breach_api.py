"""Реестр утечек ПДн через ручки (152-ФЗ разд. 66.3, срез-207).

Правила сроков проверяются без базы в ``tests/test_privacy_breach.py``. Здесь —
МЕСТО ПОДКЛЮЧЕНИЯ: что запись доезжает до базы, сроки считаются на чтении, три
шага отмечаются по отдельности и чужая утечка не видна.

Урок среза-187: тесты шва не заменяют теста места подключения.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/api/test_pdn_breach_api.py -v``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.models.models import RoleEnum

BREACHES = "/api/v1/privacy/breaches"


def _payload(**overrides) -> dict:
    discovered = datetime.now(tz=timezone.utc) - timedelta(hours=2)
    payload = {
        "summary": "Выгрузка личных дел ушла на посторонний адрес",
        "discovered_at": discovered.isoformat(),
        "affected_people": 37,
    }
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_утечка_регистрируется_и_сроки_считаются(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(BREACHES, json=_payload(), headers=headers)

    assert created.status_code == 201, created.text
    body = created.json()
    stages = {item["stage"]: item for item in body["deadlines"]}
    assert set(stages) == {"notify_regulator", "report_findings", "notify_subjects"}
    # Срок идёт, и человеку видно, сколько осталось ЧАСОВ, а не дней.
    assert stages["notify_regulator"]["status"] == "pending"
    assert stages["notify_regulator"]["hours_left"] == 21
    # Подпись словами приходит с сервера.
    assert stages["notify_regulator"]["title"].startswith("Уведомить Роскомнадзор")


@pytest.mark.anyio
async def test_платформа_честно_говорит_что_не_уведомляет_сама(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """ГЛАВНОЕ ДЛЯ ЧЕЛОВЕКА. Без этой строки экран выглядел бы как «мы уведомим
    за вас», и организация пропустила бы срок, считая, что всё сделано."""

    headers = await make_auth_headers(RoleEnum.ADMIN)

    listed = await async_client.get(BREACHES, headers=headers)

    assert listed.status_code == 200, listed.text
    assert "не отправляет уведомления" in listed.json()["notice"]


@pytest.mark.anyio
async def test_просроченный_срок_виден_словами(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    long_ago = (datetime.now(tz=timezone.utc) - timedelta(hours=30)).isoformat()

    created = await async_client.post(
        BREACHES, json=_payload(discovered_at=long_ago), headers=headers
    )

    stages = {item["stage"]: item for item in created.json()["deadlines"]}
    assert stages["notify_regulator"]["status"] == "overdue"
    assert stages["notify_regulator"]["status_title"] == "ПРОСРОЧЕНО"


@pytest.mark.anyio
async def test_шаги_отмечаются_по_отдельности(async_client: AsyncClient, make_auth_headers) -> None:
    """ТО, РАДИ ЧЕГО ТРИ ОТДЕЛЬНЫХ ПОЛЯ: одна галочка на три обязательства
    означала бы, что выполнив лёгкое, организация считает закрытым и трудное."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(BREACHES, json=_payload(), headers=headers)
    breach_id = created.json()["id"]

    marked = await async_client.post(
        f"{BREACHES}/{breach_id}/steps/notify_regulator", json={}, headers=headers
    )

    assert marked.status_code == 200, marked.text
    stages = {item["stage"]: item for item in marked.json()["deadlines"]}
    assert stages["notify_regulator"]["status"] == "done"
    assert stages["report_findings"]["status"] == "pending"
    assert stages["notify_subjects"]["status"] == "no_deadline"


@pytest.mark.anyio
async def test_выдуманный_шаг_отвергается(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(BREACHES, json=_payload(), headers=headers)

    response = await async_client.post(
        f"{BREACHES}/{created.json()['id']}/steps/всё_сделано", json={}, headers=headers
    )

    assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_утечка_позже_обнаружения_отвергается(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе в реестре появилась бы запись, которую невозможно прочитать:
    обнаружили раньше, чем случилось."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    now = datetime.now(tz=timezone.utc)

    response = await async_client.post(
        BREACHES,
        json=_payload(
            discovered_at=(now - timedelta(hours=5)).isoformat(),
            happened_at=now.isoformat(),
        ),
        headers=headers,
    )

    assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_чужая_утечка_не_видна(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """Чужая запись об утечке — это и репутация, и основание для проверки."""

    owner = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(BREACHES, json=_payload(), headers=owner)
    assert created.status_code == 201, created.text
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="outsider207", session=session)
        await session.commit()
    stranger = await make_auth_headers(
        RoleEnum.ADMIN, tenant="outsider207", email="admin-outsider207@example.com"
    )

    listed = await async_client.get(BREACHES, headers=stranger)
    step = await async_client.post(
        f"{BREACHES}/{created.json()['id']}/steps/notify_regulator", json={}, headers=stranger
    )

    assert created.json()["id"] not in {item["id"] for item in listed.json()["items"]}
    assert step.status_code == 404, step.text


@pytest.mark.anyio
async def test_рядовая_роль_не_ведёт_реестр_утечек(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(BREACHES, json=_payload(), headers=headers)

    assert response.status_code == 403, response.text
