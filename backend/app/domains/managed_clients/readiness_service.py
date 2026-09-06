"""BIZ-51 срез-5: сбор чисел для светофора одного клиента (разд. 51.3).

Считается по ОДНОМУ клиенту, а не по портфелю: светофор открывают из карточки
клиента и перед отчётом ему; сводку «по всем» уже даёт «Центр внимания».

**Сами правила счёта переехали в общий сервис**
(``app/services/discipline_numbers.py``, BIZ-54-57 срез-3): тот же счёт ведёт
карточка площадки 360°, и второй его экземпляр разошёлся бы с первым — тогда
«медосмотр закрыт» на двух соседних экранах стало бы означать разное. Здесь
осталось местное: кто такие «люди клиента» и «площадки клиента».

ПБ клиента (BIZ-54-57 срез-86, разд. 54.1) — той же формулой, что у площадки
360° и сводки модуля (``services/discipline_fire_safety``): средства,
тренировки и документы на ПЛОЩАДКАХ организации клиента плюс противопожарные
инструктажи его людей. Средство без площадки к клиенту не относится: чьё оно,
платформа не угадывает.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discipline_status import DisciplineCounts, FireSafetyNumbers, RoadSafetyNumbers
from app.models.master_data import Person, Site
from app.services.discipline_fire_safety import collect_fire_safety_numbers
from app.services.discipline_numbers import collect_people_numbers
from app.services.person_scope import employed_person_where

__all__ = ["ClientReadinessNumbers", "collect_client_numbers"]


class ClientReadinessNumbers:
    """Числа трёх измеримых направлений одного клиента + факты БДД (срез-64) и ПБ (срез-86)."""

    def __init__(
        self,
        medical: DisciplineCounts,
        ppe: DisciplineCounts,
        training_overdue: int,
        road_safety: RoadSafetyNumbers | None = None,
        fire_safety: FireSafetyNumbers | None = None,
    ) -> None:
        self.medical = medical
        self.ppe = ppe
        self.training_overdue = training_overdue
        # Удостоверения водителей клиента — тем же правилом, что у карточки
        # сотрудника и площадки: клиенту нельзя показывать другой БДД, чем его
        # людям.
        self.road_safety = road_safety or RoadSafetyNumbers()
        # Сроки ПБ площадок клиента и инструктажи его людей — той же формулой,
        # что у площадки 360°: один истёкший ПТМ обязан быть просрочкой и у
        # площадки, и у человека, и у клиента.
        self.fire_safety = fire_safety or FireSafetyNumbers()


async def _company_people(session: AsyncSession, tenant_id: str, company_id: str) -> list[Person]:
    rows = (
        await session.execute(
            select(Person).where(
                Person.tenant_id == tenant_id,
                Person.company_id == company_id,
                *employed_person_where(),
            )
        )
    ).scalars()
    return list(rows)


async def _company_site_ids(session: AsyncSession, tenant_id: str, company_id: str) -> list[str]:
    rows = (
        await session.execute(
            select(Site.id).where(
                Site.tenant_id == tenant_id,
                Site.company_id == company_id,
                Site.deleted_at.is_(None),
            )
        )
    ).scalars()
    return [str(site_id) for site_id in rows]


async def collect_client_numbers(
    session: AsyncSession,
    *,
    tenant_id: str,
    company_id: str,
    today: date | None = None,
    now: datetime | None = None,
    horizon_days: int = 30,
) -> ClientReadinessNumbers:
    """Собрать числа светофора по организации клиента (Shared-модель)."""

    people = await _company_people(session, tenant_id, company_id)
    numbers = await collect_people_numbers(
        session,
        tenant_id=tenant_id,
        people=people,
        today=today,
        now=now,
        horizon_days=horizon_days,
    )
    fire_safety = await collect_fire_safety_numbers(
        session,
        tenant_id=tenant_id,
        site_ids=await _company_site_ids(session, tenant_id, company_id),
        person_ids=[str(person.id) for person in people],
        today=today,
        now=now,
    )
    return ClientReadinessNumbers(
        medical=numbers.medical,
        ppe=numbers.ppe,
        training_overdue=numbers.training_overdue,
        road_safety=numbers.road_safety,
        fire_safety=fire_safety,
    )
