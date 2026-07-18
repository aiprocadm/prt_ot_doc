"""Схемы бюджетного контура §12.4 (срез-1)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, model_validator

from app.models.budget import BUDGET_DOMAINS
from app.schemas.base import BaseSchema


def _check_period(values):
    if values.period_end < values.period_start:
        raise ValueError("period_end must be >= period_start")
    return values


class SafetyBudgetCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    domain: str
    period_start: date
    period_end: date
    planned_amount: float = Field(ge=0)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate(self):
        if self.domain not in BUDGET_DOMAINS:
            raise ValueError(f"unknown domain: {self.domain}")
        return _check_period(self)


class SafetyBudgetUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    period_start: date | None = None
    period_end: date | None = None
    planned_amount: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)
    # domain намеренно НЕ обновляется (перенос бюджета между доменами = удалить+создать)


class SafetyBudgetRead(BaseSchema):
    id: str
    name: str
    domain: str
    period_start: date
    period_end: date
    planned_amount: float
    notes: str | None


class SafetyBudgetPage(BaseSchema):
    items: list[SafetyBudgetRead]
    total: int
    limit: int
    offset: int


class BudgetArticleActualRead(BaseSchema):
    article_id: str | None
    article_name: str  # "— без статьи" для NULL
    amount: float


class SafetyBudgetDetail(SafetyBudgetRead):
    actual_total: float
    remaining: float  # planned - actual; отрицательный = перерасход
    expense_count: int
    by_article: list[BudgetArticleActualRead]


class BudgetArticleCreate(BaseSchema):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    domain: str | None = None  # NULL = универсальная
    is_active: bool = True

    @model_validator(mode="after")
    def _validate(self):
        if self.domain is not None and self.domain not in BUDGET_DOMAINS:
            raise ValueError(f"unknown domain: {self.domain}")
        return self


class BudgetArticleUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    domain: str | None = None
    is_active: bool | None = None
    # code иммутабелен (ключ уникальности/сида)

    @model_validator(mode="after")
    def _validate(self):
        if self.domain is not None and self.domain not in BUDGET_DOMAINS:
            raise ValueError(f"unknown domain: {self.domain}")
        return self


class BudgetArticleRead(BaseSchema):
    id: str
    code: str
    name: str
    domain: str | None
    is_active: bool


class BudgetArticlePage(BaseSchema):
    items: list[BudgetArticleRead]
    total: int
    limit: int
    offset: int


class BudgetSeedResult(BaseSchema):
    created: int
    skipped: int


class BudgetExpenseCreate(BaseSchema):
    domain: str
    article_id: str | None = None
    title: str = Field(min_length=1, max_length=255)
    occurred_on: date
    amount: float = Field(gt=0)
    company_id: str | None = None
    branch_id: str | None = None
    site_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate(self):
        if self.domain not in BUDGET_DOMAINS:
            raise ValueError(f"unknown domain: {self.domain}")
        if (self.entity_id is None) != (self.entity_type is None):
            raise ValueError("entity_type and entity_id must be provided together")
        return self


class BudgetExpenseUpdate(BaseSchema):
    article_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    occurred_on: date | None = None
    amount: float | None = Field(default=None, gt=0)
    company_id: str | None = None
    branch_id: str | None = None
    site_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    notes: str | None = Field(default=None, max_length=1000)
    # domain иммутабелен (перенос расхода между доменами = удалить+создать)


class BudgetExpenseRead(BaseSchema):
    id: str
    domain: str
    article_id: str | None
    article_name: str | None  # outerjoin в сервисе
    title: str
    occurred_on: date
    amount: float
    company_id: str | None
    branch_id: str | None
    site_id: str | None
    entity_type: str | None
    entity_id: str | None
    notes: str | None


class BudgetExpensePage(BaseSchema):
    items: list[BudgetExpenseRead]
    total: int
    limit: int
    offset: int


class BudgetOverviewBudgetRow(BaseSchema):
    id: str
    name: str
    period_start: date
    period_end: date
    planned_amount: float
    actual_own_period: float
    remaining: float


class BudgetOverviewDomain(BaseSchema):
    domain: str  # training|medical|events|ppe
    read_only: bool  # True только для ppe
    planned: float
    actual: float
    remaining: float
    warning_unpriced_receipts: int | None = None  # только ppe
    budgets: list[BudgetOverviewBudgetRow]


class BudgetOverviewResponse(BaseSchema):
    generated_at: datetime
    date_from: date
    date_to: date
    domains: list[BudgetOverviewDomain]


class BudgetBreakdownItem(BaseSchema):
    id: str  # "" = None-bucket «— без привязки»/«— без статьи»
    name: str
    amount: float


class BudgetBreakdownResponse(BaseSchema):
    dimension: str
    date_from: date
    date_to: date
    total: int  # строк ДО cap 200
    items: list[BudgetBreakdownItem]
