"""BIZ-50 срез-6 — ручка третьего шага мастера (разд. 50.2)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.models import RoleEnum

URL = "/api/v1/packs/preview"
SCENARIO = "OT_NEW_EMPLOYEE"


def _codes(body: dict) -> set[str]:
    return {problem["code"] for problem in body["problems"]}


@pytest.mark.anyio
async def test_preview_names_every_missing_thing_at_once(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """Ровно то, чего не хватало: причины списком, а не по одной за запуск."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Ромашка", session=session
        )
        company_id = company.id

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post(
        URL,
        headers=headers,
        json={
            "pack_code": SCENARIO,
            "company_id": company_id,
            "person_ids": ["нет-такого-человека"],
            "data": {},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is False
    assert {"PERSONS_NOT_FOUND", "REQUIRED_FIELDS_BLANK"} <= _codes(body)


@pytest.mark.anyio
async def test_preview_creates_nothing(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """«Посмотреть, что получится» не должно тратить прогон.

    Генерация требует ключ идемпотентности и создаёт запись; предпросмотр не
    делает ни того, ни другого — иначе кнопка «назад» в мастере оставляла бы
    за собой мусор.
    """

    from sqlalchemy import func, select

    from app.models.models import DocumentPack

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Ромашка", session=session
        )
        company_id = company.id
        before = (
            await session.execute(select(func.count()).select_from(DocumentPack))
        ).scalar_one()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    for _ in range(3):
        response = await async_client.post(
            URL,
            headers=headers,
            json={"pack_code": SCENARIO, "company_id": company_id, "data": {}},
        )
        assert response.status_code == 200, response.text

    async with sessionmaker() as session:
        after = (await session.execute(select(func.count()).select_from(DocumentPack))).scalar_one()
    assert after == before, "предпросмотр создал пакеты"


@pytest.mark.anyio
async def test_preview_lists_the_forms(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """«Какие формы будут сгенерированы» — список, а не обещание."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Ромашка", session=session
        )
        company_id = company.id

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post(
        URL,
        headers=headers,
        json={"pack_code": SCENARIO, "company_id": company_id, "data": {}},
    )

    body = response.json()
    assert body["documents"], "мастеру нечего показать на третьем шаге"
    assert body["documents_total"] == len(body["documents"])
    assert all(item["template_name"] for item in body["documents"])


@pytest.mark.anyio
async def test_unknown_scenario_is_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Ромашка", session=session
        )
        company_id = company.id

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post(
        URL,
        headers=headers,
        json={"pack_code": "НЕТ-ТАКОГО", "company_id": company_id, "data": {}},
    )

    assert response.status_code == 404, response.text


@pytest.mark.anyio
async def test_missing_company_is_a_problem_not_a_crash(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Генерация на это отвечает 404 и молчит про остальное.

    Предпросмотр обязан назвать это одной из причин — вместе с прочими.
    """

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post(
        URL,
        headers=headers,
        json={
            "pack_code": SCENARIO,
            "company_id": "00000000-0000-0000-0000-000000000000",
            "data": {},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is False
    assert "COMPANY_MISSING" in _codes(body)
    assert body["score"] == 0
