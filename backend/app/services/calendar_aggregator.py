"""Smart Calendar aggregator service (vNext-CAL-01 / Phase 4.1).

Reads from existing domain modules (medicals, PPE, permits, training,
inspections, compliance deadlines, briefings, calendar projections) and
emits a single normalized stream of `CalendarEventItem` rows. The service
deliberately does not introduce a new master-data table; it joins
existing rows so each domain remains the source of truth.

Design notes
------------
* Tenant scope is mandatory. Every per-source query filters by
  `tenant_id` (and `deleted_at IS NULL` where the model uses
  SoftDeleteMixin).
* Date-range filter clamps each source by its own "anchor" timestamp
  (`valid_until` for medicals/permits/PPE; `due_at` for deadlines;
  `scheduled_at`/`started_at` for training and inspections;
  `briefing_date` for briefings; `starts_at` for legacy
  `calendar_events`).
* Items are bounded by `MAX_ITEMS_PER_SOURCE` per source (50 by default)
  to keep the response shape predictable; counters reflect the unbounded
  totals so the UI can render badges accurately even when the list is
  truncated.
* The service does not paginate across sources — it returns up to
  `MAX_ITEMS_PER_SOURCE * sources` items in chronological order. For
  typical month/quarter views this is more than enough; longer ranges
  should request narrower filters.
* «Уволенный не в счёт» (BIZ-54-57 срез-93). Поимённые источники —
  медосмотры, направления, СИЗ, обучение, зачисления, сертификаты,
  инструктажи, удостоверения водителей — не показывают и не считают записи
  удалённых и уволенных людей: тем же правилом, что портфель, светофоры и
  карточка сотрудника (``services/person_scope``). Иначе Центр внимания и
  разрез руководителя (разд. 57.2/57.4) горели бы истёкшим медосмотром того,
  у кого обязательств уже нет, а ``discipline_deadline_events`` слал бы по
  нему напоминания. Записи без человека (``person_id IS NULL`` — журнал,
  площадка) остаются; «висячий» ``person_id`` без карточки — тоже, как и
  раньше: календарь join'а с ``Person`` не требует. Наряды-допуски и сроки
  соответствия — про работу и организацию, их не трогаем.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Iterable

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import BRIEFING_TYPE_TITLES
from app.models.civil_defense import CivilDefenseDrill
from app.models.ecology import (
    REPORTING_KINDS,
    EcologyReportingDeadline,
    EmissionMonitoringPlanItem,
    EmissionNorm,
    WaterUsagePoint,
)
from app.models.fire_safety import (
    FIRE_DOCUMENT_KINDS,
    FireDrill,
    FireSafetyDocument,
    FireSafetyEquipment,
)
from app.models.industrial_safety import TechnicalDevice
from app.models.master_data import Person
from app.models.models import (
    BriefingEntry,
    BriefingTemplate,
    CalendarEvent,
    ComplianceDeadline,
    Inspection,
    InspectionStatus,
    MedicalExam,
    MedicalReferral,
    Permit,
    PermitStatus,
    PPEIssue,
    PPEIssueStatus,
    TrainingCertificate,
    TrainingCourse,
    TrainingEnrollment,
    TrainingProgram,
    TrainingSession,
    TrainingSessionStatus,
)
from app.models.road_safety import Driver, Vehicle
from app.schemas.calendar import (
    CalendarEventItem,
    CalendarEventsResponse,
    CalendarSourceCount,
)
from app.services.discipline_road_safety import admitted_driver_where
from app.services.discipline_training import (
    overdue_training_enrollment_where,
    pending_training_enrollment_where,
)
from app.services.person_scope import employed_record_where

__all__ = [
    "CalendarAggregatorService",
    "MAX_ITEMS_PER_SOURCE",
    "ALL_SOURCES",
    "overdue_compliance_deadline_where",
]

MAX_ITEMS_PER_SOURCE = 50

ALL_SOURCES: tuple[str, ...] = (
    "medical_exam",
    "medical_referral",
    "ppe_issue",
    "permit",
    "training_session",
    # Доп. №1 разд. 57.2 (срез-75): истёкшее удостоверение по обучению —
    # самый частый срок охраны труда, а в календаре его не было вовсе:
    # ``training_session`` — это занятия, ``compliance_deadline`` — снимок,
    # который делает только ручной пересчёт. Источник поимённый.
    "training_certificate",
    # Срез-77: срок назначения обучения (``TrainingEnrollment.due_at``, контур
    # обучение-next). Блокер готовности и светофор дисциплины считали его
    # просрочку, а календарь и Центр внимания — нет: ``training_session`` читает
    # старую модель занятий. Источник поимённый, формула — ``discipline_training``.
    "training_enrollment",
    "inspection",
    "compliance_deadline",
    "briefing_entry",
    "calendar_event",
    # Доп. №1 разд. 55.3 «экологический календарь». Два источника, а не один:
    # продлить разрешение и заказать замер — разные задачи эколога, и смешать
    # их значило бы отнять возможность отфильтровать.
    "ecology_permit",
    "ecology_measurement",
    # Доп. №1 разд. 55.3 «2-ТП, декларация НВОС, платежи» (срез-71): срок
    # отчёта или платежа, который эколог внёс сам. Платформа дат не вычисляет
    # (решение среза-23), а исполненный срок из календаря уходит — он не событие.
    "ecology_report",
    # Доп. №1 разд. 57.2 (срез-57): Центр внимания обязан видеть «просрочена
    # ЭПБ на ОПО», «не проведены учения по ГО», «просрочен техосмотр ТС».
    # Три источника — по одному на дисциплину, у которой сроков в календаре
    # не было вовсе; модули считали их у себя, а общий календарь молчал.
    "industrial_safety_epb",
    "civil_defense_drill",
    "road_safety_vehicle",
    # Доп. №1 разд. 56.2 (срез-59): водительское удостоверение — поимённый
    # срок БДД, в отличие от документов машины
    "road_safety_driver",
    # Доп. №1 разд. 54.1 / 57.2 (срез-79): перезарядка огнетушителей и
    # поверка/ТО систем защиты. Модуль ПБ считал эти просрочки в своей сводке
    # готовности к проверке МЧС, а общий календарь и Центр внимания молчали —
    # строка «Пожарная безопасность» видела только инструктажи.
    "fire_safety_equipment",
    # Срез-80: тренировки по ПБ из плана-графика (не проведённые к дате —
    # как учения ГО) и срок пересмотра документов ПБ. Сводка модуля считала
    # ``overdue_drills`` и ``overdue_documents``, календарь их не знал.
    "fire_safety_drill",
    "fire_safety_document",
)

#: Сроки документов ТС: колонка → (код вида, подпись). Порядок — порядок
#: строк в календаре при одной дате. Водительские удостоверения сюда НЕ входят:
#: это поимённый учёт водителя, а не документ машины.
_VEHICLE_DUE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("inspection_due", "inspection", "Техосмотр ТС"),
    ("insurance_due", "insurance", "Полис ОСАГО"),
    ("license_due", "license", "Лицензия на перевозки"),
    ("tachograph_due", "tachograph", "Поверка тахографа"),
)

#: Сроки средств и систем ПБ: колонка → (код вида, подпись). Один источник на
#: оба срока — как у документов ТС: для ответственного за ПБ это один вопрос
#: «что по средствам защиты истекает», вид срока лежит в ``extra.kind``.
_FIRE_EQUIPMENT_DUE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("recharge_due", "recharge", "Перезарядка"),
    ("inspection_due", "inspection", "Поверка/ТО"),
)

_CLOSED_DEADLINE_STATUSES = frozenset({"closed", "completed", "cancelled"})


def overdue_compliance_deadline_where(now: datetime):
    """Одно условие «контрольный срок просрочен» для календаря и Центра внимания (срез-73).

    Просрочка считается по времени, а не по сохранённому статусу: статус `overdue`
    пишет только ручной пересчёт сертификатов, и между пересчётами строка с `upcoming`
    и прошедшей датой иначе выпадала бы из счётчика. Закрытые статусы не считаются.
    """
    return and_(
        ComplianceDeadline.status.notin_(tuple(_CLOSED_DEADLINE_STATUSES)),
        ComplianceDeadline.due_at < now,
    )


# Per-source SLA thresholds: (critical_window_days, warning_window_days).
# `critical` ⇒ inner band (urgent, immediate attention); `warning` ⇒ outer
# band (planning horizon); beyond `warning` ⇒ `ok`. Defaults are tuned for
# the typical HSE planning cadence and remain hard-coded in v1 — per-tenant
# overrides are explicitly out of scope (see Session 25 handoff #2 for the
# v1.1 follow-up that introduces tenant-configurable bands).
_SLA_THRESHOLDS: dict[str, tuple[int, int]] = {
    "medical_exam": (7, 30),
    "medical_referral": (7, 30),
    "ppe_issue": (7, 30),
    "permit": (7, 30),
    "training_session": (3, 14),
    "inspection": (7, 30),
    "compliance_deadline": (3, 14),
    "briefing_entry": (7, 30),
    "calendar_event": (1, 7),
    # Разрешение продлевают заранее: переоформление занимает месяцы, поэтому
    # окно шире, чем у медосмотра.
    "ecology_permit": (30, 90),
    "ecology_measurement": (7, 30),
    # Отчёт и платёж готовят по данным за период — за неделю уже поздно начинать.
    "ecology_report": (7, 30),
    # ЭПБ заказывают у экспертной организации за месяцы — окно как у разрешений;
    # у модуля ПромБез «скоро истекает» = 30 дней, это внутренняя полоса.
    "industrial_safety_epb": (30, 90),
    "civil_defense_drill": (7, 30),
    "road_safety_vehicle": (7, 30),
    "road_safety_driver": (7, 30),
    "training_certificate": (7, 30),
    "training_enrollment": (3, 14),
    # у модуля ПБ «скоро» = 30 дней (``_DUE_SOON_DAYS``) — та же полоса
    "fire_safety_equipment": (7, 30),
    "fire_safety_drill": (7, 30),
    # пересмотр инструкции или плана эвакуации — недели работы, не день
    "fire_safety_document": (14, 30),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_dt(value: date | datetime | None) -> datetime | None:
    """Normalize date/datetime to a UTC datetime so downstream sort/compare is total."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _variance_days(expected: datetime | None, actual: datetime | None) -> int | None:
    """Return whole-day delta `actual - expected` (positive = late)."""
    if expected is None or actual is None:
        return None
    return (actual - expected).days


def _days_to_due(anchor: datetime | None, now: datetime) -> int | None:
    """Return whole-day delta from `now.date()` to `anchor.date()`.

    Positive ⇒ in the future; negative ⇒ already past-due. Date-grain
    matches the resolution at which the calendar reasons about deadlines
    (medical valid_until, permit expiry, compliance due dates).
    """
    if anchor is None:
        return None
    return (anchor.date() - now.date()).days


def _sla_band(source_type: str, *, days_to_due: int | None, is_overdue: bool) -> str | None:
    """Bucket the event into an SLA band (`overdue`/`critical`/`warning`/`ok`).

    `is_overdue=True` is the single source of truth for past-due rows —
    even when `days_to_due >= 0`, the source flagged the row as overdue
    (e.g. status mismatch), so we honour that and emit `overdue`.
    """
    if is_overdue:
        return "overdue"
    if days_to_due is None:
        return None
    if days_to_due < 0:
        return "overdue"
    critical, warning = _SLA_THRESHOLDS.get(source_type, (7, 30))
    if days_to_due <= critical:
        return "critical"
    if days_to_due <= warning:
        return "warning"
    return "ok"


class CalendarAggregatorService:
    """Build a tenant-scoped `CalendarEventsResponse`."""

    def __init__(
        self, *, tenant_id: str, db: AsyncSession, limit: int = MAX_ITEMS_PER_SOURCE
    ) -> None:
        self.tenant_id = str(tenant_id)
        self.db = db
        # Потолок строк на источник. По умолчанию — экранный (календарь и
        # Центр внимания показывают первые 50, остальное — числом). Обход
        # сроков ради событий (срез-62) поднимает его: ему нужна каждая
        # просроченная строка, а не первые полсотни.
        self._limit = max(int(limit), 1)

    async def list_events(
        self,
        *,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        source_types: Iterable[str] | None = None,
        person_id: str | None = None,
        site_id: str | None = None,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> CalendarEventsResponse:
        sources = tuple(source_types) if source_types else ALL_SOURCES
        unknown = [s for s in sources if s not in ALL_SOURCES]
        if unknown:
            raise ValueError(f"Unknown calendar source_types: {unknown!r}")

        items: list[CalendarEventItem] = []
        by_source: list[CalendarSourceCount] = []
        now = _utcnow()

        if "ecology_permit" in sources:
            collected, total, overdue = await self._build_ecology_permits(
                from_at=from_at,
                to_at=to_at,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="ecology_permit", count=total, overdue_count=overdue
                )
            )

        if "ecology_measurement" in sources:
            collected, total, overdue = await self._build_ecology_measurements(
                from_at=from_at,
                to_at=to_at,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="ecology_measurement", count=total, overdue_count=overdue
                )
            )

        if "ecology_report" in sources:
            collected, total, overdue = await self._build_ecology_reports(
                from_at=from_at,
                to_at=to_at,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="ecology_report", count=total, overdue_count=overdue
                )
            )

        if "industrial_safety_epb" in sources:
            collected, total, overdue = await self._build_epb(
                from_at=from_at,
                to_at=to_at,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="industrial_safety_epb", count=total, overdue_count=overdue
                )
            )

        if "civil_defense_drill" in sources:
            collected, total, overdue = await self._build_cd_drills(
                from_at=from_at,
                to_at=to_at,
                site_id=site_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="civil_defense_drill", count=total, overdue_count=overdue
                )
            )

        if "road_safety_vehicle" in sources:
            collected, total, overdue = await self._build_vehicle_documents(
                from_at=from_at,
                to_at=to_at,
                site_id=site_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="road_safety_vehicle", count=total, overdue_count=overdue
                )
            )

        if "fire_safety_equipment" in sources:
            collected, total, overdue = await self._build_fire_equipment(
                from_at=from_at,
                to_at=to_at,
                site_id=site_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="fire_safety_equipment", count=total, overdue_count=overdue
                )
            )

        if "fire_safety_drill" in sources:
            collected, total, overdue = await self._build_fire_drills(
                from_at=from_at,
                to_at=to_at,
                site_id=site_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="fire_safety_drill", count=total, overdue_count=overdue
                )
            )

        if "fire_safety_document" in sources:
            collected, total, overdue = await self._build_fire_documents(
                from_at=from_at,
                to_at=to_at,
                site_id=site_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="fire_safety_document", count=total, overdue_count=overdue
                )
            )

        if "road_safety_driver" in sources:
            collected, total, overdue = await self._build_driver_licenses(
                from_at=from_at,
                to_at=to_at,
                person_id=person_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="road_safety_driver", count=total, overdue_count=overdue
                )
            )

        if "training_certificate" in sources:
            collected, total, overdue = await self._build_training_certificates(
                from_at=from_at,
                to_at=to_at,
                person_id=person_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="training_certificate", count=total, overdue_count=overdue
                )
            )

        if "training_enrollment" in sources:
            collected, total, overdue = await self._build_training_enrollments(
                from_at=from_at,
                to_at=to_at,
                person_id=person_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="training_enrollment", count=total, overdue_count=overdue
                )
            )

        if "medical_exam" in sources:
            collected, total, overdue = await self._build_medicals(
                from_at=from_at,
                to_at=to_at,
                person_id=person_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(source_type="medical_exam", count=total, overdue_count=overdue)
            )

        if "medical_referral" in sources:
            collected, total, overdue = await self._build_medical_referrals(
                from_at=from_at,
                to_at=to_at,
                person_id=person_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="medical_referral", count=total, overdue_count=overdue
                )
            )

        if "ppe_issue" in sources:
            collected, total, overdue = await self._build_ppe(
                from_at=from_at,
                to_at=to_at,
                person_id=person_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(source_type="ppe_issue", count=total, overdue_count=overdue)
            )

        if "permit" in sources:
            collected, total, overdue = await self._build_permits(
                from_at=from_at,
                to_at=to_at,
                person_id=person_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(source_type="permit", count=total, overdue_count=overdue)
            )

        if "training_session" in sources:
            collected, total, overdue = await self._build_training(
                from_at=from_at,
                to_at=to_at,
                person_id=person_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="training_session", count=total, overdue_count=overdue
                )
            )

        if "inspection" in sources:
            collected, total, overdue = await self._build_inspections(
                from_at=from_at,
                to_at=to_at,
                site_id=site_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(source_type="inspection", count=total, overdue_count=overdue)
            )

        if "compliance_deadline" in sources:
            collected, total, overdue = await self._build_deadlines(
                from_at=from_at,
                to_at=to_at,
                person_id=person_id,
                site_id=site_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="compliance_deadline",
                    count=total,
                    overdue_count=overdue,
                )
            )

        if "briefing_entry" in sources:
            collected, total, overdue, overdue_by_kind = await self._build_briefings(
                from_at=from_at,
                to_at=to_at,
                person_id=person_id,
                site_id=site_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="briefing_entry",
                    count=total,
                    overdue_count=overdue,
                    overdue_by_kind=overdue_by_kind,
                )
            )

        if "calendar_event" in sources:
            collected, total, overdue = await self._build_calendar_events(
                from_at=from_at,
                to_at=to_at,
                site_id=site_id,
                now=now,
                include_fact=include_fact,
                include_sla=include_sla,
            )
            items.extend(collected)
            by_source.append(
                CalendarSourceCount(
                    source_type="calendar_event", count=total, overdue_count=overdue
                )
            )

        items.sort(key=lambda item: item.starts_at)
        total = sum(s.count for s in by_source)
        overdue_total = sum(s.overdue_count for s in by_source)
        return CalendarEventsResponse(
            generated_at=now,
            range_from=from_at,
            range_to=to_at,
            total=total,
            overdue_count=overdue_total,
            by_source=by_source,
            items=items,
        )

    # ------------------------------------------------------------------
    # Per-source builders
    # ------------------------------------------------------------------

    async def _build_driver_licenses(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        person_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Сроки водительских удостоверений — поимённый источник БДД.

        Правило то же, что у готовности модуля БДД: считаются ТОЛЬКО допущенные
        к управлению (``status == "admitted"``) — просроченные права
        отстранённого или уволенного водителя ничего не блокируют. Пустая дата
        — «сведений нет» (бессрочных удостоверений не бывает), это не срок и
        в календарь не попадает. Источник поимённый: у рабочего в его личном
        центре внимания — его удостоверение, и только оно.
        """

        today = now.date()
        stmt = (
            select(Driver, Person.last_name, Person.first_name)
            .join(Person, Person.id == Driver.person_id)
            .where(
                # Правило «допущенный водитель» одно с цифрами дисциплины и портфелем (срез-88).
                *admitted_driver_where(self.tenant_id),
                Driver.license_due.is_not(None),
                self._employed_only(Driver),
            )
            .order_by(Driver.license_due.asc())
            .limit(self._limit)
        )
        if person_id:
            stmt = stmt.where(Driver.person_id == person_id)
        if from_at is not None:
            stmt = stmt.where(Driver.license_due >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(Driver.license_due <= to_at.date())

        items: list[CalendarEventItem] = []
        for driver, last_name, first_name in (await self.db.execute(stmt)).all():
            anchor = _coerce_dt(driver.license_due)
            if anchor is None:
                continue
            is_overdue = driver.license_due < today
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            person_name = " ".join(part for part in (last_name, first_name) if part)
            items.append(
                CalendarEventItem(
                    id=f"road_safety_driver:{driver.id}",
                    source_type="road_safety_driver",
                    source_id=str(driver.id),
                    title=f"Водительское удостоверение: {person_name or driver.license_number}",
                    starts_at=anchor,
                    ends_at=None,
                    status="expired" if is_overdue else "valid",
                    is_overdue=is_overdue,
                    person_id=str(driver.person_id),
                    site_id=None,
                    expected_at=anchor if include_fact else None,
                    actual_at=None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=(
                        _sla_band(
                            "road_safety_driver", days_to_due=days_to_due, is_overdue=is_overdue
                        )
                        if include_sla
                        else None
                    ),
                    extra={
                        "license_number": driver.license_number,
                        "categories": list(driver.categories or []),
                        "license_due": driver.license_due.isoformat(),
                    },
                )
            )

        base_count = self._apply_window(
            self._scoped_count(Driver, person_id=person_id).where(
                *admitted_driver_where(self.tenant_id),
                Driver.license_due.is_not(None),
                self._employed_only(Driver),
            ),
            Driver.license_due,
            from_at,
            to_at,
            as_date=True,
        )
        total = await self._count(base_count)
        overdue = await self._count(base_count.where(Driver.license_due < today))
        return items, total, overdue

    async def _build_training_certificates(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        person_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Сроки удостоверений по обучению — поимённый источник обучения (срез-75).

        Считаются ТОЛЬКО действующие удостоверения (``status == "active"``,
        не удалённые): отозванное ничего не блокирует. Пустая дата — бессрочное
        удостоверение, это не срок и в календарь не попадает. Правило просрочки
        то же, что у медосмотров: ``valid_until < today`` — в день окончания
        удостоверение ещё действует. Название берётся из программы, иначе из
        курса, иначе — номер или код: у старых удостоверений программы нет.
        В заголовке — фамилия и имя (срез-76): из него складывается задача
        правила «направить на переобучение», и без имени она никому не адресована
        (как у водительских удостоверений, срез-62).
        """

        today = now.date()
        stmt = (
            select(
                TrainingCertificate,
                TrainingProgram.title,
                TrainingCourse.title,
                Person.last_name,
                Person.first_name,
            )
            .outerjoin(
                TrainingProgram, TrainingProgram.id == TrainingCertificate.training_program_id
            )
            .outerjoin(TrainingCourse, TrainingCourse.id == TrainingCertificate.course_id)
            .outerjoin(Person, Person.id == TrainingCertificate.person_id)
            .where(
                TrainingCertificate.tenant_id == self.tenant_id,
                TrainingCertificate.deleted_at.is_(None),
                TrainingCertificate.status == "active",
                TrainingCertificate.valid_until.is_not(None),
                self._employed_only(TrainingCertificate),
            )
            .order_by(TrainingCertificate.valid_until.asc(), TrainingCertificate.issued_at.asc())
            .limit(self._limit)
        )
        if person_id:
            stmt = stmt.where(TrainingCertificate.person_id == person_id)
        if from_at is not None:
            stmt = stmt.where(TrainingCertificate.valid_until >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(TrainingCertificate.valid_until <= to_at.date())

        items: list[CalendarEventItem] = []
        rows = (await self.db.execute(stmt)).all()
        for cert, program_title, course_title, last_name, first_name in rows:
            anchor = _coerce_dt(cert.valid_until)
            if anchor is None:
                continue
            is_overdue = cert.valid_until < today
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            subject = program_title or course_title or cert.number or cert.code or "без программы"
            person_name = " ".join(part for part in (last_name, first_name) if part)
            title = f"Удостоверение: {subject}"
            if person_name:
                title = f"{title} — {person_name}"
            items.append(
                CalendarEventItem(
                    id=f"training_certificate:{cert.id}",
                    source_type="training_certificate",
                    source_id=str(cert.id),
                    title=title,
                    starts_at=anchor,
                    ends_at=None,
                    status="expired" if is_overdue else "valid",
                    is_overdue=is_overdue,
                    person_id=str(cert.person_id) if cert.person_id else None,
                    site_id=None,
                    expected_at=anchor if include_fact else None,
                    actual_at=_coerce_dt(cert.issued_at) if include_fact else None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=(
                        _sla_band(
                            "training_certificate", days_to_due=days_to_due, is_overdue=is_overdue
                        )
                        if include_sla
                        else None
                    ),
                    extra={
                        "number": cert.number,
                        "code": cert.code,
                        "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
                        "valid_until": cert.valid_until.isoformat(),
                        "program_title": program_title,
                        "course_title": course_title,
                        "person_name": person_name or None,
                    },
                )
            )

        base_count = self._apply_window(
            self._scoped_count(TrainingCertificate, person_id=person_id).where(
                TrainingCertificate.status == "active",
                TrainingCertificate.valid_until.is_not(None),
                self._employed_only(TrainingCertificate),
            ),
            TrainingCertificate.valid_until,
            from_at,
            to_at,
            as_date=True,
        )
        total = await self._count(base_count)
        overdue = await self._count(base_count.where(TrainingCertificate.valid_until < today))
        return items, total, overdue

    async def _build_training_enrollments(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        person_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Сроки назначений обучения — поимённый источник обучения (срез-77).

        Считаются ТОЛЬКО живые назначения со сроком
        (``pending_training_enrollment_where``): сданное или проваленное — итог
        получен, срок больше не давит; без срока — не срок. Просрочка —
        ``overdue_training_enrollment_where``: та же формула, что у блокера
        готовности, светофора дисциплины и сервисного центра. В заголовке —
        фамилия и имя: задача по назначению адресована человеку.
        """

        stmt = (
            select(TrainingEnrollment, TrainingProgram.title, Person.last_name, Person.first_name)
            .outerjoin(
                TrainingProgram, TrainingProgram.id == TrainingEnrollment.training_program_id
            )
            .outerjoin(Person, Person.id == TrainingEnrollment.person_id)
            .where(
                *pending_training_enrollment_where(self.tenant_id),
                self._employed_only(TrainingEnrollment),
            )
            .order_by(TrainingEnrollment.due_at.asc(), TrainingEnrollment.assigned_at.asc())
            .limit(self._limit)
        )
        if person_id:
            stmt = stmt.where(TrainingEnrollment.person_id == person_id)
        if from_at is not None:
            stmt = stmt.where(TrainingEnrollment.due_at >= from_at)
        if to_at is not None:
            stmt = stmt.where(TrainingEnrollment.due_at <= to_at)

        items: list[CalendarEventItem] = []
        for enrollment, program_title, last_name, first_name in (await self.db.execute(stmt)).all():
            anchor = _coerce_dt(enrollment.due_at)
            if anchor is None:
                continue
            is_overdue = anchor < now
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            person_name = " ".join(part for part in (last_name, first_name) if part)
            title = f"Назначение: {program_title or 'без программы'}"
            if person_name:
                title = f"{title} — {person_name}"
            items.append(
                CalendarEventItem(
                    id=f"training_enrollment:{enrollment.id}",
                    source_type="training_enrollment",
                    source_id=str(enrollment.id),
                    title=title,
                    starts_at=anchor,
                    ends_at=None,
                    status="overdue" if is_overdue else str(enrollment.status),
                    is_overdue=is_overdue,
                    person_id=str(enrollment.person_id) if enrollment.person_id else None,
                    site_id=None,
                    expected_at=anchor if include_fact else None,
                    actual_at=_coerce_dt(enrollment.started_at) if include_fact else None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=(
                        _sla_band(
                            "training_enrollment", days_to_due=days_to_due, is_overdue=is_overdue
                        )
                        if include_sla
                        else None
                    ),
                    extra={
                        "status": str(enrollment.status),
                        "program_id": (
                            str(enrollment.training_program_id)
                            if enrollment.training_program_id
                            else None
                        ),
                        "program_title": program_title,
                        "person_name": person_name or None,
                        "assigned_at": (
                            enrollment.assigned_at.isoformat() if enrollment.assigned_at else None
                        ),
                        "due_at": anchor.isoformat(),
                        "progress_percent": (
                            float(enrollment.progress_percent)
                            if enrollment.progress_percent is not None
                            else None
                        ),
                    },
                )
            )

        base_count = self._apply_window(
            self._scoped_count(TrainingEnrollment, person_id=person_id).where(
                *pending_training_enrollment_where(self.tenant_id),
                self._employed_only(TrainingEnrollment),
            ),
            TrainingEnrollment.due_at,
            from_at,
            to_at,
        )
        total = await self._count(base_count)
        overdue = await self._count(
            self._apply_window(
                self._scoped_count(TrainingEnrollment, person_id=person_id).where(
                    *overdue_training_enrollment_where(self.tenant_id, now),
                    self._employed_only(TrainingEnrollment),
                ),
                TrainingEnrollment.due_at,
                from_at,
                to_at,
            )
        )
        return items, total, overdue

    async def _build_medicals(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        person_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        today = now.date()
        stmt = (
            select(MedicalExam)
            .where(
                MedicalExam.tenant_id == self.tenant_id,
                MedicalExam.deleted_at.is_(None),
                self._employed_only(MedicalExam),
            )
            .order_by(MedicalExam.valid_until.asc())
            .limit(self._limit)
        )
        if person_id:
            stmt = stmt.where(MedicalExam.person_id == person_id)
        if from_at is not None:
            stmt = stmt.where(MedicalExam.valid_until >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(MedicalExam.valid_until <= to_at.date())

        rows = (await self.db.execute(stmt)).scalars().all()
        items: list[CalendarEventItem] = []
        for exam in rows:
            anchor = _coerce_dt(exam.valid_until)
            if anchor is None:
                continue
            is_overdue = exam.valid_until < today
            expected_at = anchor if include_fact else None
            actual_at = _coerce_dt(exam.exam_date) if include_fact else None
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            sla_band = (
                _sla_band("medical_exam", days_to_due=days_to_due, is_overdue=is_overdue)
                if include_sla
                else None
            )
            items.append(
                CalendarEventItem(
                    id=f"medical_exam:{exam.id}",
                    source_type="medical_exam",
                    source_id=str(exam.id),
                    title=f"Медосмотр: {exam.exam_type}",
                    starts_at=anchor,
                    ends_at=None,
                    status="expired" if is_overdue else "active",
                    is_overdue=is_overdue,
                    person_id=str(exam.person_id) if exam.person_id else None,
                    site_id=None,
                    company_id=None,
                    expected_at=expected_at,
                    actual_at=actual_at,
                    variance_days=_variance_days(expected_at, actual_at),
                    days_to_due=days_to_due,
                    sla_band=sla_band,
                    extra={
                        "exam_type": exam.exam_type,
                        "exam_date": exam.exam_date.isoformat() if exam.exam_date else None,
                        "valid_until": exam.valid_until.isoformat(),
                        "conclusion": exam.conclusion,
                    },
                )
            )

        base_count = self._apply_window(
            self._scoped_count(MedicalExam, person_id=person_id).where(
                self._employed_only(MedicalExam)
            ),
            MedicalExam.valid_until,
            from_at,
            to_at,
            as_date=True,
        )
        total = await self._count(base_count)
        overdue = await self._count(base_count.where(MedicalExam.valid_until < today))
        return items, total, overdue

    async def _build_medical_referrals(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        person_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        today = now.date()
        stmt = (
            select(MedicalReferral)
            .where(
                MedicalReferral.tenant_id == self.tenant_id,
                MedicalReferral.deleted_at.is_(None),
                MedicalReferral.due_at.is_not(None),
                self._employed_only(MedicalReferral),
            )
            .order_by(MedicalReferral.due_at.asc())
            .limit(self._limit)
        )
        if person_id:
            stmt = stmt.where(MedicalReferral.person_id == person_id)
        if from_at is not None:
            stmt = stmt.where(MedicalReferral.due_at >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(MedicalReferral.due_at <= to_at.date())

        rows = (await self.db.execute(stmt)).scalars().all()
        items: list[CalendarEventItem] = []
        for ref in rows:
            anchor = _coerce_dt(ref.due_at)
            if anchor is None:
                continue
            is_overdue = ref.due_at < today
            expected_at = anchor if include_fact else None
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            sla_band = (
                _sla_band(
                    "medical_referral",
                    days_to_due=days_to_due,
                    is_overdue=is_overdue,
                )
                if include_sla
                else None
            )
            items.append(
                CalendarEventItem(
                    id=f"medical_referral:{ref.id}",
                    source_type="medical_referral",
                    source_id=str(ref.id),
                    title=f"Направление на медосмотр: {ref.exam_kind.value}",
                    starts_at=anchor,
                    ends_at=None,
                    status="expired" if is_overdue else "active",
                    is_overdue=is_overdue,
                    person_id=str(ref.person_id) if ref.person_id else None,
                    site_id=None,
                    company_id=None,
                    expected_at=expected_at,
                    actual_at=None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=sla_band,
                    extra={
                        "exam_kind": ref.exam_kind.value,
                        "due_at": ref.due_at.isoformat() if ref.due_at else None,
                        "status": (
                            ref.status.value if hasattr(ref.status, "value") else str(ref.status)
                        ),
                        "medical_org_name": ref.medical_org_name,
                    },
                )
            )

        base_count = self._apply_window(
            self._scoped_count(MedicalReferral, person_id=person_id).where(
                MedicalReferral.due_at.is_not(None), self._employed_only(MedicalReferral)
            ),
            MedicalReferral.due_at,
            from_at,
            to_at,
            as_date=True,
        )
        total = await self._count(base_count)
        overdue = await self._count(base_count.where(MedicalReferral.due_at < today))
        return items, total, overdue

    async def _build_ecology_permits(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Сроки продления разрешений: нормативы выброса и водопользование.

        Оба вида в ОДНОМ источнике: для эколога это один вопрос «что
        продлевать», и оба срока живут по одному правилу.

        БЕССРОЧНОЕ разрешение в календарь не попадает: события без даты не
        бывает, а придумывать дату — враньё. Пустой срок означает «бессрочно»
        (так решено на срезе-3), и календарь обязан это уважать.
        """

        today = now.date()
        lo = from_at.date() if from_at is not None else None
        hi = to_at.date() if to_at is not None else None

        norms_stmt = (
            select(EmissionNorm)
            .where(
                EmissionNorm.tenant_id == self.tenant_id,
                EmissionNorm.deleted_at.is_(None),
                EmissionNorm.valid_until.is_not(None),
            )
            .order_by(EmissionNorm.valid_until.asc())
            .limit(self._limit)
        )
        points_stmt = (
            select(WaterUsagePoint)
            .where(
                WaterUsagePoint.tenant_id == self.tenant_id,
                WaterUsagePoint.deleted_at.is_(None),
                WaterUsagePoint.permit_valid_until.is_not(None),
            )
            .order_by(WaterUsagePoint.permit_valid_until.asc())
            .limit(self._limit)
        )
        if lo is not None:
            norms_stmt = norms_stmt.where(EmissionNorm.valid_until >= lo)
            points_stmt = points_stmt.where(WaterUsagePoint.permit_valid_until >= lo)
        if hi is not None:
            norms_stmt = norms_stmt.where(EmissionNorm.valid_until <= hi)
            points_stmt = points_stmt.where(WaterUsagePoint.permit_valid_until <= hi)

        items: list[CalendarEventItem] = []
        for norm in (await self.db.execute(norms_stmt)).scalars().all():
            anchor = _coerce_dt(norm.valid_until)
            if anchor is None:
                continue
            items.append(
                self._ecology_permit_item(
                    entity_id=str(norm.id),
                    title=f"Разрешение на выброс: {norm.substance}",
                    anchor=anchor,
                    now=now,
                    include_fact=include_fact,
                    include_sla=include_sla,
                    extra={
                        "kind": "emission_norm",
                        "permit_number": norm.permit_number,
                        "valid_until": norm.valid_until.isoformat(),
                    },
                )
            )
        for point in (await self.db.execute(points_stmt)).scalars().all():
            anchor = _coerce_dt(point.permit_valid_until)
            if anchor is None:
                continue
            items.append(
                self._ecology_permit_item(
                    entity_id=str(point.id),
                    title=f"Разрешение водопользования: {point.name}",
                    anchor=anchor,
                    now=now,
                    include_fact=include_fact,
                    include_sla=include_sla,
                    extra={
                        "kind": "water_permit",
                        "permit_number": point.permit_number,
                        "valid_until": point.permit_valid_until.isoformat(),
                    },
                )
            )
        items.sort(key=lambda item: item.starts_at)
        items = items[: self._limit]

        total = 0
        overdue = 0
        for model, column in (
            (EmissionNorm, EmissionNorm.valid_until),
            (WaterUsagePoint, WaterUsagePoint.permit_valid_until),
        ):
            base = self._apply_window(
                self._scoped_count(model).where(column.is_not(None)),
                column,
                from_at,
                to_at,
                as_date=True,
            )
            total += await self._count(base)
            overdue += await self._count(base.where(column < today))
        return items, total, overdue

    def _ecology_permit_item(
        self,
        *,
        entity_id: str,
        title: str,
        anchor: datetime,
        now: datetime,
        include_fact: bool,
        include_sla: bool,
        extra: dict[str, Any],
    ) -> CalendarEventItem:
        is_overdue = anchor < now
        days_to_due = _days_to_due(anchor, now) if include_sla else None
        return CalendarEventItem(
            id=f"ecology_permit:{entity_id}",
            source_type="ecology_permit",
            source_id=entity_id,
            title=title,
            starts_at=anchor,
            ends_at=None,
            status="expired" if is_overdue else "valid",
            is_overdue=is_overdue,
            expected_at=anchor if include_fact else None,
            actual_at=None,
            variance_days=None,
            days_to_due=days_to_due,
            sla_band=(
                _sla_band("ecology_permit", days_to_due=days_to_due, is_overdue=is_overdue)
                if include_sla
                else None
            ),
            extra=extra,
        )

    async def _build_ecology_measurements(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Плановые даты замеров ПЭК из плана-графика.

        Периодичность платформа не назначает (граница среза-4) — календарь
        показывает ту дату, которая уже внесена в строке графика.
        """

        today = now.date()
        stmt = (
            select(EmissionMonitoringPlanItem)
            .where(
                EmissionMonitoringPlanItem.tenant_id == self.tenant_id,
                EmissionMonitoringPlanItem.deleted_at.is_(None),
            )
            .order_by(EmissionMonitoringPlanItem.next_due_on.asc())
            .limit(self._limit)
        )
        if from_at is not None:
            stmt = stmt.where(EmissionMonitoringPlanItem.next_due_on >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(EmissionMonitoringPlanItem.next_due_on <= to_at.date())

        items: list[CalendarEventItem] = []
        for plan in (await self.db.execute(stmt)).scalars().all():
            anchor = _coerce_dt(plan.next_due_on)
            if anchor is None:
                continue
            is_overdue = anchor < now
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            items.append(
                CalendarEventItem(
                    id=f"ecology_measurement:{plan.id}",
                    source_type="ecology_measurement",
                    source_id=str(plan.id),
                    title=f"Замер ПЭК: {plan.substance}",
                    starts_at=anchor,
                    ends_at=None,
                    status="overdue" if is_overdue else "planned",
                    is_overdue=is_overdue,
                    expected_at=anchor if include_fact else None,
                    actual_at=None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=(
                        _sla_band(
                            "ecology_measurement",
                            days_to_due=days_to_due,
                            is_overdue=is_overdue,
                        )
                        if include_sla
                        else None
                    ),
                    extra={
                        "substance": plan.substance,
                        "periodicity_months": plan.periodicity_months,
                        "next_due_on": plan.next_due_on.isoformat(),
                    },
                )
            )

        base = self._apply_window(
            self._scoped_count(EmissionMonitoringPlanItem),
            EmissionMonitoringPlanItem.next_due_on,
            from_at,
            to_at,
            as_date=True,
        )
        total = await self._count(base)
        overdue = await self._count(base.where(EmissionMonitoringPlanItem.next_due_on < today))
        return items, total, overdue

    async def _build_ecology_reports(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Сроки экологической отчётности и платежей (разд. 55.3, срез-71).

        Дату вносит эколог по нормативному акту; платформа её не назначает и не
        вычисляет — это граница среза-23. Исполненный срок (``done_on`` задан)
        в календарь НЕ попадает: сданный отчёт — не событие и не просрочка,
        иначе он лежал бы «просроченным» вечно после срока. Срок — на всю
        организацию, площадки у него нет, поэтому сужения по площадке нет.
        """

        today = now.date()
        stmt = (
            select(EcologyReportingDeadline)
            .where(
                EcologyReportingDeadline.tenant_id == self.tenant_id,
                EcologyReportingDeadline.deleted_at.is_(None),
                EcologyReportingDeadline.done_on.is_(None),
            )
            .order_by(EcologyReportingDeadline.due_on.asc(), EcologyReportingDeadline.title.asc())
            .limit(self._limit)
        )
        if from_at is not None:
            stmt = stmt.where(EcologyReportingDeadline.due_on >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(EcologyReportingDeadline.due_on <= to_at.date())

        items: list[CalendarEventItem] = []
        for row in (await self.db.execute(stmt)).scalars().all():
            anchor = _coerce_dt(row.due_on)
            if anchor is None:
                continue
            is_overdue = anchor < now
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            kind_label = REPORTING_KINDS.get(row.kind, row.kind)
            items.append(
                CalendarEventItem(
                    id=f"ecology_report:{row.id}",
                    source_type="ecology_report",
                    source_id=str(row.id),
                    title=f"{kind_label}: {row.title}",
                    starts_at=anchor,
                    ends_at=None,
                    status="overdue" if is_overdue else "planned",
                    is_overdue=is_overdue,
                    expected_at=anchor if include_fact else None,
                    actual_at=None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=(
                        _sla_band("ecology_report", days_to_due=days_to_due, is_overdue=is_overdue)
                        if include_sla
                        else None
                    ),
                    extra={
                        "kind": row.kind,
                        "kind_label": kind_label,
                        "period": row.period,
                        "due_on": row.due_on.isoformat(),
                        "responsible": row.responsible,
                    },
                )
            )

        base = self._apply_window(
            self._scoped_count(EcologyReportingDeadline).where(
                EcologyReportingDeadline.done_on.is_(None)
            ),
            EcologyReportingDeadline.due_on,
            from_at,
            to_at,
            as_date=True,
        )
        total = await self._count(base)
        overdue = await self._count(base.where(EcologyReportingDeadline.due_on < today))
        return items, total, overdue

    async def _build_epb(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Сроки заключений ЭПБ технических устройств на ОПО (разд. 57.2).

        Правила ТЕ ЖЕ, что у модуля ПромБез (``_epb_status``): списанное
        устройство просрочкой быть не может, а устройство БЕЗ срока — это
        «заключения нет», отдельное состояние, не срок и не просрочка; в
        календарь оно не попадает, потому что события без даты не бывает.
        Устройство привязано к ОПО, а не к площадке, поэтому сужения по
        площадке у источника нет.
        """

        today = now.date()
        stmt = (
            select(TechnicalDevice)
            .where(
                TechnicalDevice.tenant_id == self.tenant_id,
                TechnicalDevice.deleted_at.is_(None),
                TechnicalDevice.status != "decommissioned",
                TechnicalDevice.epb_valid_until.is_not(None),
            )
            .order_by(TechnicalDevice.epb_valid_until.asc())
            .limit(self._limit)
        )
        if from_at is not None:
            stmt = stmt.where(TechnicalDevice.epb_valid_until >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(TechnicalDevice.epb_valid_until <= to_at.date())

        items: list[CalendarEventItem] = []
        for device in (await self.db.execute(stmt)).scalars().all():
            anchor = _coerce_dt(device.epb_valid_until)
            if anchor is None:
                continue
            is_overdue = anchor < now
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            items.append(
                CalendarEventItem(
                    id=f"industrial_safety_epb:{device.id}",
                    source_type="industrial_safety_epb",
                    source_id=str(device.id),
                    title=f"ЭПБ: {device.name}",
                    starts_at=anchor,
                    ends_at=None,
                    status="expired" if is_overdue else "valid",
                    is_overdue=is_overdue,
                    expected_at=anchor if include_fact else None,
                    actual_at=None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=(
                        _sla_band(
                            "industrial_safety_epb",
                            days_to_due=days_to_due,
                            is_overdue=is_overdue,
                        )
                        if include_sla
                        else None
                    ),
                    extra={
                        "kind": device.kind,
                        "serial_number": device.serial_number,
                        "facility_id": str(device.facility_id),
                        "epb_conclusion_number": device.epb_conclusion_number,
                        "epb_valid_until": device.epb_valid_until.isoformat(),
                    },
                )
            )

        base = self._apply_window(
            self._scoped_count(TechnicalDevice).where(
                TechnicalDevice.status != "decommissioned",
                TechnicalDevice.epb_valid_until.is_not(None),
            ),
            TechnicalDevice.epb_valid_until,
            from_at,
            to_at,
            as_date=True,
        )
        total = await self._count(base)
        overdue = await self._count(base.where(TechnicalDevice.epb_valid_until < today))
        return items, total, overdue

    async def _build_cd_drills(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        site_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Учения и тренировки ГО из плана-графика, ещё НЕ проведённые (разд. 57.2).

        Проведённое учение — протокол, а не срок: в календарь оно не идёт, как
        и в модуле ГО (``_drill_status``: есть ``held_on`` — «проведено»).
        Дата в прошлом без протокола — «не проведены учения по ГО».
        """

        today = now.date()
        stmt = (
            select(CivilDefenseDrill)
            .where(
                CivilDefenseDrill.tenant_id == self.tenant_id,
                CivilDefenseDrill.deleted_at.is_(None),
                CivilDefenseDrill.held_on.is_(None),
            )
            .order_by(CivilDefenseDrill.planned_on.asc())
            .limit(self._limit)
        )
        if site_id:
            stmt = stmt.where(CivilDefenseDrill.site_id == site_id)
        if from_at is not None:
            stmt = stmt.where(CivilDefenseDrill.planned_on >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(CivilDefenseDrill.planned_on <= to_at.date())

        items: list[CalendarEventItem] = []
        for drill in (await self.db.execute(stmt)).scalars().all():
            anchor = _coerce_dt(drill.planned_on)
            if anchor is None:
                continue
            is_overdue = drill.planned_on < today
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            items.append(
                CalendarEventItem(
                    id=f"civil_defense_drill:{drill.id}",
                    source_type="civil_defense_drill",
                    source_id=str(drill.id),
                    title=f"Учение ГО: {drill.title}",
                    starts_at=anchor,
                    ends_at=None,
                    status="overdue" if is_overdue else "planned",
                    is_overdue=is_overdue,
                    expected_at=anchor if include_fact else None,
                    actual_at=None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=(
                        _sla_band(
                            "civil_defense_drill",
                            days_to_due=days_to_due,
                            is_overdue=is_overdue,
                        )
                        if include_sla
                        else None
                    ),
                    site_id=str(drill.site_id) if drill.site_id else None,
                    extra={
                        "kind": drill.kind,
                        "formation_id": str(drill.formation_id) if drill.formation_id else None,
                        "planned_on": drill.planned_on.isoformat(),
                    },
                )
            )

        base = self._apply_window(
            self._scoped_count(CivilDefenseDrill, site_id=site_id).where(
                CivilDefenseDrill.held_on.is_(None)
            ),
            CivilDefenseDrill.planned_on,
            from_at,
            to_at,
            as_date=True,
        )
        total = await self._count(base)
        overdue = await self._count(base.where(CivilDefenseDrill.planned_on < today))
        return items, total, overdue

    async def _build_vehicle_documents(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        site_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Сроки документов ТС: техосмотр, ОСАГО, лицензия, поверка тахографа.

        Один источник на все четыре срока: для ответственного за БДД это один
        вопрос «что по машинам истекает», вид срока лежит в ``extra.kind``.
        Считаются ТОЛЬКО эксплуатируемые ТС — как в модуле БДД: у списанной
        машины просроченный полис это шум, а не проблема. Пустая дата у ТС
        значит «сведений нет» (бессрочных техосмотров не бывает) — это не срок
        и в календарь не попадает; поверка тахографа — только если он стоит.
        """

        today = now.date()
        lo = from_at.date() if from_at is not None else None
        hi = to_at.date() if to_at is not None else None

        def _base(attr: str) -> Select[tuple[int]]:
            column = getattr(Vehicle, attr)
            stmt = self._scoped_count(Vehicle, site_id=site_id).where(
                Vehicle.status == "in_service", column.is_not(None)
            )
            if attr == "tachograph_due":
                stmt = stmt.where(Vehicle.tachograph_installed.is_(True))
            return stmt

        items: list[CalendarEventItem] = []
        for attr, kind, label in _VEHICLE_DUE_COLUMNS:
            column = getattr(Vehicle, attr)
            stmt = (
                select(Vehicle)
                .where(
                    Vehicle.tenant_id == self.tenant_id,
                    Vehicle.deleted_at.is_(None),
                    Vehicle.status == "in_service",
                    column.is_not(None),
                )
                .order_by(column.asc())
                .limit(self._limit)
            )
            if attr == "tachograph_due":
                stmt = stmt.where(Vehicle.tachograph_installed.is_(True))
            if site_id:
                stmt = stmt.where(Vehicle.site_id == site_id)
            if lo is not None:
                stmt = stmt.where(column >= lo)
            if hi is not None:
                stmt = stmt.where(column <= hi)
            for vehicle in (await self.db.execute(stmt)).scalars().all():
                due = getattr(vehicle, attr)
                anchor = _coerce_dt(due)
                if anchor is None:
                    continue
                is_overdue = due < today
                days_to_due = _days_to_due(anchor, now) if include_sla else None
                items.append(
                    CalendarEventItem(
                        id=f"road_safety_vehicle:{vehicle.id}:{kind}",
                        source_type="road_safety_vehicle",
                        source_id=str(vehicle.id),
                        title=f"{label}: {vehicle.plate_number}",
                        starts_at=anchor,
                        ends_at=None,
                        status="expired" if is_overdue else "valid",
                        is_overdue=is_overdue,
                        expected_at=anchor if include_fact else None,
                        actual_at=None,
                        variance_days=None,
                        days_to_due=days_to_due,
                        sla_band=(
                            _sla_band(
                                "road_safety_vehicle",
                                days_to_due=days_to_due,
                                is_overdue=is_overdue,
                            )
                            if include_sla
                            else None
                        ),
                        site_id=str(vehicle.site_id) if vehicle.site_id else None,
                        extra={
                            "kind": kind,
                            "plate_number": vehicle.plate_number,
                            "brand_model": vehicle.brand_model,
                            "due_on": due.isoformat(),
                        },
                    )
                )
        items.sort(key=lambda item: item.starts_at)
        items = items[: self._limit]

        total = 0
        overdue = 0
        for attr, _kind, _label in _VEHICLE_DUE_COLUMNS:
            column = getattr(Vehicle, attr)
            base = self._apply_window(_base(attr), column, from_at, to_at, as_date=True)
            total += await self._count(base)
            overdue += await self._count(base.where(column < today))
        return items, total, overdue

    async def _build_fire_equipment(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        site_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Сроки средств и систем ПБ: перезарядка и поверка/ТО (разд. 54.1, срез-79).

        Один источник на оба срока, вид — в ``extra.kind`` (как у документов
        ТС). Считаются ТОЛЬКО действующие единицы (``status == "active"``) —
        как в сводке готовности модуля ПБ: у списанного огнетушителя
        просроченная перезарядка это шум. Пустая дата значит «не применимо»
        (у крана нет перезарядки) — это не срок и в календарь не попадает.
        Срок двигает сама запись о выполненной работе (журнал ``fire_maintenance``),
        поэтому «факт» здесь не отдаётся: выполненная работа уже перенесла срок.
        """

        today = now.date()
        lo = from_at.date() if from_at is not None else None
        hi = to_at.date() if to_at is not None else None

        def _base(attr: str) -> Select[tuple[int]]:
            column = getattr(FireSafetyEquipment, attr)
            return self._scoped_count(FireSafetyEquipment, site_id=site_id).where(
                FireSafetyEquipment.status == "active", column.is_not(None)
            )

        items: list[CalendarEventItem] = []
        for attr, kind, label in _FIRE_EQUIPMENT_DUE_COLUMNS:
            column = getattr(FireSafetyEquipment, attr)
            stmt = (
                select(FireSafetyEquipment)
                .where(
                    FireSafetyEquipment.tenant_id == self.tenant_id,
                    FireSafetyEquipment.deleted_at.is_(None),
                    FireSafetyEquipment.status == "active",
                    column.is_not(None),
                )
                .order_by(column.asc())
                .limit(self._limit)
            )
            if site_id:
                stmt = stmt.where(FireSafetyEquipment.site_id == site_id)
            if lo is not None:
                stmt = stmt.where(column >= lo)
            if hi is not None:
                stmt = stmt.where(column <= hi)
            for unit in (await self.db.execute(stmt)).scalars().all():
                due = getattr(unit, attr)
                anchor = _coerce_dt(due)
                if anchor is None:
                    continue
                is_overdue = due < today
                days_to_due = _days_to_due(anchor, now) if include_sla else None
                title = f"{label}: {unit.label}"
                if unit.location:
                    title = f"{title} ({unit.location})"
                items.append(
                    CalendarEventItem(
                        id=f"fire_safety_equipment:{unit.id}:{kind}",
                        source_type="fire_safety_equipment",
                        source_id=str(unit.id),
                        title=title,
                        starts_at=anchor,
                        ends_at=None,
                        status="overdue" if is_overdue else "valid",
                        is_overdue=is_overdue,
                        expected_at=anchor if include_fact else None,
                        actual_at=None,
                        variance_days=None,
                        days_to_due=days_to_due,
                        sla_band=(
                            _sla_band(
                                "fire_safety_equipment",
                                days_to_due=days_to_due,
                                is_overdue=is_overdue,
                            )
                            if include_sla
                            else None
                        ),
                        site_id=str(unit.site_id) if unit.site_id else None,
                        extra={
                            "kind": kind,
                            "equipment_kind": unit.kind,
                            "label": unit.label,
                            "location": unit.location,
                            "due_on": due.isoformat(),
                        },
                    )
                )
        items.sort(key=lambda item: item.starts_at)
        items = items[: self._limit]

        total = 0
        overdue = 0
        for attr, _kind, _label in _FIRE_EQUIPMENT_DUE_COLUMNS:
            column = getattr(FireSafetyEquipment, attr)
            base = self._apply_window(_base(attr), column, from_at, to_at, as_date=True)
            total += await self._count(base)
            overdue += await self._count(base.where(column < today))
        return items, total, overdue

    async def _build_fire_drills(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        site_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Тренировки и учения по ПБ из плана-графика, ещё НЕ проведённые (разд. 54.1, срез-80).

        Та же логика, что у учений ГО (``_build_cd_drills``) и у сводки
        модуля ПБ (``overdue_drills``): проведённая тренировка — протокол,
        а не срок, в календарь не идёт; плановая дата в прошлом без
        ``held_on`` — «тренировка не проведена».
        """

        today = now.date()
        stmt = (
            select(FireDrill)
            .where(
                FireDrill.tenant_id == self.tenant_id,
                FireDrill.deleted_at.is_(None),
                FireDrill.held_on.is_(None),
            )
            .order_by(FireDrill.planned_on.asc())
            .limit(self._limit)
        )
        if site_id:
            stmt = stmt.where(FireDrill.site_id == site_id)
        if from_at is not None:
            stmt = stmt.where(FireDrill.planned_on >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(FireDrill.planned_on <= to_at.date())

        items: list[CalendarEventItem] = []
        for drill in (await self.db.execute(stmt)).scalars().all():
            anchor = _coerce_dt(drill.planned_on)
            if anchor is None:
                continue
            is_overdue = drill.planned_on < today
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            items.append(
                CalendarEventItem(
                    id=f"fire_safety_drill:{drill.id}",
                    source_type="fire_safety_drill",
                    source_id=str(drill.id),
                    title=f"Тренировка ПБ: {drill.title}",
                    starts_at=anchor,
                    ends_at=None,
                    status="overdue" if is_overdue else "planned",
                    is_overdue=is_overdue,
                    expected_at=anchor if include_fact else None,
                    actual_at=None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=(
                        _sla_band(
                            "fire_safety_drill",
                            days_to_due=days_to_due,
                            is_overdue=is_overdue,
                        )
                        if include_sla
                        else None
                    ),
                    site_id=str(drill.site_id) if drill.site_id else None,
                    extra={
                        "kind": drill.kind,
                        "planned_on": drill.planned_on.isoformat(),
                    },
                )
            )

        base = self._apply_window(
            self._scoped_count(FireDrill, site_id=site_id).where(FireDrill.held_on.is_(None)),
            FireDrill.planned_on,
            from_at,
            to_at,
            as_date=True,
        )
        total = await self._count(base)
        overdue = await self._count(base.where(FireDrill.planned_on < today))
        return items, total, overdue

    async def _build_fire_documents(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        site_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        """Срок пересмотра документов ПБ (разд. 54.1, срез-80).

        Бессрочный документ (``review_due IS NULL``) — не срок, как в сводке
        модуля (``overdue_documents``) и в статусе карточки
        (``_document_status``). Пересмотренный документ срок двигает сам —
        «факта» отдельно нет.
        """

        today = now.date()
        stmt = (
            select(FireSafetyDocument)
            .where(
                FireSafetyDocument.tenant_id == self.tenant_id,
                FireSafetyDocument.deleted_at.is_(None),
                FireSafetyDocument.review_due.is_not(None),
            )
            .order_by(FireSafetyDocument.review_due.asc())
            .limit(self._limit)
        )
        if site_id:
            stmt = stmt.where(FireSafetyDocument.site_id == site_id)
        if from_at is not None:
            stmt = stmt.where(FireSafetyDocument.review_due >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(FireSafetyDocument.review_due <= to_at.date())

        items: list[CalendarEventItem] = []
        for doc in (await self.db.execute(stmt)).scalars().all():
            due = doc.review_due
            anchor = _coerce_dt(due)
            if anchor is None or due is None:
                continue
            is_overdue = due < today
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            kind_title = FIRE_DOCUMENT_KINDS.get(doc.kind, "Документ ПБ")
            label = f"{kind_title} № {doc.number}" if doc.number else kind_title
            items.append(
                CalendarEventItem(
                    id=f"fire_safety_document:{doc.id}",
                    source_type="fire_safety_document",
                    source_id=str(doc.id),
                    title=f"Пересмотр: {label} — {doc.title}",
                    starts_at=anchor,
                    ends_at=None,
                    status="overdue" if is_overdue else "valid",
                    is_overdue=is_overdue,
                    expected_at=anchor if include_fact else None,
                    actual_at=None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=(
                        _sla_band(
                            "fire_safety_document",
                            days_to_due=days_to_due,
                            is_overdue=is_overdue,
                        )
                        if include_sla
                        else None
                    ),
                    site_id=str(doc.site_id) if doc.site_id else None,
                    extra={
                        "kind": doc.kind,
                        "number": doc.number,
                        "location": doc.location,
                        "responsible": doc.responsible,
                        "review_due": due.isoformat(),
                    },
                )
            )

        base = self._apply_window(
            self._scoped_count(FireSafetyDocument, site_id=site_id).where(
                FireSafetyDocument.review_due.is_not(None)
            ),
            FireSafetyDocument.review_due,
            from_at,
            to_at,
            as_date=True,
        )
        total = await self._count(base)
        overdue = await self._count(base.where(FireSafetyDocument.review_due < today))
        return items, total, overdue

    async def _build_ppe(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        person_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        stmt = (
            select(PPEIssue)
            .where(
                PPEIssue.tenant_id == self.tenant_id,
                PPEIssue.deleted_at.is_(None),
                PPEIssue.expires_at.is_not(None),
                self._employed_only(PPEIssue),
            )
            .order_by(PPEIssue.expires_at.asc())
            .limit(self._limit)
        )
        if person_id:
            stmt = stmt.where(PPEIssue.person_id == person_id)
        if from_at is not None:
            stmt = stmt.where(PPEIssue.expires_at >= from_at)
        if to_at is not None:
            stmt = stmt.where(PPEIssue.expires_at <= to_at)

        rows = (await self.db.execute(stmt)).scalars().all()
        items: list[CalendarEventItem] = []
        for issue in rows:
            anchor = _coerce_dt(issue.expires_at)
            if anchor is None:
                continue
            is_overdue = bool(issue.status == PPEIssueStatus.ISSUED and anchor < now)
            status_value = (
                "expired"
                if is_overdue
                else (issue.status.value if hasattr(issue.status, "value") else str(issue.status))
            )
            expected_at = anchor if include_fact else None
            actual_at = (
                _coerce_dt(issue.returned_at)
                if include_fact and issue.status == PPEIssueStatus.RETURNED
                else None
            )
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            sla_band = (
                _sla_band("ppe_issue", days_to_due=days_to_due, is_overdue=is_overdue)
                if include_sla
                else None
            )
            items.append(
                CalendarEventItem(
                    id=f"ppe_issue:{issue.id}",
                    source_type="ppe_issue",
                    source_id=str(issue.id),
                    title=f"СИЗ: {issue.item_name}",
                    starts_at=anchor,
                    ends_at=None,
                    status=status_value,
                    is_overdue=is_overdue,
                    person_id=str(issue.person_id) if issue.person_id else None,
                    expected_at=expected_at,
                    actual_at=actual_at,
                    variance_days=_variance_days(expected_at, actual_at),
                    days_to_due=days_to_due,
                    sla_band=sla_band,
                    extra={
                        "item_name": issue.item_name,
                        "quantity": issue.quantity,
                        "issued_at": issue.issued_at.isoformat() if issue.issued_at else None,
                        "expires_at": issue.expires_at.isoformat() if issue.expires_at else None,
                        "raw_status": (
                            issue.status.value
                            if hasattr(issue.status, "value")
                            else str(issue.status)
                        ),
                    },
                )
            )

        base_count = self._apply_window(
            self._scoped_count(PPEIssue, person_id=person_id).where(
                PPEIssue.expires_at.is_not(None), self._employed_only(PPEIssue)
            ),
            PPEIssue.expires_at,
            from_at,
            to_at,
        )
        total = await self._count(base_count)
        overdue = await self._count(
            base_count.where(
                PPEIssue.status == PPEIssueStatus.ISSUED,
                PPEIssue.expires_at < now,
            )
        )
        return items, total, overdue

    async def _build_permits(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        person_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        today = now.date()
        stmt = (
            select(Permit)
            .where(
                Permit.tenant_id == self.tenant_id,
                Permit.valid_until.is_not(None),
                # Срез-127: наряды-допуски были единственной веткой календаря
                # без этого отбора — медосмотры, СИЗ, обучение и сроки его
                # применяют с среза-93. Календарь не может считать уволенного
                # в одной строке и не считать в соседней.
                self._employed_only(Permit),
            )
            .order_by(Permit.valid_until.asc())
            .limit(self._limit)
        )
        if person_id:
            stmt = stmt.where(Permit.person_id == person_id)
        if from_at is not None:
            stmt = stmt.where(Permit.valid_until >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(Permit.valid_until <= to_at.date())

        rows = (await self.db.execute(stmt)).scalars().all()
        items: list[CalendarEventItem] = []
        for permit in rows:
            anchor = _coerce_dt(permit.valid_until)
            if anchor is None:
                continue
            is_overdue = bool(
                permit.status == PermitStatus.ACTIVE.value
                and permit.valid_until is not None
                and permit.valid_until < today
            )
            status_value = permit.status
            expected_at = anchor if include_fact else None
            actual_at = _coerce_dt(permit.issued_at) if include_fact else None
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            sla_band = (
                _sla_band("permit", days_to_due=days_to_due, is_overdue=is_overdue)
                if include_sla
                else None
            )
            items.append(
                CalendarEventItem(
                    id=f"permit:{permit.id}",
                    source_type="permit",
                    source_id=str(permit.id),
                    title=f"Допуск: {permit.permit_type}",
                    starts_at=anchor,
                    ends_at=None,
                    status="expired" if is_overdue else status_value,
                    is_overdue=is_overdue,
                    person_id=str(permit.person_id) if permit.person_id else None,
                    expected_at=expected_at,
                    actual_at=actual_at,
                    variance_days=_variance_days(expected_at, actual_at),
                    days_to_due=days_to_due,
                    sla_band=sla_band,
                    extra={
                        "permit_type": permit.permit_type,
                        "issued_at": permit.issued_at.isoformat() if permit.issued_at else None,
                        "valid_until": (
                            permit.valid_until.isoformat() if permit.valid_until else None
                        ),
                        "raw_status": status_value,
                    },
                )
            )

        base_count = self._apply_window(
            self._scoped_count(Permit, person_id=person_id).where(
                Permit.valid_until.is_not(None), self._employed_only(Permit)
            ),
            Permit.valid_until,
            from_at,
            to_at,
            as_date=True,
        )
        total = await self._count(base_count)
        overdue = await self._count(
            base_count.where(
                Permit.status == PermitStatus.ACTIVE.value,
                Permit.valid_until < today,
            )
        )
        return items, total, overdue

    async def _build_training(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        person_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        # `started_at` is the planning anchor; if absent, fall back to
        # `created_at` so unscheduled drafts still surface.
        anchor_col = func.coalesce(TrainingSession.started_at, TrainingSession.created_at)
        stmt = (
            select(TrainingSession, TrainingCourse.title)
            .outerjoin(TrainingCourse, TrainingCourse.id == TrainingSession.course_id)
            .where(
                TrainingSession.tenant_id == self.tenant_id, self._employed_only(TrainingSession)
            )
            .order_by(anchor_col.asc())
            .limit(self._limit)
        )
        if person_id:
            stmt = stmt.where(TrainingSession.person_id == person_id)
        if from_at is not None:
            stmt = stmt.where(anchor_col >= from_at)
        if to_at is not None:
            stmt = stmt.where(anchor_col <= to_at)

        rows = (await self.db.execute(stmt)).all()
        items: list[CalendarEventItem] = []
        for session_row, course_title in rows:
            anchor = _coerce_dt(session_row.started_at) or _coerce_dt(session_row.created_at)
            if anchor is None:
                continue
            status_raw = (
                session_row.status.value
                if hasattr(session_row.status, "value")
                else str(session_row.status)
            )
            is_overdue = bool(
                session_row.status == TrainingSessionStatus.SCHEDULED and anchor < now
            )
            expected_at = anchor if include_fact else None
            actual_at = (
                _coerce_dt(session_row.completed_at)
                if include_fact and session_row.status == TrainingSessionStatus.COMPLETED
                else None
            )
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            sla_band = (
                _sla_band("training_session", days_to_due=days_to_due, is_overdue=is_overdue)
                if include_sla
                else None
            )
            items.append(
                CalendarEventItem(
                    id=f"training_session:{session_row.id}",
                    source_type="training_session",
                    source_id=str(session_row.id),
                    title=(f"Обучение: {course_title}" if course_title else "Обучение (сессия)"),
                    starts_at=anchor,
                    ends_at=_coerce_dt(session_row.completed_at),
                    status=status_raw,
                    is_overdue=is_overdue,
                    person_id=str(session_row.person_id) if session_row.person_id else None,
                    expected_at=expected_at,
                    actual_at=actual_at,
                    variance_days=_variance_days(expected_at, actual_at),
                    days_to_due=days_to_due,
                    sla_band=sla_band,
                    extra={
                        "course_id": str(session_row.course_id) if session_row.course_id else None,
                        "course_title": course_title,
                        "plan_id": str(session_row.plan_id) if session_row.plan_id else None,
                        "score": session_row.score,
                    },
                )
            )

        base_count = self._apply_window(
            self._scoped_count(TrainingSession, person_id=person_id).where(
                self._employed_only(TrainingSession)
            ),
            anchor_col,
            from_at,
            to_at,
        )
        total = await self._count(base_count)
        # Approximate overdue: SCHEDULED with anchor < now.
        overdue = await self._count(
            base_count.where(
                TrainingSession.status == TrainingSessionStatus.SCHEDULED,
                anchor_col < now,
            )
        )
        return items, total, overdue

    async def _build_inspections(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        site_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        today = now.date()
        stmt = (
            select(Inspection)
            .where(
                Inspection.tenant_id == self.tenant_id,
                Inspection.deleted_at.is_(None),
                Inspection.scheduled_at.is_not(None),
            )
            .order_by(Inspection.scheduled_at.asc())
            .limit(self._limit)
        )
        if site_id:
            stmt = stmt.where(Inspection.site_id == site_id)
        if from_at is not None:
            stmt = stmt.where(Inspection.scheduled_at >= from_at.date())
        if to_at is not None:
            stmt = stmt.where(Inspection.scheduled_at <= to_at.date())

        rows = (await self.db.execute(stmt)).scalars().all()
        items: list[CalendarEventItem] = []
        for inspection in rows:
            anchor = _coerce_dt(inspection.scheduled_at)
            if anchor is None:
                continue
            status_raw = (
                inspection.status.value
                if hasattr(inspection.status, "value")
                else str(inspection.status)
            )
            is_overdue = bool(
                inspection.status == InspectionStatus.PLANNED
                and inspection.scheduled_at is not None
                and inspection.scheduled_at < today
            )
            expected_at = anchor if include_fact else None
            actual_at = (
                _coerce_dt(inspection.finished_at)
                if include_fact and inspection.status == InspectionStatus.COMPLETED
                else None
            )
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            sla_band = (
                _sla_band("inspection", days_to_due=days_to_due, is_overdue=is_overdue)
                if include_sla
                else None
            )
            items.append(
                CalendarEventItem(
                    id=f"inspection:{inspection.id}",
                    source_type="inspection",
                    source_id=str(inspection.id),
                    title=f"Проверка: {inspection.authority}",
                    starts_at=anchor,
                    ends_at=_coerce_dt(inspection.finished_at),
                    status=status_raw,
                    is_overdue=is_overdue,
                    site_id=str(inspection.site_id) if inspection.site_id else None,
                    company_id=str(inspection.company_id) if inspection.company_id else None,
                    assigned_user_id=(
                        str(inspection.responsible_id) if inspection.responsible_id else None
                    ),
                    expected_at=expected_at,
                    actual_at=actual_at,
                    variance_days=_variance_days(expected_at, actual_at),
                    days_to_due=days_to_due,
                    sla_band=sla_band,
                    extra={
                        "authority": inspection.authority,
                        "purpose": inspection.purpose,
                        "inspection_type": (
                            inspection.inspection_type.value
                            if hasattr(inspection.inspection_type, "value")
                            else str(inspection.inspection_type)
                        ),
                        "scheduled_at": (
                            inspection.scheduled_at.isoformat() if inspection.scheduled_at else None
                        ),
                    },
                )
            )

        base_count = (
            select(func.count())
            .select_from(Inspection)
            .where(
                Inspection.tenant_id == self.tenant_id,
                Inspection.deleted_at.is_(None),
                Inspection.scheduled_at.is_not(None),
            )
        )
        if site_id:
            base_count = base_count.where(Inspection.site_id == site_id)
        base_count = self._apply_window(
            base_count, Inspection.scheduled_at, from_at, to_at, as_date=True
        )
        total = await self._count(base_count)
        overdue = await self._count(
            base_count.where(
                Inspection.status == InspectionStatus.PLANNED,
                Inspection.scheduled_at < today,
            )
        )
        return items, total, overdue

    async def _build_deadlines(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        person_id: str | None,
        site_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        stmt = (
            select(ComplianceDeadline)
            .where(
                ComplianceDeadline.tenant_id == self.tenant_id,
                # Срез-116: снимок контрольных сроков — про человека, значит на
                # него распространяется общее правило «уволенный не в счёт».
                # Раньше единственный источник календаря, который его не знал:
                # просроченное удостоверение уволенного оставалось «горящим».
                self._employed_only(ComplianceDeadline),
            )
            .order_by(ComplianceDeadline.due_at.asc())
            .limit(self._limit)
        )
        if person_id:
            stmt = stmt.where(ComplianceDeadline.person_id == person_id)
        if site_id:
            stmt = stmt.where(ComplianceDeadline.site_id == site_id)
        if from_at is not None:
            stmt = stmt.where(ComplianceDeadline.due_at >= from_at)
        if to_at is not None:
            stmt = stmt.where(ComplianceDeadline.due_at <= to_at)

        rows = (await self.db.execute(stmt)).scalars().all()
        items: list[CalendarEventItem] = []
        for deadline in rows:
            anchor = _coerce_dt(deadline.due_at)
            if anchor is None:
                continue
            is_overdue = bool(deadline.status not in _CLOSED_DEADLINE_STATUSES and anchor < now)
            expected_at = anchor if include_fact else None
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            sla_band = (
                _sla_band(
                    "compliance_deadline",
                    days_to_due=days_to_due,
                    is_overdue=is_overdue,
                )
                if include_sla
                else None
            )
            items.append(
                CalendarEventItem(
                    id=f"compliance_deadline:{deadline.id}",
                    source_type="compliance_deadline",
                    source_id=str(deadline.id),
                    title=f"Срок: {deadline.entity_type}",
                    starts_at=anchor,
                    ends_at=None,
                    status=deadline.status,
                    is_overdue=is_overdue,
                    person_id=str(deadline.person_id) if deadline.person_id else None,
                    site_id=str(deadline.site_id) if deadline.site_id else None,
                    expected_at=expected_at,
                    actual_at=None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=sla_band,
                    extra={
                        "entity_type": deadline.entity_type,
                        "entity_id": str(deadline.entity_id),
                        "reminder_policy": deadline.reminder_policy,
                    },
                )
            )

        base_count = self._apply_window(
            self._scoped_count(ComplianceDeadline, person_id=person_id, site_id=site_id).where(
                self._employed_only(ComplianceDeadline)
            ),
            ComplianceDeadline.due_at,
            from_at,
            to_at,
        )
        total = await self._count(base_count)
        overdue = await self._count(
            base_count.where(
                overdue_compliance_deadline_where(now),
            )
        )
        return items, total, overdue

    async def _build_briefings(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        person_id: str | None,
        site_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int, dict[str, int]]:
        # Anchor on `valid_until` so the calendar shows when re-briefing is
        # due; rows without `valid_until` (one-shot/targeted) fall back to
        # `briefing_date`.
        anchor_col = func.coalesce(BriefingEntry.valid_until, BriefingEntry.briefing_date)
        stmt = (
            select(BriefingEntry, BriefingTemplate.title, Person.last_name, Person.first_name)
            .outerjoin(
                BriefingTemplate,
                BriefingTemplate.id == BriefingEntry.briefing_template_id,
            )
            .outerjoin(Person, Person.id == BriefingEntry.person_id)
            .where(
                BriefingEntry.tenant_id == self.tenant_id,
                BriefingEntry.deleted_at.is_(None),
                self._employed_only(BriefingEntry),
            )
            .order_by(anchor_col.asc())
            .limit(self._limit)
        )
        if person_id:
            stmt = stmt.where(BriefingEntry.person_id == person_id)
        if site_id:
            stmt = stmt.where(BriefingEntry.site_id == site_id)
        if from_at is not None:
            stmt = stmt.where(anchor_col >= from_at)
        if to_at is not None:
            stmt = stmt.where(anchor_col <= to_at)

        rows = (await self.db.execute(stmt)).all()
        items: list[CalendarEventItem] = []
        for entry, template_title, last_name, first_name in rows:
            anchor = _coerce_dt(entry.valid_until or entry.briefing_date)
            if anchor is None:
                continue
            valid_until_dt = _coerce_dt(entry.valid_until)
            is_overdue = bool(valid_until_dt is not None and valid_until_dt < now)
            # срез-81: вид — словами из закрытого словаря, а не кодом
            # (``fire_ptm`` на экране и в задаче по правилу — не подпись);
            # человек — в заголовке, как у назначений на обучение.
            kind_title = BRIEFING_TYPE_TITLES.get(entry.briefing_type, entry.briefing_type)
            title = f"Инструктаж: {template_title or kind_title}"
            person_name = " ".join(part for part in (last_name, first_name) if part)
            if person_name:
                title = f"{title} — {person_name}"
            expected_at = anchor if include_fact else None
            actual_at = _coerce_dt(entry.briefing_date) if include_fact else None
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            sla_band = (
                _sla_band("briefing_entry", days_to_due=days_to_due, is_overdue=is_overdue)
                if include_sla
                else None
            )
            items.append(
                CalendarEventItem(
                    id=f"briefing_entry:{entry.id}",
                    source_type="briefing_entry",
                    source_id=str(entry.id),
                    title=title,
                    starts_at=anchor,
                    ends_at=None,
                    status=entry.status,
                    is_overdue=is_overdue,
                    person_id=str(entry.person_id) if entry.person_id else None,
                    site_id=str(entry.site_id) if entry.site_id else None,
                    expected_at=expected_at,
                    actual_at=actual_at,
                    variance_days=_variance_days(expected_at, actual_at),
                    days_to_due=days_to_due,
                    sla_band=sla_band,
                    extra={
                        "briefing_type": entry.briefing_type,
                        "briefing_template_id": (
                            str(entry.briefing_template_id) if entry.briefing_template_id else None
                        ),
                        "briefing_template_title": template_title,
                        "briefing_date": (
                            entry.briefing_date.isoformat() if entry.briefing_date else None
                        ),
                        "valid_until": entry.valid_until.isoformat() if entry.valid_until else None,
                    },
                )
            )

        base_count = self._apply_window(
            self._scoped_count(BriefingEntry, person_id=person_id, site_id=site_id).where(
                self._employed_only(BriefingEntry)
            ),
            anchor_col,
            from_at,
            to_at,
        )
        total = await self._count(base_count)
        overdue_where = (
            BriefingEntry.valid_until.is_not(None),
            BriefingEntry.valid_until < now,
        )
        overdue = await self._count(base_count.where(*overdue_where))
        # Срез-58: те же просрочки, разложенные по виду инструктажа. Дисциплина
        # инструктажа зависит от вида, а не от таблицы (разд. 54.1 / 56.2:
        # противопожарный и по БДД живут рядом с инструктажем по охране труда),
        # и Центру внимания нужен честный COUNT по каждому виду, а не догадка
        # по показанному (обрезанному) списку. Фильтры — те же, что у
        # ``base_count``: окно, человек, площадка, без удалённых.
        by_kind_stmt = self._apply_window(
            select(BriefingEntry.briefing_type, func.count())
            .where(
                BriefingEntry.tenant_id == self.tenant_id,
                BriefingEntry.deleted_at.is_(None),
                self._employed_only(BriefingEntry),
                *overdue_where,
            )
            .group_by(BriefingEntry.briefing_type),
            anchor_col,
            from_at,
            to_at,
        )
        if person_id:
            by_kind_stmt = by_kind_stmt.where(BriefingEntry.person_id == person_id)
        if site_id:
            by_kind_stmt = by_kind_stmt.where(BriefingEntry.site_id == site_id)
        overdue_by_kind = {
            str(kind): int(amount or 0)
            for kind, amount in (await self.db.execute(by_kind_stmt)).all()
        }
        return items, total, overdue, overdue_by_kind

    async def _build_calendar_events(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        site_id: str | None,
        now: datetime,
        include_fact: bool = False,
        include_sla: bool = False,
    ) -> tuple[list[CalendarEventItem], int, int]:
        stmt = (
            select(CalendarEvent)
            .where(CalendarEvent.tenant_id == self.tenant_id)
            .order_by(CalendarEvent.starts_at.asc())
            .limit(self._limit)
        )
        if site_id:
            stmt = stmt.where(CalendarEvent.site_id == site_id)
        if from_at is not None:
            stmt = stmt.where(CalendarEvent.starts_at >= from_at)
        if to_at is not None:
            stmt = stmt.where(CalendarEvent.starts_at <= to_at)

        rows = (await self.db.execute(stmt)).scalars().all()
        items: list[CalendarEventItem] = []
        for event in rows:
            anchor = _coerce_dt(event.starts_at)
            if anchor is None:
                continue
            is_overdue = bool(event.status == "active" and anchor < now)
            expected_at = anchor if include_fact else None
            days_to_due = _days_to_due(anchor, now) if include_sla else None
            sla_band = (
                _sla_band("calendar_event", days_to_due=days_to_due, is_overdue=is_overdue)
                if include_sla
                else None
            )
            items.append(
                CalendarEventItem(
                    id=f"calendar_event:{event.id}",
                    source_type="calendar_event",
                    source_id=str(event.id),
                    title=event.title,
                    starts_at=anchor,
                    ends_at=_coerce_dt(event.ends_at),
                    status=event.status,
                    is_overdue=is_overdue,
                    site_id=str(event.site_id) if event.site_id else None,
                    assigned_user_id=(
                        str(event.assigned_user_id) if event.assigned_user_id else None
                    ),
                    expected_at=expected_at,
                    actual_at=None,
                    variance_days=None,
                    days_to_due=days_to_due,
                    sla_band=sla_band,
                    extra={
                        "projection_source_type": event.source_type,
                        "projection_source_id": str(event.source_id),
                    },
                )
            )

        base_count = (
            select(func.count())
            .select_from(CalendarEvent)
            .where(CalendarEvent.tenant_id == self.tenant_id)
        )
        if site_id:
            base_count = base_count.where(CalendarEvent.site_id == site_id)
        base_count = self._apply_window(base_count, CalendarEvent.starts_at, from_at, to_at)
        total = await self._count(base_count)
        overdue = await self._count(
            base_count.where(
                CalendarEvent.status == "active",
                CalendarEvent.starts_at < now,
            )
        )
        return items, total, overdue

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _employed_only(self, model: type[Any]) -> Any:
        """«Уволенный не в счёт» (срез-93): запись удалённого или уволенного
        человека в календарь не попадает. Запись без человека остаётся — она
        про журнал или площадку, а не про сотрудника. Само условие — общее
        с блокерами готовности и Командным центром (срез-95)."""

        return employed_record_where(model, self.tenant_id)

    def _scoped_count(
        self,
        model: type[Any],
        *,
        person_id: str | None = None,
        site_id: str | None = None,
    ) -> Select[tuple[int]]:
        stmt = select(func.count()).select_from(model).where(model.tenant_id == self.tenant_id)
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        if person_id and hasattr(model, "person_id"):
            stmt = stmt.where(model.person_id == person_id)
        if site_id and hasattr(model, "site_id"):
            stmt = stmt.where(model.site_id == site_id)
        return stmt

    @staticmethod
    def _apply_window(
        stmt: Select[tuple[int]],
        column: Any,
        from_at: datetime | None,
        to_at: datetime | None,
        *,
        as_date: bool = False,
    ) -> Select[tuple[int]]:
        """Apply the same from_at/to_at window to a count query that the matching
        item-list query uses, so per-source totals/overdue match the windowed list
        (a count without the window reports all-time figures)."""
        lo = from_at.date() if (as_date and from_at is not None) else from_at
        hi = to_at.date() if (as_date and to_at is not None) else to_at
        if lo is not None:
            stmt = stmt.where(column >= lo)
        if hi is not None:
            stmt = stmt.where(column <= hi)
        return stmt

    async def _count(self, stmt: Select[tuple[int]]) -> int:
        return int((await self.db.execute(stmt)).scalar_one() or 0)
