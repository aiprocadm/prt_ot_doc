"""Открытые происшествия дисциплины — одна формула на контуры и разрез.

Экран каждой дисциплины (Доп. №1 разд. 57.4 «операционный дашборд по
дисциплине») показывает, сколько происшествий этой дисциплины сейчас
открыто; разрез «по дисциплинам» на управленческом дашборде показывает то же
число директору. Что такое «открытое», решено здесь один раз: не закрыто и
не отменено. Свой расчёт в каждом из пяти контуров разошёлся бы с разрезом
на первой же правке словаря статусов — и руководитель контура с директором
видели бы про одну дисциплину разное.

Срез-69: та же формула — у сводки дашборда (``/dashboard/summary``), KPI
отчётов (``/reports/kpi``), рабочего стола роли (``/workspace/role-summary``),
проекций площадок и сводки аналитики. До этого у них было пять копий: две
считали удалённые, рабочий стол не считал «корректирующие действия» — и один
человек видел на разных экранах разные числа. Сторож
``tests/test_open_incidents_formula.py`` не даёт завести шестую копию.

Для контуров считаются ТОЛЬКО размеченные происшествия (``Incident.discipline``):
платформа не угадывает дисциплину по типу события (граница среза-44).
Неразмеченное происшествие не попадает ни в один контур — оно видно в общем
реестре и отдельной строкой разреза «— не размечено».
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import Discipline
from app.models.incidents import Incident, IncidentStatus

#: Состояния, в которых происшествие уже не «открыто». Остальные — от
#: «сообщено» до «корректирующие действия» — живая работа.
FINISHED_INCIDENT_STATUSES: tuple[IncidentStatus, ...] = (
    IncidentStatus.CLOSED,
    IncidentStatus.CANCELLED,
)


def open_incidents_where(tenant_id: str) -> tuple[ColumnElement[bool], ...]:
    """Условия «открытое происшествие арендатора» — подставляются в любой запрос."""

    return (
        Incident.tenant_id == tenant_id,
        Incident.deleted_at.is_(None),
        Incident.status.notin_(list(FINISHED_INCIDENT_STATUSES)),
    )


async def open_incidents_count(
    session: AsyncSession, tenant_id: str, discipline: Discipline
) -> int:
    """Сколько открытых происшествий размечено этой дисциплиной."""

    stmt = (
        select(func.count())
        .select_from(Incident)
        .where(*open_incidents_where(tenant_id), Incident.discipline == discipline.value)
    )
    return int((await session.execute(stmt)).scalar_one() or 0)
