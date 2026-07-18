"""API-контракт декларации СОУТ (monkeypatch как test_sout_print_api.py)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.api.routes.sout as routes
from app.services.sout_print import PdfRendererUnavailable, RenderedDoc

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1", name="ООО Ромашка")


@pytest.mark.asyncio
async def test_declaration_print_docx_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(
        routes, "render_declaration",
        AsyncMock(return_value=RenderedDoc(content=b"DOCX", filename="sout-declaration.docx", media_type=_DOCX)),
    )
    resp = await routes.print_declaration(
        cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, fmt="docx",
    )
    assert resp.status_code == 200
    assert resp.media_type == _DOCX


@pytest.mark.asyncio
async def test_declaration_print_404_when_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "render_declaration", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.print_declaration(
            cid="missing", tenant=_tenant(), session=AsyncMock(), access=None, fmt="docx",
        )
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_declaration_print_503_when_pdf_unavailable(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "render_declaration", AsyncMock(side_effect=PdfRendererUnavailable("no soffice")))
    with pytest.raises(Exception) as exc:
        await routes.print_declaration(
            cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, fmt="pdf",
        )
    assert getattr(exc.value, "status_code", None) == 503


@pytest.mark.asyncio
async def test_declaration_preview_splits_eligible(monkeypatch):
    from app.domains.sout.declaration import DeclarationRow

    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_campaign", AsyncMock(return_value=SimpleNamespace(
        id="c1", name="СОУТ 2026", report_number="N1", report_date=None)))
    monkeypatch.setattr(routes, "_load_declaration_pairs", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes, "build_declaration_projection", lambda **k: [
        DeclarationRow("РМ-01", "Слесарь", "acceptable", "1", "N1", True, None),
        DeclarationRow("РМ-02", "Сварщик", "harmful_3_1", "—", "N1", False, "класс 3.1 — вредные/опасные условия"),
    ])
    out = await routes.get_declaration(
        cid="c1", tenant=_tenant(), session=AsyncMock(), access=None,
    )
    assert out.eligible_count == 1 and out.ineligible_count == 1
    assert out.eligible[0].workplace_code == "РМ-01"
    assert out.ineligible[0].ineligible_reason is not None
