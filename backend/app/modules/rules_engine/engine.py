"""Оркестрация движка правил: вызывается синхронно из OutboxService.enqueue.

Инварианты:
- ЛЮБАЯ ошибка движка изолируется (evaluate_event_safe) — исходная транзакция
  доменного события не страдает; на PostgreSQL это гарантируют SAVEPOINT'ы
  (session.begin_nested): внешний вокруг всей оценки, вложенный на каждое действие
  (IntegrityError внутри savepoint не отравляет внешнюю транзакцию);
- события ``rule.triggered`` не оцениваются (guard от каскада, глубина = 1);
- лог пишется только при матче условий (или при ошибке оценки/действий);
- всё flush-only, транзакцию владеет вызывающий.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.feature_flags import is_module_enabled
from app.models.rules_engine import AutomationRule, AutomationRuleTrigger, RuleTriggerStatus
from app.modules.rules_engine import actions as actions_mod
from app.modules.rules_engine import conditions as conditions_mod

logger = logging.getLogger(__name__)

FEATURE_CODE = "rules_engine"
RULE_TRIGGERED_EVENT = "rule.triggered"


async def evaluate_event_safe(
    session: AsyncSession,
    *,
    tenant_id: str,
    event_type: str,
    payload: Mapping[str, Any],
    event_key: str,
) -> None:
    """Точка входа hook'а. Никогда не поднимает исключений наружу."""
    try:
        async with session.begin_nested():
            await _evaluate_event(
                session,
                tenant_id=tenant_id,
                event_type=event_type,
                payload=payload,
                event_key=event_key,
            )
    except Exception:  # noqa: BLE001 — изоляция движка от доменной транзакции
        logger.exception(
            "rules_engine.evaluate_failed",
            extra={"tenant_id": tenant_id, "event_type": event_type},
        )


async def _evaluate_event(
    session: AsyncSession,
    *,
    tenant_id: str,
    event_type: str,
    payload: Mapping[str, Any],
    event_key: str,
) -> None:
    if event_type == RULE_TRIGGERED_EVENT:
        return
    if not await is_module_enabled(session, tenant_id, FEATURE_CODE):
        return
    stmt = (
        select(AutomationRule)
        .where(
            AutomationRule.tenant_id == tenant_id,
            AutomationRule.event_type == event_type,
            AutomationRule.is_enabled.is_(True),
            AutomationRule.deleted_at.is_(None),
        )
        .order_by(AutomationRule.priority.asc(), AutomationRule.created_at.asc())
    )
    rules = (await session.execute(stmt)).scalars().all()
    for rule in rules:
        await _fire_rule(
            session, tenant_id=tenant_id, rule=rule, payload=payload, event_key=event_key
        )


async def _fire_rule(
    session: AsyncSession,
    *,
    tenant_id: str,
    rule: AutomationRule,
    payload: Mapping[str, Any],
    event_key: str,
) -> None:
    try:
        matched = conditions_mod.evaluate(rule.conditions_json, payload)
    except Exception:  # noqa: BLE001 — ошибка оценки условий не роняет движок
        logger.exception(
            "rules_engine.conditions_failed",
            extra={"rule_id": rule.id, "event_type": rule.event_type},
        )
        await _write_trigger(
            session,
            tenant_id=tenant_id,
            rule=rule,
            event_key=event_key,
            payload=payload,
            status=RuleTriggerStatus.ERROR,
            results=[{"type": "conditions", "outcome": "error", "detail": "evaluation failed"}],
        )
        return
    if not matched:
        return

    already = await actions_mod.was_already_triggered(
        session, tenant_id=tenant_id, rule_id=rule.id, event_key=event_key
    )
    results: list[dict[str, Any]] = []
    errors = 0
    for action in rule.actions_json or []:
        try:
            async with session.begin_nested():
                outcome = await actions_mod.execute_action(
                    session,
                    tenant_id=tenant_id,
                    rule=rule,
                    action=action,
                    event_key=event_key,
                    payload=payload,
                    already_triggered=already,
                )
        except Exception as exc:  # noqa: BLE001 — одно действие не роняет остальные
            logger.exception(
                "rules_engine.action_failed",
                extra={
                    "rule_id": rule.id,
                    "action_type": action.get("type") if isinstance(action, Mapping) else None,
                },
            )
            outcome = actions_mod.ActionOutcome(
                type=str(action.get("type")) if isinstance(action, Mapping) else "unknown",
                outcome="error",
                detail=exc.__class__.__name__,
            )
        if outcome.outcome == "error":
            errors += 1
        results.append(outcome.as_dict())

    if errors == 0:
        status = RuleTriggerStatus.SUCCESS
    elif results and errors == len(results):
        status = RuleTriggerStatus.ERROR
    else:
        status = RuleTriggerStatus.PARTIAL
    await _write_trigger(
        session,
        tenant_id=tenant_id,
        rule=rule,
        event_key=event_key,
        payload=payload,
        status=status,
        results=results,
    )


async def _write_trigger(
    session: AsyncSession,
    *,
    tenant_id: str,
    rule: AutomationRule,
    event_key: str,
    payload: Mapping[str, Any],
    status: RuleTriggerStatus,
    results: list[dict[str, Any]],
) -> None:
    correlation_raw = payload.get("correlation_id")
    session.add(
        AutomationRuleTrigger(
            tenant_id=tenant_id,
            rule_id=rule.id,
            event_type=rule.event_type,
            event_key=event_key[:255],
            correlation_id=str(correlation_raw)[:128] if correlation_raw else None,
            event_payload=dict(payload),
            status=status,
            actions_result=results,
        )
    )
    await session.flush()
