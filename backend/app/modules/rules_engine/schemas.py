"""Pydantic-схемы rules-engine API (P10-10 срез-1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AutomationRuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    event_type: str
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    actions_json: list[dict[str, Any]] = Field(default_factory=list)
    priority: int = Field(default=100, ge=0, le=10000)
    is_enabled: bool = True


class AutomationRuleCreate(AutomationRuleBase):
    pass


class AutomationRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    event_type: str | None = None
    conditions_json: dict[str, Any] | None = None
    actions_json: list[dict[str, Any]] | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)
    is_enabled: bool | None = None


class AutomationRuleRead(AutomationRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class AutomationRulePage(BaseModel):
    items: list[AutomationRuleRead]
    total: int
    limit: int
    offset: int


class EventFieldMeta(BaseModel):
    name: str
    kind: str


class EventTypeMeta(BaseModel):
    event_type: str
    fields: list[EventFieldMeta]


class RuleLibraryDiscipline(BaseModel):
    """Покрытие одной дисциплины библиотекой (BIZ-54-57 срез-4, разд. 57.3)."""

    discipline: str
    title: str
    #: Сколько правил библиотеки относится к дисциплине.
    rules: int
    #: ПОЧЕМУ правил нет. Пустая строка у дисциплин, где правила есть. Ноль без
    #: причины прочитали бы как «забыли завести», а не как решение.
    reason: str = ""


class RuleLibraryPage(BaseModel):
    """Библиотека целиком: покрытие по дисциплинам + сколько уже выдано."""

    items: list[RuleLibraryDiscipline]
    #: Всего правил в библиотеке продукта.
    total: int
    #: Сколько из них уже заведено у этого арендатора (по имени).
    installed: int


class EventTypePage(BaseModel):
    items: list[EventTypeMeta]
    total: int


class DryRunEvent(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class DryRunIn(BaseModel):
    rule: AutomationRuleBase
    event: DryRunEvent


class ConditionResult(BaseModel):
    field: str
    op: str
    value: Any = None
    actual: Any = None
    matched: bool


class DryRunOut(BaseModel):
    matched: bool
    condition_results: list[ConditionResult]
    would_actions: list[str]


class RuleTestIn(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)


class RuleTestResultItem(BaseModel):
    event_key: str
    occurred_at: str | None = None
    matched: bool


class RuleTestOut(BaseModel):
    events_checked: int
    matched_count: int
    results: list[RuleTestResultItem]


class TriggerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_id: str
    event_type: str
    event_key: str
    correlation_id: str | None
    status: str
    actions_result: list[dict[str, Any]]
    created_at: datetime


class TriggerPage(BaseModel):
    items: list[TriggerRead]
    total: int
    limit: int
    offset: int
