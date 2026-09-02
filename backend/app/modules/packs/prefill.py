"""Подсказки мастера фабрики из реестров (решение владельца, handoff #960).

ЗАЧЕМ. Три комплекта отчётности подряд — экология (разд. 55.3), БДД (56.2) и
ГО-ЧС (56.1) — заставили написать одну и ту же границу: «числа в отчёт вносит
специалист, платформа их из реестров не собирает». При этом реестры полны:
парк, водители, ДТП, нарушения. Человек открывает отчёт и вручную переписывает
в него то, что система уже знает.

ГЛАВНОЕ РЕШЕНИЕ: ПОДСКАЗКА, А НЕ ОТВЕТ.

Значение из реестра приходит в поле ``suggested`` и НЕ становится ответом само
собой. Причина не в осторожности, а в том, чьё имя стоит под документом:
отчёт подписывает специалист, и он отвечает за каждое число в нём. Подставь
платформа число молча — и человек подпишет то, чего не проверял, а расхождение
реестра с действительностью станет ЕГО расхождением.

Поэтому подсказка всегда приходит С ИСТОЧНИКОМ («ДТП за 365 дней по реестру
БДД»): по нему видно, что именно посчитано и за какой срок. Число без
источника проверить нельзя, а значит нельзя и подтвердить.

ГРАНИЦА ОСТАЁТСЯ: платформа не решает, какой период у отчёта и какие числа в
нём верны. Она показывает своё и называет, откуда оно.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.road_safety import Driver, RoadAccident, TrafficViolation, Vehicle
from app.modules.packs.definitions import PACK_CODE_BDD_REPORTS

__all__ = ["Suggestion", "suggestions_for_pack"]

#: окно подсказок по происшествиям — ТО ЖЕ, что у сводки контура БДД. Два
#: разных окна дали бы два разных числа на соседних экранах, и специалист не
#: смог бы понять, какое из них правда.
_WINDOW_DAYS = 365


@dataclass(slots=True, frozen=True)
class Suggestion:
    """Подсказка к одному вопросу мастера.

    ``source`` обязателен: число без объяснения, откуда оно, проверить нельзя,
    а неподтверждаемую подсказку подставлять в документ бессмысленно.
    """

    value: str
    source: str


async def _road_safety_suggestions(
    session: AsyncSession, tenant_id: str
) -> dict[str, Suggestion]:
    """Подсказки для отчётности БДД — из реестров контура.

    Считается ТОЛЬКО то, что реестр знает точно:

    * парк и водительский состав — на СЕГОДНЯ (число в эксплуатации меняется
      каждый день, и «сколько их было в прошлом квартале» реестр не помнит);
    * происшествия и нарушения — за окно, ТО ЖЕ, что в сводке контура.

    Мероприятия по предупреждению ДТП НЕ подсказываются: они живут в ядровом
    CAPA и относятся к конкретным происшествиям, а «сколько мероприятий
    запланировано на период» — вопрос плана, которого у платформы нет.
    """

    today = date.today()
    window_start = datetime.combine(
        today - timedelta(days=_WINDOW_DAYS), time.min, tzinfo=timezone.utc
    )

    vehicles = int(
        await session.scalar(
            select(func.count())
            .select_from(Vehicle)
            .where(
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
                Vehicle.status == "in_service",
            )
        )
        or 0
    )
    drivers = int(
        await session.scalar(
            select(func.count())
            .select_from(Driver)
            .where(
                Driver.tenant_id == tenant_id,
                Driver.deleted_at.is_(None),
                Driver.status == "admitted",
            )
        )
        or 0
    )
    accident_window = (
        RoadAccident.tenant_id == tenant_id,
        RoadAccident.deleted_at.is_(None),
        RoadAccident.occurred_at >= window_start,
    )
    accidents = int(
        await session.scalar(
            select(func.count()).select_from(RoadAccident).where(*accident_window)
        )
        or 0
    )
    injured, fatalities = (
        await session.execute(
            select(
                func.coalesce(func.sum(RoadAccident.injured_count), 0),
                func.coalesce(func.sum(RoadAccident.fatalities_count), 0),
            ).where(*accident_window)
        )
    ).one()
    violations = int(
        await session.scalar(
            select(func.count())
            .select_from(TrafficViolation)
            .where(
                TrafficViolation.tenant_id == tenant_id,
                TrafficViolation.deleted_at.is_(None),
                TrafficViolation.occurred_at >= window_start,
            )
        )
        or 0
    )

    window = f"за {_WINDOW_DAYS} дн."
    return {
        "bdd_report_vehicles": Suggestion(
            str(vehicles), "в эксплуатации сегодня по реестру ТС"
        ),
        "bdd_report_drivers": Suggestion(
            str(drivers), "допущено сегодня по карточкам водителей"
        ),
        "bdd_report_accidents": Suggestion(
            str(accidents), f"ДТП {window} по учёту ДТП"
        ),
        # пострадавшие и погибшие в одном ответе, потому что и в форме они
        # одной строкой: разносить их по двум подсказкам значило бы
        # предлагать то, чего в документе нет
        "bdd_report_injured": Suggestion(
            f"{int(injured)} / {int(fatalities)}",
            f"пострадало / погибло {window} по учёту ДТП",
        ),
        "bdd_report_violations": Suggestion(
            str(violations), f"нарушений {window} по учёту нарушений"
        ),
    }


#: Комплекты, у которых есть источник в реестрах. Пусто для комплекта —
#: НЕ ошибка: у большинства документов числа берутся не из данных, а из
#: решения специалиста, и подсказывать там нечего.
_RESOLVERS = {
    PACK_CODE_BDD_REPORTS: _road_safety_suggestions,
}


async def suggestions_for_pack(
    session: AsyncSession, tenant_id: str, pack_code: str
) -> dict[str, Suggestion]:
    """Подсказки к вопросам мастера или пустой словарь.

    Пустой словарь — законный ответ, а не «не нашли»: у комплекта может не
    быть ни одного вопроса, на который отвечает реестр.
    """

    resolver = _RESOLVERS.get(pack_code)
    if resolver is None:
        return {}
    return await resolver(session, tenant_id)
