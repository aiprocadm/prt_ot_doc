"""Тесты движка правил (P10-10 срез-1): синхронный hook в OutboxService.enqueue."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Outbox
from app.models.notifications import Notification, NotificationType
from app.models.obligations import Task
from app.models.rules_engine import AutomationRule, AutomationRuleTrigger, RuleTriggerStatus
from app.services.outbox import OutboxService
from tests.utils.factories import TestDataFactory

SEVERITY_CONDITIONS = {
    "match": "all",
    "conditions": [{"field": "severity", "op": "in", "value": ["high", "critical"]}],
}


async def _enable_flag(sessionmaker, data_factory: TestDataFactory, *, on: bool = True) -> str:
    from app.models.feature import Feature, FeatureEnablement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "rules_engine"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="rules_engine", title="Движок правил")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=str(tenant.id), feature_id=feature.id, on=on))
        await session.commit()
        return str(tenant.id)


async def _make_rule(
    session: AsyncSession, tenant_id: str, *, name: str, **overrides: Any
) -> AutomationRule:
    rule = AutomationRule(
        tenant_id=tenant_id,
        name=name,
        event_type=overrides.pop("event_type", "IncidentCreated"),
        conditions_json=overrides.pop("conditions_json", {}),
        actions_json=overrides.pop("actions_json", []),
        **overrides,
    )
    session.add(rule)
    await session.flush()
    return rule


def _incident(
    tenant_id: str, *, severity: str = "critical", incident_id: str | None = None
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "incident_id": incident_id or str(uuid4()),
        "company_id": "comp-1",
        "site_id": "site-1",
        "status": "reported",
        "severity": severity,
        "incident_type": "injury",
    }


async def _enqueue_incident(session: AsyncSession, tenant_id: str, payload: dict[str, Any]):
    return await OutboxService(session).enqueue(
        tenant_id=tenant_id, event_type="IncidentCreated", payload=payload
    )


async def _trigger_rows(session: AsyncSession, tenant_id: str) -> list[AutomationRuleTrigger]:
    return list(
        (
            await session.execute(
                select(AutomationRuleTrigger)
                .where(AutomationRuleTrigger.tenant_id == tenant_id)
                .order_by(AutomationRuleTrigger.created_at.asc())
            )
        )
        .scalars()
        .all()
    )


async def _task_count(session: AsyncSession, tenant_id: str) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(Task).where(Task.tenant_id == tenant_id)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_happy_path_creates_task_notification_and_trigger(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    tenant_id = await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(
            tenant=tenant, email="engine-notify@example.com", session=session
        )
        rule = await _make_rule(
            session,
            tenant_id,
            name="Критичный инцидент",
            conditions_json=SEVERITY_CONDITIONS,
            actions_json=[
                {
                    "type": "create_task",
                    "title_template": "Разбор {severity}",
                    "priority": "high",
                    "due_in_days": 3,
                },
                {
                    "type": "notify",
                    "title_template": "Инцидент {severity}",
                    "body_template": "Статус: {status}",
                    "recipient_mode": "user_id",
                    "user_id": str(user.id),
                },
            ],
        )
        payload = _incident(tenant_id)
        await _enqueue_incident(session, tenant_id, payload)
        await session.commit()

        triggers = await _trigger_rows(session, tenant_id)
        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.rule_id == rule.id
        assert trigger.status == RuleTriggerStatus.SUCCESS
        assert trigger.event_key == payload["incident_id"]
        assert [r["type"] for r in trigger.actions_result] == ["create_task", "notify"]
        assert [r["outcome"] for r in trigger.actions_result] == ["created", "created"]

        task = (
            await session.execute(
                select(Task).where(
                    Task.tenant_id == tenant_id, Task.entity_type == "automation_rule"
                )
            )
        ).scalar_one()
        assert task.entity_id == rule.id
        assert task.title == "Разбор critical"

        notification = (
            await session.execute(
                select(Notification).where(
                    Notification.tenant_id == tenant_id,
                    Notification.type == NotificationType.AUTOMATION_RULE,
                )
            )
        ).scalar_one()
        assert str(notification.user_id) == str(user.id)


@pytest.mark.asyncio
async def test_no_match_writes_no_trigger(sessionmaker, data_factory: TestDataFactory) -> None:
    tenant_id = await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        await _make_rule(
            session,
            tenant_id,
            name="Только критичные",
            conditions_json=SEVERITY_CONDITIONS,
            actions_json=[{"type": "create_task", "title_template": "Т"}],
        )
        await _enqueue_incident(session, tenant_id, _incident(tenant_id, severity="low"))
        await session.commit()

        assert await _trigger_rows(session, tenant_id) == []
        assert await _task_count(session, tenant_id) == 0


@pytest.mark.asyncio
async def test_flag_off_no_evaluation(sessionmaker, data_factory: TestDataFactory) -> None:
    # FeatureEnablement НЕ создаётся: движок default-off.
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant_id = str(tenant.id)
        await _make_rule(
            session,
            tenant_id,
            name="Флаг выключен",
            actions_json=[{"type": "create_task", "title_template": "Т"}],
        )
        await _enqueue_incident(session, tenant_id, _incident(tenant_id))
        await session.commit()

        assert await _trigger_rows(session, tenant_id) == []
        assert await _task_count(session, tenant_id) == 0


@pytest.mark.asyncio
async def test_priority_order(sessionmaker, data_factory: TestDataFactory) -> None:
    tenant_id = await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        # Правило с приоритетом 2 создаётся ПЕРВЫМ: порядок обязан прийти из priority,
        # а не из порядка вставки.
        rule_b = await _make_rule(session, tenant_id, name="Приоритет 2", priority=2)
        rule_a = await _make_rule(session, tenant_id, name="Приоритет 1", priority=1)
        await _enqueue_incident(session, tenant_id, _incident(tenant_id))
        await session.commit()

        triggers = await _trigger_rows(session, tenant_id)
        assert len(triggers) == 2
        assert {t.rule_id for t in triggers} == {rule_a.id, rule_b.id}
        # created_at питоновский (µs-точность), но на Windows гранулярность системных
        # часов может дать одинаковые метки — строгий порядок проверяем только когда
        # метки различимы (fallback, зафиксированный в плане Task 5).
        if triggers[0].created_at != triggers[1].created_at:
            assert [t.rule_id for t in triggers] == [rule_a.id, rule_b.id]


@pytest.mark.asyncio
async def test_dedup_replay_does_not_refire(sessionmaker, data_factory: TestDataFactory) -> None:
    tenant_id = await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        await _make_rule(
            session,
            tenant_id,
            name="Реплей",
            actions_json=[{"type": "create_task", "title_template": "Разбор"}],
        )
        payload = _incident(tenant_id)
        await _enqueue_incident(session, tenant_id, payload)
        # Тот же incident_id → тот же idempotency key → реплей возвращает
        # существующую outbox-строку и НЕ перезапускает правила.
        await _enqueue_incident(session, tenant_id, payload)
        await session.commit()

        assert len(await _trigger_rows(session, tenant_id)) == 1
        assert await _task_count(session, tenant_id) == 1


@pytest.mark.asyncio
async def test_action_error_isolated_partial(sessionmaker, data_factory: TestDataFactory) -> None:
    tenant_id = await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(
            tenant=tenant, email="engine-partial@example.com", session=session
        )
        # Сломанное действие записано в модель напрямую (мимо validate_actions):
        # TaskPriority("bogus") поднимет ValueError внутри исполнителя.
        await _make_rule(
            session,
            tenant_id,
            name="Частичный сбой",
            actions_json=[
                {"type": "create_task", "title_template": "Т", "priority": "bogus"},
                {
                    "type": "notify",
                    "title_template": "Т",
                    "body_template": "Б",
                    "recipient_mode": "user_id",
                    "user_id": str(user.id),
                },
            ],
        )
        # enqueue обязан пройти без исключений — ошибка действия изолирована.
        await _enqueue_incident(session, tenant_id, _incident(tenant_id))
        await session.commit()

        triggers = await _trigger_rows(session, tenant_id)
        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.status == RuleTriggerStatus.PARTIAL
        assert trigger.actions_result[0]["outcome"] == "error"
        assert trigger.actions_result[1]["outcome"] == "created"
        # Соседнее действие пережило сбой (per-action SAVEPOINT): уведомление создано.
        notification = (
            await session.execute(
                select(Notification).where(
                    Notification.tenant_id == tenant_id,
                    Notification.type == NotificationType.AUTOMATION_RULE,
                )
            )
        ).scalar_one()
        assert str(notification.user_id) == str(user.id)


@pytest.mark.asyncio
async def test_action_savepoint_rolls_back_flushed_writes(
    sessionmaker, data_factory: TestDataFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пин ревью Task 5: per-action SAVEPOINT откатывает УЖЕ flushed-записи действия.

    Первый получатель notify реально создаётся и flush'ится в БД, второй роняет
    RuntimeError — savepoint действия обязан откатить первый INSERT, а соседнее
    create_task (свой savepoint) — выжить.
    """
    # Патчим по месту импорта: actions.py импортирует ИМЯ send_notification.
    import app.modules.rules_engine.actions as actions_mod
    from app.services.notifications import send_notification as real_send_notification

    tenant_id = await _enable_flag(sessionmaker, data_factory)

    calls = {"count": 0}

    async def _flaky_send_notification(session: AsyncSession, **kwargs: Any):
        calls["count"] += 1
        if calls["count"] >= 2:
            raise RuntimeError("boom")
        row = await real_send_notification(session, **kwargs)
        await session.flush()  # гарантия: INSERT дошёл до БД внутри savepoint до сбоя
        return row

    monkeypatch.setattr(actions_mod, "send_notification", _flaky_send_notification)

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        # Два админа → два вызова send_notification внутри ОДНОГО действия notify.
        await data_factory.create_user(
            tenant=tenant, email="sp-admin-1@example.com", session=session
        )
        await data_factory.create_user(
            tenant=tenant, email="sp-admin-2@example.com", session=session
        )
        rule = await _make_rule(
            session,
            tenant_id,
            name="Savepoint откатывает flush",
            actions_json=[
                {
                    "type": "notify",
                    "title_template": "Т",
                    "body_template": "Б",
                    "recipient_mode": "role",
                    "roles": ["admin"],
                },
                {"type": "create_task", "title_template": "Задача выжила"},
            ],
        )
        await _enqueue_incident(session, tenant_id, _incident(tenant_id))
        await session.commit()

        assert calls["count"] == 2  # первый создан+flushed, второй упал

        triggers = await _trigger_rows(session, tenant_id)
        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.status == RuleTriggerStatus.PARTIAL
        assert trigger.actions_result[0]["outcome"] == "error"
        assert trigger.actions_result[0]["detail"] == "RuntimeError"
        assert trigger.actions_result[1]["outcome"] == "created"

        # Flushed-уведомление первого получателя откатил savepoint действия.
        leaked = (
            await session.execute(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.tenant_id == tenant_id,
                    Notification.dedup_key.like(f"rules:{rule.id}:%"),
                )
            )
        ).scalar_one()
        assert leaked == 0

        # Соседнее действие (свой savepoint) пережило откат.
        task = (
            await session.execute(
                select(Task).where(
                    Task.tenant_id == tenant_id, Task.entity_type == "automation_rule"
                )
            )
        ).scalar_one()
        assert task.entity_id == rule.id
        assert task.title == "Задача выжила"


@pytest.mark.asyncio
async def test_engine_error_does_not_break_enqueue(
    sessionmaker, data_factory: TestDataFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.rules_engine.engine as engine_mod

    tenant_id = await _enable_flag(sessionmaker, data_factory)

    async def _boom(*args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(engine_mod, "is_module_enabled", _boom)

    async with sessionmaker() as session:
        await _make_rule(
            session,
            tenant_id,
            name="Движок сломан",
            actions_json=[{"type": "create_task", "title_template": "Т"}],
        )
        entries = await _enqueue_incident(session, tenant_id, _incident(tenant_id))
        await session.commit()

        assert entries  # enqueue пережил ошибку движка
        outbox_rows = (
            (
                await session.execute(
                    select(Outbox).where(
                        Outbox.tenant_id == tenant_id,
                        Outbox.event_type == "IncidentCreated",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(outbox_rows) == 1  # доменное событие сохранено
        assert await _trigger_rows(session, tenant_id) == []


@pytest.mark.asyncio
async def test_rule_triggered_cascade_guard(sessionmaker, data_factory: TestDataFactory) -> None:
    tenant_id = await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        webhook_rule = await _make_rule(
            session, tenant_id, name="Webhook при инциденте", actions_json=[{"type": "webhook"}]
        )
        # Правило на rule.triggered пишется в БД напрямую (API такое отвергает):
        # guard движка обязан не дать ему сработать.
        await _make_rule(
            session,
            tenant_id,
            name="Каскад (не должен сработать)",
            event_type="rule.triggered",
            actions_json=[{"type": "create_task", "title_template": "Каскад"}],
        )
        await _enqueue_incident(session, tenant_id, _incident(tenant_id))
        await session.commit()

        rule_triggered_rows = (
            (
                await session.execute(
                    select(Outbox).where(
                        Outbox.tenant_id == tenant_id,
                        Outbox.event_type == "rule.triggered",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert rule_triggered_rows  # webhook-правило дошло до outbox

        triggers = await _trigger_rows(session, tenant_id)
        assert [t.rule_id for t in triggers] == [webhook_rule.id]
        assert await _task_count(session, tenant_id) == 0


@pytest.mark.asyncio
async def test_disabled_rule_does_not_fire(sessionmaker, data_factory: TestDataFactory) -> None:
    tenant_id = await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        await _make_rule(
            session,
            tenant_id,
            name="Выключенное правило",
            is_enabled=False,
            actions_json=[{"type": "create_task", "title_template": "Т"}],
        )
        await _enqueue_incident(session, tenant_id, _incident(tenant_id))
        await session.commit()

        assert await _trigger_rows(session, tenant_id) == []
        assert await _task_count(session, tenant_id) == 0
