"""BIZ-51 срез-7: прогон авто-аудита по клиентам арендатора (разд. 51.3).

Отделено от чистой сборки (``audit_report.py``): здесь SQL и обход клиентов.

**Прогон идемпотентен по дате.** Тик ретраится Celery, а владелец может нажать
«собрать сейчас» после тика: отчёт за ту же дату не пишется второй раз —
дубликаты еженедельных отчётов превратили бы динамику в шум.

**Dedicated пропускается и СЧИТАЕТСЯ.** Данные такого клиента живут в его
собственном арендаторе — отчёт «по нулям» был бы враньём (правило «Центра
внимания»). Пропуск виден числом в итоге, а не молчит.

**Происшествия — по компании клиента, той же формулой, что у директора
(срез-52).** ``open_incidents_where`` + ``Incident.company_id``: заказчик
читает в отчёте те же числа, что аутсорсер видит в разрезе по дисциплинам,
только суженные до его организации.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.managed_clients.audit_report import build_report
from app.domains.managed_clients.change_feed import ChangeStatus, title_for
from app.domains.managed_clients.lifecycle import ManagedClientMode
from app.domains.managed_clients.readiness import build_directions
from app.domains.managed_clients.readiness_service import collect_client_numbers
from app.models.client_changes import ClientAuditReport, ClientChange
from app.models.incidents import Incident
from app.models.managed_clients import ManagedClient
from app.services.discipline_applicability import collect_applicability, only_applicable
from app.services.discipline_incidents import open_incidents_where

__all__ = ["AUDIT_PERIOD_DAYS", "AuditRunOutcome", "run_tenant_audit"]

#: Неделя — как в ТЗ («напр. еженедельно»).
AUDIT_PERIOD_DAYS = 7


@dataclass(frozen=True)
class AuditRunOutcome:
    """Честный итог прогона: каждая судьба клиента — отдельным числом."""

    created: int
    already_current: int
    skipped_dedicated: int


async def _changes_by_kind(
    session: AsyncSession, tenant_id: str, client_id: str, period_start: date
) -> dict[str, int]:
    rows = (
        await session.execute(
            select(ClientChange.kind, func.count())
            .where(
                ClientChange.tenant_id == tenant_id,
                ClientChange.managed_client_id == client_id,
                ClientChange.deleted_at.is_(None),
                ClientChange.happened_on >= period_start,
            )
            .group_by(ClientChange.kind)
        )
    ).all()
    counter: Counter[str] = Counter()
    for kind, count in rows:
        counter[title_for(kind)] += int(count or 0)
    return dict(counter)


async def _unhandled_count(session: AsyncSession, tenant_id: str, client_id: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).where(
                    ClientChange.tenant_id == tenant_id,
                    ClientChange.managed_client_id == client_id,
                    ClientChange.deleted_at.is_(None),
                    ClientChange.status == ChangeStatus.NEW,
                )
            )
        ).scalar_one()
        or 0
    )


async def _incidents_by_discipline(
    session: AsyncSession, tenant_id: str, company_id: str
) -> tuple[dict[str, int], int]:
    """Открытые происшествия компании клиента: по коду дисциплины + без разметки."""

    rows = (
        await session.execute(
            select(Incident.discipline, func.count())
            .where(*open_incidents_where(tenant_id), Incident.company_id == company_id)
            .group_by(Incident.discipline)
        )
    ).all()
    by_discipline: dict[str, int] = {}
    unmarked = 0
    for discipline, count in rows:
        if discipline is None:
            unmarked += int(count or 0)
        else:
            by_discipline[str(discipline)] = int(count or 0)
    return by_discipline, unmarked


async def _report_exists(
    session: AsyncSession, tenant_id: str, client_id: str, period_end: date
) -> bool:
    found = (
        await session.execute(
            select(ClientAuditReport.id)
            .where(
                ClientAuditReport.tenant_id == tenant_id,
                ClientAuditReport.managed_client_id == client_id,
                ClientAuditReport.period_end == period_end,
            )
            .limit(1)
        )
    ).first()
    return found is not None


async def run_tenant_audit(
    session: AsyncSession,
    tenant_id: str,
    *,
    today: date | None = None,
) -> AuditRunOutcome:
    """Собрать отчёты авто-аудита по всем Shared-клиентам арендатора.

    Ничего не коммитит — транзакцией владеет вызывающий.
    """

    today = today or datetime.now(tz=timezone.utc).date()
    period_start = today - timedelta(days=AUDIT_PERIOD_DAYS)

    clients = (
        (
            await session.execute(
                select(ManagedClient).where(
                    ManagedClient.tenant_id == tenant_id,
                    ManagedClient.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    # Редакция — у исполнителя одна на всех клиентов: спрашиваем один раз.
    applicability = await collect_applicability(session, tenant_id)
    created = already = skipped = 0
    for client in clients:
        if client.mode is ManagedClientMode.DEDICATED or not client.company_id:
            skipped += 1
            continue
        if await _report_exists(session, tenant_id, str(client.id), today):
            already += 1
            continue

        numbers = await collect_client_numbers(
            session, tenant_id=tenant_id, company_id=str(client.company_id), today=today
        )
        directions = only_applicable(
            build_directions(
                medical=numbers.medical,
                ppe=numbers.ppe,
                training_overdue=numbers.training_overdue,
                road_safety=numbers.road_safety,
            ),
            applicability,
        )
        incidents_open, incidents_unmarked = await _incidents_by_discipline(
            session, tenant_id, str(client.company_id)
        )
        content = build_report(
            period_start=period_start,
            period_end=today,
            directions=directions,
            changes_by_kind=await _changes_by_kind(
                session, tenant_id, str(client.id), period_start
            ),
            changes_unhandled=await _unhandled_count(session, tenant_id, str(client.id)),
            incidents_open=incidents_open,
            incidents_unmarked=incidents_unmarked,
            not_applicable=applicability.hidden_titles,
        )
        session.add(
            ClientAuditReport(
                tenant_id=tenant_id,
                managed_client_id=str(client.id),
                period_start=period_start,
                period_end=today,
                overall=content.overall,
                summary=content.summary,
                payload=content.payload,
            )
        )
        created += 1

    if created:
        await session.flush()
    return AuditRunOutcome(created=created, already_current=already, skipped_dedicated=skipped)
