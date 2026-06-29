"""Рендер декларации соответствия условий труда: БД → DOCX/PDF.

Зеркало services/sout_print.py. Переиспользует RenderedDoc / PdfRendererUnavailable
/ _to_pdf / helpers из sout_print (один контур СОУТ — DRY)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sout import declaration as decl
from app.domains.sout.print_form import SoutCardFactorRow
from app.models.sout import SoutWorkplace
from app.models.tenanting import Tenant
from app.services.sout_print import (
    _DOCX_MEDIA,
    PdfRendererUnavailable,  # noqa: F401  (re-export for route import symmetry)
    RenderedDoc,
    _iso,
    _load_campaign,
    _load_factors,
    _org_header,
    _raw,
    _to_pdf,
)


def _date_str(value) -> str | None:
    """date/datetime → ISO string; plain string returned as-is; None → None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return _iso(value)


def _report_ref(campaign) -> str | None:
    rd = getattr(campaign, "report_date", None)
    parts = [
        getattr(campaign, "report_number", None),
        f"от {_date_str(rd)}" if rd else None,
    ]
    joined = " ".join(p for p in parts if p)
    return joined or None


def build_declaration_projection(*, campaign, workplaces_with_factors) -> list[decl.DeclarationRow]:
    """Чистая сборка строк декларации (тестируется без БД)."""
    ref = _report_ref(campaign)
    rows: list[decl.DeclarationRow] = []
    for wp, factors in workplaces_with_factors:
        card_factors = [
            SoutCardFactorRow(code=f.code, name=f.name, measured_class=_raw(f.measured_class))
            for f in factors
        ]
        assessed = _raw(wp.assessed_class)
        eligible, reason = decl.evaluate_eligibility(assessed, card_factors)
        rows.append(
            decl.DeclarationRow(
                workplace_code=wp.workplace_code,
                position_name=wp.position_name,
                assessed_class=assessed,
                headcount="1" if getattr(wp, "person_id", None) else "—",
                report_ref=ref,
                eligible=eligible,
                ineligible_reason=reason,
            )
        )
    return rows


async def _load_workplaces(session: AsyncSession, tenant: Tenant, cid: str) -> list[SoutWorkplace]:
    return list(
        (
            await session.execute(
                select(SoutWorkplace)
                .where(
                    SoutWorkplace.campaign_id == cid,
                    SoutWorkplace.tenant_id == tenant.id,
                    SoutWorkplace.deleted_at.is_(None),
                )
                .order_by(SoutWorkplace.workplace_code.asc())
            )
        )
        .scalars()
        .all()
    )


async def render_declaration(
    session: AsyncSession, *, tenant: Tenant, campaign_id: str, fmt: str = "docx"
) -> RenderedDoc | None:
    campaign = await _load_campaign(session, tenant, campaign_id)
    if campaign is None:
        return None
    workplaces = await _load_workplaces(session, tenant, campaign_id)
    pairs = [(wp, await _load_factors(session, tenant, wp.id)) for wp in workplaces]
    all_rows = build_declaration_projection(campaign=campaign, workplaces_with_factors=pairs)
    data = decl.DeclarationPrintData(
        org_header=_org_header(tenant),
        generated_at=datetime.now(timezone.utc).date().isoformat(),
        campaign_name=campaign.name,
        report_number=getattr(campaign, "report_number", None),
        report_date=_iso(getattr(campaign, "report_date", None)),
        rows=[r for r in all_rows if r.eligible],  # печать — только подлежащие
    )
    docx_bytes = decl.build_declaration_docx(data)
    base_name = "sout-declaration"
    if fmt == "pdf":
        return await _to_pdf(docx_bytes, base_name=base_name)
    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)
