"""API-контракт печатных форм СОУТ (monkeypatch как test_sout_api.py)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.api.routes.sout as routes
from app.services.sout_print import PdfRendererUnavailable, RenderedDoc

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1", name="ООО Ромашка")


@pytest.mark.asyncio
async def test_card_print_docx_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(
        routes,
        "render_sout_card",
        AsyncMock(
            return_value=RenderedDoc(
                content=b"DOCX", filename="sout-card-РМ-01.docx", media_type=_DOCX
            )
        ),
    )
    resp = await routes.print_sout_card(
        wid="w1",
        tenant=_tenant(),
        session=AsyncMock(),
        access=None,
        fmt="docx",
    )
    assert resp.status_code == 200
    assert resp.media_type == _DOCX
    assert "attachment" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_card_print_404_when_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "render_sout_card", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.print_sout_card(
            wid="missing",
            tenant=_tenant(),
            session=AsyncMock(),
            access=None,
            fmt="docx",
        )
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_card_print_503_when_pdf_unavailable(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(
        routes, "render_sout_card", AsyncMock(side_effect=PdfRendererUnavailable("no soffice"))
    )
    with pytest.raises(Exception) as exc:
        await routes.print_sout_card(
            wid="w1",
            tenant=_tenant(),
            session=AsyncMock(),
            access=None,
            fmt="pdf",
        )
    assert getattr(exc.value, "status_code", None) == 503


@pytest.mark.asyncio
async def test_summary_print_docx_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(
        routes,
        "render_summary_sheet",
        AsyncMock(
            return_value=RenderedDoc(
                content=b"DOCX", filename="sout-summary.docx", media_type=_DOCX
            )
        ),
    )
    resp = await routes.print_summary_sheet(
        cid="c1",
        tenant=_tenant(),
        session=AsyncMock(),
        access=None,
        fmt="docx",
    )
    assert resp.status_code == 200
    assert resp.media_type == _DOCX


@pytest.mark.asyncio
async def test_summary_print_404_when_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "render_summary_sheet", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.print_summary_sheet(
            cid="missing",
            tenant=_tenant(),
            session=AsyncMock(),
            access=None,
            fmt="docx",
        )
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_summary_print_503_when_pdf_unavailable(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(
        routes, "render_summary_sheet", AsyncMock(side_effect=PdfRendererUnavailable("no soffice"))
    )
    with pytest.raises(Exception) as exc:
        await routes.print_summary_sheet(
            cid="c1",
            tenant=_tenant(),
            session=AsyncMock(),
            access=None,
            fmt="pdf",
        )
    assert getattr(exc.value, "status_code", None) == 503
