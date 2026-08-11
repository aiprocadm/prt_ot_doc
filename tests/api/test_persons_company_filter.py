"""BIZ-50 срез-8 — список сотрудников фильтруется по организации.

Мастер комплекта выбирает людей ОДНОЙ организации: генерация отвергает
сотрудника из другой (400), поэтому предлагать таких в списке значит вести
человека в тупик.

Фильтровать на стороне интерфейса было нельзя: список постраничный, и
сотрудники за пределами страницы молча не попали бы в выбор.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.models import RoleEnum

URL = "/api/v1/persons"


@pytest.mark.anyio
async def test_filter_returns_only_that_company(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        first = await data_factory.create_company(tenant=tenant, name="ООО Первая", session=session)
        second = await data_factory.create_company(
            tenant=tenant, name="ООО Вторая", session=session
        )
        await data_factory.create_person(
            tenant=tenant, company=first, last_name="Первый", session=session
        )
        await data_factory.create_person(
            tenant=tenant, company=second, last_name="Второй", session=session
        )
        first_id, second_id = first.id, second.id

    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get(URL, headers=headers, params={"company_id": first_id})
    assert response.status_code == 200, response.text
    names = {item["last_name"] for item in response.json()["items"]}
    assert "Первый" in names
    assert "Второй" not in names, "в списке одной организации оказался сотрудник другой"

    other = await async_client.get(URL, headers=headers, params={"company_id": second_id})
    assert {item["last_name"] for item in other.json()["items"]} == {"Второй"}


@pytest.mark.anyio
async def test_two_filters_do_not_share_one_cache(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """Иначе второй запрос получил бы 304 со списком чужой организации.

    Ответ на список сопровождается ETag; не учти он фильтр — два разных
    вопроса получили бы один и тот же ярлык кэша.
    """

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        first = await data_factory.create_company(tenant=tenant, name="ООО Раз", session=session)
        second = await data_factory.create_company(tenant=tenant, name="ООО Два", session=session)
        await data_factory.create_person(
            tenant=tenant, company=first, last_name="Разов", session=session
        )
        await data_factory.create_person(
            tenant=tenant, company=second, last_name="Двоев", session=session
        )
        first_id, second_id = first.id, second.id

    headers = await make_auth_headers(RoleEnum.ADMIN)
    one = await async_client.get(URL, headers=headers, params={"company_id": first_id})
    two = await async_client.get(URL, headers=headers, params={"company_id": second_id})

    assert one.headers.get("etag"), "ответ без ETag — проверять нечего"
    assert one.headers["etag"] != two.headers["etag"], "разные организации, один ярлык кэша"


@pytest.mark.anyio
async def test_without_filter_nothing_changed(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """Фильтр необязательный: без него список остаётся прежним."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Общая", session=session
        )
        await data_factory.create_person(
            tenant=tenant, company=company, last_name="Общий", session=session
        )

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(URL, headers=headers)

    assert response.status_code == 200, response.text
    assert any(item["last_name"] == "Общий" for item in response.json()["items"])
