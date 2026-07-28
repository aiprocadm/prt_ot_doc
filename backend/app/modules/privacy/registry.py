"""SEC-66 срез-3: реестр обработки ПДн и договоры поручения (разд. 66.1, 66.3).

Реестр обработки должен быть «данными в системе, а не Excel» — но пустая форма
на 12 полей этого не даёт: её никто не заполнит, и в проверку арендатор придёт с
пустым реестром. Поэтому здесь есть :data:`DEFAULT_ACTIVITIES` — типовой реестр,
выведенный из того, что платформа РЕАЛЬНО делает с ПДн (кадровый учёт, медосмотры
как специальная категория, обучение, СИЗ, инциденты). Арендатор досевает его одной
операцией и дальше правит под себя.

Сроки хранения в типовом реестре указаны вместе с основанием: «3 года» без ссылки
на норму в реестре бесполезно, потому что проверяют именно основание срока.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.privacy_registry import (
    PDN_AGREEMENT_KINDS,
    PDN_AGREEMENT_STATUSES,
    PDN_DATA_CATEGORIES,
    PDN_PARTY_ROLES,
    PDN_SUBJECT_CATEGORIES,
    PdnProcessingActivity,
    PdnProcessingAgreement,
)

__all__ = [
    "PdnProcessingRegistryService",
    "PdnAgreementService",
    "DEFAULT_ACTIVITIES",
    "DefaultActivity",
    "InvalidRegistryValueError",
]


class InvalidRegistryValueError(ValueError):
    """Значение вне справочника разд. 66.1/66.3."""

    def __init__(self, field_name: str, value: str) -> None:
        super().__init__(f"{field_name}={value}")
        self.field_name = field_name
        self.value = value


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class DefaultActivity:
    code: str
    name: str
    purpose: str
    legal_basis: str
    data_categories: tuple[str, ...]
    subject_categories: tuple[str, ...]
    retention_months: int | None
    retention_basis: str | None
    access_roles: tuple[str, ...]
    recipients: tuple[str, ...] = field(default=())


# Типовой реестр: то, что платформа делает с ПДн «из коробки».
DEFAULT_ACTIVITIES: tuple[DefaultActivity, ...] = (
    DefaultActivity(
        code="hr_records",
        name="Кадровый учёт работников",
        purpose="employment",
        legal_basis="contract",
        data_categories=("regular",),
        subject_categories=("employees",),
        retention_months=600,  # 50 лет
        retention_basis="ст. 22.1 ФЗ-125 «Об архивном деле» — документы по личному составу",
        access_roles=("admin", "owner", "hr"),
    ),
    DefaultActivity(
        code="medical_exams",
        name="Медицинские осмотры и допуски",
        # СПЕЦИАЛЬНАЯ категория: данные о здоровье. Основание — не согласие, а
        # обязанность работодателя, поэтому отзыв согласия их не затрагивает.
        purpose="medical_exams",
        legal_basis="legal_obligation",
        data_categories=("regular", "special_health"),
        subject_categories=("employees",),
        retention_months=600,
        retention_basis="ст. 220 ТК РФ; приказ Минздрава 29н — обязательные медосмотры",
        access_roles=("admin", "owner", "hr"),
        recipients=("медицинская организация",),
    ),
    DefaultActivity(
        code="occupational_safety",
        name="Охрана труда: инструктажи, СИЗ, оценка рисков",
        purpose="occupational_safety",
        legal_basis="legal_obligation",
        data_categories=("regular",),
        subject_categories=("employees", "contractor_employees"),
        retention_months=60,
        retention_basis="разд. X ТК РФ; правила ведения журналов инструктажей",
        access_roles=("admin", "owner", "hr", "ot_pb_lead", "line_manager"),
    ),
    DefaultActivity(
        code="training",
        name="Обучение и аттестация по охране труда",
        purpose="training",
        legal_basis="legal_obligation",
        data_categories=("regular",),
        subject_categories=("employees",),
        retention_months=60,
        retention_basis="постановление 2464 — обучение по охране труда",
        access_roles=("admin", "owner", "hr", "ot_pb_lead"),
        recipients=("учебный центр", "ФРДО"),
    ),
    DefaultActivity(
        code="incidents",
        name="Расследование несчастных случаев и инцидентов",
        purpose="occupational_safety",
        legal_basis="legal_obligation",
        data_categories=("regular", "special_health"),
        subject_categories=("employees", "contractor_employees"),
        retention_months=540,  # 45 лет
        retention_basis="ст. 230.1 ТК РФ — хранение материалов расследования",
        access_roles=("admin", "owner", "ot_pb_lead"),
        recipients=("ГИТ", "ФСС"),
    ),
)


class PdnProcessingRegistryService:
    """Реестр обработки ПДн (разд. 66.1)."""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = str(tenant_id)

    async def list_activities(self, *, active_only: bool = False) -> list[PdnProcessingActivity]:
        stmt = select(PdnProcessingActivity).where(
            PdnProcessingActivity.tenant_id == self.tenant_id
        )
        if active_only:
            stmt = stmt.where(PdnProcessingActivity.is_active.is_(True))
        rows = (
            (await self.session.execute(stmt.order_by(PdnProcessingActivity.code.asc())))
            .scalars()
            .all()
        )
        return list(rows)

    async def get_by_code(self, code: str) -> PdnProcessingActivity | None:
        return (
            await self.session.execute(
                select(PdnProcessingActivity).where(
                    PdnProcessingActivity.tenant_id == self.tenant_id,
                    PdnProcessingActivity.code == code,
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def _validate(
        *,
        data_categories: list[str] | tuple[str, ...],
        subject_categories: list[str] | tuple[str, ...],
    ) -> None:
        for value in data_categories:
            if value not in PDN_DATA_CATEGORIES:
                raise InvalidRegistryValueError("data_categories", value)
        for value in subject_categories:
            if value not in PDN_SUBJECT_CATEGORIES:
                raise InvalidRegistryValueError("subject_categories", value)

    async def upsert(
        self,
        *,
        code: str,
        name: str,
        purpose: str,
        legal_basis: str,
        data_categories: list[str],
        subject_categories: list[str],
        retention_months: int | None = None,
        retention_basis: str | None = None,
        access_roles: list[str] | None = None,
        recipients: list[str] | None = None,
        storage_location: str = "RU",
        cross_border_transfer: bool = False,
        review_at=None,
        notes: str | None = None,
    ) -> PdnProcessingActivity:
        """Создать или обновить строку реестра по коду.

        Upsert, а не отдельные create/update: код процесса — естественный ключ
        (UNIQUE(tenant_id, code)), и повторная отправка того же процесса должна
        обновлять его, а не падать на конфликте.
        """

        self._validate(data_categories=data_categories, subject_categories=subject_categories)

        activity = await self.get_by_code(code)
        if activity is None:
            activity = PdnProcessingActivity(tenant_id=self.tenant_id, code=code)
            self.session.add(activity)

        activity.name = name
        activity.purpose = purpose
        activity.legal_basis = legal_basis
        activity.data_categories = list(data_categories)
        activity.subject_categories = list(subject_categories)
        activity.retention_months = retention_months
        activity.retention_basis = retention_basis
        activity.access_roles = list(access_roles or [])
        activity.recipients = list(recipients or [])
        activity.storage_location = storage_location
        activity.cross_border_transfer = cross_border_transfer
        activity.review_at = review_at
        activity.notes = notes
        activity.is_active = True
        await self.session.flush()
        return activity

    async def deactivate(self, code: str) -> PdnProcessingActivity | None:
        """Процессы не удаляются: реестр должен показывать и прекращённую обработку."""

        activity = await self.get_by_code(code)
        if activity is None:
            return None
        activity.is_active = False
        await self.session.flush()
        return activity

    async def seed_defaults(self) -> list[PdnProcessingActivity]:
        """Досеять типовой реестр. Существующие строки НЕ перезаписываются.

        Идемпотентно и неразрушающе: арендатор мог уже поправить сроки и состав
        получателей под себя, и повторный засев не должен это затирать.
        """

        existing = {row.code for row in await self.list_activities()}
        created: list[PdnProcessingActivity] = []
        for default in DEFAULT_ACTIVITIES:
            if default.code in existing:
                continue
            created.append(
                await self.upsert(
                    code=default.code,
                    name=default.name,
                    purpose=default.purpose,
                    legal_basis=default.legal_basis,
                    data_categories=list(default.data_categories),
                    subject_categories=list(default.subject_categories),
                    retention_months=default.retention_months,
                    retention_basis=default.retention_basis,
                    access_roles=list(default.access_roles),
                    recipients=list(default.recipients),
                )
            )
        return created


class PdnAgreementService:
    """Договоры поручения и роли Оператор / Обработчик (разд. 66.3)."""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = str(tenant_id)

    async def list_agreements(self) -> list[PdnProcessingAgreement]:
        rows = (
            (
                await self.session.execute(
                    select(PdnProcessingAgreement)
                    .where(PdnProcessingAgreement.tenant_id == self.tenant_id)
                    .order_by(PdnProcessingAgreement.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def create(
        self,
        *,
        kind: str,
        party_role: str,
        counterparty_name: str,
        counterparty_inn: str | None = None,
        counterparty_tenant_slug: str | None = None,
        document_ref: str | None = None,
        signed_at=None,
        valid_until=None,
        status: str = "draft",
        subprocessing_allowed: bool = False,
        breach_notification_hours: int | None = None,
        covered_activity_codes: list[str] | None = None,
        notes: str | None = None,
    ) -> PdnProcessingAgreement:
        if kind not in PDN_AGREEMENT_KINDS:
            raise InvalidRegistryValueError("kind", kind)
        if party_role not in PDN_PARTY_ROLES:
            raise InvalidRegistryValueError("party_role", party_role)
        if status not in PDN_AGREEMENT_STATUSES:
            raise InvalidRegistryValueError("status", status)

        agreement = PdnProcessingAgreement(
            tenant_id=self.tenant_id,
            kind=kind,
            party_role=party_role,
            counterparty_name=counterparty_name,
            counterparty_inn=counterparty_inn,
            counterparty_tenant_slug=counterparty_tenant_slug,
            document_ref=document_ref,
            signed_at=signed_at,
            valid_until=valid_until,
            status=status,
            subprocessing_allowed=subprocessing_allowed,
            breach_notification_hours=breach_notification_hours,
            covered_activity_codes=list(covered_activity_codes or []),
            notes=notes,
        )
        self.session.add(agreement)
        await self.session.flush()
        return agreement

    async def terminate(self, agreement_id: str) -> PdnProcessingAgreement | None:
        """Расторжение — смена статуса, не удаление: цепочку ответственности
        по 152-ФЗ нужно уметь восстановить и после расторжения."""

        agreement = (
            await self.session.execute(
                select(PdnProcessingAgreement).where(
                    PdnProcessingAgreement.tenant_id == self.tenant_id,
                    PdnProcessingAgreement.id == str(agreement_id),
                )
            )
        ).scalar_one_or_none()
        if agreement is None:
            return None
        agreement.status = "terminated"
        agreement.terminated_at = _utcnow()
        await self.session.flush()
        return agreement

    async def uncovered_activity_codes(self) -> list[str]:
        """Активные процессы реестра, не покрытые ни одним ДЕЙСТВУЮЩИМ договором.

        Прямой ответ на вопрос разд. 66.3 «кто за что отвечает»: если процесс
        обработки ни в одном поручении не назван, ответственность не распределена.
        """

        registry = PdnProcessingRegistryService(self.session, tenant_id=self.tenant_id)
        active_codes = {row.code for row in await registry.list_activities(active_only=True)}
        covered: set[str] = set()
        for agreement in await self.list_agreements():
            if agreement.status != "active":
                continue
            covered.update(agreement.covered_activity_codes or [])
        return sorted(active_codes - covered)
