"""Схемы контура ПДн / 152-ФЗ (SEC-66 срез-1, разд. 66.2 «права субъекта»).

Два права субъекта закрываются этим срезом:

* «доступ к своим данным» — `PdnSubjectExport`: машиночитаемая выгрузка всех ПДн
  субъекта одним документом;
* «журнал доступа» — `PdnAccessLogPage`: кто и когда эти данные читал.

Выгрузка переиспользует агрегат `EmployeeCard` (единый источник правды о
сотруднике) и не заводит параллельного представления данных.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

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
