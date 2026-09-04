"""Просрочки по дисциплинам — одна формула на Центр внимания и разрез руководителя.

Центр внимания (разд. 57.2) считает просрочки по дисциплинам из общего
календарного агрегатора: что считается просрочкой медосмотра или выдачи СИЗ,
решено в ``CalendarAggregatorService`` и покрыто его тестами. Разрез
«по дисциплинам» на управленческом дашборде (разд. 57.4) показывает ТЕ ЖЕ
числа руководителю. Формула здесь одна на двоих намеренно: второй расчёт
рядом разошёлся бы с первым на первой же правке, и директор с специалистом
видели бы про одну дисциплину разное.

Считаются ТОЛЬКО размеченные источники (``SOURCE_DISCIPLINE``): у остальных
дисциплина не хранится, и их строки некуда отнести. Дисциплина без единого
размеченного источника просрочек НЕ ИМЕЕТ — не «ноль», а «не считается»;
кто показывает такую строку, обязан отличать одно от другого
(``ATTENTION_DISCIPLINES``).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import SOURCE_DISCIPLINE, Discipline, attention_sources, discipline_of
from app.schemas.calendar import CalendarEventsResponse
from app.services.calendar_aggregator import CalendarAggregatorService

#: Насколько глубоко в прошлое смотрит Центр внимания. Просрочку двухлетней
#: давности он не покажет: это уже не «внимание», а разбор архива, и такой
#: запрос стоил бы посадочной странице лишних строк на каждый источник.
DISCIPLINE_LOOKBACK = timedelta(days=180)

#: Насколько вперёд: близкий срок — три дня, как у задач в том же центре.
DISCIPLINE_LOOKAHEAD = timedelta(days=3)

#: Дисциплины, у которых есть хотя бы один размеченный источник сроков —
#: только по ним просрочка вообще считается.
ATTENTION_DISCIPLINES: frozenset[Discipline] = frozenset(SOURCE_DISCIPLINE.values())


async def attention_events(
    *,
    session: AsyncSession,
    tenant_id: str,
    person_id: str | None,
    now: datetime,
) -> CalendarEventsResponse:
    """События внимания по размеченным источникам в окне центра внимания."""

    service = CalendarAggregatorService(tenant_id=tenant_id, db=session)
    return await service.list_events(
        from_at=now - DISCIPLINE_LOOKBACK,
        to_at=now + DISCIPLINE_LOOKAHEAD,
        source_types=attention_sources(person_id=person_id),
        person_id=person_id,
        include_sla=True,
    )


def overdue_by_discipline(response: CalendarEventsResponse) -> dict[Discipline, int]:
    """Честные итоги просрочек: сумма COUNT'ов источников, а не длина списка."""

    overdue: dict[Discipline, int] = {}
    for source in response.by_source:
        discipline = discipline_of(source.source_type)
        if discipline is None:
            continue
        overdue[discipline] = overdue.get(discipline, 0) + int(source.overdue_count or 0)
    return overdue
