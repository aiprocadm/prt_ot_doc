"""Рендер печатных форм СОУТ (Карта СОУТ + Сводная ведомость): БД → DOCX/PDF.

Зеркало services/medical_print.py: tenant-scoped загрузка → чистая сборка снимка
→ python-docx сборщик → опц. PDF через LibreOffice. RenderedDoc /
PdfRendererUnavailable объявлены локально (модуль не зависит от medical/work_permits)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sout import print_form as pf
from app.models.sout import SoutCampaign, SoutFactor, SoutGuarantee, SoutWorkplace
from app.models.tenanting import Tenant

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


def _raw(value) -> str | None:
    """Enum-объект (.value) либо строка → raw-строка; None пропускает."""
    if value is None:
        return None
    return getattr(value, "value", value)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _org_header(tenant: Tenant) -> str:
    return getattr(tenant, "name", None) or getattr(tenant, "slug", "")


# --- чистая сборка снимков (тестируется без БД) ---
def _card_print_data(
    *, org_header, generated_at, campaign, workplace, factors, guarantees
) -> pf.SoutCardPrintData:
    return pf.SoutCardPrintData(
        org_header=org_header,
        generated_at=generated_at,
        expert_org_name=getattr(campaign, "expert_org_name", None),
        report_number=getattr(campaign, "report_number", None),
        report_date=_iso(getattr(campaign, "report_date", None)) or getattr(campaign, "report_date", None),
        workplace_code=workplace.workplace_code,
        position_name=workplace.position_name,
        assessed_class=_raw(workplace.assessed_class),
        assessment_date=_iso(getattr(workplace, "assessment_date", None)),
        next_assessment_date=_iso(getattr(workplace, "next_assessment_date", None)),
        factors=[
            pf.SoutCardFactorRow(code=f.code, name=f.name, measured_class=_raw(f.measured_class))
            for f in factors
        ],
        guarantees=[
            pf.SoutCardGuaranteeRow(kind=_raw(g.kind), detail=g.detail) for g in guarantees
        ],
    )


def _summary_print_data(
    *, org_header, generated_at, campaign, workplaces_with_factors
) -> pf.SoutSummaryPrintData:
    rows = []
    for wp, factors in workplaces_with_factors:
        card_factors = [
            pf.SoutCardFactorRow(code=f.code, name=f.name, measured_class=_raw(f.measured_class))
            for f in factors
        ]
        rows.append(
            pf.SoutSummaryRow(
                workplace_code=wp.workplace_code,
                position_name=wp.position_name,
                assessed_class=_raw(wp.assessed_class),
                harmful_factor_count=pf.harmful_factor_count(card_factors),
                next_assessment_date=_iso(getattr(wp, "next_assessment_date", None)),
            )
        )
    counts = pf.class_counts([_raw(wp.assessed_class) for wp, _ in workplaces_with_factors])
    return pf.SoutSummaryPrintData(
        org_header=org_header,
        generated_at=generated_at,
        campaign_name=campaign.name,
        expert_org_name=getattr(campaign, "expert_org_name", None),
        report_number=getattr(campaign, "report_number", None),
        report_date=_iso(getattr(campaign, "report_date", None)) or getattr(campaign, "report_date", None),
        rows=rows,
        class_counts=counts,
    )


async def _to_pdf(docx_bytes: bytes, *, base_name: str) -> RenderedDoc:
    try:
        from app.modules.pdf.convert import convert_docx_bytes
        from app.modules.pdf.service_pool import LibreOfficePool

        pdf_bytes, _sha = await asyncio.to_thread(
            convert_docx_bytes,
            source_bytes=docx_bytes,
            timeout_s=_PDF_TIMEOUT_S,
            pool=LibreOfficePool(),
            passport=None,
        )
    except Exception as exc:
        logger.warning("sout print: PDF conversion failed: %s", exc, exc_info=True)
        raise PdfRendererUnavailable(str(exc)) from exc
    return RenderedDoc(content=pdf_bytes, filename=f"{base_name}.pdf", media_type=_PDF_MEDIA)


async def _load_workplace(session: AsyncSession, tenant: Tenant, wid: str) -> SoutWorkplace | None:
    return (
        await session.execute(
            select(SoutWorkplace).where(
                SoutWorkplace.id == wid,
                SoutWorkplace.tenant_id == tenant.id,
                SoutWorkplace.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _load_campaign(session: AsyncSession, tenant: Tenant, cid: str) -> SoutCampaign | None:
    return (
        await session.execute(
            select(SoutCampaign).where(
                SoutCampaign.id == cid,
                SoutCampaign.tenant_id == tenant.id,
                SoutCampaign.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _load_factors(session: AsyncSession, tenant: Tenant, wid: str):
    return list(
        (
            await session.execute(
                select(SoutFactor).where(
                    SoutFactor.workplace_id == wid, SoutFactor.tenant_id == tenant.id
                )
            )
        ).scalars().all()
    )


async def _load_guarantees(session: AsyncSession, tenant: Tenant, wid: str):
    return list(
        (
            await session.execute(
                select(SoutGuarantee).where(
                    SoutGuarantee.workplace_id == wid, SoutGuarantee.tenant_id == tenant.id
                )
            )
        ).scalars().all()
    )


async def render_sout_card(
    session: AsyncSession, *, tenant: Tenant, workplace_id: str, fmt: str = "docx"
) -> RenderedDoc | None:
    wp = await _load_workplace(session, tenant, workplace_id)
    if wp is None:
        return None
    campaign = await _load_campaign(session, tenant, wp.campaign_id)
    factors = await _load_factors(session, tenant, workplace_id)
    guarantees = await _load_guarantees(session, tenant, workplace_id)
    data = _card_print_data(
        org_header=_org_header(tenant),
        generated_at=datetime.now(timezone.utc).date().isoformat(),
        campaign=campaign or SoutCampaign(),
        workplace=wp,
        factors=factors,
        guarantees=guarantees,
    )
    docx_bytes = pf.build_sout_card_docx(data)
    base_name = f"sout-card-{wp.workplace_code}"
    if fmt == "pdf":
        return await _to_pdf(docx_bytes, base_name=base_name)
    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)


async def render_summary_sheet(
    session: AsyncSession, *, tenant: Tenant, campaign_id: str, fmt: str = "docx"
) -> RenderedDoc | None:
    campaign = await _load_campaign(session, tenant, campaign_id)
    if campaign is None:
        return None
    workplaces = list(
        (
            await session.execute(
                select(SoutWorkplace)
                .where(
                    SoutWorkplace.campaign_id == campaign_id,
                    SoutWorkplace.tenant_id == tenant.id,
                    SoutWorkplace.deleted_at.is_(None),
                )
                .order_by(SoutWorkplace.workplace_code.asc())
            )
        ).scalars().all()
    )
    pairs = [(wp, await _load_factors(session, tenant, wp.id)) for wp in workplaces]
    data = _summary_print_data(
        org_header=_org_header(tenant),
        generated_at=datetime.now(timezone.utc).date().isoformat(),
        campaign=campaign,
        workplaces_with_factors=pairs,
    )
    docx_bytes = pf.build_summary_sheet_docx(data)
    base_name = "sout-summary"
    if fmt == "pdf":
        return await _to_pdf(docx_bytes, base_name=base_name)
    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)
