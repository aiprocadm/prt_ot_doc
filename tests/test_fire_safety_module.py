"""BIZ-54-57 срез-2: пожарная безопасность стала продаваемым модулем.

Доп. №1 разд. 54.1, приёмка §58.3 «дисциплины включаются/выключаются
feature-флагами». Решение владельца 19.08.2026.

Закрепляется главное:

* модуль объявлен со ВСЕМИ своими экранами и правами — иначе выключение
  спрятало бы часть, а остальное осталось бы висеть в меню;
* «Всё включено» действительно включает новый модуль — тариф обязан выполнять
  своё обещание;
* простой тариф его НЕ включает: дисциплина продаётся, а не раздаётся;
* новый арендатор получает явную строку выдачи (продано и выключено ≠ никогда
  не выдавалось).
"""

from __future__ import annotations

import pytest

from app.modules.subscription.plans import (
    DEFAULT_PLAN_CODE,
    FEATURE_CATALOG,
    MODULE_EVENT_TYPES,
    PLANS,
    plan_code_for_features,
)
from app.modules.subscription.registry import MODULE_REGISTRY, SELLABLE_MODULES

CODE = "fire_safety"


def _module():
    return next(m for m in SELLABLE_MODULES if m.code == CODE)


class TestRegistry:
    def test_модуль_продаётся_и_не_ядро(self) -> None:
        module = _module()
        assert module.is_core is False
        assert CODE in FEATURE_CATALOG

    def test_объявлены_все_три_экрана(self) -> None:
        """Выключенный модуль обязан спрятать ВСЕ свои экраны, а не часть."""

        assert set(_module().ui_routes) == {
            "/fire-safety",
            "/fire-training",
            "/fire-inspections",
        }

    def test_объявлены_права_экранов(self) -> None:
        """Срез-119: у контура появилось право ВЕСТИ записи, а не только смотреть.

        До него запись охранял список ролей на сервере, а экран проверял своё
        право `fire_safety.view` — и две стороны разошлись: инженеру ПБ экран
        показывали, а запись сервер отклонял.
        """

        assert set(_module().permissions) == {
            "fire_safety.view",
            "fire_safety.manage",
            "fire_training.view",
            "fire_inspections.view",
        }

    def test_запись_о_событиях_есть(self) -> None:
        """Правило проекта: код без записи валит контракт вебхуков."""

        assert MODULE_EVENT_TYPES[CODE] == frozenset()

    def test_зависимостей_нет(self) -> None:
        """Пустой depends_on — осознанно: зависимость открывает больше ожидаемого."""

        assert _module().depends_on == ()

    def test_у_каждого_модуля_реестра_есть_категория(self) -> None:
        for module in MODULE_REGISTRY:
            assert module.category.strip(), module.code


class TestPlans:
    def test_всё_включено_включает_дисциплину(self) -> None:
        assert CODE in PLANS["enterprise"].features

    def test_простой_тариф_не_включает(self) -> None:
        """Дисциплина продаётся, а не раздаётся вместе с базовым тарифом."""

        assert CODE not in PLANS[DEFAULT_PLAN_CODE].features

    def test_тариф_всё_включено_по_прежнему_выводится(self) -> None:
        """Набор «всё включено» обязан читаться как тариф, а не «свой набор».

        Это и есть ловушка среза: пресет enterprise равен всему каталогу,
        поэтому новый код расширил его автоматически — и арендатор со СТАРЫМ
        набором стал бы «своим набором». Миграция fs01 выдаёт ему модуль.
        """

        assert plan_code_for_features(set(PLANS["enterprise"].features)) == "enterprise"

    def test_старый_набор_без_дисциплины_уже_не_всё_включено(self) -> None:
        """Сторож самой ловушки: без миграции такой арендатор — «свой набор»."""

        legacy = set(PLANS["enterprise"].features) - {CODE}
        assert plan_code_for_features(legacy) is None


@pytest.mark.anyio
async def test_новый_арендатор_получает_явную_строку(sessionmaker, monkeypatch) -> None:
    """Продано-и-выключено ≠ никогда не выдавалось (правило BIZ-53 среза-1)."""

    from sqlalchemy import select

    from app.models.feature import Feature, FeatureEnablement
    from app.models.models import Tenant
    from app.services.tenants.bootstrap.service import BootstrapTenantService

    async def _noop(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr("app.services.tenants.bootstrap.service.seed_authz_catalog", _noop)
    monkeypatch.setattr("app.services.tenants.bootstrap.service.aensure_tenant_schema", _noop)

    async with sessionmaker() as session:
        service = BootstrapTenantService(session)
        for name in (
            "_ensure_tenant_settings",
            "_ensure_owner",
            "_log_bootstrap_event",
            "_seed_starter_pack",
            "_seed_package_presets",
            "_ensure_company_profile",
        ):
            monkeypatch.setattr(service, name, _noop)
        await service.run(
            tenant_slug="fire-mod",
            tenant_name="ООО Огонь",
            owner_email="owner@fire.example.com",
            owner_password="Secret123!",
        )
        await session.flush()
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "fire-mod"))
        ).scalar_one()

        row = (
            await session.execute(
                select(FeatureEnablement.on)
                .select_from(FeatureEnablement)
                .join(Feature, Feature.id == FeatureEnablement.feature_id)
                .where(
                    FeatureEnablement.tenant_id == tenant.id,
                    Feature.code == CODE,
                )
            )
        ).scalar_one_or_none()

    assert row is not None, "строка выдачи обязана существовать даже для выключенного"
    assert row is False, "простой тариф дисциплину не включает"
