"""API-контракт импорта СОУТ (monkeypatch, как test_sout_print_api.py)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.api.routes.sout as routes
from app.domains.sout.import_report import UnsupportedImportFormat
from app.schemas.sout import ImportPreview, ImportResult
from app.services.sout_import import ImportValidationError


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1", name="ООО Ромашка")


def _file(name="r.csv"):
    return SimpleNamespace(filename=name, read=AsyncMock(return_value=b"x"))


@pytest.mark.asyncio
async def test_preview_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "preview_import", AsyncMock(return_value=ImportPreview(
        campaign_id="c1", rows=[], new_count=0, changed_count=0,
        unchanged_count=0, removed_count=0, error_count=0, can_apply=True,
    )))
    out = await routes.import_preview(cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, file=_file())
    assert out.campaign_id == "c1"


@pytest.mark.asyncio
async def test_preview_404_when_campaign_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "preview_import", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.import_preview(cid="nope", tenant=_tenant(), session=AsyncMock(), access=None, file=_file())
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_preview_422_on_unsupported_format(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "preview_import", AsyncMock(side_effect=UnsupportedImportFormat("pdf")))
    with pytest.raises(Exception) as exc:
        await routes.import_preview(cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, file=_file("r.pdf"))
    assert getattr(exc.value, "status_code", None) == 422


@pytest.mark.asyncio
async def test_apply_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_campaign", AsyncMock(return_value=SimpleNamespace(id="c1", status="planned")))
    monkeypatch.setattr(routes, "ensure_campaign_open", lambda s: None)
    monkeypatch.setattr(routes, "apply_import", AsyncMock(return_value=ImportResult(
        campaign_id="c1", created=2, updated=1, skipped=0, removed_detected=0, errors=[],
    )))
    out = await routes.import_apply(cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, file=_file())
    assert out.created == 2 and out.updated == 1


@pytest.mark.asyncio
async def test_apply_422_on_validation_error(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_campaign", AsyncMock(return_value=SimpleNamespace(id="c1", status="planned")))
    monkeypatch.setattr(routes, "ensure_campaign_open", lambda s: None)
    monkeypatch.setattr(routes, "apply_import", AsyncMock(side_effect=ImportValidationError(["строка 1: пустая должность"])))
    with pytest.raises(Exception) as exc:
        await routes.import_apply(cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, file=_file())
    assert getattr(exc.value, "status_code", None) == 422
