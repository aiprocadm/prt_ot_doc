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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature, FeatureEnablement

__all__ = ["is_feature_enabled", "is_module_enabled"]


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
    """

    stmt = (
        select(FeatureEnablement.on)
        .join(Feature, Feature.id == FeatureEnablement.feature_id)
        .where(
            FeatureEnablement.tenant_id == tenant_id,
            Feature.code == code,
        )
    )
    enabled = (await session.execute(stmt)).scalar_one_or_none()
    if enabled is None:
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
