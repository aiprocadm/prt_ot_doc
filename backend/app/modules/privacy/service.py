"""SEC-66 срез-1: выгрузка ПДн субъекта и журнал доступа к ним (разд. 66.2).

Два сервиса:

* :class:`PdnAccessJournal` — append-only запись «кто/когда/зачем читал ПДн
  субъекта» + чтение журнала по субъекту. Единственный писатель таблицы
  ``pdn_access_log``.
* :class:`PdnSubjectExportService` — «право на доступ к своим данным»: собирает
  все ПДн субъекта в один машиночитаемый документ.

Выгрузка не дублирует доменную логику: она берёт готовый агрегат
:class:`~app.services.employee_card.EmployeeCardService`, лишь поднимая предел
строк на секцию (UI-карточке хватает 50, юридической выгрузке — нет).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_data import Person
from app.models.privacy import PdnAccessLog
from app.schemas.employee import EmployeeCard
from app.schemas.privacy import PdnAccessLogEntry, PdnExportSubject, PdnSubjectExport
from app.services.employee_card import EmployeeCardService

__all__ = [
    "PdnAccessJournal",
    "PdnSubjectExportService",
    "load_subject",
    "to_access_log_entry",
    "PDN_EXPORT_MAX_ITEMS",
    "PDN_ACCESS_LOG_IN_EXPORT",
    "PDN_FEATURE_CODE",
]

# Фичефлаг контура. Default-ON (см. app/modules/privacy/api.py): это требование
# закона, а не пилот. Живёт в сервисе, чтобы карточка сотрудника могла свериться
# с ним, не импортируя чужой API-модуль.
PDN_FEATURE_CODE = "pdn_subject_rights"

# Потолок строк на секцию в выгрузке. Не «без лимита»: запрос субъекта не должен
# превращаться в способ выкачать историю арендатора одним ответом. Секции несут
# полные счётчики, поэтому обрезка видна получателю (`PdnSubjectExport.truncated`).
PDN_EXPORT_MAX_ITEMS = 1000

# Сколько последних записей журнала доступа кладём в саму выгрузку.
PDN_ACCESS_LOG_IN_EXPORT = 200

# Категории ПДн по разд. 66.1. «Специальная категория» (здоровье) появляется в
# выгрузке только если у субъекта реально есть медицинские записи.
_CATEGORY_REGULAR = "regular"
_CATEGORY_SPECIAL_HEALTH = "special_health"

# (счётчик, список) по секциям карточки — для честного признака обрезки.
_SECTION_COUNTERS: tuple[tuple[str, str, str], ...] = (
    ("training", "sessions_count", "sessions"),
    ("training", "certificates_count", "certificates"),
    ("medicals", "count", "items"),
    ("ppe", "count", "items"),
    ("permits", "count", "items"),
    ("incidents", "count", "items"),
    ("documents", "count", "items"),
    ("briefings", "count", "items"),
    ("compliance_deadlines", "count", "items"),
    ("audit", "count", "items"),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def load_subject(session: AsyncSession, *, tenant_id: str, person_id: str) -> Person | None:
    """Найти субъекта ПДн в границах арендатора (дешёвая проверка существования)."""

    return (
        await session.execute(
            select(Person).where(
                Person.id == person_id,
                Person.tenant_id == str(tenant_id),
                Person.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


def to_access_log_entry(row: PdnAccessLog) -> PdnAccessLogEntry:
    return PdnAccessLogEntry(
        id=str(row.id),
        subject_person_id=str(row.subject_person_id),
        action=row.action,
        actor_user_id=str(row.actor_user_id) if row.actor_user_id else None,
        actor_email=row.actor_email,
        actor_role=row.actor_role,
        purpose=row.purpose,
        ip=row.ip,
        request_id=row.request_id,
        occurred_at=row.occurred_at,
    )


class PdnAccessJournal:
    """Append-only журнал обращений к ПДн субъекта (разд. 66.2)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        tenant_id: str,
        subject_person_id: str,
        action: str,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
        actor_role: str | None = None,
        purpose: str | None = None,
        ip: str | None = None,
        request_id: str | None = None,
    ) -> PdnAccessLog:
        """Записать обращение. Ошибки НЕ глушатся: молчаливый no-op здесь означал бы
        «журнал ведётся», хотя он пуст — ровно та поломка, которую нельзя заметить."""

        entry = PdnAccessLog(
            tenant_id=str(tenant_id),
            subject_person_id=str(subject_person_id),
            action=action,
            actor_user_id=str(actor_user_id) if actor_user_id else None,
            actor_email=actor_email,
            actor_role=actor_role,
            purpose=purpose,
            ip=ip,
            request_id=request_id,
            occurred_at=_utcnow(),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_for_subject(
        self,
        *,
        tenant_id: str,
        subject_person_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PdnAccessLog], int]:
        base = select(PdnAccessLog).where(
            PdnAccessLog.tenant_id == str(tenant_id),
            PdnAccessLog.subject_person_id == str(subject_person_id),
        )
        total = (
            await self.session.execute(
                select(func.count())
                .select_from(PdnAccessLog)
                .where(
                    PdnAccessLog.tenant_id == str(tenant_id),
                    PdnAccessLog.subject_person_id == str(subject_person_id),
                )
            )
        ).scalar_one()
        rows = (
            (
                await self.session.execute(
                    base.order_by(PdnAccessLog.occurred_at.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), int(total)


class PdnSubjectExportService:
    """«Право на доступ»: все ПДн субъекта одним машиночитаемым документом."""

    def __init__(self, *, tenant_id: str, session: AsyncSession) -> None:
        self.tenant_id = str(tenant_id)
        self.session = session

    async def build(self, person_id: str) -> PdnSubjectExport | None:
        person = await load_subject(self.session, tenant_id=self.tenant_id, person_id=person_id)
        if person is None:
            return None

        card_service = EmployeeCardService(
            tenant_id=self.tenant_id,
            db=self.session,
            max_items_per_section=PDN_EXPORT_MAX_ITEMS,
        )
        card = await card_service.build(person_id)
        if card is None:  # pragma: no cover — person уже проверен выше
            return None

        journal = PdnAccessJournal(self.session)
        log_rows, _ = await journal.list_for_subject(
            tenant_id=self.tenant_id,
            subject_person_id=person_id,
            limit=PDN_ACCESS_LOG_IN_EXPORT,
        )

        return PdnSubjectExport(
            tenant_id=self.tenant_id,
            generated_at=_utcnow(),
            subject=PdnExportSubject(
                person_id=str(person.id),
                full_name=card.personal.fio,
                email=person.email,
                personnel_number=person.personnel_number,
            ),
            data_categories=self._categories(card),
            truncated=self._is_truncated(card),
            max_items_per_section=PDN_EXPORT_MAX_ITEMS,
            data=card,
            access_log=[to_access_log_entry(row) for row in log_rows],
        )

    @staticmethod
    def _categories(card: EmployeeCard) -> list[str]:
        categories = [_CATEGORY_REGULAR]
        if card.medicals.count > 0:
            categories.append(_CATEGORY_SPECIAL_HEALTH)
        return categories

    @staticmethod
    def _is_truncated(card: EmployeeCard) -> bool:
        for section_name, counter_attr, list_attr in _SECTION_COUNTERS:
            section = getattr(card, section_name)
            if getattr(section, counter_attr) > len(getattr(section, list_attr)):
                return True
        return False
