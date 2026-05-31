"""Unit tests for per-tenant pilot feature-flag resolution
(``app.core.feature_flags.is_feature_enabled``) — W-A / TZ-3.2-V11-01.

These run without the FastAPI app harness (which cannot be imported on this
Py3.13/Windows environment — native access violation in the create_app import
chain), so they verify the gate's core semantics directly against an in-memory
SQLite database: default-on when no row exists, explicit off -> disabled,
explicit on -> enabled, and per-tenant isolation.

Each scenario runs inside a single ``asyncio.run`` (engine created within the
coroutine) so the aiosqlite connection never crosses event loops.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

_WAREHOUSE = "warehouse"


async def _resolve(seeds, query_tenant: str, code: str = _WAREHOUSE) -> bool:
    """Build a fresh in-memory DB, apply ``seeds`` and resolve the flag.

    ``seeds`` is a list of ``(tenant_id, code | None, on | None)`` tuples:
    ``code is None`` seeds only the tenant; ``on is None`` seeds the feature but
    no per-tenant enablement row.
    """

    from app.core.feature_flags import is_feature_enabled
    from app.models.feature import Feature, FeatureEnablement
    from app.models.models import Tenant

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        # Copy the three tables into a fresh MetaData so every FK referent
        # (notably the always-present tenant_id -> tenant cross-base FK, which
        # the runtime mirror normally resolves) is present locally for DDL.
        md = MetaData()
        for src in (Tenant.__table__, Feature.__table__, FeatureEnablement.__table__):
            src.to_metadata(md, schema=None)
        async with engine.begin() as conn:
            await conn.run_sync(md.create_all)

        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            tenants: set[str] = set()
            features: dict[str, str] = {}
            for tenant_id, feature_code, on in seeds:
                if tenant_id not in tenants:
                    session.add(
                        Tenant(
                            id=tenant_id,
                            slug=f"t-{tenant_id}",
                            name="T",
                            contact_email=f"{tenant_id}@example.com",
                        )
                    )
                    tenants.add(tenant_id)
                if feature_code is not None and feature_code not in features:
                    feature = Feature(code=feature_code, title=feature_code.title())
                    session.add(feature)
                    await session.flush()
                    features[feature_code] = feature.id
                if feature_code is not None and on is not None:
                    session.add(
                        FeatureEnablement(
                            tenant_id=tenant_id, feature_id=features[feature_code], on=on
                        )
                    )
            await session.commit()

        async with maker() as session:
            return await is_feature_enabled(session, query_tenant, code)
    finally:
        await engine.dispose()


def test_default_on_when_no_enablement_row() -> None:
    assert asyncio.run(_resolve([("tenant-1", None, None)], "tenant-1")) is True


def test_default_on_when_feature_exists_but_no_tenant_row() -> None:
    # Feature(code="warehouse") exists globally but this tenant has no override.
    assert asyncio.run(_resolve([("tenant-1", _WAREHOUSE, None)], "tenant-1")) is True


def test_disabled_when_enablement_off() -> None:
    assert asyncio.run(_resolve([("tenant-1", _WAREHOUSE, False)], "tenant-1")) is False


def test_enabled_when_enablement_on() -> None:
    assert asyncio.run(_resolve([("tenant-1", _WAREHOUSE, True)], "tenant-1")) is True


def test_other_tenants_disable_does_not_leak() -> None:
    seeds = [("tenant-2", _WAREHOUSE, False), ("tenant-1", None, None)]
    assert asyncio.run(_resolve(seeds, "tenant-1")) is True
    assert asyncio.run(_resolve(seeds, "tenant-2")) is False
