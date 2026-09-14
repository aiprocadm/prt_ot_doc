"""Схемы реестра требований (B.18 разд. 19.2, срез-145)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

RequirementSeverity = Literal["low", "medium", "high", "critical"]
RequirementStatus = Literal["active", "fulfilled", "retired"]


class ComplianceRequirementCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    npa_id: str | None = None
    clause_id: str | None = None
    role_code: str | None = Field(default=None, max_length=64)
    site_id: str | None = None
    process_code: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = None
    #: Дней между исполнениями; пусто — разовое требование.
    periodicity_days: int | None = Field(default=None, ge=1, le=3660)
    next_due_at: date | None = None
    severity: RequirementSeverity = "medium"


class ComplianceRequirementUpdate(BaseModel):
    """Частичное обновление: присланные поля меняются, остальные — нет.

    Код и статус здесь не правятся: код — естественный ключ (ссылки на него
    живут в доказательствах и импорте), статус меняют ручки «исполнено» и
    «снять с контроля», чтобы переход был осмысленным, а не произвольным.
    """

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    npa_id: str | None = None
    clause_id: str | None = None
    role_code: str | None = Field(default=None, max_length=64)
    site_id: str | None = None
    process_code: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = None
    periodicity_days: int | None = Field(default=None, ge=1, le=3660)
    next_due_at: date | None = None
    severity: RequirementSeverity | None = None


class ComplianceEvidenceCreate(BaseModel):
    """Доказательство исполнения: документ и/или заметка.

    ``confirmed_at`` — день исполнения (по умолчанию сегодня по UTC); от него
    отсчитывается следующая контрольная дата.
    """

    document_id: str | None = None
    note: str | None = Field(default=None, max_length=2000)
    confirmed_at: date | None = None


class ComplianceEvidenceRead(BaseModel):
    id: str
    requirement_id: str
    document_id: str | None = None
    document_title: str | None = None
    note: str | None = None
    confirmed_at: date
    confirmed_by: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ComplianceRequirementRead(BaseModel):
    id: str
    code: str
    title: str
    description: str | None = None
    npa_id: str | None = None
    npa_code: str | None = None
    npa_title: str | None = None
    clause_id: str | None = None
    clause_code: str | None = None
    role_code: str | None = None
    #: Роль словами (срез-147, словарь ``app.core.role_labels``); код — для машин.
    role_label: str | None = None
    site_id: str | None = None
    #: Имя площадки (срез-147): без него привязка к объекту на витрине невидима.
    site_name: str | None = None
    process_code: str | None = None
    owner_user_id: str | None = None
    owner_name: str | None = None
    periodicity_days: int | None = None
    next_due_at: date | None = None
    last_confirmed_at: date | None = None
    severity: RequirementSeverity
    status: RequirementStatus
    retired_at: datetime | None = None
    #: Вычислено на чтении по UTC-«сегодня» (срез-140): контрольная дата
    #: прошла, требование ещё активно.
    overdue: bool = False
    #: Дней до контрольной даты (отрицательно — просрочено); None без даты.
    days_left: int | None = None
    evidence_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ComplianceRequirementDetail(ComplianceRequirementRead):
    evidence: list[ComplianceEvidenceRead] = Field(default_factory=list)


class ComplianceRequirementListResponse(BaseModel):
    items: list[ComplianceRequirementRead]
    #: Счётчики по ВСЕЙ выборке при текущих фильтрах, а не по выданной странице
    #: (срез-195). Счётчик по странице — класс ошибки, который в проекте ловили
    #: дважды: человек видит «просрочено: 0» над первой страницей и считает,
    #: что просроченных нет вовсе.
    total: int
    active: int
    overdue: int
    #: Может ли пришедший заводить и закрывать требования (роли записи).
    can_manage: bool = False
    #: Какая часть выдана. Клиент не должен вычислять это из длины списка:
    #: пустая последняя страница неотличима от «ничего не найдено».
    limit: int = 0
    offset: int = 0


class RequirementOwnerOption(BaseModel):
    """Кандидат в ответственные: только то, что нужно, чтобы выбрать человека."""

    id: str
    name: str
    role: str
    role_label: str


class RequirementSiteOption(BaseModel):
    id: str
    name: str
    #: Компания площадки: у арендатора-аутсорсера «Цех №1» бывает у нескольких клиентов.
    company_name: str


class RequirementRoleOption(BaseModel):
    code: str
    label: str


class ComplianceRequirementOptions(BaseModel):
    """Справочники формы требования (срез-147): кого назначить ответственным,
    к какой площадке и к какой роли отнести. Отдаются ролям записи."""

    owners: list[RequirementOwnerOption] = Field(default_factory=list)
    sites: list[RequirementSiteOption] = Field(default_factory=list)
    roles: list[RequirementRoleOption] = Field(default_factory=list)
