"""BIZ-53 срез-1: новый арендатор рождается с тарифом (Доп. №1 разд. 53.1).

До этого среза выдача не писала НИ ОДНОЙ строки ``FeatureEnablement``, а
умолчание продаваемого модуля — «выключен» (BIZ-61 срез-2). Значит новый
клиент получал 404 на всех девяти продаваемых модулях, хотя пункты меню
владелец и админ видят всегда: у этих ролей есть все права. Квоты при этом
ставились числами, не совпадающими ни с одним тарифом, и консоль показывала
такого арендатора как «Свой набор».

Решение владельца (19.08.2026): по умолчанию — самый простой тариф.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.feature_flags import is_module_enabled
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant, TenantQuota
from app.modules.subscription.plans import DEFAULT_PLAN_CODE, PLANS, plan_code_for_features
from app.services.tenants.bootstrap.service import BootstrapTenantService


async def _bootstrap(session, monkeypatch, slug: str, **kwargs):
    async def _noop(*args, **kw) -> None:
        return None

    monkeypatch.setattr("app.services.tenants.bootstrap.service.seed_authz_catalog", _noop)
    monkeypatch.setattr("app.services.tenants.bootstrap.service.aensure_tenant_schema", _noop)
    service = BootstrapTenantService(session)
    monkeypatch.setattr(service, "_ensure_tenant_settings", _noop)
    monkeypatch.setattr(service, "_ensure_owner", _noop)
    monkeypatch.setattr(service, "_log_bootstrap_event", _noop)
    monkeypatch.setattr(service, "_seed_starter_pack", _noop)
    monkeypatch.setattr(service, "_seed_package_presets", _noop)
    monkeypatch.setattr(service, "_ensure_company_profile", _noop)
    summary = await service.run(
        tenant_slug=slug,
        tenant_name=f"ООО {slug}",
        owner_email=f"owner@{slug}.example.com",
        owner_password="Secret123!",
        **kwargs,
    )
    await session.flush()
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one()
    return summary, tenant


async def _enabled_codes(session, tenant_id: str) -> set[str]:
    rows = (
        await session.execute(
            select(Feature.code, FeatureEnablement.on)
            .select_from(FeatureEnablement)
            .join(Feature, Feature.id == FeatureEnablement.feature_id)
            .where(FeatureEnablement.tenant_id == tenant_id)
        )
    ).all()
    return {code for code, on in rows if on}


@pytest.mark.anyio
async def test_новый_арендатор_получает_модули_простого_тарифа(sessionmaker, monkeypatch) -> None:
    async with sessionmaker() as session:
        _summary, tenant = await _bootstrap(session, monkeypatch, "plan-default")

        enabled = await _enabled_codes(session, tenant.id)

    assert enabled == set(
        PLANS[DEFAULT_PLAN_CODE].features
    ), "новый арендатор обязан получить ровно модули простого тарифа"
    assert enabled, "пустая выдача означала бы 404 на каждом продаваемом модуле"


@pytest.mark.anyio
async def test_модуль_тарифа_действительно_включён_для_гейта(sessionmaker, monkeypatch) -> None:
    """Проверяем не строку в таблице, а ответ самого гейта.

    Строка выдачи есть ≠ модуль работает: гейт читает пару (on, expires_at) и
    имеет своё умолчание. Проверка боевым путём — правило волны BIZ-52.
    """

    async with sessionmaker() as session:
        _summary, tenant = await _bootstrap(session, monkeypatch, "plan-gate")

        for code in PLANS[DEFAULT_PLAN_CODE].features:
            assert await is_module_enabled(session, tenant.id, code) is True, code
        # Модуль, которого в простом тарифе нет, остаётся закрытым.
        assert await is_module_enabled(session, tenant.id, "warehouse") is False


@pytest.mark.anyio
async def test_выключенные_модули_записаны_строкой(sessionmaker, monkeypatch) -> None:
    """«Продано и выключено» и «никогда не выдавалось» — разные состояния."""

    async with sessionmaker() as session:
        _summary, tenant = await _bootstrap(session, monkeypatch, "plan-rows")

        total = (
            (
                await session.execute(
                    select(FeatureEnablement).where(FeatureEnablement.tenant_id == tenant.id)
                )
            )
            .scalars()
            .all()
        )

    from app.modules.subscription.plans import FEATURE_CATALOG

    assert len(total) == len(FEATURE_CATALOG), "строка нужна каждому продаваемому модулю"


@pytest.mark.anyio
async def test_квоты_соответствуют_тарифу(sessionmaker, monkeypatch) -> None:
    """«Базовый» с квотами уровня «Про» — неверная подпись в консоли и в счёте."""

    async with sessionmaker() as session:
        _summary, tenant = await _bootstrap(session, monkeypatch, "plan-quota")

        quota = (
            await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant.id))
        ).scalar_one()

        preset = PLANS[DEFAULT_PLAN_CODE].quotas
        for key, value in preset.items():
            assert getattr(quota, key) == value, key


@pytest.mark.anyio
async def test_консоль_видит_настоящий_тариф_а_не_свой_набор(sessionmaker, monkeypatch) -> None:
    """Раньше набор не совпадал ни с одним пресетом — консоль писала «Свой набор»."""

    async with sessionmaker() as session:
        _summary, tenant = await _bootstrap(session, monkeypatch, "plan-derive")

        enabled = await _enabled_codes(session, tenant.id)

    assert plan_code_for_features(enabled) == DEFAULT_PLAN_CODE


@pytest.mark.anyio
async def test_тариф_можно_задать_явно(sessionmaker, monkeypatch) -> None:
    async with sessionmaker() as session:
        _summary, tenant = await _bootstrap(session, monkeypatch, "plan-explicit", plan_code="pro")

        enabled = await _enabled_codes(session, tenant.id)

    assert enabled == set(PLANS["pro"].features)
    assert plan_code_for_features(enabled) == "pro"


@pytest.mark.anyio
async def test_повторная_выдача_не_переписывает_тариф(sessionmaker, monkeypatch) -> None:
    """Идемпотентность: у арендатора с квотой шаг ничего не трогает.

    Иначе повторный bootstrap (а он идемпотентен по замыслу) сбросил бы
    купленные модули обратно к простому тарифу.
    """

    async with sessionmaker() as session:
        _summary, tenant = await _bootstrap(session, monkeypatch, "plan-idem", plan_code="pro")

        _summary2, _tenant2 = await _bootstrap(session, monkeypatch, "plan-idem")

        enabled = await _enabled_codes(session, tenant.id)

    assert enabled == set(PLANS["pro"].features), "повторный прогон не должен разжаловать тариф"
