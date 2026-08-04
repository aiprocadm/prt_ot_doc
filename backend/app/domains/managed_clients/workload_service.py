"""BIZ-49 срез-5: сбор загрузки специалистов по портфелю (разд. 49.2).

**Переиспользует готовые коллекторы**, а не повторяет их SQL: сводка внимания
(``attention_service``) и календарь (``calendar_service``) уже отвечают на
вопросы «сколько сигналов» и «сколько просрочено», и вторая реализация тех же
правил неизбежно разъехалась бы с первой — а расхождение в цифрах между
экраном загрузки и экраном внимания читается как ошибка платформы.

Цена — несколько лишних запросов на нечастом экране; она принята осознанно.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.managed_clients.attention import AggregationStatus, Severity
from app.domains.managed_clients.attention_service import collect_portfolio_attention
from app.domains.managed_clients.calendar_service import collect_portfolio_deadlines
from app.domains.managed_clients.workload import (
    DEFAULT_THRESHOLDS,
    UNASSIGNED_KEY,
    SpecialistWorkload,
    WorkloadThresholds,
    build_workload_row,
    sort_workload,
)
from app.models.managed_clients import ManagedClient
from app.models.master_data import Person

__all__ = ["collect_specialist_workload"]


def _fio(person: Person) -> str:
    parts = [person.last_name, person.first_name, person.middle_name]
    return " ".join(p for p in parts if p) or person.id


async def collect_specialist_workload(
    session: AsyncSession,
    *,
    tenant_id: str,
    today: date,
    horizon_days: int,
    thresholds: WorkloadThresholds = DEFAULT_THRESHOLDS,
    now: datetime | None = None,
) -> list[SpecialistWorkload]:
    """Загрузка по ответственным специалистам портфеля."""

    now = now or datetime.now(tz=timezone.utc)

    clients = list(
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
    if not clients:
        return []

    attention = await collect_portfolio_attention(
        session, tenant_id=tenant_id, today=today, now=now, horizon_days=horizon_days
    )
    deadlines = await collect_portfolio_deadlines(
        session, tenant_id=tenant_id, today=today, horizon_days=horizon_days, now=now
    )

    attention_by_client = {row.client_id: row for row in attention}
    overdue_by_client: dict[str, int] = {}
    for event in deadlines:
        if event.overdue:
            overdue_by_client[event.client_id] = overdue_by_client.get(event.client_id, 0) + 1

    buckets: dict[str, dict[str, int]] = {}
    for client in clients:
        key = client.responsible_person_id or UNASSIGNED_KEY
        bucket = buckets.setdefault(key, {"clients": 0, "critical": 0, "signals": 0, "overdue": 0})
        bucket["clients"] += 1
        bucket["overdue"] += overdue_by_client.get(client.id, 0)

        row = attention_by_client.get(client.id)
        if row is None:
            continue
        if row.severity is Severity.CRITICAL:
            bucket["critical"] += 1
        # У клиента «данные не собраны» (свой контур) total = None — это не ноль,
        # и приписывать специалисту чужую тишину как «нагрузки нет» нельзя;
        # видимые сигналы (договор) считаем по длине списка.
        if row.aggregation is AggregationStatus.NOT_AGGREGATED:
            bucket["signals"] += len(row.signals)
        else:
            bucket["signals"] += row.total or 0

    names: dict[str, str] = {}
    person_ids = {k for k in buckets if k != UNASSIGNED_KEY}
    if person_ids:
        persons = (
            (
                await session.execute(
                    select(Person).where(Person.id.in_(person_ids), Person.tenant_id == tenant_id)
                )
            )
            .scalars()
            .all()
        )
        names = {p.id: _fio(p) for p in persons}

    rows = [
        build_workload_row(
            person_id=key,
            # Имени может не быть (сотрудник удалён/из другой организации) —
            # тогда показываем идентификатор, но строку не прячем.
            person_name=None if key == UNASSIGNED_KEY else names.get(key, key),
            clients_total=data["clients"],
            clients_critical=data["critical"],
            signals_total=data["signals"],
            overdue_deadlines=data["overdue"],
            thresholds=thresholds,
        )
        for key, data in buckets.items()
    ]
    return sort_workload(rows)
