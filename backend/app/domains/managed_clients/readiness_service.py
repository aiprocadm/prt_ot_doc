"""BIZ-51 срез-5: сбор чисел для светофора одного клиента (разд. 51.3).

Считается по ОДНОМУ клиенту, а не по портфелю: светофор открывают из карточки
клиента и перед отчётом ему; сводку «по всем» уже даёт «Центр внимания».

**Сами правила счёта переехали в общий сервис**
(``app/services/discipline_numbers.py``, BIZ-54-57 срез-3): тот же счёт ведёт
карточка площадки 360°, и второй его экземпляр разошёлся бы с первым — тогда
«медосмотр закрыт» на двух соседних экранах стало бы означать разное. Здесь
осталось местное: кто такие «люди клиента».
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discipline_status import DisciplineCounts, RoadSafetyNumbers
from app.models.master_data import EmploymentStatus, Person
from app.services.discipline_numbers import collect_people_numbers

__all__ = ["ClientReadinessNumbers", "collect_client_numbers"]


class ClientReadinessNumbers:
    """Числа трёх измеримых направлений одного клиента + факт БДД (срез-64)."""

    def __init__(
        self,
        medical: DisciplineCounts,
        ppe: DisciplineCounts,
        training_overdue: int,
        road_safety: RoadSafetyNumbers | None = None,
    ) -> None:
        self.medical = medical
        self.ppe = ppe
        self.training_overdue = training_overdue
        # Удостоверения водителей клиента — тем же правилом, что у карточки
        # сотрудника и площадки: клиенту нельзя показывать другой БДД, чем его
        # людям.
        self.road_safety = road_safety or RoadSafetyNumbers()


async def _company_people(session: AsyncSession, tenant_id: str, company_id: str) -> list[Person]:
    rows = (
        await session.execute(
            select(Person).where(
                Person.tenant_id == tenant_id,
                Person.company_id == company_id,
                Person.deleted_at.is_(None),
                Person.employment_status != EmploymentStatus.TERMINATED,
            )
        )
    ).scalars()
    return list(rows)


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

    numbers = await collect_people_numbers(
        session,
        tenant_id=tenant_id,
        people=await _company_people(session, tenant_id, company_id),
        today=today,
        now=now,
        horizon_days=horizon_days,
    )
    return ClientReadinessNumbers(
        medical=numbers.medical,
        ppe=numbers.ppe,
        training_overdue=numbers.training_overdue,
        road_safety=numbers.road_safety,
    )
