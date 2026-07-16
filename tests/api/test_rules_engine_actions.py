"""Тесты исполнителей действий правил (P10-10 срез-1): create_task / notify / webhook."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.utils.factories import TestDataFactory


async def _make_rule(session: AsyncSession, tenant_id: str, *, name: str, **overrides):
    from app.models.models import AutomationRule

    rule = AutomationRule(
        tenant_id=tenant_id,
        name=name,
        event_type=overrides.pop("event_type", "incident.created"),
        conditions_json=overrides.pop("conditions_json", {}),
        actions_json=overrides.pop("actions_json", []),
        **overrides,
    )
    session.add(rule)
    await session.flush()
    return rule


@pytest.mark.asyncio
async def test_create_task_created(sessionmaker, data_factory: TestDataFactory) -> None:
    from app.models.obligations import Task, TaskPriority
    from app.modules.rules_engine.actions import execute_action

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        rule = await _make_rule(session, str(tenant.id), name="Задача при инциденте")

        before = datetime.now(tz=timezone.utc)
        outcome = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action={
                "type": "create_task",
                "title_template": "Инцидент {severity}",
                "priority": "high",
                "due_in_days": 3,
            },
            event_key="incident:1",
            payload={"severity": "critical"},
            already_triggered=False,
        )

        assert outcome.outcome == "created"
        assert len(outcome.entity_ids) == 1
        task = (
            await session.execute(select(Task).where(Task.id == outcome.entity_ids[0]))
        ).scalar_one()
        assert task.title == "Инцидент critical"
        assert task.entity_type == "automation_rule"
        assert task.entity_id == rule.id
        assert task.priority == TaskPriority.HIGH
        assert task.assignee_id is None
        assert task.due_at is not None
        # SQLite возвращает naive datetime — нормализуем к UTC для сравнения.
        due_at = (
            task.due_at.replace(tzinfo=timezone.utc) if task.due_at.tzinfo is None else task.due_at
        )
        assert due_at > before + timedelta(days=2)
        assert due_at < before + timedelta(days=4)


@pytest.mark.asyncio
async def test_create_task_assignee_modes(sessionmaker, data_factory: TestDataFactory) -> None:
    from app.models.obligations import Task
    from app.modules.rules_engine.actions import execute_action

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        actor = await data_factory.create_user(
            tenant=tenant, email="actions-actor@example.com", session=session
        )
        assignee = await data_factory.create_user(
            tenant=tenant, email="actions-assignee@example.com", session=session
        )

        rule_actor = await _make_rule(session, str(tenant.id), name="Назначение на актора")
        outcome_actor = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule_actor,
            action={
                "type": "create_task",
                "title_template": "Разобрать инцидент",
                "assignee_mode": "actor",
            },
            event_key="incident:2",
            payload={"actor_id": str(actor.id)},
            already_triggered=False,
        )
        task_actor = (
            await session.execute(select(Task).where(Task.id == outcome_actor.entity_ids[0]))
        ).scalar_one()
        assert task_actor.assignee_id == str(actor.id)

        rule_user = await _make_rule(session, str(tenant.id), name="Назначение по user_id")
        outcome_user = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule_user,
            action={
                "type": "create_task",
                "title_template": "Проверить площадку",
                "assignee_mode": "user_id",
                "user_id": str(assignee.id),
            },
            event_key="incident:3",
            payload={},
            already_triggered=False,
        )
        task_user = (
            await session.execute(select(Task).where(Task.id == outcome_user.entity_ids[0]))
        ).scalar_one()
        assert task_user.assignee_id == str(assignee.id)


@pytest.mark.asyncio
async def test_create_task_deduped_on_repeat(sessionmaker, data_factory: TestDataFactory) -> None:
    from app.models.obligations import Task
    from app.modules.rules_engine.actions import execute_action

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        rule = await _make_rule(session, str(tenant.id), name="Повтор без дубля")

        outcome = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action={"type": "create_task", "title_template": "Дубль"},
            event_key="incident:4",
            payload={},
            already_triggered=True,
        )

        assert outcome.outcome == "deduped"
        assert outcome.entity_ids == []
        count = (await session.execute(select(func.count()).select_from(Task))).scalar_one()
        assert count == 0


@pytest.mark.asyncio
async def test_notify_user_id_created_then_deduped(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    from app.models.notifications import Notification, NotificationChannel, NotificationType
    from app.modules.rules_engine.actions import execute_action, short_key

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        rule = await _make_rule(session, str(tenant.id), name="Уведомление по user_id")
        user_id = str(uuid4())
        event_key = "incident:5"
        action = {
            "type": "notify",
            "title_template": "Инцидент {severity}",
            "body_template": "Уровень: {severity}",
            "recipient_mode": "user_id",
            "user_id": user_id,
        }

        first = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action=action,
            event_key=event_key,
            payload={"severity": "high"},
            already_triggered=False,
        )
        assert first.outcome == "created"
        assert first.detail == "created=1 deduped=0 suppressed=0"
        expected_dedup = f"rules:{rule.id}:{short_key(event_key)}:{user_id}"
        notification = (
            await session.execute(
                select(Notification).where(Notification.id == first.entity_ids[0])
            )
        ).scalar_one()
        assert notification.dedup_key == expected_dedup
        assert notification.type == NotificationType.AUTOMATION_RULE
        assert notification.channel == NotificationChannel.INAPP
        assert notification.title == "Инцидент high"

        second = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action=action,
            event_key=event_key,
            payload={"severity": "high"},
            already_triggered=True,
        )
        assert second.outcome == "deduped"
        assert second.detail == "created=0 deduped=1 suppressed=0"
        count = (await session.execute(select(func.count()).select_from(Notification))).scalar_one()
        assert count == 1


@pytest.mark.asyncio
async def test_notify_actor_mode_without_actor_suppressed(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    from app.modules.rules_engine.actions import execute_action

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        rule = await _make_rule(session, str(tenant.id), name="Актор отсутствует")

        outcome = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action={
                "type": "notify",
                "title_template": "Т",
                "body_template": "Б",
                "recipient_mode": "actor",
            },
            event_key="incident:6",
            payload={"severity": "low"},
            already_triggered=False,
        )

        assert outcome.outcome == "suppressed"
        assert outcome.detail == "no recipients"


@pytest.mark.asyncio
async def test_notify_role_mode(sessionmaker, data_factory: TestDataFactory) -> None:
    from app.models.models import RoleEnum
    from app.models.notifications import Notification
    from app.modules.rules_engine.actions import execute_action

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        admin = await data_factory.create_user(
            tenant=tenant,
            email="actions-role-admin@example.com",
            role=RoleEnum.ADMIN,
            session=session,
        )
        rule = await _make_rule(session, str(tenant.id), name="Уведомление по роли")

        outcome = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action={
                "type": "notify",
                "title_template": "Для админов",
                "body_template": "Событие {severity}",
                "recipient_mode": "role",
                "roles": ["admin"],
            },
            event_key="incident:7",
            payload={"severity": "high"},
            already_triggered=False,
        )

        assert outcome.outcome == "created"
        assert len(outcome.entity_ids) >= 1
        recipients = (
            (
                await session.execute(
                    select(Notification.user_id).where(Notification.id.in_(outcome.entity_ids))
                )
            )
            .scalars()
            .all()
        )
        assert str(admin.id) in [str(r) for r in recipients]


@pytest.mark.asyncio
async def test_webhook_enqueues_rule_triggered(sessionmaker, data_factory: TestDataFactory) -> None:
    from app.models.approval_runtime import Outbox
    from app.modules.rules_engine.actions import execute_action, short_key

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        rule = await _make_rule(session, str(tenant.id), name="Webhook при инциденте")
        event_key = "incident:8"

        outcome = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action={"type": "webhook"},
            event_key=event_key,
            payload={"severity": "critical", "actor_id": None},
            already_triggered=False,
        )

        assert outcome.outcome == "created"
        assert len(outcome.entity_ids) >= 1
        entries = (
            (await session.execute(select(Outbox).where(Outbox.id.in_(outcome.entity_ids))))
            .scalars()
            .all()
        )
        assert entries
        for entry in entries:
            assert entry.event_type == "rule.triggered"
            assert entry.idempotency_key == f"rule-triggered:{rule.id}:{short_key(event_key)}"
            assert entry.payload["rule_id"] == rule.id
            assert entry.payload["source_event_type"] == "incident.created"
            assert entry.payload["source_payload"]["severity"] == "critical"


def test_validate_actions_errors() -> None:
    from app.modules.rules_engine.actions import ActionsError, validate_actions

    with pytest.raises(ActionsError) as excinfo:
        validate_actions([])
    assert excinfo.value.code == "invalid_actions"

    with pytest.raises(ActionsError) as excinfo:
        validate_actions("not a list")
    assert excinfo.value.code == "invalid_actions"

    with pytest.raises(ActionsError) as excinfo:
        validate_actions([{"type": "webhook"}] * 11)
    assert excinfo.value.code == "too_many_actions"

    with pytest.raises(ActionsError) as excinfo:
        validate_actions(["not a mapping"])
    assert excinfo.value.code == "invalid_action"

    with pytest.raises(ActionsError) as excinfo:
        validate_actions([{"type": "delete_everything"}])
    assert excinfo.value.code == "invalid_action_type"

    with pytest.raises(ActionsError) as excinfo:
        validate_actions([{"type": "notify", "title_template": "Т", "recipient_mode": "actor"}])
    assert excinfo.value.code == "invalid_action"

    with pytest.raises(ActionsError) as excinfo:
        validate_actions(
            [
                {
                    "type": "notify",
                    "title_template": "Т",
                    "body_template": "Б",
                    "recipient_mode": "role",
                    "roles": ["galactic_emperor"],
                }
            ]
        )
    assert excinfo.value.code == "invalid_action"

    with pytest.raises(ActionsError) as excinfo:
        validate_actions([{"type": "create_task", "title_template": "Т", "due_in_days": 400}])
    assert excinfo.value.code == "invalid_action"

    # Unhashable значения — typed 422, а не TypeError от `in frozenset` (review Task 4).
    with pytest.raises(ActionsError) as excinfo:
        validate_actions([{"type": ["create_task"]}])
    assert excinfo.value.code == "invalid_action_type"

    with pytest.raises(ActionsError) as excinfo:
        validate_actions(
            [
                {
                    "type": "notify",
                    "title_template": "Т",
                    "body_template": "Б",
                    "recipient_mode": {"x": 1},
                }
            ]
        )
    assert excinfo.value.code == "invalid_action"

    # Валидные конфигурации проходят без исключений.
    validate_actions(
        [
            {"type": "webhook"},
            {"type": "create_task", "title_template": "Т", "due_in_days": 3},
            {
                "type": "notify",
                "title_template": "Т",
                "body_template": "Б",
                "recipient_mode": "role",
                "roles": ["ADMIN"],
            },
        ]
    )


def test_render_template_substitution_and_limit() -> None:
    from app.modules.rules_engine.actions import render_template

    payload = {"severity": "high", "before": {"level": "low"}}
    assert render_template("{severity}/{missing}/{before.level}", payload, limit=100) == "high//low"
    assert render_template("{severity}", payload, limit=2) == "hi"
