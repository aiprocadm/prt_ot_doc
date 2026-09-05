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
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discipline_status import FireSafetyNumbers
from app.models.fire_safety import (
    FireDrill,
    FireMaintenanceRecord,
    FireSafetyDocument,
    FireSafetyEquipment,
)

__all__ = ["FIRE_DUE_SOON_DAYS", "collect_fire_safety_numbers"]

#: горизонт «скоро истекает» — общий у сводки модуля и карточки площадки
FIRE_DUE_SOON_DAYS = 30


async def collect_fire_safety_numbers(
    session: AsyncSession,
    *,
    tenant_id: str,
    site_id: str | None = None,
    today: date | None = None,
) -> FireSafetyNumbers:
    """Числа ПБ по арендатору (``site_id=None``) или по одной площадке."""

    today = today or date.today()
    soon = today + timedelta(days=FIRE_DUE_SOON_DAYS)

    def _scoped(stmt, model):
        stmt = stmt.where(model.tenant_id == tenant_id, model.deleted_at.is_(None))
        if site_id is not None:
            stmt = stmt.where(model.site_id == site_id)
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
    )
