"""BIZ-49 срез-4: сбор дедлайнов портфеля для единого календаря (разд. 49.2).

Отделено от чистых правил (``calendar.py``) так же, как сбор внимания: здесь
только SQL и склейка. Привязка к клиенту — через ``Person.company_id``, как
в сводке внимания; у Dedicated-клиентов виден ТОЛЬКО дедлайн договора, потому
что остальные данные лежат в другом арендаторе (см. ``attention_service``).

**Горизонт обязателен.** Календарь «на всё будущее» бесполезен человеку и
тяжёл для базы; окно задаётся вызывающим, просрочка попадает в выборку всегда —
именно она самая срочная.

**Уволенный не в счёт (срез-90).** Люди берутся тем же правилом
``person_scope.employed_person_where``, что в сводке внимания (срез-89) и
светофоре клиента: истёкший медосмотр уволенного — история, а не дедлайн, и
в календаре (а через него — в нагрузке специалиста) он не должен всплывать
«просрочкой» там, где сводка внимания того же клиента молчит.

**Удостоверения водителей (срез-91).** Тем же правилом «допущен + дата не
пустая» (``discipline_road_safety.admitted_driver_where``), что сигнал
``driver_license_expired`` сводки внимания, светофор клиента и общий
календарь: отстранённый водитель и удостоверение без срока — не дедлайн.

**Сроки ПБ (срез-92).** Собирает ``discipline_fire_safety
.collect_fire_safety_deadlines_by_company`` — тем же отбором, что сигнал
``fire_safety_overdue`` сводки: площадки организаций клиентов и их
работающие люди; здесь только склейка в события.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.managed_clients.calendar import (
    CalendarFilters,
    DeadlineEvent,
    DeadlineKind,
    apply_filters,
    build_event,
    sort_deadlines,
)
from app.domains.managed_clients.lifecycle import ManagedClientMode
from app.models.managed_clients import ManagedClient
from app.models.master_data import Person
from app.models.medical import MedicalExam
from app.models.ppe import PPEIssue
from app.models.road_safety import Driver
from app.models.training import TrainingEnrollment
from app.services.discipline_fire_safety import collect_fire_safety_deadlines_by_company
from app.services.discipline_road_safety import admitted_driver_where
from app.services.discipline_training import pending_training_enrollment_where
from app.services.person_scope import employed_person_where

__all__ = ["collect_portfolio_deadlines"]

#: Насколько глубоко в прошлое собираем просрочку. Без потолка выборка тянула бы
#: годы мёртвых записей, а человеку нужны те, что ещё можно закрыть.
OVERDUE_LOOKBACK_DAYS = 365


def _fio(person: Person) -> str:
    parts = [person.last_name, person.first_name, person.middle_name]
    return " ".join(p for p in parts if p) or person.id


async def collect_portfolio_deadlines(
    session: AsyncSession,
    *,
    tenant_id: str,
    today: date,
    horizon_days: int,
    filters: CalendarFilters | None = None,
    now: datetime | None = None,
) -> list[DeadlineEvent]:
    """Дедлайны всех ведомых клиентов в окне ``today ± горизонт``."""

    now = now or datetime.now(tz=timezone.utc)
    filters = filters or CalendarFilters()
    until = today + timedelta(days=horizon_days)
    since = today - timedelta(days=OVERDUE_LOOKBACK_DAYS)

    clients = list(
        (
            await session.execute(
                select(ManagedClient).where(
                    ManagedClient.tenant_id == tenant_id,
                    ManagedClient.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not clients:
        return []

    by_company: dict[str, ManagedClient] = {
        c.company_id: c for c in clients if c.mode is ManagedClientMode.LIGHTWEIGHT and c.company_id
    }
    events: list[DeadlineEvent] = []

    # Договоры видны у всех клиентов, включая Dedicated: договор ведёт аутсорсер.
    for client in clients:
        if client.contract_ends_at and since <= client.contract_ends_at <= until:
            events.append(
                build_event(
                    kind=DeadlineKind.CONTRACT,
                    due_date=client.contract_ends_at,
                    client_id=client.id,
                    client_name=client.name,
                    subject=client.contract_no or "Договор без номера",
                    responsible_person_id=client.responsible_person_id,
                    today=today,
                )
            )

    if by_company:
        company_ids = set(by_company)

        med_rows = (
            await session.execute(
                select(MedicalExam, Person)
                .join(Person, Person.id == MedicalExam.person_id)
                .where(
                    MedicalExam.tenant_id == tenant_id,
                    MedicalExam.deleted_at.is_(None),
                    MedicalExam.valid_until >= since,
                    MedicalExam.valid_until <= until,
                    Person.company_id.in_(company_ids),
                    *employed_person_where(),
                )
            )
        ).all()
        for exam, person in med_rows:
            client = by_company[person.company_id]
            events.append(
                build_event(
                    kind=DeadlineKind.MEDICAL,
                    due_date=exam.valid_until,
                    client_id=client.id,
                    client_name=client.name,
                    subject=_fio(person),
                    responsible_person_id=client.responsible_person_id,
                    today=today,
                )
            )

        ppe_rows = (
            await session.execute(
                select(PPEIssue, Person)
                .join(Person, Person.id == PPEIssue.person_id)
                .where(
                    PPEIssue.tenant_id == tenant_id,
                    PPEIssue.deleted_at.is_(None),
                    # Возвращённый СИЗ дедлайна не имеет — он уже не у человека.
                    PPEIssue.returned_at.is_(None),
                    PPEIssue.expires_at.is_not(None),
                    PPEIssue.expires_at
                    >= datetime.combine(since, datetime.min.time()).replace(tzinfo=timezone.utc),
                    PPEIssue.expires_at
                    <= datetime.combine(until, datetime.max.time()).replace(tzinfo=timezone.utc),
                    Person.company_id.in_(company_ids),
                    *employed_person_where(),
                )
            )
        ).all()
        for issue, person in ppe_rows:
            client = by_company[person.company_id]
            events.append(
                build_event(
                    kind=DeadlineKind.PPE,
                    due_date=issue.expires_at.date(),
                    client_id=client.id,
                    client_name=client.name,
                    subject=f"{issue.item_name} — {_fio(person)}",
                    responsible_person_id=client.responsible_person_id,
                    today=today,
                )
            )

        training_rows = (
            await session.execute(
                select(TrainingEnrollment, Person)
                .join(Person, Person.id == TrainingEnrollment.person_id)
                .where(
                    # «Живое назначение со сроком» — одна формула с общим календарём (срез-77).
                    *pending_training_enrollment_where(tenant_id),
                    TrainingEnrollment.due_at
                    >= datetime.combine(since, datetime.min.time()).replace(tzinfo=timezone.utc),
                    TrainingEnrollment.due_at
                    <= datetime.combine(until, datetime.max.time()).replace(tzinfo=timezone.utc),
                    Person.company_id.in_(company_ids),
                    *employed_person_where(),
                )
            )
        ).all()
        for enrollment, person in training_rows:
            client = by_company[person.company_id]
            events.append(
                build_event(
                    kind=DeadlineKind.TRAINING,
                    due_date=enrollment.due_at.date(),
                    client_id=client.id,
                    client_name=client.name,
                    subject=_fio(person),
                    responsible_person_id=client.responsible_person_id,
                    today=today,
                )
            )

        license_rows = (
            await session.execute(
                select(Driver, Person)
                .join(Person, Person.id == Driver.person_id)
                .where(
                    # Только допущенные водители с датой — одно правило со сводкой
                    # внимания, светофором клиента и общим календарём (срез-88).
                    *admitted_driver_where(tenant_id),
                    Driver.license_due.is_not(None),
                    Driver.license_due >= since,
                    Driver.license_due <= until,
                    Person.company_id.in_(company_ids),
                    *employed_person_where(),
                )
            )
        ).all()
        for driver, person in license_rows:
            client = by_company[person.company_id]
            events.append(
                build_event(
                    kind=DeadlineKind.DRIVER_LICENSE,
                    due_date=driver.license_due,
                    client_id=client.id,
                    client_name=client.name,
                    subject=_fio(person),
                    responsible_person_id=client.responsible_person_id,
                    today=today,
                )
            )

        fire_items = await collect_fire_safety_deadlines_by_company(
            session, tenant_id=tenant_id, company_ids=list(company_ids), since=since, until=until
        )
        for item in fire_items:
            client = by_company[item.company_id]
            events.append(
                build_event(
                    kind=DeadlineKind.FIRE_SAFETY,
                    due_date=item.due_date,
                    client_id=client.id,
                    client_name=client.name,
                    subject=item.subject,
                    responsible_person_id=client.responsible_person_id,
                    today=today,
                )
            )

    return sort_deadlines(apply_filters(events, filters))
