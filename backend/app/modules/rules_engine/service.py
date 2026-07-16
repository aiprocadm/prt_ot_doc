"""CRUD + dry-run/test оркестрация правил автоматизации (P10-10 срез-1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Outbox
from app.models.rules_engine import AutomationRule, AutomationRuleTrigger
from app.modules.rules_engine import actions as actions_mod
from app.modules.rules_engine import catalog
from app.modules.rules_engine import conditions as conditions_mod
from app.modules.rules_engine.schemas import (
    AutomationRuleCreate,
    AutomationRuleUpdate,
    ConditionResult,
    DryRunIn,
    DryRunOut,
    RuleTestOut,
    RuleTestResultItem,
)

__all__ = [
    "RuleNotFound",
    "RuleNameConflict",
    "RulesConfigError",
    "RulesEngineService",
]

_CONFIG_FIELDS = ("event_type", "conditions_json", "actions_json")
# Дедуп по idempotency_key схлопывает multi-destination fan-out одного события,
# поэтому выборка с запасом.
_TEST_FETCH_FACTOR = 5


class RuleNotFound(Exception):
    pass


class RuleNameConflict(Exception):
    pass


class RulesConfigError(ValueError):
    """Typed-ошибка конфигурации правила; code уходит в 422 API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RulesEngineService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def _base_stmt(self):
        return select(AutomationRule).where(
            AutomationRule.tenant_id == self.tenant_id,
            AutomationRule.deleted_at.is_(None),
        )

    async def list_rules(self, *, limit: int, offset: int) -> tuple[list[AutomationRule], int]:
        stmt = self._base_stmt()
        total = int(
            await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = list(
            (
                await self.session.execute(
                    stmt.order_by(AutomationRule.priority.asc(), AutomationRule.created_at.asc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows, total

    async def get_rule(self, rule_id: str) -> AutomationRule:
        row = await self.session.scalar(self._base_stmt().where(AutomationRule.id == rule_id))
        if row is None:
            raise RuleNotFound(rule_id)
        return row

    async def _validate_config(
        self, event_type: str, conditions_json: dict[str, Any], actions_json: list[dict[str, Any]]
    ) -> None:
        if event_type not in catalog.known_event_types():
            raise RulesConfigError("unknown_event_type", f"unknown event type {event_type!r}")
        conditions_mod.validate_conditions(
            conditions_json, known_fields=catalog.known_fields_for(event_type)
        )
        actions_mod.validate_actions(actions_json)
        await actions_mod.validate_action_user_ids(
            self.session, tenant_id=self.tenant_id, actions=actions_json
        )

    async def _ensure_name_free(self, name: str) -> None:
        # Осознанно БЕЗ фильтра deleted_at: soft-deleted тёзка блокирует создание
        # (unique-constraint uq_automation_rule_tenant_name тоже её видит).
        existing = await self.session.scalar(
            select(AutomationRule.id)
            .where(AutomationRule.tenant_id == self.tenant_id, AutomationRule.name == name)
            .limit(1)
        )
        if existing is not None:
            raise RuleNameConflict(name)

    async def create_rule(self, data: AutomationRuleCreate) -> AutomationRule:
        await self._validate_config(data.event_type, data.conditions_json, data.actions_json)
        await self._ensure_name_free(data.name)
        record = AutomationRule(
            tenant_id=self.tenant_id,
            name=data.name,
            description=data.description,
            event_type=data.event_type,
            conditions_json=data.conditions_json,
            actions_json=data.actions_json,
            priority=data.priority,
            is_enabled=data.is_enabled,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:  # гонка параллельных create — паттерн report_builder
            await self.session.rollback()
            raise RuleNameConflict(data.name) from exc
        return record

    async def update_rule(self, rule_id: str, patch: AutomationRuleUpdate) -> AutomationRule:
        rule = await self.get_rule(rule_id)
        fields = patch.model_dump(exclude_unset=True)
        # Explicit null на NOT NULL колонках дошёл бы до flush и IntegrityError
        # мис-мапился бы в 409 → ловим до применения (422 через RulesConfigError).
        # Конфигурационные null'ы ловит _validate_config (unknown_event_type / ...).
        for key in ("name", "priority", "is_enabled"):
            if key in fields and fields[key] is None:
                raise RulesConfigError("invalid_field_null", f"{key} cannot be null")
        if any(key in fields for key in _CONFIG_FIELDS):
            await self._validate_config(
                fields.get("event_type", rule.event_type),
                fields.get("conditions_json", rule.conditions_json),
                fields.get("actions_json", rule.actions_json),
            )
        new_name = fields.get("name")
        if new_name is not None and new_name != rule.name:
            await self._ensure_name_free(new_name)
        for key, value in fields.items():
            setattr(rule, key, value)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise RuleNameConflict(str(new_name)) from exc
        return rule

    async def delete_rule(self, rule_id: str) -> None:
        rule = await self.get_rule(rule_id)
        rule.deleted_at = datetime.now(tz=timezone.utc)
        await self.session.flush()

    async def dry_run(self, body: DryRunIn) -> DryRunOut:
        await self._validate_config(
            body.rule.event_type, body.rule.conditions_json, body.rule.actions_json
        )
        if body.event.event_type not in catalog.known_event_types():
            raise RulesConfigError(
                "unknown_event_type", f"unknown event type {body.event.event_type!r}"
            )
        payload = body.event.payload
        condition_results: list[ConditionResult] = []
        for cond in body.rule.conditions_json.get("conditions") or []:
            matched_i = conditions_mod.evaluate_condition(cond, payload)
            found, actual = conditions_mod.resolve_field(payload, str(cond.get("field", "")))
            condition_results.append(
                ConditionResult(
                    field=str(cond.get("field", "")),
                    op=str(cond.get("op", "")),
                    value=cond.get("value"),
                    actual=actual if found else None,
                    matched=matched_i,
                )
            )
        matched = conditions_mod.evaluate(body.rule.conditions_json, payload)
        would_actions = (
            [actions_mod.describe_action(a) for a in body.rule.actions_json] if matched else []
        )
        return DryRunOut(
            matched=matched, condition_results=condition_results, would_actions=would_actions
        )

    async def test_rule(self, rule_id: str, *, limit: int) -> RuleTestOut:
        rule = await self.get_rule(rule_id)
        rows = (
            (
                await self.session.execute(
                    select(Outbox)
                    .where(
                        Outbox.tenant_id == self.tenant_id,
                        Outbox.event_type == rule.event_type,
                    )
                    .order_by(Outbox.created_at.desc())
                    .limit(limit * _TEST_FETCH_FACTOR)
                )
            )
            .scalars()
            .all()
        )
        seen_keys: set[str] = set()
        selected: list[Outbox] = []
        for row in rows:
            key = row.idempotency_key
            if key is not None:
                if key in seen_keys:
                    continue
                seen_keys.add(key)
            selected.append(row)
            if len(selected) >= limit:
                break
        results: list[RuleTestResultItem] = []
        matched_count = 0
        for row in selected:
            payload = row.payload or {}
            matched = conditions_mod.evaluate(rule.conditions_json, payload)
            if matched:
                matched_count += 1
            occurred_at = payload.get("occurred_at")
            results.append(
                RuleTestResultItem(
                    event_key=row.idempotency_key or row.id,
                    occurred_at=str(occurred_at) if occurred_at is not None else None,
                    matched=matched,
                )
            )
        return RuleTestOut(
            events_checked=len(results), matched_count=matched_count, results=results
        )

    async def list_triggers(
        self, *, rule_id: str | None, limit: int, offset: int
    ) -> tuple[list[AutomationRuleTrigger], int]:
        stmt = select(AutomationRuleTrigger).where(
            AutomationRuleTrigger.tenant_id == self.tenant_id
        )
        if rule_id is not None:
            stmt = stmt.where(AutomationRuleTrigger.rule_id == rule_id)
        total = int(
            await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = list(
            (
                await self.session.execute(
                    stmt.order_by(AutomationRuleTrigger.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows, total
