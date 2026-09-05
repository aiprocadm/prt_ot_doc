"""Карточка площадки 360° (BIZ-54-57 срез-3, Доп. №1 разд. 57.1).

ТЗ: «на одном экране — обязательства и статус по ВСЕМ применимым дисциплинам,
а не отдельные экраны на каждую». Приёмка §58.3 повторяет то же требование
отдельной строкой.

## Что здесь своё, а что берётся общим

Светофор дисциплин считается ОБЩИМ счётом
(``app/services/discipline_numbers.py``) и красится ОБЩИМИ правилами
(``app/core/discipline_status.py``) — теми же, что у светофора клиента. Своего
здесь ровно одно: **кто такие «люди площадки»**.

## Пожарная безопасность — по объекту, не по людям (срез-82, разд. 54.1)

У площадки есть свои сроки ПБ: перезарядка и поверка средств защиты,
плановые тренировки, пересмотр документов. Считаются они той же формулой,
что сводка готовности модуля ПБ (``app/services/discipline_fire_safety.py``),
только по одной площадке; красятся общим правилом
(``core/discipline_status.fire_safety_status``): просрочка — красный, срок
в горизонте — жёлтый, порядок — «не измеряется» с фактом, зелёного не бывает.
Средство без площадки к площадке не относится — как человек без рабочего
места.

## Применимые дисциплины — по выданным модулям (срез-54, приёмка §58.3)

Дисциплины, модуль которых арендатору не выдан или выключен, на карточке не
показываются (``app/services/discipline_applicability.py``) — и НЕ молча:
они названы строкой в «не посчитано». Единственная применимость, которая
следует из данных самой площадки, — ОПО → промышленная безопасность; она
дописывается в расшифровку, если модуль ПромБеза выдан.

## Люди площадки — через рабочее место, и это видно

Сотрудник привязан к площадке только через рабочее место
(``Person.workplace_id`` → ``Workplace.site_id``). У кого рабочего места нет —
к площадке НЕ относится, и молча включить его в счёт «по площадке» нельзя: это
приписало бы площадке чужие разрывы. Но и молчать нельзя — иначе зелёная
карточка означала бы «у площадки всё хорошо» там, где половина людей компании
просто не разнесена по рабочим местам. Поэтому такие люди названы отдельным
числом.

## Наряды-допуски: дисциплина есть у части видов работ

Вид работ — ЗАКРЫТЫЙ список из шести (``domains/work_permits/lifecycle.py``), и
у двух видов дисциплина следует из закона: огневые работы — пожарная
безопасность, газоопасные — промышленная. Остальные четыре относятся к общей
охране труда, отдельной дисциплины для неё в словаре нет (см.
``app/core/disciplines.py``).

**Факт не красит светофор.** Наличие нарядов-допусков дописывается к
расшифровке дисциплины, но цвет остаётся прежним: наряд — это документ о
работах, а не доказательство соответствия. Перекрасить ПБ в зелёный из-за
оформленных нарядов значило бы выдать активность за порядок.

## Чего здесь НЕТ и почему (граница среза)

Проверки, инциденты и риски к площадке привязаны, но каждая из этих сущностей
живёт в БОЛЬШЕ ЧЕМ ОДНОЙ таблице (``models/checks.py``, ``models/inspections.py``
и ``models/safety_ops.py``; ``models/incidents.py`` и ``models/safety_ops.py``).
Счётчик по одной из них выдал бы часть за целое — это хуже, чем отсутствие
счётчика. Поэтому они названы в ``NOT_COUNTED`` с причиной, а не показаны
числом. Разбор дублирующих реестров — отдельная работа.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discipline_status import (
    DisciplineStatus,
    FireSafetyNumbers,
    TrafficLight,
    build_discipline_statuses,
    with_extra_reason,
    worst_light,
)
from app.core.disciplines import (
    UNMAPPED_PERMIT_WORK_TYPES,
    Discipline,
    discipline_of_permit,
)
from app.models.master_data import EmploymentStatus, Person, Site, Workplace
from app.models.work_permit import WorkPermit
from app.services.discipline_applicability import (
    ALL_APPLICABLE,
    DisciplineApplicability,
    collect_applicability,
    only_applicable,
)
from app.services.discipline_fire_safety import collect_fire_safety_numbers
from app.services.discipline_numbers import DisciplineNumbers, collect_people_numbers

__all__ = [
    "NOT_COUNTED",
    "OPEN_PERMIT_STATUSES",
    "PermitFacts",
    "SiteFacts",
    "SiteOverview",
    "build_site_overview",
    "collect_site_overview",
]

#: Наряд-допуск считается действующим, пока он выдан или приостановлен.
#: Черновик — ещё не работа, закрытый и отменённый — уже не работа.
OPEN_PERMIT_STATUSES: tuple[str, ...] = ("issued", "suspended")

#: Что к площадке привязано, но на карточке НЕ считается — с причиной.
#: Молчание про это однажды прочитали бы как «ничего такого у площадки нет».
NOT_COUNTED: tuple[tuple[str, str], ...] = (
    (
        "Проверки",
        "в системе три таблицы проверок (checks, inspections, safety_ops); "
        "счётчик по одной выдал бы часть за целое",
    ),
    (
        "Инциденты",
        "в системе две таблицы инцидентов (incidents, safety_ops); "
        "счётчик по одной выдал бы часть за целое",
    ),
    (
        "Риски",
        "в системе три таблицы рисков (risk, risk_card, risk_map); "
        "счётчик по одной выдал бы часть за целое",
    ),
)

#: Названия видов работ — зеркало печатной формы наряда-допуска.
_WORK_TYPE_TITLES: dict[str, str] = {
    "hot_work": "огневые работы",
    "gas_hazardous": "газоопасные работы",
    "height": "работа на высоте",
    "confined_space": "замкнутые пространства",
    "excavation": "земляные работы",
    "electrical": "электроустановки",
}


@dataclass(frozen=True)
class PermitFacts:
    """Действующие наряды-допуски площадки, разложенные по дисциплинам."""

    total: int = 0
    by_discipline: dict[Discipline, int] = field(default_factory=dict)
    without_discipline: int = 0
    #: Виды работ без дисциплины — названиями, чтобы «прочее» не было немым.
    without_discipline_titles: tuple[str, ...] = ()
    #: ПОЧЕМУ у них нет дисциплины. Без этой строки «без дисциплины: 1» читалось
    #: бы как недоделка разметки, а не как решение.
    without_discipline_reason: str = ""


@dataclass(frozen=True)
class SiteFacts:
    """Факты площадки: то, что можно пересчитать, а не оценить."""

    workplaces: int = 0
    people: int = 0
    #: Люди КОМПАНИИ площадки, у которых рабочего места нет вовсе. Число
    #: компании, а не площадки: у площадки таких людей быть не может.
    people_without_workplace: int = 0
    permits: PermitFacts = field(default_factory=PermitFacts)


@dataclass(frozen=True)
class SiteOverview:
    site_id: str
    name: str
    company_id: str
    address: str | None
    hazard_class: str | None
    is_hazardous_production_facility: bool
    opo_register_number: str | None
    overall: TrafficLight
    disciplines: list[DisciplineStatus]
    facts: SiteFacts
    not_counted: tuple[tuple[str, str], ...] = NOT_COUNTED


def _permit_notes(facts: PermitFacts) -> dict[Discipline, str]:
    """Наблюдения про наряды-допуски — к дисциплинам, которым они принадлежат."""

    return {
        discipline: f"К площадке привязано действующих нарядов-допусков: {count}"
        for discipline, count in facts.by_discipline.items()
        if count
    }


def build_site_overview(
    site: Site,
    *,
    numbers: DisciplineNumbers,
    facts: SiteFacts,
    applicability: DisciplineApplicability = ALL_APPLICABLE,
    fire_safety: FireSafetyNumbers | None = None,
) -> SiteOverview:
    """Собрать карточку из чисел и фактов. Без базы — правила проверяемы построчно.

    ``fire_safety`` — сроки ПБ самой площадки (срез-82); без них строка ПБ
    остаётся с причиной словаря, как у светофора клиента.
    """

    rows = only_applicable(
        build_discipline_statuses(
            medical=numbers.medical,
            ppe=numbers.ppe,
            training_overdue=numbers.training_overdue,
            road_safety=numbers.road_safety,
            fire_safety=fire_safety,
        ),
        applicability,
    )

    notes = _permit_notes(facts.permits)
    if site.is_hazardous_production_facility:
        # Единственная дисциплина, чья ПРИМЕНИМОСТЬ следует из данных площадки.
        # У остальных применимость в системе не хранится вовсе, и выводить её
        # из названия площадки значило бы решать за специалиста.
        register = site.opo_register_number or "без регистрационного номера"
        opo = f"Площадка учтена как ОПО ({register})"
        existing = notes.get(Discipline.INDUSTRIAL_SAFETY)
        notes[Discipline.INDUSTRIAL_SAFETY] = f"{opo}. {existing}" if existing else opo

    rows = with_extra_reason(rows, notes)
    return SiteOverview(
        site_id=str(site.id),
        name=site.name,
        company_id=str(site.company_id),
        address=site.address,
        hazard_class=site.hazard_class,
        is_hazardous_production_facility=bool(site.is_hazardous_production_facility),
        opo_register_number=site.opo_register_number,
        overall=worst_light(rows),
        disciplines=rows,
        facts=facts,
        not_counted=_not_counted(applicability),
    )


def _not_counted(applicability: DisciplineApplicability) -> tuple[tuple[str, str], ...]:
    """Постоянный список «не посчитано» плюс скрытые по редакции дисциплины."""

    if not applicability.hidden:
        return NOT_COUNTED
    return (
        *NOT_COUNTED,
        (
            "Дисциплины вне редакции",
            f"{', '.join(applicability.hidden_titles)} — модуль не выдан арендатору "
            "или выключен; статус по ним не считается и в итог не входит",
        ),
    )


async def _site_workplace_ids(session: AsyncSession, tenant_id: str, site_id: str) -> list[str]:
    rows = (
        await session.execute(
            select(Workplace.id).where(
                Workplace.tenant_id == tenant_id,
                Workplace.site_id == site_id,
                Workplace.deleted_at.is_(None),
            )
        )
    ).scalars()
    return [str(row) for row in rows]


async def _site_people(
    session: AsyncSession, tenant_id: str, workplace_ids: list[str]
) -> list[Person]:
    if not workplace_ids:
        return []
    rows = (
        await session.execute(
            select(Person).where(
                Person.tenant_id == tenant_id,
                Person.workplace_id.in_(workplace_ids),
                Person.deleted_at.is_(None),
                Person.employment_status != EmploymentStatus.TERMINATED,
            )
        )
    ).scalars()
    return list(rows)


async def _people_without_workplace(session: AsyncSession, tenant_id: str, company_id: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).where(
                    Person.tenant_id == tenant_id,
                    Person.company_id == company_id,
                    Person.workplace_id.is_(None),
                    Person.deleted_at.is_(None),
                    Person.employment_status != EmploymentStatus.TERMINATED,
                )
            )
        ).scalar_one()
        or 0
    )


async def _permit_facts(session: AsyncSession, tenant_id: str, site_id: str) -> PermitFacts:
    rows = (
        await session.execute(
            select(WorkPermit.work_type, func.count())
            .where(
                WorkPermit.tenant_id == tenant_id,
                WorkPermit.site_id == site_id,
                WorkPermit.status.in_(OPEN_PERMIT_STATUSES),
            )
            .group_by(WorkPermit.work_type)
        )
    ).all()

    by_discipline: Counter[Discipline] = Counter()
    without = 0
    titles: list[str] = []
    total = 0
    for work_type, raw_count in rows:
        count = int(raw_count or 0)
        total += count
        discipline = discipline_of_permit(str(work_type))
        if discipline is None:
            without += count
            titles.append(_WORK_TYPE_TITLES.get(str(work_type), str(work_type)))
        else:
            by_discipline[discipline] += count
    return PermitFacts(
        total=total,
        by_discipline=dict(by_discipline),
        without_discipline=without,
        without_discipline_titles=tuple(sorted(titles)),
        without_discipline_reason=UNMAPPED_PERMIT_WORK_TYPES if without else "",
    )


async def collect_site_overview(
    session: AsyncSession,
    *,
    tenant_id: str,
    site: Site,
    today: date | None = None,
    now: datetime | None = None,
) -> SiteOverview:
    """Собрать карточку площадки 360° одним проходом по базе."""

    site_id = str(site.id)
    workplace_ids = await _site_workplace_ids(session, tenant_id, site_id)
    people = await _site_people(session, tenant_id, workplace_ids)
    numbers = await collect_people_numbers(
        session, tenant_id=tenant_id, people=people, today=today, now=now
    )
    facts = SiteFacts(
        workplaces=len(workplace_ids),
        people=len(people),
        people_without_workplace=await _people_without_workplace(
            session, tenant_id, str(site.company_id)
        ),
        permits=await _permit_facts(session, tenant_id, site_id),
    )
    applicability = await collect_applicability(session, tenant_id)
    fire_safety = await collect_fire_safety_numbers(
        session, tenant_id=tenant_id, site_id=site_id, today=today
    )
    return build_site_overview(
        site,
        numbers=numbers,
        facts=facts,
        applicability=applicability,
        fire_safety=fire_safety,
    )
