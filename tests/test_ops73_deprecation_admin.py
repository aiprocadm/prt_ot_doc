"""OPS-73 срез-3 — платформенный обзор устареваний (/admin/deprecations)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import deprecation_admin as routes
from app.services.api_deprecation_usage import record_hit

_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def _tenant(slug="platform"):
    return SimpleNamespace(id="t-1", is_active=True, slug=slug, code=slug)


@pytest.mark.asyncio
async def test_overview_returns_registry_and_usage(sessionmaker, monkeypatch):
    monkeypatch.setattr(routes, "_require_managing_admin", lambda credentials, tenant: {})
    async with sessionmaker() as session:
        await record_hit(session, tenant_slug="demo", path_prefix="/api/v1/files-legacy", when=_NOW)
        await session.commit()
        out = await routes.deprecation_overview(session=session, tenant=_tenant(), credentials=None)
    assert any(e.path_prefix == "/api/v1/files-legacy" for e in out.registry)
    assert out.registry[0].successor
    assert len(out.usage) == 1
    assert out.usage[0].tenant_slug == "demo"
    assert out.usage[0].hits_2xx == 1


@pytest.mark.asyncio
async def test_overview_requires_managing_admin(sessionmaker):
    """Без токена управляющий гейт отвечает 401 — данные межарендаторские."""
    async with sessionmaker() as session:
        with pytest.raises(HTTPException) as exc:
            await routes.deprecation_overview(
                session=session, tenant=_tenant(slug="regular"), credentials=None
            )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_партнёру_платформенный_обзор_закрыт(sessionmaker, monkeypatch):
    """BIZ-52 срез-2: кабинет партнёра открылся, а этот раздел — нет.

    Здесь видно потребление ВСЕХ арендаторов платформы, поэтому уровень
    проверяется явно: партнёр получает отказ с кодом `PLATFORM_OWNER_ONLY`.
    Без этого теста расширение кабинета однажды прихватило бы и эту страницу.

    Подменяем только «кто пришёл» — сам отказ выдаёт НАСТОЯЩИЙ
    `_require_managing_admin`, иначе тест проверял бы собственную подделку.
    """

    import app.api.routes.platform_tenants as platform_routes
    from app.domains.reseller import FleetScope, TenantLevel

    reseller_scope = FleetScope(level=TenantLevel.RESELLER, owner_id="t-1")
    monkeypatch.setattr(
        platform_routes,
        "_require_fleet_actor",
        lambda credentials, tenant: ({}, reseller_scope),
    )
    async with sessionmaker() as session:
        with pytest.raises(HTTPException) as exc:
            await routes.deprecation_overview(
                session=session, tenant=_tenant(slug="partner"), credentials=None
            )
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "PLATFORM_OWNER_ONLY"
