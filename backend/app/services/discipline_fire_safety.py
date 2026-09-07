"""Сроки пожарной безопасности объекта — одна формула на сводку и карточку (срез-82).

Разд. 54.1 «Аналитика ПБ: состояние объектов, просрочки ТО/перезарядки,
готовность к проверке МЧС». Сводка модуля ``/fire-safety/readiness`` считала
эти числа по всему арендатору у себя в ручке; карточка площадки 360° (разд.
57.1 — «статус по всем применимым дисциплинам на одном экране») про ПБ
говорила только «учёт не ведётся». Второй расчёт рядом разошёлся бы с первым
на первой же правке — как разошлись бы светофоры клиента и площадки, не
вынеси их в ``discipline_numbers`` (срез-3). Поэтому формула здесь одна и
принимает ``site_id``: сводка модуля считает без него (весь арендатор),
карточка — с ним (один объект).

Правила счёта — те, что были в сводке, слово в слово:

- средства — только эксплуатируемые (``FIRE_EQUIPMENT_ACTIVE_STATUS``, срез-111:
  состояние стало закрытым словарём), не удалённые;
  просрочка — ``recharge_due < today`` / ``inspection_due < today``; «скоро» —
  в горизонте ``FIRE_DUE_SOON_DAYS`` от сегодня включительно;
- «без записи о работах» — средство, у которого нет НИ ОДНОЙ не удалённой
  ``FireMaintenanceRecord``: срок стоит, а подтвердить его нечем;
- тренировка без протокола (``held_on IS NULL``) — срок: просрочена, если
  ``planned_on < today``, назначена — если позже; проведённая — факт, и
  последняя из них даёт ``last_drill_on``;
- документ — срок только с датой пересмотра; бессрочный не считается.

Средство, тренировка или документ БЕЗ площадки (``site_id IS NULL``) в счёт
арендатора входят, а в счёт площадки — нет: приписать их одной из площадок
значило бы угадать.

Противопожарные инструктажи (срез-83) — единственный ПОИМЁННЫЙ срок ПБ, как
удостоверение водителя у БДД. Люди площадки известны через рабочее место
(``domains/sites/overview._site_people``), поэтому формула принимает
``person_ids``: ``None`` — весь арендатор (сводка модуля), список — люди
площадки (карточка), пустой список — ноль. Считается не запись, а
**человек × вид**: у одного человека по одному виду берётся самая поздняя
дата ``valid_until``; она в прошлом — просрочка, в горизонте — «скоро»,
дальше — действует. Иначе старая запись, которую давно перекрыл свежий
повторный инструктаж, красила бы площадку красным навсегда — светофор, которому
перестают верить. Запись без человека (журнал без привязки) — сама себе
ключ, перекрыть её нечем; запись без ``valid_until`` — бессрочная, не срок.
Виды не перекрывают друг друга: повторный не закрывает истёкший ПТМ (это
другая обязанность), а первичный обычно без срока.

Карточка сотрудника (срез-84) считает ПБ одного человека —
``collect_fire_briefing_numbers``: те же инструктажи, но без объектов
(``objects_counted=False``): средства, тренировки и документы — сроки
площадки, у человека их нет.

Само правило «человек × вид по самой поздней дате действия» живёт в
``services/briefing_validity.latest_briefing_validity`` (срез-85) и не
привязано к пожарным видам: вкладка инструктажей карточки сотрудника считает
им «просрочено» по всем видам и помечает перекрытые записи, — иначе строка
ПБ и вкладка на одной карточке говорили бы разное про одну и ту же запись.

Светофор клиента (срез-86, разд. 51.3) — та же формула по СПИСКУ площадок
(``site_ids`` — площадки организации клиента) и его людям: у клиента
площадок много, а сводка арендатора приписала бы ему огнетушители всех
клиентов сразу. Средство без площадки к клиенту не относится — как и к
одной площадке: чьё оно, платформа не угадывает.

Сводка внимания по портфелю клиентов (срез-87, разд. 49.2) считает ОДНО
число — просрочки ПБ — сразу по всем организациям
(``collect_fire_safety_overdue_by_company``): портфель бывает на сотню
клиентов, и шесть запросов на каждого превратили бы экран в сотни
round-trip'ов. Слагаемые — те же, что у ``FireSafetyNumbers.overdue``
(перезарядка, поверка, тренировки, документы, инструктажи), и предикаты у
двух функций общие: второй экземпляр формулы разошёлся бы с первым.

Календарь портфеля (срез-92, разд. 49.2) — те же слагаемые, но с ДАТОЙ:
``collect_fire_safety_deadlines_by_company`` отдаёт каждый срок ПБ
организаций клиентов в окне дат (просрочка + горизонт) с предметом «что
именно и где». Отбор записей — тот же, что у сигнала (действующее средство
площадки организации, тренировка без протокола, документ с датой
пересмотра, инструктаж работающего человека по самой поздней записи
человек × вид), поэтому просроченных в календаре столько же, сколько в
сигнале — с двумя оговорками, общими для всего календаря: окно смотрит в
прошлое на год, а «сегодня» в календаре ещё не просрочка (в сигнале срок
инструктажа сравнивается с моментом ``now``).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discipline_status import FireSafetyNumbers
from app.core.disciplines import BRIEFING_TYPE_DISCIPLINE, BRIEFING_TYPE_TITLES, Discipline
from app.models.fire_safety import (
    FIRE_EQUIPMENT_ACTIVE_STATUS,
    FireDrill,
    FireMaintenanceRecord,
    FireSafetyDocument,
    FireSafetyEquipment,
)
from app.models.master_data import Person, Site
from app.services.briefing_validity import latest_briefing_validity
from app.services.person_scope import employed_person_where

__all__ = [
    "FIRE_BRIEFING_TYPES",
    "FIRE_DUE_SOON_DAYS",
    "FireSafetyDeadline",
    "collect_fire_briefing_numbers",
    "collect_fire_safety_deadlines_by_company",
    "collect_fire_safety_numbers",
    "collect_fire_safety_overdue_by_company",
]

#: горизонт «скоро истекает» — общий у сводки модуля и карточки площадки
FIRE_DUE_SOON_DAYS = 30

#: виды инструктажа, которые относятся к ПБ, — из закрытого словаря, а не
#: по префиксу «fire_»: словарь — единственное место, где вид получает дисциплину
FIRE_BRIEFING_TYPES: tuple[str, ...] = tuple(
    code
    for code, discipline in BRIEFING_TYPE_DISCIPLINE.items()
    if discipline is Discipline.FIRE_SAFETY
)


def _recharge_overdue(unit: FireSafetyEquipment, today: date) -> bool:
    return unit.recharge_due is not None and unit.recharge_due < today


def _inspection_overdue(unit: FireSafetyEquipment, today: date) -> bool:
    return unit.inspection_due is not None and unit.inspection_due < today


def _overdue_drill_where(today: date) -> tuple:
    """Тренировка без протокола, чей срок прошёл."""

    return (FireDrill.held_on.is_(None), FireDrill.planned_on < today)


def _overdue_document_where(today: date) -> tuple:
    """Документ с датой пересмотра в прошлом; бессрочный — не срок."""

    return (FireSafetyDocument.review_due.is_not(None), FireSafetyDocument.review_due < today)


async def _fire_briefing_numbers(
    session: AsyncSession,
    *,
    tenant_id: str,
    person_ids: Sequence[str] | None,
    now: datetime,
) -> tuple[int, int, int]:
    """(просрочено, скоро истекает, действует) — по человеку × виду, не по записи."""

    latest = await latest_briefing_validity(
        session, tenant_id=tenant_id, person_ids=person_ids, briefing_types=FIRE_BRIEFING_TYPES
    )
    soon = now + timedelta(days=FIRE_DUE_SOON_DAYS)
    overdue = sum(1 for value in latest.values() if value < now)
    due_soon = sum(1 for value in latest.values() if now <= value <= soon)
    return overdue, due_soon, len(latest) - overdue - due_soon


async def collect_fire_briefing_numbers(
    session: AsyncSession,
    *,
    tenant_id: str,
    person_ids: Sequence[str],
    now: datetime | None = None,
) -> FireSafetyNumbers:
    """ПБ этих людей без объектов — только их инструктажи (карточка сотрудника)."""

    overdue, due_soon, valid = await _fire_briefing_numbers(
        session,
        tenant_id=tenant_id,
        person_ids=person_ids,
        now=now or datetime.now(tz=timezone.utc),
    )
    return FireSafetyNumbers(
        due_soon_days=FIRE_DUE_SOON_DAYS,
        overdue_briefings=overdue,
        briefings_due_soon=due_soon,
        briefings_valid=valid,
        objects_counted=False,
    )


async def collect_fire_safety_numbers(
    session: AsyncSession,
    *,
    tenant_id: str,
    site_id: str | None = None,
    site_ids: Sequence[str] | None = None,
    person_ids: Sequence[str] | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> FireSafetyNumbers:
    """Числа ПБ по арендатору, по одной площадке или по списку площадок.

    ``site_id`` — одна площадка (карточка 360°); ``site_ids`` — площадки
    клиента (светофор клиента, срез-86), ``[]`` — ни одной; вместе их не
    задают. ``person_ids`` — чьи противопожарные инструктажи считать:
    ``None`` — всех людей арендатора, список — только этих, ``[]`` — никого.
    """

    if site_id is not None and site_ids is not None:
        raise ValueError("site_id и site_ids вместе не задают: одна площадка или список")

    today = today or date.today()
    now = now or datetime.now(tz=timezone.utc)
    soon = today + timedelta(days=FIRE_DUE_SOON_DAYS)

    def _scoped(stmt, model):
        stmt = stmt.where(model.tenant_id == tenant_id, model.deleted_at.is_(None))
        if site_id is not None:
            stmt = stmt.where(model.site_id == site_id)
        if site_ids is not None:
            stmt = stmt.where(model.site_id.in_(list(site_ids)))
        return stmt

    rows = (
        (
            await session.execute(
                _scoped(select(FireSafetyEquipment), FireSafetyEquipment).where(
                    FireSafetyEquipment.status == FIRE_EQUIPMENT_ACTIVE_STATUS
                )
            )
        )
        .scalars()
        .all()
    )
    overdue_recharge = sum(1 for r in rows if _recharge_overdue(r, today))
    overdue_inspection = sum(1 for r in rows if _inspection_overdue(r, today))
    due_soon = sum(
        1
        for r in rows
        if (r.recharge_due is not None and today <= r.recharge_due <= soon)
        or (r.inspection_due is not None and today <= r.inspection_due <= soon)
    )
    confirmed_ids: set[str] = set()
    if rows:
        confirmed_ids = {
            str(row)
            for row in (
                await session.execute(
                    select(FireMaintenanceRecord.equipment_id.distinct()).where(
                        FireMaintenanceRecord.tenant_id == tenant_id,
                        FireMaintenanceRecord.deleted_at.is_(None),
                        FireMaintenanceRecord.equipment_id.in_([r.id for r in rows]),
                    )
                )
            ).scalars()
        }
    without_maintenance = sum(1 for r in rows if str(r.id) not in confirmed_ids)

    pending = _scoped(select(func.count()).select_from(FireDrill), FireDrill).where(
        FireDrill.held_on.is_(None)
    )
    overdue_drills = int(await session.scalar(pending.where(*_overdue_drill_where(today))) or 0)
    planned_drills = int(await session.scalar(pending.where(FireDrill.planned_on >= today)) or 0)
    last_drill_on = await session.scalar(
        _scoped(select(func.max(FireDrill.held_on)), FireDrill).where(
            FireDrill.held_on.is_not(None)
        )
    )

    documents_stmt = _scoped(
        select(func.count()).select_from(FireSafetyDocument), FireSafetyDocument
    )
    documents = int(await session.scalar(documents_stmt) or 0)
    overdue_documents = int(
        await session.scalar(documents_stmt.where(*_overdue_document_where(today))) or 0
    )

    overdue_briefings, briefings_due_soon, briefings_valid = await _fire_briefing_numbers(
        session, tenant_id=tenant_id, person_ids=person_ids, now=now
    )

    return FireSafetyNumbers(
        units=len(rows),
        overdue_recharge=overdue_recharge,
        overdue_inspection=overdue_inspection,
        due_soon=due_soon,
        due_soon_days=FIRE_DUE_SOON_DAYS,
        without_maintenance=without_maintenance,
        overdue_drills=overdue_drills,
        planned_drills=planned_drills,
        last_drill_on=last_drill_on,
        days_since_last_drill=((today - last_drill_on).days if last_drill_on is not None else None),
        documents=documents,
        overdue_documents=overdue_documents,
        overdue_briefings=overdue_briefings,
        briefings_due_soon=briefings_due_soon,
        briefings_valid=briefings_valid,
    )


async def collect_fire_safety_overdue_by_company(
    session: AsyncSession,
    *,
    tenant_id: str,
    company_ids: Sequence[str],
    today: date | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Просрочек ПБ по организациям клиентов — сразу по портфелю (срез-87).

    Слагаемые те же, что у ``FireSafetyNumbers.overdue`` для одного клиента
    (``collect_fire_safety_numbers(site_ids=..., person_ids=...)``): просроченные
    перезарядка и поверка средств на площадках организации, тренировки без
    протокола со сроком в прошлом, документы с датой пересмотра в прошлом и
    противопожарные инструктажи её людей (человек × вид). Организации без
    просрочек в ответе нет.
    """

    if not company_ids:
        return {}
    today = today or date.today()
    now = now or datetime.now(tz=timezone.utc)
    wanted = list(company_ids)
    overdue: dict[str, int] = defaultdict(int)

    site_company = {
        str(site_id): str(company_id)
        for site_id, company_id in (
            await session.execute(
                select(Site.id, Site.company_id).where(
                    Site.tenant_id == tenant_id,
                    Site.company_id.in_(wanted),
                    Site.deleted_at.is_(None),
                )
            )
        ).all()
    }
    if site_company:
        site_ids = list(site_company)
        units = (
            (
                await session.execute(
                    select(FireSafetyEquipment).where(
                        FireSafetyEquipment.tenant_id == tenant_id,
                        FireSafetyEquipment.deleted_at.is_(None),
                        FireSafetyEquipment.status == FIRE_EQUIPMENT_ACTIVE_STATUS,
                        FireSafetyEquipment.site_id.in_(site_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        for unit in units:
            overdue[site_company[str(unit.site_id)]] += int(_recharge_overdue(unit, today)) + int(
                _inspection_overdue(unit, today)
            )
        for model, where in (
            (FireDrill, _overdue_drill_where(today)),
            (FireSafetyDocument, _overdue_document_where(today)),
        ):
            counted = await session.execute(
                select(model.site_id, func.count())
                .where(
                    model.tenant_id == tenant_id,
                    model.deleted_at.is_(None),
                    model.site_id.in_(site_ids),
                    *where,
                )
                .group_by(model.site_id)
            )
            for site_id, count in counted.all():
                overdue[site_company[str(site_id)]] += int(count)

    # люди — те же, что у светофора клиента: одно правило «уволенный не в счёт» (срез-89)
    person_company = {
        str(person_id): str(company_id)
        for person_id, company_id in (
            await session.execute(
                select(Person.id, Person.company_id).where(
                    Person.tenant_id == tenant_id,
                    Person.company_id.in_(wanted),
                    *employed_person_where(),
                )
            )
        ).all()
    }
    if person_company:
        latest = await latest_briefing_validity(
            session,
            tenant_id=tenant_id,
            person_ids=list(person_company),
            briefing_types=FIRE_BRIEFING_TYPES,
        )
        for (owner, _briefing_type), value in latest.items():
            if value < now:
                overdue[person_company[owner]] += 1

    return dict(overdue)


@dataclass(frozen=True)
class FireSafetyDeadline:
    """Один датированный срок ПБ организации клиента — для календаря портфеля."""

    company_id: str
    due_date: date
    #: «что именно и где»: «Перезарядка ОП-4 №1 (Склад)», «ПТМ: Иванов Иван».
    subject: str


def _person_fio(last: str | None, first: str | None, middle: str | None, fallback: str) -> str:
    return " ".join(part for part in (last, first, middle) if part) or fallback


async def collect_fire_safety_deadlines_by_company(
    session: AsyncSession,
    *,
    tenant_id: str,
    company_ids: Sequence[str],
    since: date,
    until: date,
) -> list[FireSafetyDeadline]:
    """Сроки ПБ организаций клиентов в окне ``since..until`` — для календаря (срез-92).

    Отбор записей — тот же, что у ``collect_fire_safety_overdue_by_company``:
    действующие средства площадок организации (перезарядка и поверка —
    два срока одного средства), тренировки без протокола, документы с датой
    пересмотра, противопожарные инструктажи работающих людей — по самой
    поздней записи человек × вид (перекрытая запись — не срок). Порядок —
    дело календаря; здесь только факты.
    """

    if not company_ids:
        return []
    wanted = list(company_ids)
    found: list[FireSafetyDeadline] = []

    def _in_window(value: date | None) -> bool:
        return value is not None and since <= value <= until

    sites = (
        await session.execute(
            select(Site.id, Site.name, Site.company_id).where(
                Site.tenant_id == tenant_id,
                Site.company_id.in_(wanted),
                Site.deleted_at.is_(None),
            )
        )
    ).all()
    site_company = {str(site_id): str(company_id) for site_id, _name, company_id in sites}
    site_name = {str(site_id): str(name) for site_id, name, _company_id in sites}
    if site_company:
        site_ids = list(site_company)
        units = (
            (
                await session.execute(
                    select(FireSafetyEquipment).where(
                        FireSafetyEquipment.tenant_id == tenant_id,
                        FireSafetyEquipment.deleted_at.is_(None),
                        FireSafetyEquipment.status == FIRE_EQUIPMENT_ACTIVE_STATUS,
                        FireSafetyEquipment.site_id.in_(site_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        for unit in units:
            sid = str(unit.site_id)
            where = f"{unit.label} ({site_name[sid]})"
            if _in_window(unit.recharge_due):
                found.append(
                    FireSafetyDeadline(site_company[sid], unit.recharge_due, f"Перезарядка {where}")
                )
            if _in_window(unit.inspection_due):
                found.append(
                    FireSafetyDeadline(site_company[sid], unit.inspection_due, f"Поверка {where}")
                )
        drills = (
            (
                await session.execute(
                    select(FireDrill).where(
                        FireDrill.tenant_id == tenant_id,
                        FireDrill.deleted_at.is_(None),
                        FireDrill.site_id.in_(site_ids),
                        FireDrill.held_on.is_(None),
                        FireDrill.planned_on >= since,
                        FireDrill.planned_on <= until,
                    )
                )
            )
            .scalars()
            .all()
        )
        for drill in drills:
            sid = str(drill.site_id)
            found.append(
                FireSafetyDeadline(
                    site_company[sid],
                    drill.planned_on,
                    f"Тренировка «{drill.title}» ({site_name[sid]})",
                )
            )
        documents = (
            (
                await session.execute(
                    select(FireSafetyDocument).where(
                        FireSafetyDocument.tenant_id == tenant_id,
                        FireSafetyDocument.deleted_at.is_(None),
                        FireSafetyDocument.site_id.in_(site_ids),
                        FireSafetyDocument.review_due.is_not(None),
                        FireSafetyDocument.review_due >= since,
                        FireSafetyDocument.review_due <= until,
                    )
                )
            )
            .scalars()
            .all()
        )
        for document in documents:
            sid = str(document.site_id)
            found.append(
                FireSafetyDeadline(
                    site_company[sid],
                    document.review_due,
                    f"Пересмотр «{document.title}» ({site_name[sid]})",
                )
            )

    # люди — те же, что у сигнала и светофора клиента: «уволенный не в счёт» (срез-89)
    people = (
        await session.execute(
            select(
                Person.id, Person.company_id, Person.last_name, Person.first_name, Person.middle_name
            ).where(
                Person.tenant_id == tenant_id,
                Person.company_id.in_(wanted),
                *employed_person_where(),
            )
        )
    ).all()
    person_company = {str(pid): str(company_id) for pid, company_id, *_ in people}
    person_name = {
        str(pid): _person_fio(last, first, middle, str(pid))
        for pid, _company_id, last, first, middle in people
    }
    if person_company:
        latest = await latest_briefing_validity(
            session,
            tenant_id=tenant_id,
            person_ids=list(person_company),
            briefing_types=FIRE_BRIEFING_TYPES,
        )
        for (owner, briefing_type), value in latest.items():
            if _in_window(value.date()):
                found.append(
                    FireSafetyDeadline(
                        person_company[owner],
                        value.date(),
                        f"{BRIEFING_TYPE_TITLES.get(briefing_type, briefing_type)}: "
                        f"{person_name[owner]}",
                    )
                )

    return found
