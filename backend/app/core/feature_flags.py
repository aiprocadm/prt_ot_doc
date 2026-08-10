"""Per-tenant pilot feature-flag resolution (docs/FEATURE_FLAGS.md).

The shared ``feature`` catalogue (:class:`~app.models.feature.Feature`, a
SharedModel) defines pilot flags; ``featureenablement``
(:class:`~app.models.feature.FeatureEnablement`, a TenantBaseModel) carries the
per-tenant overrides. The two live in different declarative metadatas, so there
is intentionally no SQLAlchemy ForeignKey between them (see
``app/models/feature.py``); the relationship is expressed as an explicit join
here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature, FeatureEnablement

__all__ = ["as_utc", "grant_expired", "is_feature_enabled", "is_module_enabled"]


def as_utc(moment: datetime | None) -> datetime | None:
    """Привести момент к UTC-осведомлённому виду.

    SQLite хранит время без зоны и отдаёт наивную дату. Дальше она либо
    роняет сравнение (``TypeError`` ровно в момент проверки доступа), либо
    уходит в ответ API — и консоль показывает «до 24.08 09:00» без указания,
    в чьих это часах.
    """

    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def grant_expired(expires_at: datetime | None, *, now: datetime | None = None) -> bool:
    """Истёк ли срок выдачи (BIZ-61 срез-3, разд. 61.2 «временный доступ»).

    ``None`` — бессрочная выдача, не истекает никогда.

    Срок сверяется ПРИ ЧТЕНИИ, а не гасится фоновой задачей. Задача
    выполняется раз в сутки (или падает), и всё это время модуль остаётся
    открытым после окончания пробного периода — то есть бесплатным. Дата в
    строке отвечает точно.

    Наивная дата читается как UTC (см. :func:`as_utc`).
    """

    moment = as_utc(expires_at)
    if moment is None:
        return False
    return moment <= (now or datetime.now(UTC))


async def is_feature_enabled(
    session: AsyncSession,
    tenant_id: str,
    code: str,
    *,
    default: bool = True,
) -> bool:
    """Return whether pilot feature ``code`` is enabled for ``tenant_id``.

    Default-on: when the tenant has no ``FeatureEnablement`` row for the feature
    — including when the feature is absent from the shared catalogue entirely —
    the ``default`` (``True``) applies. An explicit row returns its ``on`` value,
    so a tenant opts out only by storing ``FeatureEnablement(on=False)``.

    Строка с истёкшим ``expires_at`` не действует — применяется ``default``
    (BIZ-61 срез-3, разд. 61.2).
    """

    stmt = (
        select(FeatureEnablement.on, FeatureEnablement.expires_at)
        .join(Feature, Feature.id == FeatureEnablement.feature_id)
        .where(
            FeatureEnablement.tenant_id == tenant_id,
            Feature.code == code,
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return default
    enabled, expires_at = row
    if grant_expired(expires_at):
        # Срок вышел — строка больше не действует, отвечает умолчание. Не жёсткое
        # «выключено»: у модуля ядра умолчание «включено», и просроченное
        # временное ОТКЛЮЧЕНИЕ обязано вернуть его, а не оставить погашенным.
        return default
    return bool(enabled)


class UnknownModuleError(LookupError):
    """Гейт поставлен на код, которого нет в реестре модулей."""


async def is_module_enabled(session: AsyncSession, tenant_id: str, code: str) -> bool:
    """Выдан ли арендатору модуль ``code`` (BIZ-61, разд. 61.2).

    **Умолчание — ВЫКЛЮЧЕНО**, и это системное свойство, а не договорённость
    на каждой точке вызова. Разд. 61.2 требует обратной логики к прежней
    default-on: «по умолчанию заказчик видит только ядро + модули своей
    редакции, остальное выключено, пока не выдано явно».

    Почему одной договорённости было мало: у :func:`is_feature_enabled`
    умолчание ``True``, и четыре гейта вызывали её БЕЗ ``default=False`` —
    «Подрядчики», «Медосмотры» и «Склад СИЗ» оставались доступны арендатору,
    у которого просто нет строки о выдаче. Модуль, который не продавали,
    открывался сам.

    Модули ядра выключить нельзя — для них умолчание ``True``.

    Неизвестный код — ГРОМКАЯ ошибка, а не «наверное, выключено»: гейт на
    незарегистрированный модуль означает, что модуль не попадёт ни в тариф,
    ни в консоль, и разбираться будут по жалобе заказчика.
    """

    from app.modules.subscription.registry import MODULE_REGISTRY  # noqa: PLC0415 - цикл

    module = next((item for item in MODULE_REGISTRY if item.code == code), None)
    if module is None:
        raise UnknownModuleError(
            f"модуль {code!r} не зарегистрирован в реестре "
            "(app/modules/subscription/registry.py) — гейт без записи в реестре "
            "не попадёт ни в тариф, ни в консоль"
        )
    return await is_feature_enabled(session, tenant_id, code, default=module.is_core)
