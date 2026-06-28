"""API-контракт каскада СОУТ (monkeypatch + прямой вызов route-функций, как test_sout_import_api.py)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.api.routes.sout as routes
from app.domains.sout.lifecycle import CampaignTransitionError
from app.schemas.sout import CascadePreview, CascadeResult


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1", name="ООО Ромашка")


@pytest.mark.asyncio
async def test_preview_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "preview_cascade", AsyncMock(return_value=CascadePreview(
        assessed_class="harmful_3_1", can_apply=True, medical=[], ppe_advisory=[],
    )))
    out = await routes.cascade_preview(wid="w1", tenant=_tenant(), session=AsyncMock(), access=None)
    assert out.assessed_class == "harmful_3_1"


@pytest.mark.asyncio
async def test_preview_404_when_workplace_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "preview_cascade", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.cascade_preview(wid="nope", tenant=_tenant(), session=AsyncMock(), access=None)
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_apply_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "apply_cascade", AsyncMock(return_value=CascadeResult(
        created=1, reclassified=0, conflicts=0, ppe_advisory_count=2,
    )))
    out = await routes.cascade_apply(wid="w1", tenant=_tenant(), session=AsyncMock(), access=None)
    assert out.created == 1 and out.ppe_advisory_count == 2


@pytest.mark.asyncio
async def test_apply_404_when_workplace_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "apply_cascade", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.cascade_apply(wid="nope", tenant=_tenant(), session=AsyncMock(), access=None)
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_apply_409_when_campaign_closed(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "apply_cascade", AsyncMock(
        side_effect=CampaignTransitionError("Campaign roster is editable only while planned/in_progress")
    ))
    with pytest.raises(Exception) as exc:
        await routes.cascade_apply(wid="w1", tenant=_tenant(), session=AsyncMock(), access=None)
    assert getattr(exc.value, "status_code", None) == 409
