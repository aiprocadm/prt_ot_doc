"""BIZ-50 срез-4 — ручка вопросов мастера (разд. 50.2, шаг 2)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_fields_are_returned_with_russian_labels(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    response = await async_client.get(
        "/api/v1/packs/scenarios/OT_NEW_EMPLOYEE/fields", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["scenario_code"] == "OT_NEW_EMPLOYEE"
    assert body["scenario_name"] == "Приём нового сотрудника"
    names = {item["name"] for item in body["fields"]}
    assert {"employee_name", "position", "hire_date"} <= names
    labels = {item["label"] for item in body["fields"]}
    assert "ФИО работника" in labels

    required = {item["name"] for item in body["fields"] if item["required"]}
    assert "employee_name" in required
    # Стажировка осмысленна пустой («не требуется») — обязательной быть не должна.
    assert "internship_days" not in required


@pytest.mark.anyio
async def test_client_facts_are_not_asked_but_are_named(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Разд. 50.2: «система подтягивает всё, что уже знает о клиенте».

    Молча не спрашивать мало — специалист должен видеть, что эти сведения
    подставятся, иначе он будет искать, где их ввести.
    """

    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    response = await async_client.get(
        "/api/v1/packs/scenarios/OT_NEW_CONTRACTOR/fields", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()

    names = {item["name"] for item in body["fields"]}
    assert not (names & {"company", "company_name", "inn", "site", "site_address"})
    assert body["known_from_client"], "не сказано, что платформа подставит сама"


@pytest.mark.anyio
async def test_unknown_scenario_is_404(async_client: AsyncClient, make_auth_headers) -> None:
    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    response = await async_client.get("/api/v1/packs/scenarios/НЕТ-ТАКОГО/fields", headers=headers)
    assert response.status_code == 404


@pytest.mark.anyio
async def test_every_catalog_scenario_answers(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Сценарий из каталога без вопросов — тупик в мастере."""

    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    catalog = await async_client.get("/api/v1/packs/scenarios", headers=headers)
    assert catalog.status_code == 200, catalog.text

    for item in catalog.json()["data"]:
        response = await async_client.get(
            f"/api/v1/packs/scenarios/{item['code']}/fields", headers=headers
        )
        assert response.status_code == 200, f"{item['code']}: {response.text}"
        assert response.json()["fields"], f"{item['code']}: мастеру нечего спросить"
