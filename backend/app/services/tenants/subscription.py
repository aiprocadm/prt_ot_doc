"""Apply a subscription plan to a tenant and read back its feature state.

The managing tenant drives this. Two stores are touched:

* **Feature flags** — ``FeatureEnablement`` is a TenantBaseModel, so its rows live in
  the *target* tenant's schema. We open a session bound to that schema (exactly how
  ``demo_bootstrap`` seeds flags) and write an explicit ``on`` row for **every**
  catalogued feature — ``True`` if the plan includes it, ``False`` otherwise. Writing
  ``on=False`` matters: several flags are default-on, so a lower tier must actively
  switch them off to take the function away.
* **Quotas** — ``TenantQuota`` is a SharedModel (public schema) and is SEC-65-armed, so
  it is updated on the caller-provided session — the fleet endpoints pass a trusted
  ``rls_bypass`` shared-schema session (``platform_tenants._fleet_session``), since the
  managing tenant's request session cannot see another tenant's quota under FORCE RLS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.feature_flags import as_utc, grant_expired
from app.db.session import AsyncSessionLocal
from app.models.approval_runtime import WebhookEndpoint
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant, TenantQuota
from app.models.tenant_billing import WebhookSubscription
from app.modules.subscription.plans import (
    FEATURE_CATALOG,
    MODULE_EVENT_TYPES,
    SubscriptionPlan,
)

#: Максимальная длина пробного доступа. Не «сколько угодно»: бессрочная выдача
#: уже есть (тариф и надбавка), а «пробный на три года» — это подарок, который
#: никто не заметит в отчёте.
MAX_TRIAL_DAYS = 180

__all__ = [
    "MAX_TRIAL_DAYS",
    "FeatureGrants",
    "apply_plan",
    "provision_plan",
    "grant_module_trial",
    "read_enabled_feature_codes",
    "read_feature_grants",
    "revoke_module_trial",
]


class TrialError(ValueError):
    """Пробный доступ выдать нельзя (неизвестный модуль или негодный срок)."""


@dataclass(frozen=True)
class FeatureGrants:
    """Что арендатору выдано: бессрочно и на срок — раздельно.

    Раздельно, потому что вопросы разные. «Какой тариф у клиента» отвечает
    только бессрочная часть: подмешай туда пробный доступ — и клиент с тарифом
    «Базовый» плюс пробный СОУТ перестанет совпадать с любым тарифом и
    отобразится как «свой набор». «Что клиенту сейчас открыто» отвечает
    объединение.
    """

    permanent: set[str] = field(default_factory=set)
    trials: dict[str, datetime] = field(default_factory=dict)

    @property
    def effective(self) -> set[str]:
        return self.permanent | set(self.trials)


def _target_session(target: Tenant) -> AsyncSession:
    """A session bound to ``target``'s own schema (shared catalogue still visible)."""

    return AsyncSessionLocal(
        tenant=target.slug,
        tenant_id=target.id,
        include_public=True,
        create_schema=False,
    )


async def read_enabled_feature_codes(target: Tenant) -> set[str]:
    """Catalogued feature codes explicitly switched **on** for ``target``.

    Only explicit ``FeatureEnablement(on=True)`` rows count — a tenant that never had a
    plan applied reads back as an empty set (→ "custom"), which is honest. Any error
    reaching the tenant's schema (e.g. it was never provisioned) yields an empty set
    rather than failing the whole fleet listing.
    """

    return (await read_feature_grants(target)).effective


async def read_feature_grants(target: Tenant) -> FeatureGrants:
    """Разложить выдачи ``target`` на бессрочные и срочные (BIZ-61 срез-3)."""

    try:
        async with _target_session(target) as session:
            # Filter ``on`` in Python, not SQL: Boolean-column predicates render
            # inconsistently across Postgres/SQLite, so mirror is_feature_enabled and
            # test truthiness here.
            rows = (
                await session.execute(
                    select(Feature.code, FeatureEnablement.on, FeatureEnablement.expires_at)
                    .join(FeatureEnablement, FeatureEnablement.feature_id == Feature.id)
                    .where(FeatureEnablement.tenant_id == target.id)
                )
            ).all()
    except Exception:  # noqa: BLE001 - a broken/absent tenant schema must not 500 the list
        return FeatureGrants()

    grants = FeatureGrants()
    for code, on, expires_at in rows:
        if not on or code not in FEATURE_CATALOG or grant_expired(expires_at):
            continue
        if expires_at is None:
            grants.permanent.add(code)
        else:
            # Осведомлённая дата: значение уходит в ответ API, а «до 24.08 09:00»
            # без зоны — это вопрос «в чьих часах», а не ответ.
            grants.trials[code] = as_utc(expires_at)
    return grants


async def _prune_module_webhooks(
    target_session: AsyncSession, target: Tenant, plan: SubscriptionPlan
) -> None:
    """SEC-63 (разд. 63.3): отключение модуля деактивирует связанные вебхуки.

    Для каждого кода каталога, которого нет в ``plan.features``, события из
    ``MODULE_EVENT_TYPES`` убираются из ``subscribed_events`` эндпоинтов
    арендатора; эндпоинт, у которого событий не осталось, гасится — пустой
    список у диспетчера значит «все события», так что оставить его включённым
    значило бы расширить доставку. Подписки ``WebhookSubscription`` на события
    модуля выключаются (``enabled=False``), а не удаляются: остаётся след для
    аудита и возможность осознанного возврата. Обратного автоматического
    включения при апгрейде нет — платформа не помнит, чьи подписки гасила.
    Прунинг идемпотентен: повторное применение того же плана — no-op.
    """

    removed_events: set[str] = set()
    for code in FEATURE_CATALOG:
        if code not in plan.features:
            removed_events |= MODULE_EVENT_TYPES[code]
    if not removed_events:
        return

    endpoints = (
        (
            await target_session.execute(
                select(WebhookEndpoint).where(WebhookEndpoint.tenant_id == target.id)
            )
        )
        .scalars()
        .all()
    )
    for endpoint in endpoints:
        subscribed = list(endpoint.subscribed_events or [])
        if not subscribed:
            # Пустой список = «все события»: тут нечего убирать, и гасить такой
            # эндпоинт нельзя — он обслуживает и события оставшихся модулей.
            continue
        kept = [event for event in subscribed if event not in removed_events]
        if kept == subscribed:
            continue
        endpoint.subscribed_events = kept
        if not kept:
            endpoint.is_enabled = False

    subscriptions = (
        (
            await target_session.execute(
                select(WebhookSubscription).where(
                    WebhookSubscription.tenant_id == target.id,
                    WebhookSubscription.event_type.in_(sorted(removed_events)),
                )
            )
        )
        .scalars()
        .all()
    )
    for subscription in subscriptions:
        subscription.enabled = False


async def apply_plan(session: AsyncSession, target: Tenant, plan: SubscriptionPlan) -> None:
    """Switch ``target`` onto ``plan``: rewrite its feature flags and its quota preset.

    Feature writes commit on the target-schema session immediately; quota changes are
    staged on the caller's ``session`` (a trusted ``rls_bypass`` fleet session, see the
    module docstring) and committed by the endpoint. Re-applying the same plan is a
    no-op, so this is safe to retry.
    """

    async with _target_session(target) as target_session:
        for code in FEATURE_CATALOG:
            feature = (
                await target_session.execute(select(Feature).where(Feature.code == code))
            ).scalar_one_or_none()
            if feature is None:
                feature = Feature(code=code, title=FEATURE_CATALOG[code])
                target_session.add(feature)
                await target_session.flush()
            enablement = (
                await target_session.execute(
                    select(FeatureEnablement).where(
                        FeatureEnablement.tenant_id == target.id,
                        FeatureEnablement.feature_id == feature.id,
                    )
                )
            ).scalar_one_or_none()
            desired = code in plan.features
            if enablement is None:
                target_session.add(
                    FeatureEnablement(tenant_id=target.id, feature_id=feature.id, on=desired)
                )
                continue
            if desired:
                # Модуль вошёл в тариф — он продан бессрочно, и пробный срок
                # на нём поглощается. Иначе клиент оплатил модуль, а тот
                # погаснет в день окончания давней демонстрации.
                enablement.on = True
                enablement.expires_at = None
                continue
            if enablement.on and not grant_expired(enablement.expires_at):
                if enablement.expires_at is not None:
                    # Действующий пробный доступ тариф НЕ отменяет: срок назначен
                    # осознанно и обещан клиенту, а смена тарифа — рутинная
                    # операция, которая не должна тихо забирать обещанное.
                    # Отозвать пробный доступ можно явно (revoke_module_trial).
                    continue
            enablement.on = False
            enablement.expires_at = None
        await _prune_module_webhooks(target_session, target, plan)
        await target_session.commit()

    quota = (
        await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == target.id))
    ).scalar_one_or_none()
    if quota is None:
        quota = TenantQuota(tenant_id=target.id, **plan.quotas)
        session.add(quota)
    else:
        for key, value in plan.quotas.items():
            setattr(quota, key, value)


async def _catalogued_feature(session: AsyncSession, code: str) -> Feature:
    """Строка каталога для ``code``, создаётся при первом обращении."""

    feature = (
        await session.execute(select(Feature).where(Feature.code == code))
    ).scalar_one_or_none()
    if feature is None:
        feature = Feature(code=code, title=FEATURE_CATALOG[code])
        session.add(feature)
        await session.flush()
    return feature


async def grant_module_trial(target: Tenant, code: str, days: int) -> datetime:
    """Выдать ``target`` модуль ``code`` на ``days`` дней (разд. 61.2, «временный доступ»).

    Возвращает момент окончания. Повторная выдача **переписывает** срок, а не
    продлевает от старого: «дай ещё на 14 дней» человек говорит, глядя на
    сегодня, а не на дату, которую он не помнит.

    Модуль вне продаваемого каталога выдать нельзя: ядро и так включено, а
    незарегистрированный код означал бы строку выдачи, которую нечем показать
    в консоли.
    """

    if code not in FEATURE_CATALOG:
        raise TrialError(
            f"модуль {code!r} не продаётся: пробный доступ выдаётся только "
            "модулям каталога (ядро включено всегда)"
        )
    if days < 1 or days > MAX_TRIAL_DAYS:
        raise TrialError(f"срок пробного доступа — от 1 до {MAX_TRIAL_DAYS} дней, получено {days}")

    expires_at = datetime.now(UTC) + timedelta(days=days)
    async with _target_session(target) as session:
        feature = await _catalogued_feature(session, code)
        enablement = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == target.id,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()
        if enablement is None:
            session.add(
                FeatureEnablement(
                    tenant_id=target.id,
                    feature_id=feature.id,
                    on=True,
                    expires_at=expires_at,
                )
            )
        elif enablement.on and enablement.expires_at is None:
            # Модуль уже выдан бессрочно (тариф или надбавка). Ставить ему срок
            # значило бы отобрать оплаченное под видом «пробного доступа».
            raise TrialError(
                f"модуль {code!r} уже выдан бессрочно — пробный доступ поверх него "
                "только ограничил бы оплаченное"
            )
        else:
            enablement.on = True
            enablement.expires_at = expires_at
        await session.commit()
    return expires_at


async def revoke_module_trial(target: Tenant, code: str) -> bool:
    """Отозвать пробный доступ досрочно. ``False`` — отзывать было нечего.

    Бессрочную выдачу не трогает: тариф отзывается сменой тарифа, иначе кнопка
    «прекратить демонстрацию» однажды снимет модуль, за который платят.
    """

    async with _target_session(target) as session:
        feature = (
            await session.execute(select(Feature).where(Feature.code == code))
        ).scalar_one_or_none()
        if feature is None:
            return False
        enablement = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == target.id,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()
        if enablement is None or enablement.expires_at is None:
            return False
        enablement.on = False
        enablement.expires_at = None
        await session.commit()
    return True


async def provision_plan(session: AsyncSession, *, tenant_id: str, plan: SubscriptionPlan) -> None:
    """Первичная выдача тарифа НОВОМУ арендатору (BIZ-53 разд. 53.1).

    Отдельная функция рядом с :func:`apply_plan` нужна из-за транзакции, а не
    из-за логики. ``apply_plan`` открывает СВОЮ сессию к схеме арендатора и
    коммитит её: для смены тарифа у живого клиента это правильно, а при
    заведении арендатор ещё не закоммичен, и вторая сессия его не увидит.
    Здесь всё пишется той же доверенной сессией, что создаёт самого
    арендатора, — либо оба шага произойдут, либо ни одного.

    Правда о тарифах одна: набор модулей и квоты берутся из того же
    ``SubscriptionPlan``, что и при смене тарифа. Ничего «для новичка»
    отдельно не настраивается — иначе консоль показывала бы тариф, которого у
    арендатора на самом деле нет.
    """

    for code, title in FEATURE_CATALOG.items():
        feature = (
            await session.execute(select(Feature).where(Feature.code == code))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code=code, title=title)
            session.add(feature)
            await session.flush()
        existing = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == tenant_id,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()
        desired = code in plan.features
        if existing is None:
            # Строка пишется и для ВЫКЛЮЧЕННОГО модуля: «продано и выключено»
            # и «никогда не выдавалось» — разные состояния, и консоль обязана
            # показывать первое, а не пустоту.
            session.add(FeatureEnablement(tenant_id=tenant_id, feature_id=feature.id, on=desired))
        else:
            existing.on = desired
            existing.expires_at = None

    quota = (
        await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if quota is None:
        session.add(TenantQuota(tenant_id=tenant_id, enforce_billing_gate=False, **plan.quotas))
    else:
        for key, value in plan.quotas.items():
            setattr(quota, key, value)
    await session.flush()
