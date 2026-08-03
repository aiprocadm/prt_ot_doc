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
