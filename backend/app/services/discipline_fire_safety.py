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

- средства — только действующие (``status == "active"``), не удалённые;
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
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discipline_status import FireSafetyNumbers
from app.core.disciplines import BRIEFING_TYPE_DISCIPLINE, Discipline
from app.models.fire_safety import (
    FireDrill,
    FireMaintenanceRecord,
    FireSafetyDocument,
    FireSafetyEquipment,
)
from app.services.briefing_validity import latest_briefing_validity

__all__ = [
    "FIRE_BRIEFING_TYPES",
    "FIRE_DUE_SOON_DAYS",
    "collect_fire_briefing_numbers",
    "collect_fire_safety_numbers",
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
                    FireSafetyEquipment.status == "active"
                )
            )
        )
        .scalars()
        .all()
    )
    overdue_recharge = sum(1 for r in rows if r.recharge_due is not None and r.recharge_due < today)
    overdue_inspection = sum(
        1 for r in rows if r.inspection_due is not None and r.inspection_due < today
    )
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
    overdue_drills = int(await session.scalar(pending.where(FireDrill.planned_on < today)) or 0)
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
        await session.scalar(
            documents_stmt.where(
                FireSafetyDocument.review_due.is_not(None),
                FireSafetyDocument.review_due < today,
            )
        )
        or 0
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
