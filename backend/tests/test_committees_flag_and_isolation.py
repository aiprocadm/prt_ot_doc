"""Flag gate (default off) + cross-tenant 404 isolation (P10-01).

The flag helper is tested directly (not through an endpoint) so the assertion
is about the flag decision, not about TenantContextValidator/DI side effects.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import committees as routes


def _tenant(tid="tenant-1"):
    return SimpleNamespace(id=tid)


@pytest.mark.asyncio
async def test_require_enabled_raises_when_flag_off(monkeypatch):
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=False))
    with pytest.raises(Exception) as exc:
        await routes._require_committees_enabled(AsyncMock(), _tenant())
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_require_enabled_passes_when_flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=True))
    await routes._require_committees_enabled(AsyncMock(), _tenant())


@pytest.mark.asyncio
async def test_require_enabled_passes_default_false_arg(monkeypatch):
    spy = AsyncMock(return_value=False)
    monkeypatch.setattr(routes, "is_feature_enabled", spy)
    with pytest.raises(Exception):
        await routes._require_committees_enabled(AsyncMock(), _tenant())
    assert spy.await_args.kwargs.get("default") is False


@pytest.mark.asyncio
async def test_get_committee_cross_tenant_is_404():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    with pytest.raises(Exception) as exc:
        await routes._get_committee(session, _tenant("tenant-1"), "committee-owned-by-tenant-2")
    assert getattr(exc.value, "status_code", None) == 404
