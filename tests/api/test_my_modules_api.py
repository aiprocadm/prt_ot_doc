"""BIZ-61 срез-5 — «мои модули» для фронтенда (Доп. №2, разд. 61.3).

Разд. 61.3 требует трёх слоёв: спрятать пункт меню, закрыть прямой переход по
адресу и не пустить запрос на сервере. Третий слой закрыт срезами 2–4, а
первым двум было не на что опереться: связь «модуль → экраны» жила только в
платформенной консоли, закрытой управляющему тенанту.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.models import RoleEnum, Tenant

URL = "/api/v1/tenants/me/modules"


def _module(body: dict, code: str) -> dict:
    return next(item for item in body["modules"] if item["code"] == code)


async def _set_grant(sessionmaker, slug: str, code: str, *, on: bool) -> None:
    """Выдать или отобрать модуль напрямую — как это делает консоль платформы."""

    async with sessionmaker() as session:
        tenant_id = (
            await session.execute(select(Tenant.id).where(Tenant.slug == slug))
        ).scalar_one()
        feature = (
            await session.execute(select(Feature).where(Feature.code == code))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code=code, title=code)
            session.add(feature)
            await session.flush()
        row = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == str(tenant_id),
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            # Обновить-или-вставить: вторая строка выдачи ломает уникальность
            # и делает ответ гейта неопределённым.
            session.add(FeatureEnablement(tenant_id=str(tenant_id), feature_id=feature.id, on=on))
        else:
            row.on = on
            row.expires_at = None
        await session.commit()


@pytest.mark.anyio
async def test_every_module_is_listed_with_its_screens(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Экраны приходят с сервера: описать связь на фронте — значит завести её дважды."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(URL, headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["modules"], "список модулей пуст — прятать нечего и показывать нечего"
    for item in body["modules"]:
        assert item["ui_routes"], f"{item['code']}: не сказано, какие экраны прятать"
        assert all(route.startswith("/") for route in item["ui_routes"]), item["code"]


@pytest.mark.anyio
async def test_core_modules_are_always_enabled(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе фронт спрячет документы или сотрудников — арендатор ослепнет."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = (await async_client.get(URL, headers=headers)).json()

    core = [item for item in body["modules"] if item["is_core"]]
    assert core, "ядро не перечислено"
    assert all(item["enabled"] for item in core)


@pytest.mark.anyio
async def test_answer_follows_the_real_grant_not_the_billing_plan(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """Ровно тот дефект, ради которого срез: источник признака был не тот.

    Фронт брал признаки из `/billing/plan` — это фичи ТАРИФА БИЛЛИНГА, а
    фактическая выдача живёт в ``FeatureEnablement``. Хранилища расходятся, и
    клиент видел пункт меню модуля, которого у него нет.
    """

    headers = await make_auth_headers(RoleEnum.ADMIN)

    await _set_grant(sessionmaker, "test", "sout", on=False)
    body = (await async_client.get(URL, headers=headers)).json()
    assert _module(body, "sout")["enabled"] is False

    await _set_grant(sessionmaker, "test", "sout", on=True)
    body = (await async_client.get(URL, headers=headers)).json()
    assert _module(body, "sout")["enabled"] is True


@pytest.mark.anyio
async def test_plain_user_gets_the_list_too(async_client: AsyncClient, make_auth_headers) -> None:
    """Меню рисуют всем, а не только владельцу.

    Прежний источник признаков был закрыт ролью owner/admin: у рядового
    пользователя список всегда оставался пустым, и не скрывалось ничего.
    """

    headers = await make_auth_headers(RoleEnum.EMPLOYEE)
    response = await async_client.get(URL, headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["modules"]


@pytest.mark.anyio
async def test_anonymous_is_refused(async_client: AsyncClient) -> None:
    """Состав модулей — сведения об арендаторе, а не публичная витрина."""

    response = await async_client.get(URL)

    assert response.status_code >= 400, "список модулей отдан без предъявления прав"
    assert response.status_code < 500, response.text
