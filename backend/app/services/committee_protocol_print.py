"""Срез-4: сборка печатной формы протокола заседания комитета (DOCX/PDF).

Зеркало work_permit_print: сервис грузит заседание со связями и ФИО,
чистый domains/committees/print_form.py собирает DOCX; PDF — через
LibreOffice-пул (503 наружу, если конвертер недоступен).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.committees import print_form as pf
from app.domains.committees.lifecycle import decision_outcome, tally_votes
from app.models.committees import (
    Committee,
    CommitteeAgendaItem,
    CommitteeDecision,
    CommitteeDecisionTask,
    CommitteeDecisionVote,
    CommitteeMeeting,
    CommitteeMeetingAttendance,
    CommitteeMeetingInvitation,
)
from app.models.master_data import Person

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


def _fmt_dt(value) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M") if value else None


async def _fio_map(session: AsyncSession, tenant_id: str, person_ids: set[str]) -> dict[str, str]:
    ids = {str(p) for p in person_ids if p}
    if not ids:
        return {}
    rows = (
        (
            await session.execute(
                select(Person).where(Person.id.in_(ids), Person.tenant_id == tenant_id)
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, str] = {}
    for p in rows:
        parts = [p.last_name, p.first_name, p.middle_name]
        out[p.id] = " ".join(x for x in parts if x)
    return out


async def render_committee_protocol(
    session: AsyncSession,
    *,
    tenant_id: str,
    meeting: CommitteeMeeting,
    fmt: str,
) -> RenderedDoc:
    """Собрать печатную форму для ПРОВЕДЁННОГО заседания (проверяет роут)."""
    committee = (
        await session.execute(
            select(Committee).where(
                Committee.id == meeting.committee_id, Committee.tenant_id == tenant_id
            )
        )
    ).scalar_one()

    attendance = (
        (
            await session.execute(
                select(CommitteeMeetingAttendance).where(
                    CommitteeMeetingAttendance.meeting_id == meeting.id,
                    CommitteeMeetingAttendance.tenant_id == tenant_id,
                )
            )
        )
        .scalars()
        .all()
    )
    invitations = (
        (
            await session.execute(
                select(CommitteeMeetingInvitation).where(
                    CommitteeMeetingInvitation.meeting_id == meeting.id,
                    CommitteeMeetingInvitation.tenant_id == tenant_id,
                )
            )
        )
        .scalars()
        .all()
    )
    agenda = (
        (
            await session.execute(
                select(CommitteeAgendaItem)
                .where(
                    CommitteeAgendaItem.meeting_id == meeting.id,
                    CommitteeAgendaItem.tenant_id == tenant_id,
                )
                .order_by(CommitteeAgendaItem.seq.asc())
            )
        )
        .scalars()
        .all()
    )
    decisions = (
        (
            await session.execute(
                select(CommitteeDecision)
                .where(
                    CommitteeDecision.meeting_id == meeting.id,
                    CommitteeDecision.tenant_id == tenant_id,
                )
                .order_by(CommitteeDecision.decided_at.asc())
            )
        )
        .scalars()
        .all()
    )
    agenda_by_id = {a.id: a for a in agenda}

    person_ids: set[str] = {a.person_id for a in attendance} | {i.person_id for i in invitations}
    decision_rows: list[tuple[CommitteeDecision, list, list]] = []
    for d in decisions:
        tasks = (
            (
                await session.execute(
                    select(CommitteeDecisionTask).where(
                        CommitteeDecisionTask.decision_id == d.id,
                        CommitteeDecisionTask.tenant_id == tenant_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        votes = (
            (
                await session.execute(
                    select(CommitteeDecisionVote).where(
                        CommitteeDecisionVote.decision_id == d.id,
                        CommitteeDecisionVote.tenant_id == tenant_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        person_ids |= {t.assignee_person_id for t in tasks if t.assignee_person_id}
        decision_rows.append((d, list(tasks), list(votes)))

    fio = await _fio_map(session, tenant_id, person_ids)

    def _fio(pid: str | None) -> str:
        if not pid:
            return "—"
        return fio.get(pid, pid)

    blocks: list[pf.DecisionBlock] = []
    for seq, (d, tasks, votes) in enumerate(decision_rows, start=1):
        votes_for, votes_against, votes_abstain = tally_votes([v.choice for v in votes])
        outcome = decision_outcome(votes_for, votes_against).value if votes else None
        agenda_item = agenda_by_id.get(d.agenda_item_id) if d.agenda_item_id else None
        blocks.append(
            pf.DecisionBlock(
                seq=seq,
                agenda_title=agenda_item.title if agenda_item else None,
                text=d.text,
                votes_for=votes_for,
                votes_against=votes_against,
                votes_abstain=votes_abstain,
                outcome_label=pf.outcome_label(outcome),
                tasks=[
                    (
                        _fio(t.assignee_person_id),
                        t.due_date.isoformat() if t.due_date else None,
                        pf.task_status_label(
                            t.status.value if hasattr(t.status, "value") else str(t.status)
                        ),
                    )
                    for t in tasks
                ],
            )
        )

    protocol_no = (
        f"{meeting.protocol_seq}/{meeting.protocol_year}"
        if meeting.protocol_seq is not None and meeting.protocol_year is not None
        else "б/н"
    )
    data = pf.CommitteeProtocolPrintData(
        committee_name=committee.name,
        kind_label=pf.kind_label(
            committee.kind.value if hasattr(committee.kind, "value") else str(committee.kind)
        ),
        protocol_no=protocol_no,
        held_at=_fmt_dt(meeting.held_at),
        location=meeting.location,
        quorum_text=pf.quorum_label(
            meeting.quorum_met,
            meeting.present_count,
            meeting.members_total,
            committee.quorum_threshold_pct,
        ),
        attendance=[(_fio(a.person_id), a.present) for a in attendance],
        invited=[_fio(i.person_id) for i in invitations],
        agenda=[a.title for a in agenda],
        decisions=blocks,
    )
    docx_bytes = pf.build_protocol_docx(data)

    base_name = f"committee-protocol-{protocol_no.replace('/', '-')}"
    if fmt == "pdf":
        try:
            from app.modules.pdf.convert import convert_docx_bytes
            from app.modules.pdf.service_pool import LibreOfficePool

            # soffice — синхронный subprocess (до 45с): в поток, чтобы не
            # блокировать event loop.
            pdf_bytes, _sha = await asyncio.to_thread(
                convert_docx_bytes,
                source_bytes=docx_bytes,
                timeout_s=_PDF_TIMEOUT_S,
                pool=LibreOfficePool(),
                passport=None,
            )
        except Exception as exc:  # soffice отсутствует / таймаут / сбой конвертации
            logger.warning("committee protocol print: PDF failed: %s", exc, exc_info=True)
            raise PdfRendererUnavailable(str(exc)) from exc
        return RenderedDoc(content=pdf_bytes, filename=f"{base_name}.pdf", media_type=_PDF_MEDIA)
    return RenderedDoc(content=docx_bytes, filename=f"{base_name}.docx", media_type=_DOCX_MEDIA)
