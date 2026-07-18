"""Рендер печатных форм 29н (контингент + поименный список): БД → DOCX/PDF.

Зеркало services/work_permit_print.py: загрузка через domains/medical/service →
сборка снимка → чистый python-docx сборщик → опц. PDF через LibreOffice.
RenderedDoc / PdfRendererUnavailable объявлены локально (модуль не зависит от
work_permits) — как локальные RU-словари в чистых сборщиках репо."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.medical import print_form as pf
from app.domains.medical import service as medsvc
from app.models.models import Tenant

logger = logging.getLogger(__name__)

_DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MEDIA = "application/pdf"
_PDF_TIMEOUT_S = 45


class PdfRendererUnavailable(Exception):
    """LibreOffice недоступен/таймаут (роут → 503)."""


@dataclass
class RenderedDoc:
    content: bytes
    filename: str
    media_type: str


def _factor_tuples(factors: list[dict]) -> list[tuple[str, str]]:
    return [(f["code"], f["name"]) for f in factors]


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


async def _to_pdf(docx_bytes: bytes, *, base_name: str) -> RenderedDoc:
    try:
        from app.modules.pdf.convert import convert_docx_bytes
        from app.modules.pdf.service_pool import LibreOfficePool

        # soffice — синхронный subprocess (до 45с): уводим в поток, чтобы не
        # блокировать event loop FastAPI для конкурентных запросов.
        pdf_bytes, _sha = await asyncio.to_thread(
            convert_docx_bytes,
            source_bytes=docx_bytes,
            timeout_s=_PDF_TIMEOUT_S,
            pool=LibreOfficePool(),
            passport=None,
        )
    except Exception as exc:  # soffice отсутствует / таймаут / сбой конвертации
        logger.warning("medical print: PDF conversion failed: %s", exc, exc_info=True)
        raise PdfRendererUnavailable(str(exc)) from exc
    return RenderedDoc(content=pdf_bytes, filename=f"{base_name}.pdf", media_type=_PDF_MEDIA)


async def render_contingent_register(
    session: AsyncSession, *, tenant: Tenant, fmt: str = "docx"
) -> RenderedDoc:
    today = datetime.now(timezone.utc).date()
    rows = await medsvc.build_contingent_register(session, tenant_id=str(tenant.id), today=today)
    data = pf.RegisterPrintData(
        org_header=tenant.name or tenant.slug,
        generated_at=today.isoformat(),
        rows=[
            pf.RegisterPrintRow(
                position_name=r["position_name"],
                factors=_factor_tuples(r["factors"]),
                headcount=r["headcount"],
                exam_kinds=r["exam_kinds"],
                periodicity_months=r.get("periodicity_months"),
            )
            for r in rows
        ],
    )
    docx_bytes = pf.build_contingent_register_docx(data)
    base_name = "medical-contingent-register"
    if fmt == "pdf":
        return await _to_pdf(docx_bytes, base_name=base_name)
    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)


async def render_named_list(
    session: AsyncSession, *, tenant: Tenant, fmt: str = "docx"
) -> RenderedDoc:
    today = datetime.now(timezone.utc).date()
    rows = await medsvc.build_named_list(session, tenant_id=str(tenant.id), today=today)
    data = pf.NamedListPrintData(
        org_header=tenant.name or tenant.slug,
        generated_at=today.isoformat(),
        rows=[
            pf.NamedListPrintRow(
                full_name=r["full_name"],
                position_name=r.get("position_name"),
                department=r.get("department"),
                factors=_factor_tuples(r["factors"]),
                required_kinds=r["required_kinds"],
                last_exam_date=_iso(r.get("last_exam_date")),
                next_due_date=_iso(r.get("next_due_date")),
                status=r["status"],
            )
            for r in rows
        ],
    )
    docx_bytes = pf.build_named_list_docx(data)
    base_name = "medical-named-list"
    if fmt == "pdf":
        return await _to_pdf(docx_bytes, base_name=base_name)
    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)
