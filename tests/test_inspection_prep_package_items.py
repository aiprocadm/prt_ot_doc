"""Пакет подготовки к проверке перестал быть пустым (BIZ-54-57 срез-136).

ЗАЧЕМ. Опись среза-131 нашла таблицу ``inspection_prep_items``: её читают два
экрана (состав пакета и его готовность), а не пишет никто. Список
обязательного (``InspectionPrepPackageService.collect_required_items``) был
написан и не позван НИКЕМ.

Из-за этого пакет подготовки к проверке всегда показывал пустой состав и
готовность 0 %. Накануне проверки это худшее, что может показать такой экран:
пустой список читается как «готовиться не к чему», а ноль процентов — как
«ничего не сделано», и оба раза цифра не про данные арендатора, а про то, что
строк там не бывает в принципе.

ЧТО ПРОВЕРЯЕТСЯ: пакет создаётся вместе с составом; позицию можно отметить
собранной; готовность считается от собранных позиций, а не от пустоты.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.models import RoleEnum

pytestmark = pytest.mark.anyio

BASE = "/api/v1/inspection-prep/packages"


async def _create_package(async_client: AsyncClient, headers: dict[str, str]) -> str:
    response = await async_client.post(
        BASE,
        json={"code": f"prep-{uuid.uuid4().hex[:8]}", "title": "Проверка Ростехнадзора"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_состав_пакета_появляется_вместе_с_пакетом(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Раньше список позиций был пуст при любой работе."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    package_id = await _create_package(async_client, headers)

    response = await async_client.get(f"{BASE}/{package_id}/items", headers=headers)

    assert response.status_code == 200, response.text
    items = response.json()
    assert {item["item_type"] for item in items} == {"risk_map", "ppe_card", "training_record"}
    assert all(item["status"] == "required" for item in items), items


async def test_готовность_считается_от_собранных_позиций(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Раньше готовность была нулём всегда: делить было не на что."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    package_id = await _create_package(async_client, headers)

    before = await async_client.get(f"{BASE}/{package_id}/summary", headers=headers)
    assert before.status_code == 200, before.text
    assert before.json()["items"] == 3
    assert before.json()["readiness_score"] == 0, "ничего не собрано — ноль честный"

    items = (await async_client.get(f"{BASE}/{package_id}/items", headers=headers)).json()
    marked = await async_client.patch(
        f"{BASE}/{package_id}/items/{items[0]['id']}",
        json={"status": "present", "notes": "Карта рисков приложена"},
        headers=headers,
    )
    assert marked.status_code == 200, marked.text

    after = await async_client.get(f"{BASE}/{package_id}/summary", headers=headers)
    assert after.status_code == 200, after.text
    assert after.json()["readiness_score"] == 33, "одна позиция из трёх"


async def test_состояние_позиции_из_закрытого_словаря(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Свободная строка сделала бы готовность невычислимой."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    package_id = await _create_package(async_client, headers)
    items = (await async_client.get(f"{BASE}/{package_id}/items", headers=headers)).json()

    response = await async_client.patch(
        f"{BASE}/{package_id}/items/{items[0]['id']}",
        json={"status": "почти готово"},
        headers=headers,
    )

    assert response.status_code == 422, response.text


async def test_чужая_позиция_не_правится(async_client: AsyncClient, make_auth_headers) -> None:
    """Позиция ищется В ПРЕДЕЛАХ пакета: иначе по идентификатору правилась бы соседняя."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await _create_package(async_client, headers)
    second = await _create_package(async_client, headers)
    foreign = (await async_client.get(f"{BASE}/{second}/items", headers=headers)).json()[0]

    response = await async_client.patch(
        f"{BASE}/{first}/items/{foreign['id']}",
        json={"status": "present"},
        headers=headers,
    )

    assert response.status_code == 404, response.text
