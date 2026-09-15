"""Схемы контура ПДн / 152-ФЗ (SEC-66 срез-1, разд. 66.2 «права субъекта»).

Два права субъекта закрываются этим срезом:

* «доступ к своим данным» — `PdnSubjectExport`: машиночитаемая выгрузка всех ПДн
  субъекта одним документом;
* «журнал доступа» — `PdnAccessLogPage`: кто и когда эти данные читал.

Выгрузка переиспользует агрегат `EmployeeCard` (единый источник правды о
сотруднике) и не заводит параллельного представления данных.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, model_validator

from app.schemas.base import BaseSchema
from app.schemas.employee import EmployeeCard

__all__ = [
    "PdnAccessLogEntry",
    "PdnAccessLogPage",
    "PdnSubjectExport",
    "PdnExportSubject",
    "PdnConsentEntry",
    "PdnConsentPage",
    "PdnConsentGrant",
    "PdnConsentWithdraw",
    "PdnErasureRequest",
    "PdnErasureResult",
    "PdnProcessingActivityEntry",
    "PdnProcessingActivityPage",
    "PdnProcessingActivityUpsert",
    "PdnAgreementEntry",
    "PdnAgreementPage",
    "PdnAgreementCreate",
]


class PdnAccessLogEntry(BaseSchema):
    """Одно обращение к ПДн субъекта."""

    id: str
    subject_person_id: str
    action: str
    actor_user_id: str | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    purpose: str | None = None
    ip: str | None = None
    request_id: str | None = None
    occurred_at: datetime


class PdnAccessLogPage(BaseSchema):
    items: list[PdnAccessLogEntry] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class PdnExportSubject(BaseSchema):
    """Идентификация субъекта в шапке выгрузки."""

    person_id: str
    full_name: str
    email: str | None = None
    personnel_number: str | None = None


class PdnSubjectExport(BaseSchema):
    """Ответ на запрос субъекта о предоставлении его персональных данных.

    `truncated` честно сообщает, что какая-то секция карточки упёрлась в предел
    `PDN_EXPORT_MAX_ITEMS`: счётчики внутри секций всегда полные, поэтому расхождение
    «счётчик > длины списка» видно и получателю выгрузки.
    """

    format_version: str = "1.0"
    tenant_id: str
    generated_at: datetime
    subject: PdnExportSubject
    # Категории ПДн в выгрузке (разд. 66.1): обычные и специальные (здоровье).
    data_categories: list[str] = Field(default_factory=list)
    truncated: bool = False
    max_items_per_section: int
    data: EmployeeCard
    access_log: list[PdnAccessLogEntry] = Field(default_factory=list)


class PdnConsentEntry(BaseSchema):
    """Одна версия согласия субъекта (SEC-66 срез-2, разд. 66.1)."""

    id: str
    subject_person_id: str
    purpose: str
    legal_basis: str
    version: int
    status: str
    document_ref: str | None = None
    text_sha256: str | None = None
    expires_at: datetime | None = None
    granted_at: datetime
    withdrawn_at: datetime | None = None
    withdrawal_reason: str | None = None
    recorded_by_email: str | None = None


class PdnConsentPage(BaseSchema):
    items: list[PdnConsentEntry] = Field(default_factory=list)
    total: int
    # Основания, по которым обработка остаётся правомерной. Пусто → обрабатывать
    # субъекта больше не на чем и обезличивание становится обязанностью.
    remaining_legal_bases: list[str] = Field(default_factory=list)


class PdnConsentGrant(BaseSchema):
    purpose: str
    legal_basis: str = "consent"
    document_ref: str | None = Field(default=None, max_length=255)
    text_sha256: str | None = Field(default=None, max_length=64)
    expires_at: datetime | None = None


class PdnConsentWithdraw(BaseSchema):
    purpose: str
    reason: str | None = None


class PdnErasureRequest(BaseSchema):
    reason: str | None = None


class PdnErasureResult(BaseSchema):
    """Доказательство обезличивания: что вычистили и что сохранили."""

    id: str
    subject_person_id: str
    pseudonym: str
    reason: str | None = None
    # поле → было ли в нём значение до вычистки
    scrubbed_fields: dict[str, bool] = Field(default_factory=dict)
    # раздел → сколько записей сохранено обезличенными (требование сроков хранения)
    retained_sections: dict[str, int] = Field(default_factory=dict)
    performed_at: datetime
    performed_by_email: str | None = None
    # True, если субъект уже был обезличен и повторный вызов ничего не менял
    already_anonymized: bool = False


class PdnProcessingActivityEntry(BaseSchema):
    """Строка реестра обработки ПДн (SEC-66 срез-3, разд. 66.1)."""

    id: str
    code: str
    name: str
    purpose: str
    purpose_description: str | None = None
    legal_basis: str
    data_categories: list[str] = Field(default_factory=list)
    subject_categories: list[str] = Field(default_factory=list)
    retention_months: int | None = None
    retention_basis: str | None = None
    access_roles: list[str] = Field(default_factory=list)
    recipients: list[str] = Field(default_factory=list)
    storage_location: str = "RU"
    cross_border_transfer: bool = False
    is_active: bool = True
    review_at: date | None = None
    notes: str | None = None


class PdnProcessingActivityPage(BaseSchema):
    items: list[PdnProcessingActivityEntry] = Field(default_factory=list)
    total: int
    # Признак «спец. категории обрабатываются» — повышенные требования 152-ФЗ.
    has_special_categories: bool = False


class PdnResidencyFinding(BaseSchema):
    """Расхождение между объявленной локализацией и регионом развёртывания."""

    code: str
    name: str
    declared_location: str
    deployment_region: str
    cross_border_transfer: bool
    #: ``undeclared_transfer`` — нарушение: реестр обещает одно, система делает
    #: другое. ``declared_transfer`` — осознанная трансграничная передача.
    verdict: str


class PdnResidencyReport(BaseSchema):
    """Сверка локализации ПДн (SEC-66 разд. 66.1, срез-185)."""

    region: str
    checked: int
    violations: int
    declared_transfers: int
    compliant: bool
    findings: list[PdnResidencyFinding] = Field(default_factory=list)


class PdnProcessingActivityUpsert(BaseSchema):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    purpose: str = Field(max_length=64)
    legal_basis: str = "consent"
    data_categories: list[str] = Field(default_factory=lambda: ["regular"])
    subject_categories: list[str] = Field(default_factory=lambda: ["employees"])
    retention_months: int | None = Field(default=None, ge=0)
    retention_basis: str | None = Field(default=None, max_length=255)
    access_roles: list[str] = Field(default_factory=list)
    recipients: list[str] = Field(default_factory=list)
    storage_location: str = Field(default="RU", max_length=64)
    cross_border_transfer: bool = False
    review_at: date | None = None
    notes: str | None = None


class PdnAgreementEntry(BaseSchema):
    """Договор поручения обработки / роль по 152-ФЗ (разд. 66.3)."""

    id: str
    kind: str
    party_role: str
    counterparty_name: str
    counterparty_inn: str | None = None
    counterparty_tenant_slug: str | None = None
    document_ref: str | None = None
    signed_at: date | None = None
    valid_until: date | None = None
    status: str
    subprocessing_allowed: bool = False
    breach_notification_hours: int | None = None
    covered_activity_codes: list[str] = Field(default_factory=list)
    notes: str | None = None


class PdnAgreementPage(BaseSchema):
    items: list[PdnAgreementEntry] = Field(default_factory=list)
    total: int
    # Активные процессы реестра, не покрытые ни одним действующим договором:
    # прямой ответ на «кто за что отвечает» (разд. 66.3).
    uncovered_activity_codes: list[str] = Field(default_factory=list)


class PdnAgreementCreate(BaseSchema):
    kind: str
    party_role: str
    counterparty_name: str = Field(min_length=1, max_length=255)
    counterparty_inn: str | None = Field(default=None, max_length=32)
    counterparty_tenant_slug: str | None = Field(default=None, max_length=64)
    document_ref: str | None = Field(default=None, max_length=255)
    signed_at: date | None = None
    valid_until: date | None = None
    status: str = "draft"
    subprocessing_allowed: bool = False
    breach_notification_hours: int | None = Field(default=None, ge=0)
    covered_activity_codes: list[str] = Field(default_factory=list)
    notes: str | None = None


class PdnBreachCreate(BaseSchema):
    """Заявка на регистрацию утечки ПДн (152-ФЗ разд. 66.3, срез-207).

    ``discovered_at`` ОБЯЗАТЕЛЕН и вводится человеком: от момента обнаружения
    закон считает 24 и 72 часа, а платформа не может знать, когда организации
    сообщили об утечке. Подставить «сейчас» значило бы сдвинуть отсчёт на время,
    прошедшее до записи.
    """

    summary: str = Field(min_length=1, max_length=512)
    discovered_at: datetime
    #: Когда утечка произошла, если установлено. Пусто — «не установлено»:
    #: законное состояние, а не пробел.
    happened_at: datetime | None = None
    affected_people: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _check(self) -> "PdnBreachCreate":
        if self.happened_at and self.happened_at > self.discovered_at:
            raise ValueError("утечка не может произойти позже, чем её обнаружили")
        return self


class PdnBreachStep(BaseSchema):
    """Отметка о выполненном шаге.

    Момент можно указать задним числом: уведомление часто подают раньше, чем
    доходят руки до записи в системе, и подстановка «сейчас» превратила бы
    выполненный в срок шаг в просроченный.
    """

    done_at: datetime | None = None

    model_config = {"extra": "forbid"}
