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
