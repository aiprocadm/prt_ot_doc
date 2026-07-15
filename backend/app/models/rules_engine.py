"""Automation rules engine models (P10-10 срез-1, vNext §25.2)."""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum

# Mutable.as_mutable ассоциируется с конкретным ИНСТАНСОМ типа: один инстанс
# нельзя делить между MutableDict и MutableList (coerce-конфликт: list-колонка
# получает dict-коэрсер и падает ValueError). Поэтому — по инстансу на обёртку
# (document.py делит один инстанс между колонками, но там обёртка только MutableDict).
JSONBDictType = JSONB().with_variant(JSON(), "sqlite")
JSONBListType = JSONB().with_variant(JSON(), "sqlite")


class RuleTriggerStatus(str, enum.Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"


class AutomationRule(TenantBaseModel, SoftDeleteMixin):
    """Правило автоматизации: событие → условия → действия.

    ``name`` уникален per tenant БЕЗ фильтра deleted_at (паттерн ReportDefinition):
    soft-deleted тёзка блокирует создание — осознанно, пин-тест ниже.
    """

    __tablename__ = "automation_rule"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    conditions_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONBDictType), nullable=False, default=dict
    )
    actions_json: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSONBListType), nullable=False, default=list
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_automation_rule_tenant_name"),
        Index("ix_automation_rule_tenant_event", "tenant_id", "event_type"),
    )


class AutomationRuleTrigger(TenantBaseModel):
    """Append-only лог срабатываний. Пишется ТОЛЬКО при матче условий или ошибке движка."""

    __tablename__ = "automation_rule_trigger"

    rule_id: Mapped[str] = mapped_column(
        ForeignKey("automation_rule.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONBDictType), nullable=False, default=dict
    )
    status: Mapped[RuleTriggerStatus] = mapped_column(
        native_enum(RuleTriggerStatus, name="ruletriggerstatus"), nullable=False
    )
    actions_result: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSONBListType), nullable=False, default=list
    )

    __table_args__ = (
        Index("ix_automation_rule_trigger_rule_created", "tenant_id", "rule_id", "created_at"),
        Index("ix_automation_rule_trigger_tenant_created", "tenant_id", "created_at"),
    )
