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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant, TenantQuota
from app.modules.subscription.plans import FEATURE_CATALOG, SubscriptionPlan

__all__ = ["apply_plan", "read_enabled_feature_codes"]


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

    try:
        async with _target_session(target) as session:
            # Filter ``on`` in Python, not SQL: Boolean-column predicates render
            # inconsistently across Postgres/SQLite, so mirror is_feature_enabled and
            # test truthiness here.
            rows = (
                await session.execute(
                    select(Feature.code, FeatureEnablement.on)
                    .join(FeatureEnablement, FeatureEnablement.feature_id == Feature.id)
                    .where(FeatureEnablement.tenant_id == target.id)
                )
            ).all()
            return {code for code, on in rows if on and code in FEATURE_CATALOG}
    except Exception:  # noqa: BLE001 - a broken/absent tenant schema must not 500 the list
        return set()


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
            else:
                enablement.on = desired
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
