"""Flag gate (default off) + cross-tenant 404 isolation (P10-04).

The flag helper is tested directly (not through an endpoint) so the assertion
is about the flag decision, not about TenantContextValidator/DI side effects.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import sout as routes


def _tenant(tid="tenant-1"):
    return SimpleNamespace(id=tid)


@pytest.mark.asyncio
async def test_require_enabled_raises_when_flag_off(monkeypatch):
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=False))
    with pytest.raises(Exception) as exc:
        await routes._require_sout_enabled(AsyncMock(), _tenant())
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_require_enabled_passes_when_flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))
    await routes._require_sout_enabled(AsyncMock(), _tenant())


@pytest.mark.asyncio
async def test_require_enabled_passes_default_false_arg(monkeypatch):
    spy = AsyncMock(return_value=False)
    monkeypatch.setattr(routes, "is_module_enabled", spy)
    with pytest.raises(Exception):
        await routes._require_sout_enabled(AsyncMock(), _tenant())
    # BIZ-61 срез-2: умолчание системное (из реестра), а не аргумент вызова.
    assert spy.await_args.args[2] == "sout"


@pytest.mark.asyncio
async def test_get_campaign_cross_tenant_is_404():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    with pytest.raises(Exception) as exc:
        await routes._get_campaign(session, _tenant("tenant-1"), "campaign-owned-by-tenant-2")
    assert getattr(exc.value, "status_code", None) == 404
