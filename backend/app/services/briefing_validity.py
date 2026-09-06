"""Срок инструктажа — по человеку × виду, а не по записи (срез-85).

Инструктаж записывают в журнал снова и снова: повторный — каждые полгода,
ПТМ — раз в несколько лет, и старые записи остаются навсегда. Считай
платформа «просрочено» по каждой записи, у любого давно работающего
человека была бы просрочка, которой нет, — светофор, которому перестают
верить. Поэтому у одного человека по одному виду берётся САМАЯ ПОЗДНЯЯ дата
действия: она в прошлом — просрочка, дальше — действует, а старые записи
того же вида — перекрытые, не нарушение.

Правило одно на всех потребителей: строку ПБ карточки площадки и сотрудника
и сводку модуля ПБ (``discipline_fire_safety``, только пожарные виды) и
вкладку инструктажей карточки сотрудника (все виды). Ленты — календарь,
Центр внимания, обход просрочек — по-прежнему считают записи: там каждая
истёкшая запись — событие.

Границы:

- владелец — человек; у записи без человека владелец — она сама: перекрыть
  её нечем;
- запись без ``valid_until`` — бессрочная, не срок, в правило не входит;
- виды друг друга не перекрывают: повторный не закрывает истёкший ПТМ;
- «уволенный не в счёт» (срез-94): без списка людей берутся только
  работающие (``person_scope``) и записи без человека — сводка модуля ПБ
  считала истёкший ПТМ уволенного, тогда как карточки, портфель и общий
  календарь его уже не считают. Явный список — ровно эти люди: кого считать,
  решил вызывающий (карточка сотрудника у уволенного светофор не считает
  вовсе).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.feature_flags import as_utc
from app.models.briefings import BriefingEntry
from app.services.person_scope import not_employed_person_ids

__all__ = ["latest_briefing_validity"]


async def latest_briefing_validity(
    session: AsyncSession,
    *,
    tenant_id: str,
    person_ids: Sequence[str] | None,
    briefing_types: Sequence[str] | None = None,
) -> dict[tuple[str, str], datetime]:
    """{(владелец, вид): самая поздняя дата действия} — одна на человека и вид.

    Владелец — человек, а у записи без человека — она сама: перекрыть её
    нечем. Записи без ``valid_until`` — бессрочные, не срок — не входят.
    ``person_ids=None`` — все работающие люди арендатора и записи без
    человека, ``[]`` — никто; ``briefing_types=None`` — все виды словаря.
    """

    if person_ids is not None and not person_ids:
        return {}
    owner = func.coalesce(BriefingEntry.person_id, BriefingEntry.id)
    stmt = (
        select(owner, BriefingEntry.briefing_type, func.max(BriefingEntry.valid_until))
        .where(
            BriefingEntry.tenant_id == tenant_id,
            BriefingEntry.deleted_at.is_(None),
            BriefingEntry.valid_until.is_not(None),
        )
        .group_by(owner, BriefingEntry.briefing_type)
    )
    if briefing_types is not None:
        stmt = stmt.where(BriefingEntry.briefing_type.in_(list(briefing_types)))
    if person_ids is not None:
        stmt = stmt.where(BriefingEntry.person_id.in_(list(person_ids)))
    else:
        stmt = stmt.where(
            or_(
                BriefingEntry.person_id.is_(None),
                BriefingEntry.person_id.not_in(not_employed_person_ids(tenant_id)),
            )
        )
    latest: dict[tuple[str, str], datetime] = {}
    for owner_id, briefing_type, value in (await session.execute(stmt)).all():
        moment = as_utc(value)
        if moment is not None:
            latest[(str(owner_id), str(briefing_type))] = moment
    return latest
