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

__all__ = ["is_feature_enabled"]


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
