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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.medical import lifecycle as lc
from app.domains.medical import print_form as pf
from app.domains.medical import service as medsvc
from app.models.master_data import Person, Position
from app.models.medical import MedicalReferral
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


async def render_referral(
    session: AsyncSession, *, tenant: Tenant, referral: MedicalReferral, fmt: str = "docx"
) -> RenderedDoc:
    """Печать направления на медосмотр: работник + вредные факторы 29н его должности → DOCX/PDF."""
    today = datetime.now(timezone.utc).date()
    person = (
        await session.execute(
            select(Person)
            .where(Person.id == referral.person_id, Person.tenant_id == str(tenant.id))
            .options(
                selectinload(Person.position).selectinload(Position.hazards),
                selectinload(Person.workplace),
            )
        )
    ).scalar_one_or_none()

    full_name = "—"
    position_name: str | None = None
    department: str | None = None
    birth_date: str | None = None
    snils: str | None = None
    factors: list[tuple[str, str]] = []
    if person is not None:
        full_name = " ".join(
            part for part in (person.last_name, person.first_name, person.middle_name) if part
        ).strip() or "—"
        position_name = person.position.name if person.position else person.position_title
        department = person.workplace.name if person.workplace else None
        birth_date = _iso(person.birth_date)
        snils = person.snils
        if person.position is not None:
            catalog = await medsvc._load_factor_catalog(session, tenant_id=str(tenant.id))
            codes = {
                h.medical_factor_code for h in person.position.hazards if h.medical_factor_code
            }
            factors = sorted(
                ((f[0], f[1]) for f in lc.factors_for_hazards(codes, catalog)),
                key=lambda x: x[0],
            )

    kind = referral.exam_kind
    data = pf.ReferralPrintData(
        org_header=tenant.name or tenant.slug,
        generated_at=today.isoformat(),
        full_name=full_name,
        birth_date=birth_date,
        position_name=position_name,
        department=department,
        exam_kind=kind.value if hasattr(kind, "value") else str(kind),
        medical_org_name=referral.medical_org_name,
        due_date=_iso(referral.due_at),
        snils=snils,
        factors=factors,
    )
    docx_bytes = pf.build_referral_docx(data)
    base_name = f"medical-referral-{referral.id}"
    if fmt == "pdf":
        return await _to_pdf(docx_bytes, base_name=base_name)
    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)
