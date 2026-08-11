"""BIZ-61 срез-3 — временный доступ к модулю (Доп. №2, разд. 61.2).

ТЗ называет три источника включения: редакция тарифа, индивидуальная надбавка
и **временный доступ на N дней**. Третьего не было. «Дать посмотреть на две
недели» означало включить модуль и понадеяться, что менеджер вспомнит, —
модуль оставался открытым бесплатно.

Тесты стерегут две вещи: срок действительно закрывает доступ, и срок нельзя
потерять/получить случайно при рутинных операциях (смена тарифа).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.feature_flags import grant_expired, is_module_enabled
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant
from app.modules.subscription.plans import PLANS
from app.services.tenants.subscription import (
    MAX_TRIAL_DAYS,
    TrialError,
    apply_plan,
    grant_module_trial,
    read_feature_grants,
    revoke_module_trial,
)

#: Модуль «Спецоценка» продаётся, но не входит в «Бесплатный» — удобный предмет
#: для демонстрации: обычному арендатору он закрыт.
_MODULE = "sout"


async def _make_tenant(sessionmaker, slug: str) -> Tenant:
    """Арендатор без единой записи о выдаче модулей.

    Отцепляем от сессии: службы выдачи открывают собственную сессию к схеме
    арендатора, а обращение к атрибутам объекта, привязанного к уже закрытой
    сессии, упало бы на ровном месте.
    """

    async with sessionmaker() as session:
        tenant = Tenant(
            slug=slug,
            code=slug,
            name=f"Компания {slug}",
            contact_email=f"owner@{slug}.example",
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        session.expunge(tenant)
    return tenant


async def _set_expiry(sessionmaker, tenant_id: str, code: str, moment: datetime | None) -> None:
    """Сдвинуть срок выдачи напрямую — так проверяется «уже истёк»."""

    async with sessionmaker() as session:
        feature = (
            await session.execute(select(Feature).where(Feature.code == code))
        ).scalar_one_or_none()
        assert feature is not None, f"нет строки каталога для {code}"
        row = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == tenant_id,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one()
        row.expires_at = moment
        await session.commit()


# --------------------------------------------------------------------------
# Сам срок
# --------------------------------------------------------------------------


def test_no_expiry_never_expires() -> None:
    """Бессрочная выдача — это ``None``, а не «очень далёкая дата»."""

    assert grant_expired(None) is False


def test_past_moment_is_expired_and_future_is_not() -> None:
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    assert grant_expired(now - timedelta(seconds=1), now=now) is True
    assert grant_expired(now + timedelta(seconds=1), now=now) is False
    # Ровно в момент окончания доступ уже закрыт: «до 22 августа» не значит
    # «включая ночь на 23-е».
    assert grant_expired(now, now=now) is True


def test_naive_datetime_does_not_crash_the_gate() -> None:
    """SQLite отдаёт время без зоны.

    Наивная дата в сравнении с осведомлённой роняет TypeError — и упадёт это
    ровно в момент проверки доступа, то есть у клиента.
    """

    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    assert grant_expired(datetime(2026, 8, 9, 12, 0), now=now) is True
    assert grant_expired(datetime(2026, 8, 11, 12, 0), now=now) is False


# --------------------------------------------------------------------------
# Гейт модуля
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_trial_opens_the_module_and_expiry_closes_it(sessionmaker) -> None:
    tenant = await _make_tenant(sessionmaker, "trial-life")

    async with sessionmaker() as session:
        assert await is_module_enabled(session, tenant.id, _MODULE) is False

    expires_at = await grant_module_trial(tenant, _MODULE, days=14)
    assert expires_at > datetime.now(UTC)

    async with sessionmaker() as session:
        assert await is_module_enabled(session, tenant.id, _MODULE) is True

    await _set_expiry(sessionmaker, tenant.id, _MODULE, datetime.now(UTC) - timedelta(minutes=1))

    async with sessionmaker() as session:
        assert (
            await is_module_enabled(session, tenant.id, _MODULE) is False
        ), "срок вышел, а модуль остался открытым — это бесплатная работа платформы"


@pytest.mark.anyio
async def test_expired_row_is_kept_not_deleted(sessionmaker) -> None:
    """«Модуль был выдан до такого-то числа» — ответ биллингу, а не мусор."""

    tenant = await _make_tenant(sessionmaker, "trial-history")
    await grant_module_trial(tenant, _MODULE, days=1)
    past = datetime.now(UTC) - timedelta(days=2)
    await _set_expiry(sessionmaker, tenant.id, _MODULE, past)

    async with sessionmaker() as session:
        feature = (
            await session.execute(select(Feature).where(Feature.code == _MODULE))
        ).scalar_one()
        row = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == tenant.id,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()
    assert row is not None, "история выдачи стёрта"
    assert row.expires_at is not None


@pytest.mark.anyio
async def test_revoke_closes_access_early(sessionmaker) -> None:
    tenant = await _make_tenant(sessionmaker, "trial-revoke")
    await grant_module_trial(tenant, _MODULE, days=30)

    assert await revoke_module_trial(tenant, _MODULE) is True
    async with sessionmaker() as session:
        assert await is_module_enabled(session, tenant.id, _MODULE) is False

    # Отзывать нечего — честный ``False``, а не «сделано».
    assert await revoke_module_trial(tenant, _MODULE) is False


@pytest.mark.anyio
async def test_revoke_does_not_touch_a_permanent_grant(sessionmaker) -> None:
    """Кнопка «прекратить демонстрацию» не должна забирать оплаченное."""

    tenant = await _make_tenant(sessionmaker, "trial-vs-paid")
    async with sessionmaker() as session:
        await apply_plan(session, tenant, PLANS["enterprise"])
        await session.commit()

    assert await revoke_module_trial(tenant, _MODULE) is False
    async with sessionmaker() as session:
        assert await is_module_enabled(session, tenant.id, _MODULE) is True


# --------------------------------------------------------------------------
# Выдача: что запрещено
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_trial_over_a_permanent_grant_is_refused(sessionmaker) -> None:
    """Иначе «пробный доступ» ОТНЯЛ бы бессрочно проданный модуль."""

    tenant = await _make_tenant(sessionmaker, "trial-over-paid")
    async with sessionmaker() as session:
        await apply_plan(session, tenant, PLANS["enterprise"])
        await session.commit()

    with pytest.raises(TrialError):
        await grant_module_trial(tenant, _MODULE, days=7)

    async with sessionmaker() as session:
        assert await is_module_enabled(session, tenant.id, _MODULE) is True


@pytest.mark.anyio
async def test_unsellable_and_absurd_durations_are_refused(sessionmaker) -> None:
    tenant = await _make_tenant(sessionmaker, "trial-bad-input")

    with pytest.raises(TrialError):
        await grant_module_trial(tenant, "documents", days=7)  # ядро, оно и так включено
    with pytest.raises(TrialError):
        await grant_module_trial(tenant, "нет-такого", days=7)
    with pytest.raises(TrialError):
        await grant_module_trial(tenant, _MODULE, days=0)
    with pytest.raises(TrialError):
        await grant_module_trial(tenant, _MODULE, days=MAX_TRIAL_DAYS + 1)


@pytest.mark.anyio
async def test_repeat_grant_restarts_the_clock(sessionmaker) -> None:
    """«Продли ещё на 14 дней» человек говорит, глядя на сегодня."""

    tenant = await _make_tenant(sessionmaker, "trial-restart")
    long_first = await grant_module_trial(tenant, _MODULE, days=60)
    short_second = await grant_module_trial(tenant, _MODULE, days=3)
    assert short_second < long_first, "срок сложился со старым вместо замены"


# --------------------------------------------------------------------------
# Взаимодействие с тарифом
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_plan_including_the_module_absorbs_the_trial(sessionmaker) -> None:
    """Модуль купили — он не должен погаснуть в день конца демонстрации."""

    tenant = await _make_tenant(sessionmaker, "trial-absorbed")
    await grant_module_trial(tenant, _MODULE, days=2)
    async with sessionmaker() as session:
        await apply_plan(session, tenant, PLANS["enterprise"])
        await session.commit()

    grants = await read_feature_grants(tenant)
    assert _MODULE in grants.permanent
    assert _MODULE not in grants.trials, "оплаченный модуль остался со сроком"


@pytest.mark.anyio
async def test_plan_change_does_not_silently_cancel_an_active_trial(
    sessionmaker
) -> None:
    """Срок обещан клиенту осознанно; смена тарифа — рутина, а не отзыв."""

    tenant = await _make_tenant(sessionmaker, "trial-survives-plan")
    await grant_module_trial(tenant, _MODULE, days=21)

    async with sessionmaker() as session:
        # «Бесплатный» модуль «Спецоценка» не содержит.
        await apply_plan(session, tenant, PLANS["free"])
        await session.commit()

    assert _MODULE not in PLANS["free"].features
    async with sessionmaker() as session:
        assert await is_module_enabled(session, tenant.id, _MODULE) is True


@pytest.mark.anyio
async def test_plan_change_clears_an_already_expired_grant(sessionmaker) -> None:
    """Истёкшая строка — не «действующая демонстрация», её тариф закрывает."""

    tenant = await _make_tenant(sessionmaker, "trial-expired-plan")
    await grant_module_trial(tenant, _MODULE, days=1)
    await _set_expiry(sessionmaker, tenant.id, _MODULE, datetime.now(UTC) - timedelta(days=1))

    async with sessionmaker() as session:
        await apply_plan(session, tenant, PLANS["free"])
        await session.commit()

    grants = await read_feature_grants(tenant)
    assert _MODULE not in grants.effective


@pytest.mark.anyio
async def test_trial_does_not_turn_the_tenant_into_a_custom_plan(sessionmaker) -> None:
    """Тариф выводится сравнением НАБОРА фич с набором плана.

    Подмешай пробный доступ — и клиент с «Базовым» перестанет совпадать с любым
    тарифом, то есть в консоли и в счёте станет «своим набором».
    """

    from app.modules.subscription.plans import plan_code_for_features

    tenant = await _make_tenant(sessionmaker, "trial-plan-code")
    async with sessionmaker() as session:
        await apply_plan(session, tenant, PLANS["free"])
        await session.commit()
    await grant_module_trial(tenant, _MODULE, days=10)

    grants = await read_feature_grants(tenant)
    assert plan_code_for_features(grants.permanent) == "free"
    assert _MODULE in grants.effective, "доступ-то выдан"
    assert grants.trials[_MODULE] > datetime.now(UTC)
