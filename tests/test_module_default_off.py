"""BIZ-61 срез-2 — модуль выключен, пока не выдан (Доп. №2, разд. 61.2).

ТЗ требует обратной логики к прежней: «по умолчанию заказчик видит только ядро
и модули своей редакции, остальное выключено, пока не выдано явно».

Сверка нашла, что договорённости было мало. У ``is_feature_enabled`` умолчание
``True``, и четыре гейта вызывали её БЕЗ ``default=False``: «Подрядчики»,
«Медосмотры» и «Склад СИЗ» оставались доступны арендатору, у которого просто
нет строки о выдаче. Строку создаёт применение тарифа — значит арендатор, к
которому тариф ни разу не применяли, получал непроданные модули.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.feature_flags import UnknownModuleError, is_module_enabled
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant
from app.modules.subscription.registry import CORE_MODULES, SELLABLE_MODULES


async def _tenant_id(session) -> str:
    """Арендатор БЕЗ единой записи о выдаче модулей.

    Посеянным арендаторам тестовая обвязка выдаёт модули явно (иначе почти
    каждый тест API проверял бы выдачу, а не поведение). Здесь же проверяется
    ровно умолчание, поэтому нужен чистый арендатор.
    """

    tenant = Tenant(
        slug="no-modules",
        code="no-modules",
        name="Без модулей",
        contact_email="none@example.com",
    )
    session.add(tenant)
    await session.flush()
    return str(tenant.id)


@pytest.mark.anyio("asyncio")
@pytest.mark.parametrize("module", SELLABLE_MODULES, ids=lambda module: module.code)
async def test_sellable_module_is_off_without_a_row(sessionmaker, module) -> None:
    """Нет записи о выдаче — модуля нет. Непроданное не открывается само."""

    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        assert await is_module_enabled(session, tenant_id, module.code) is False


@pytest.mark.anyio("asyncio")
@pytest.mark.parametrize("module", CORE_MODULES, ids=lambda module: module.code)
async def test_core_module_is_on_without_a_row(sessionmaker, module) -> None:
    """Ядро выключить нельзя — иначе арендатор останется без документов."""

    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        assert await is_module_enabled(session, tenant_id, module.code) is True


@pytest.mark.anyio("asyncio")
async def test_explicit_row_wins_over_the_default(sessionmaker) -> None:
    """Выданный модуль работает: умолчание не должно перебивать выдачу."""

    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        # Справочник модулей общий для всех арендаторов — строка «medical» уже
        # заведена посевом; вторая нарушила бы уникальность кода.
        feature = (
            (await session.execute(select(Feature).where(Feature.code == "medical")))
            .scalars()
            .first()
        )
        if feature is None:
            feature = Feature(code="medical", title="Медосмотры")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=tenant_id, feature_id=feature.id, on=True))
        await session.flush()

        assert await is_module_enabled(session, tenant_id, "medical") is True


@pytest.mark.anyio("asyncio")
async def test_unknown_module_fails_loudly(sessionmaker) -> None:
    """Гейт на незарегистрированный модуль — ошибка, а не «наверное, выключено».

    Тихое «выключено» выглядело бы как рабочий гейт: модуль недоступен и
    включить его нечем, потому что в тарифах и консоли его нет.
    """

    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        with pytest.raises(UnknownModuleError) as excinfo:
            await is_module_enabled(session, tenant_id, "нет-такого-модуля")
    assert "реестре" in str(excinfo.value)
