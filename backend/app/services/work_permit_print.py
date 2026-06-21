"""Ф4: загрузка наряда+связей+подписей, сборка печатного снимка, опц. бланк и PDF."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import print_form as pf
from app.models.models import Person, SignatureRequest, Tenant
from app.models.work_permit import (
    WorkPermit,
    WorkPermitBriefing,
    WorkPermitDailyAdmission,
    WorkPermitEvent,
    WorkPermitMember,
)

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


def _fmt_dt(value) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M") if value else None


def _closing_kind_label(role: str | None) -> str:
    kind = lc.role_to_closing_kind(role) if role else None
    return {"handover": "Сдал", "acceptance": "Принял"}.get(kind, role or "—")


async def _name_map(session: AsyncSession, tenant_id: str, person_ids: set) -> dict[str, str]:
    ids = {str(p) for p in person_ids if p}
    if not ids:
        return {}
    rows = (await session.execute(
        select(Person).where(Person.tenant_id == tenant_id, Person.id.in_(tuple(ids)))
    )).scalars().all()
    out: dict[str, str] = {}
    for p in rows:
        parts = [p.last_name, p.first_name]
        middle = getattr(p, "middle_name", None)
        if middle:
            parts.append(middle)
        out[str(p.id)] = " ".join(x for x in parts if x).strip()
    return out


async def render_work_permit(
    session: AsyncSession, *, tenant: Tenant, permit_id: str,
    fmt: str = "docx", with_letterhead: bool = True,
) -> RenderedDoc | None:
    tid = str(tenant.id)
    wp = (await session.execute(
        select(WorkPermit).where(WorkPermit.id == permit_id, WorkPermit.tenant_id == tid)
    )).scalar_one_or_none()
    if wp is None:
        return None

    members = (await session.execute(
        select(WorkPermitMember).where(
            WorkPermitMember.tenant_id == tid, WorkPermitMember.work_permit_id == permit_id
        ).order_by(WorkPermitMember.created_at.asc())
    )).scalars().all()

    briefings = (await session.execute(
        select(WorkPermitBriefing).where(
            WorkPermitBriefing.tenant_id == tid, WorkPermitBriefing.work_permit_id == permit_id
        ).order_by(WorkPermitBriefing.created_at.asc())
    )).scalars().all()

    admissions = (await session.execute(
        select(WorkPermitDailyAdmission).where(
            WorkPermitDailyAdmission.tenant_id == tid,
            WorkPermitDailyAdmission.work_permit_id == permit_id,
        ).order_by(WorkPermitDailyAdmission.admission_date.asc())
    )).scalars().all()

    ext_events = (await session.execute(
        select(WorkPermitEvent).where(
            WorkPermitEvent.tenant_id == tid,
            WorkPermitEvent.work_permit_id == permit_id,
            WorkPermitEvent.event_type == "extended",
        ).order_by(WorkPermitEvent.at.asc())
    )).scalars().all()

    briefing_ids = [str(b.id) for b in briefings]
    sig_object_ids = [permit_id] + briefing_ids
    signatures = (await session.execute(
        select(SignatureRequest).where(
            SignatureRequest.tenant_id == tid,
            SignatureRequest.object_type.in_(
                ("work_permit", "work_permit_briefing", "work_permit_closing")
            ),
            SignatureRequest.object_id.in_(sig_object_ids),
        ).order_by(SignatureRequest.created_at.asc())
    )).scalars().all()

    member_role_by_person: dict[str, str] = {str(m.person_id): m.role for m in members}

    person_ids: set = set()
    person_ids |= {str(m.person_id) for m in members}
    person_ids |= {str(b.conducted_by_person_id) for b in briefings if b.conducted_by_person_id}
    person_ids |= {str(a.admitted_by_person_id) for a in admissions if a.admitted_by_person_id}
    person_ids |= {str(s.signer_person_id) for s in signatures if s.signer_person_id}
    names = await _name_map(session, tid, person_ids)

    def fio(pid) -> str:
        return names.get(str(pid), "—") if pid else "—"

    # Подписи → строки SignatureLine
    sig_lines: list[pf.SignatureLine] = []
    for s in signatures:
        if s.object_type == "work_permit_closing":
            group = "closing"
            role_label = _closing_kind_label(member_role_by_person.get(str(s.signer_person_id)))
        elif s.object_type == "work_permit_briefing":
            group = "briefing"
            role_label = pf.member_role_label(member_role_by_person.get(str(s.signer_person_id), ""))
        else:
            group = "permit"
            role_label = pf.member_role_label(member_role_by_person.get(str(s.signer_person_id), ""))

        signer = fio(s.signer_person_id) if s.signer_person_id else (s.signer_name or "—")
        # эвристика режима: confirm_code_hash проставлен только в code-flow и не
        # очищается после подписи; attested-подписи его не имеют. Хрупко — при смене
        # семантики confirm_code_hash потребуется явный атрибут режима.
        mode = "code" if s.confirm_code_hash else "attested"
        sig_lines.append(pf.SignatureLine(
            group=group,
            role_label=role_label,
            fio=signer,
            status_label="Подписано" if s.status == "signed" else (s.status or "—"),
            signed_at=_fmt_dt(s.signed_at),
            mode=mode,
            hash_short=(s.content_hash[:16] if s.content_hash else "—"),
        ))

    briefing0 = briefings[0] if briefings else None
    data = pf.WorkPermitPrintData(
        number=wp.number or str(wp.id),
        work_type_label=pf.work_type_label(wp.work_type),
        status_label=pf.status_label(str(wp.status)),
        org_header=tenant.name or tenant.slug,
        subdivision=wp.subdivision_text,
        planned_start=_fmt_dt(wp.planned_start),
        planned_end=_fmt_dt(wp.planned_end),
        zone_text=wp.zone_text,
        content_text=wp.content_text,
        conditions_text=wp.conditions_text,
        equipment_text=wp.equipment_text,
        hazards_text=wp.hazards_text,
        safety_systems_labels=[pf.safety_system_label(c) for c in (wp.safety_systems or [])],
        measures_before=wp.measures_before_text,
        measures_during=wp.measures_during_text,
        special_conditions=wp.special_conditions_text,
        ppe_text=wp.ppe_text,
        members=[(pf.member_role_label(m.role), fio(m.person_id)) for m in members],
        briefing=(
            {
                "conducted_by_fio": fio(briefing0.conducted_by_person_id),
                "conducted_at": _fmt_dt(briefing0.conducted_at),
                "topics": briefing0.topics_text,
            }
            if briefing0 else None
        ),
        daily_admissions=[
            {
                "date": a.admission_date.isoformat() if a.admission_date else "",
                "start": _fmt_dt(a.start_at),
                "end": _fmt_dt(a.end_at),
                "admitted_by_fio": fio(a.admitted_by_person_id),
            }
            for a in admissions
        ],
        extensions=[
            {
                "old_end": (e.meta or {}).get("old_end"),
                "new_end": (e.meta or {}).get("new_end"),
                "at": _fmt_dt(e.at),
            }
            for e in ext_events
        ],
        completion=(
            {"text": wp.completion_text, "recorded_at": _fmt_dt(wp.completion_recorded_at)}
            if wp.completion_text else None
        ),
        closed_at=_fmt_dt(wp.closed_at),
        signatures=sig_lines,
    )

    docx_bytes = pf.build_work_permit_docx(data)

    # Фирменный бланк — best-effort (§10 спеки: сбой не должен ронять печать)
    if with_letterhead and getattr(get_settings(), "doc_pipeline_letterhead_auto", False):
        try:
            from app.modules.branding.letterhead import IssuerRef, LetterheadResolver
            from app.modules.branding.service import BrandingService
            from app.modules.headers.engine import apply_headers_to_docx

            resolver = LetterheadResolver(BrandingService(session, tenant))
            decision = await resolver.resolve(
                issuer=IssuerRef(kind="company", company_id=None),
                site_id=str(wp.site_id) if wp.site_id else None,
                doc={"title": f"Наряд-допуск {data.number}"},
                override=None,
            )
            if decision.apply:
                docx_bytes, _report = apply_headers_to_docx(
                    docx_bytes=docx_bytes,
                    preset=decision.preset,
                    context=decision.header_context,
                    watermark_override=decision.watermark,
                )
        except Exception as exc:  # best-effort: бланк не должен ронять печать
            logger.warning("work-permit print: letterhead failed: %s", exc, exc_info=True)

    base_name = f"work-permit-{(wp.number or wp.id)}"

    if fmt == "pdf":
        try:
            from app.modules.pdf.convert import convert_docx_bytes
            from app.modules.pdf.service_pool import LibreOfficePool

            pdf_bytes, _sha = convert_docx_bytes(
                source_bytes=docx_bytes,
                timeout_s=_PDF_TIMEOUT_S,
                pool=LibreOfficePool(),
                passport=None,
            )
        except Exception as exc:  # soffice отсутствует / таймаут / сбой конвертации
            raise PdfRendererUnavailable(str(exc)) from exc
        return RenderedDoc(content=pdf_bytes, filename=f"{base_name}.pdf", media_type=_PDF_MEDIA)

    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)
