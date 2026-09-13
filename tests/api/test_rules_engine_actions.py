"""Тесты исполнителей действий правил (P10-10 срез-1): create_task / notify / webhook."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
async def test_create_task_refuses_cross_tenant_assignee(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    from app.models.obligations import Task
    from app.modules.rules_engine.actions import execute_action

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        foreign_tenant = await data_factory.ensure_tenant(slug="foreign-actions", session=session)
        foreign_user = await data_factory.create_user(
            tenant=foreign_tenant, email="foreign-assignee@example.com", session=session
        )
        rule = await _make_rule(session, str(tenant.id), name="Кросс-tenant assignee")

        outcome = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action={
                "type": "create_task",
                "title_template": "Проверка",
                "assignee_mode": "user_id",
                "user_id": str(foreign_user.id),
            },
            event_key="incident:xt-1",
            payload={},
            already_triggered=False,
        )

        assert outcome.outcome == "error"
        count = (
            await session.execute(
                select(func.count()).select_from(Task).where(Task.tenant_id == str(tenant.id))
            )
        ).scalar_one()
        assert count == 0


@pytest.mark.asyncio
async def test_notify_suppresses_cross_tenant_recipient(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    from app.models.notifications import Notification
    from app.modules.rules_engine.actions import execute_action

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        foreign_tenant = await data_factory.ensure_tenant(slug="foreign-notify", session=session)
        foreign_user = await data_factory.create_user(
            tenant=foreign_tenant, email="foreign-recipient@example.com", session=session
        )
        rule = await _make_rule(session, str(tenant.id), name="Кросс-tenant notify")

        outcome = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action={
                "type": "notify",
                "title_template": "Т",
                "body_template": "Б",
                "recipient_mode": "user_id",
                "user_id": str(foreign_user.id),
            },
            event_key="incident:xt-2",
            payload={},
            already_triggered=False,
        )

        assert outcome.outcome == "suppressed"
        assert outcome.detail == "no recipients"
        count = (
            await session.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == str(foreign_user.id))
            )
        ).scalar_one()
        assert count == 0


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
        recipient = await data_factory.create_user(
            tenant=tenant, email="actions-recipient@example.com", session=session
        )
        user_id = str(recipient.id)
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


@pytest.mark.asyncio
async def test_notify_person_mode_reaches_worker_account(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """Срез-118: получатель «работник из события» — сам сотрудник, а не роль.

    Связь «работник — вход в систему» одна на продукт: совпадение почты
    (прецедент карточки сотрудника). Регистр почты не должен мешать.
    """
    from app.models.models import RoleEnum
    from app.models.notifications import Notification
    from app.modules.rules_engine.actions import execute_action

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        worker_user = await data_factory.create_user(
            tenant=tenant,
            email="worker-118@example.com",
            role=RoleEnum.EMPLOYEE,
            session=session,
        )
        person = await data_factory.create_person(
            tenant=tenant,
            first_name="Пётр",
            last_name="Петров",
            email="Worker-118@Example.com",
            session=session,
        )
        rule = await _make_rule(session, str(tenant.id), name="Скоро замена СИЗ")

        outcome = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action={
                "type": "notify",
                "title_template": "Замена СИЗ",
                "body_template": "Срок по {item_name}",
                "recipient_mode": "person",
            },
            event_key="ppe:118",
            payload={"person_id": str(person.id), "item_name": "каска"},
            already_triggered=False,
        )

        assert outcome.outcome == "created"
        recipients = (
            (
                await session.execute(
                    select(Notification.user_id).where(Notification.id.in_(outcome.entity_ids))
                )
            )
            .scalars()
            .all()
        )
        assert [str(r) for r in recipients] == [str(worker_user.id)]


@pytest.mark.asyncio
async def test_notify_person_mode_skips_terminated_worker(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """Уволенному уведомления не уходят — общее правило person_scope (срез-89)."""
    from app.models.master_data import EmploymentStatus
    from app.models.models import RoleEnum
    from app.modules.rules_engine.actions import execute_action

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_user(
            tenant=tenant,
            email="fired-118@example.com",
            role=RoleEnum.EMPLOYEE,
            session=session,
        )
        person = await data_factory.create_person(
            tenant=tenant,
            first_name="Иван",
            last_name="Уволенный",
            email="fired-118@example.com",
            employment_status=EmploymentStatus.TERMINATED,
            session=session,
        )
        rule = await _make_rule(session, str(tenant.id), name="Медосмотр просрочен")

        outcome = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action={
                "type": "notify",
                "title_template": "Медосмотр",
                "body_template": "Просрочен",
                "recipient_mode": "person",
            },
            event_key="med:118",
            payload={"person_id": str(person.id)},
            already_triggered=False,
        )

        assert outcome.outcome == "suppressed"
        assert outcome.entity_ids == []


@pytest.mark.asyncio
async def test_notify_person_mode_suppressed_without_account(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """У работника нет входа в систему — уведомление некому доставить."""
    from app.modules.rules_engine.actions import execute_action

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        person = await data_factory.create_person(
            tenant=tenant,
            first_name="Без",
            last_name="Почты",
            session=session,
        )
        rule = await _make_rule(session, str(tenant.id), name="Обучение назначено")

        outcome = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action={
                "type": "notify",
                "title_template": "Обучение",
                "body_template": "Назначено",
                "recipient_mode": "person",
            },
            event_key="training:118",
            payload={"person_id": str(person.id)},
            already_triggered=False,
        )

        assert outcome.outcome == "suppressed"
        assert outcome.detail == "no active user account for person from event"


@pytest.mark.asyncio
async def test_notify_person_mode_ignores_foreign_person(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """Чужой person_id в payload не должен вытащить получателя из другого тенанта."""
    from app.models.models import RoleEnum
    from app.modules.rules_engine.actions import execute_action

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        foreign = await data_factory.ensure_tenant(slug="foreign-person-118", session=session)
        await data_factory.create_user(
            tenant=tenant,
            email="foreign-118@example.com",
            role=RoleEnum.EMPLOYEE,
            session=session,
        )
        foreign_person = await data_factory.create_person(
            tenant=foreign,
            first_name="Чужой",
            last_name="Работник",
            email="foreign-118@example.com",
            session=session,
        )
        rule = await _make_rule(session, str(tenant.id), name="Чужой работник")

        outcome = await execute_action(
            session,
            tenant_id=str(tenant.id),
            rule=rule,
            action={
                "type": "notify",
                "title_template": "Не для вас",
                "body_template": "Тело",
                "recipient_mode": "person",
            },
            event_key="foreign:118",
            payload={"person_id": str(foreign_person.id)},
            already_triggered=False,
        )

        assert outcome.outcome == "suppressed"


def test_person_mode_rejected_for_event_without_person() -> None:
    """Правило на событии без person_id никогда бы не нашло адресата — 422 сразу."""
    from app.modules.rules_engine.actions import ActionsError, validate_actions
    from app.modules.rules_engine.catalog import known_fields_for

    action = {
        "type": "notify",
        "title_template": "Т",
        "body_template": "Б",
        "recipient_mode": "person",
    }
    with pytest.raises(ActionsError) as exc:
        validate_actions([action], known_fields=known_fields_for("IncidentCreated"))
    assert exc.value.code == "person_not_in_event"

    # У события с работником то же действие сохраняется.
    validate_actions([action], known_fields=known_fields_for("PPEReplacementDue"))
    # Без каталога (старый вызов) проверка не мешает.
    validate_actions([action])


def test_recipient_mode_titles_match_rules_screen() -> None:
    """Сторож: подписи получателей на экране правил и в описании действия — один список."""
    import re
    from pathlib import Path

    from app.modules.rules_engine.actions import _RECIPIENT_MODES, RECIPIENT_MODE_TITLES

    assert set(RECIPIENT_MODE_TITLES) == set(_RECIPIENT_MODES)

    source = Path("frontend/src/pages/rules/rulesVocab.ts").read_text(encoding="utf-8")
    block = re.search(
        r"export const RECIPIENT_MODE_LABELS: Record<string, string> = \{(.*?)\};",
        source,
        re.S,
    )
    assert block is not None, "RECIPIENT_MODE_LABELS не найден на экране правил"
    frontend = dict(re.findall(r'(\w+): "([^"]+)"', block.group(1)))
    assert frontend == RECIPIENT_MODE_TITLES


def test_известные_роли_исполнителя_совпадают_со_словарём_ролей_ядра() -> None:
    """Сторож (срез-148): исполнитель и словарь подписей знают одни и те же роли.

    Форма берёт роли из ``/rules/recipient-roles`` (``role_options``). Разойдись
    наборы — форма предложила бы роль, которую исполнитель отвергнет 422, или
    исполнитель принимал бы роль без человеческой подписи.
    """
    from app.core.role_labels import ROLE_ALIASES, ROLE_CODES, role_options
    from app.modules.rules_engine.actions import _KNOWN_ROLES

    assert _KNOWN_ROLES == ROLE_CODES
    offered = {item["code"] for item in role_options()}
    assert offered == _KNOWN_ROLES - set(ROLE_ALIASES)
    # Подписи есть у всех предлагаемых ролей и ни одна не равна коду.
    assert all(item["label"] and item["label"] != item["code"] for item in role_options())
