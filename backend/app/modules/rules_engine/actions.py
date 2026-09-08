"""Исполнители действий правил: create_task / notify / webhook.

Все действия flush-only — транзакцию владеет вызывающий (hook в enqueue).
Каждое действие возвращает ActionOutcome; исключение одного действия НЕ прерывает
остальные (ловится в engine.py).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_data import Person
from app.models.models import RoleEnum, User
from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationType,
)
from app.models.obligations import Task, TaskPriority, TaskReminderChannel, TaskStatus
from app.models.rules_engine import AutomationRule, AutomationRuleTrigger
from app.modules.rules_engine.conditions import resolve_field
from app.services.notifications import send_notification
from app.services.obligations import next_task_reminder
from app.services.person_link import resolve_user_id
from app.services.person_scope import employed_person_where

ALLOWED_ACTION_TYPES = frozenset({"create_task", "notify", "webhook"})
MAX_ACTIONS = 10
_TEMPLATE_RE = re.compile(r"\{([A-Za-z0-9_.]+)\}")
_TASK_PRIORITIES = frozenset(p.value for p in TaskPriority)
_NOTIFY_PRIORITIES = frozenset(p.value for p in NotificationPriority)
_RECIPIENT_MODES = frozenset({"actor", "user_id", "role", "person"})
# Поле события, из которого режим "person" берёт работника. Одно имя, а не
# догадки по похожим полям: правило на событии без него отклоняется при
# сохранении (см. _validate_notify), а не молчит в проде.
PERSON_EVENT_FIELD = "person_id"
# Подписи режимов получателя — общие с экраном правил
# (frontend/src/pages/rules/rulesVocab.ts, RECIPIENT_MODE_LABELS). Сторож
# tests/api/test_rules_engine_actions.py сверяет два списка.
RECIPIENT_MODE_TITLES: dict[str, str] = {
    "actor": "Автор события",
    "person": "Работник из события",
    "user_id": "Указать user ID",
    "role": "По ролям",
}
_ASSIGNEE_MODES = frozenset({"none", "actor", "user_id"})
_KNOWN_ROLES = frozenset(r.value for r in RoleEnum)
MAX_DUE_IN_DAYS = 365


class ActionsError(ValueError):
    """Typed-ошибка валидации; code уходит в 422 API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ActionOutcome:
    type: str
    outcome: str  # created | deduped | suppressed | error
    detail: str | None = None
    entity_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": self.type, "outcome": self.outcome}
        if self.detail:
            data["detail"] = self.detail
        if self.entity_ids:
            data["entity_ids"] = self.entity_ids
        return data


def _require_template(idx: int, action: Mapping[str, Any], key: str) -> None:
    value = action.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ActionsError("invalid_action", f"action #{idx}: {key} is required")


def _validate_create_task(idx: int, action: Mapping[str, Any]) -> None:
    _require_template(idx, action, "title_template")
    priority = action.get("priority", "medium")
    if not isinstance(priority, str) or priority not in _TASK_PRIORITIES:
        raise ActionsError("invalid_action", f"action #{idx}: bad priority {priority!r}")
    assignee_mode = action.get("assignee_mode", "none")
    if not isinstance(assignee_mode, str) or assignee_mode not in _ASSIGNEE_MODES:
        raise ActionsError("invalid_action", f"action #{idx}: bad assignee_mode {assignee_mode!r}")
    if assignee_mode == "user_id" and not action.get("user_id"):
        raise ActionsError(
            "invalid_action", f"action #{idx}: user_id is required for assignee_mode=user_id"
        )
    due_in_days = action.get("due_in_days")
    if due_in_days is not None and (
        isinstance(due_in_days, bool)
        or not isinstance(due_in_days, int)
        or not 0 <= due_in_days <= MAX_DUE_IN_DAYS
    ):
        raise ActionsError(
            "invalid_action", f"action #{idx}: due_in_days must be an int 0..{MAX_DUE_IN_DAYS}"
        )


def _validate_notify(
    idx: int, action: Mapping[str, Any], known_fields: frozenset[str] | None
) -> None:
    _require_template(idx, action, "title_template")
    _require_template(idx, action, "body_template")
    mode = action.get("recipient_mode")
    if not isinstance(mode, str) or mode not in _RECIPIENT_MODES:
        raise ActionsError("invalid_action", f"action #{idx}: bad recipient_mode {mode!r}")
    if mode == "user_id" and not action.get("user_id"):
        raise ActionsError(
            "invalid_action", f"action #{idx}: user_id is required for recipient_mode=user_id"
        )
    if mode == "person" and known_fields is not None and PERSON_EVENT_FIELD not in known_fields:
        raise ActionsError(
            "person_not_in_event",
            f"action #{idx}: event has no {PERSON_EVENT_FIELD!r} field",
        )
    if mode == "role":
        roles = action.get("roles")
        if not isinstance(roles, list) or not roles:
            raise ActionsError("invalid_action", f"action #{idx}: non-empty roles list is required")
        for role in roles:
            if str(role).lower() not in _KNOWN_ROLES:
                raise ActionsError("invalid_action", f"action #{idx}: unknown role {role!r}")
    priority = action.get("priority", "medium")
    if not isinstance(priority, str) or priority not in _NOTIFY_PRIORITIES:
        raise ActionsError("invalid_action", f"action #{idx}: bad priority {priority!r}")


def validate_actions(raw: Any, *, known_fields: frozenset[str] | None = None) -> None:
    """422-валидация actions_json (список из <= MAX_ACTIONS известных действий).

    ``known_fields`` — поля выбранного события (``catalog.known_fields_for``).
    Нужны режиму получателя ``person``: правило, повешенное на событие без
    ``person_id``, никогда бы не нашло адресата, и лучше сказать об этом при
    сохранении.
    """
    if not isinstance(raw, list) or not raw:
        raise ActionsError("invalid_actions", "actions_json must be a non-empty list")
    if len(raw) > MAX_ACTIONS:
        raise ActionsError("too_many_actions", f"at most {MAX_ACTIONS} actions")
    for idx, action in enumerate(raw):
        if not isinstance(action, Mapping):
            raise ActionsError("invalid_action", f"action #{idx} must be an object")
        a_type = action.get("type")
        # isinstance-guard: unhashable значение (list/dict) в `in frozenset` даёт TypeError.
        if not isinstance(a_type, str) or a_type not in ALLOWED_ACTION_TYPES:
            raise ActionsError("invalid_action_type", f"action #{idx}: bad type {a_type!r}")
        if a_type == "create_task":
            _validate_create_task(idx, action)
        elif a_type == "notify":
            _validate_notify(idx, action, known_fields)
        # webhook: параметров нет


def _collect_action_user_ids(raw: Any) -> set[str]:
    ids: set[str] = set()
    for action in raw if isinstance(raw, list) else []:
        if not isinstance(action, Mapping):
            continue
        a_type = action.get("type")
        user_id = action.get("user_id")
        if not user_id:
            continue
        if (a_type == "create_task" and action.get("assignee_mode") == "user_id") or (
            a_type == "notify" and action.get("recipient_mode") == "user_id"
        ):
            ids.add(str(user_id))
    return ids


async def validate_action_user_ids(session: AsyncSession, *, tenant_id: str, actions: Any) -> None:
    """user_id в действиях обязан принадлежать тенанту: user.id глобален, и чужой UUID
    утёк бы (имя/email) через joined Task.assignee / Notification."""
    wanted = _collect_action_user_ids(actions)
    if not wanted:
        return
    rows = (
        (
            await session.execute(
                select(User.id).where(
                    User.id.in_(wanted),
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    missing = wanted - {str(r) for r in rows}
    if missing:
        raise ActionsError("unknown_user_id", f"user_id not found in tenant: {sorted(missing)[0]}")


async def _user_in_tenant(session: AsyncSession, *, tenant_id: str, user_id: str) -> bool:
    row = await session.scalar(
        select(User.id).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
        )
    )
    return row is not None


def render_template(template: str, payload: Mapping[str, Any], *, limit: int) -> str:
    def _sub(match: re.Match[str]) -> str:
        found, value = resolve_field(payload, match.group(1))
        if not found or value is None:
            return ""
        return str(value)

    return _TEMPLATE_RE.sub(_sub, template)[:limit]


def short_key(event_key: str) -> str:
    return hashlib.sha256(event_key.encode("utf-8")).hexdigest()[:16]


def describe_action(action: Mapping[str, Any]) -> str:
    """Человекочитаемое описание для dry-run (без исполнения)."""
    a_type = action.get("type")
    if a_type == "create_task":
        return f"создать задачу «{action.get('title_template', '')}»"
    if a_type == "notify":
        mode = str(action.get("recipient_mode"))
        who = RECIPIENT_MODE_TITLES.get(mode, mode)
        return f"уведомление ({who}) «{action.get('title_template', '')}»"
    if a_type == "webhook":
        return "отправить webhook rule.triggered"
    return str(a_type)


async def was_already_triggered(
    session: AsyncSession, *, tenant_id: str, rule_id: str, event_key: str
) -> bool:
    stmt = (
        select(AutomationRuleTrigger.id)
        .where(
            AutomationRuleTrigger.tenant_id == tenant_id,
            AutomationRuleTrigger.rule_id == rule_id,
            AutomationRuleTrigger.event_key == event_key,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _resolve_person_user(
    session: AsyncSession, *, tenant_id: str, person_id: str
) -> list[str]:
    """Учётная запись работника из события.

    Связь «работник — вход в систему» в продукте одна и живёт в
    ``services/person_link``: отдельной ссылки у ``User`` нет, сопоставление
    идёт по почте. Уволенного не уведомляем — общее правило ``person_scope``
    (срез-89): его сроки больше не его обязательства.
    """
    person = await session.scalar(
        select(Person).where(
            Person.id == person_id,
            Person.tenant_id == tenant_id,
            *employed_person_where(),
        )
    )
    if person is None:
        return []
    user_id = await resolve_user_id(session, tenant_id, person.email)
    return [user_id] if user_id else []


async def _resolve_recipients(
    session: AsyncSession,
    *,
    tenant_id: str,
    action: Mapping[str, Any],
    actor_id: str | None,
    payload: Mapping[str, Any],
) -> list[str]:
    mode = action.get("recipient_mode")
    if mode == "actor":
        return [actor_id] if actor_id else []
    if mode == "user_id":
        user_id = action.get("user_id")
        if not user_id:
            return []
        # Fail-closed для правил, сохранённых до тенант-валидации user_id (или после
        # удаления пользователя): чужой/несуществующий получатель молча отбрасывается.
        if not await _user_in_tenant(session, tenant_id=tenant_id, user_id=str(user_id)):
            return []
        return [str(user_id)]
    if mode == "person":
        person_id = payload.get(PERSON_EVENT_FIELD)
        if not person_id:
            return []
        return await _resolve_person_user(session, tenant_id=tenant_id, person_id=str(person_id))
    if mode == "role":
        # Прецедент: _resolve_rule_recipients в app/tasks/notification_jobs.py —
        # lowercase-значения RoleEnum сравниваются напрямую через .in_().
        roles = [str(r).lower() for r in action.get("roles", [])]
        users = (
            (
                await session.execute(
                    select(User).where(
                        User.tenant_id == tenant_id,
                        User.deleted_at.is_(None),
                        User.role.in_(roles),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [str(u.id) for u in users]
    return []


async def _execute_create_task(
    session: AsyncSession,
    *,
    tenant_id: str,
    rule: AutomationRule,
    action: Mapping[str, Any],
    payload: Mapping[str, Any],
    already_triggered: bool,
) -> ActionOutcome:
    if already_triggered:
        return ActionOutcome(type="create_task", outcome="deduped", detail="already triggered")
    due_at: datetime | None = None
    due_in_days = action.get("due_in_days")
    if due_in_days is not None:
        due_at = datetime.now(tz=timezone.utc) + timedelta(days=int(due_in_days))
    assignee_mode = action.get("assignee_mode", "none")
    assignee_id: Any = None
    if assignee_mode == "actor":
        assignee_id = payload.get("actor_id")
    elif assignee_mode == "user_id":
        assignee_id = action.get("user_id")
        # Fail-closed для правил, сохранённых до тенант-валидации user_id.
        if assignee_id and not await _user_in_tenant(
            session, tenant_id=tenant_id, user_id=str(assignee_id)
        ):
            return ActionOutcome(
                type="create_task", outcome="error", detail="assignee is not in tenant"
            )
    actor_id = payload.get("actor_id")
    title = render_template(str(action.get("title_template", "")), payload, limit=255)
    description = render_template(
        str(action.get("description_template") or ""), payload, limit=2000
    )
    task = Task(
        tenant_id=tenant_id,
        title=title or f"Правило: {rule.name}"[:255],
        description=description or None,
        entity_type="automation_rule",
        entity_id=rule.id,
        due_at=due_at,
        status=TaskStatus.OPEN,
        assignee_id=str(assignee_id) if assignee_id else None,
        created_by=str(actor_id) if actor_id else None,
        priority=TaskPriority(str(action.get("priority", "medium"))),
        reminder_channel=TaskReminderChannel.IN_APP,
        next_remind_at=await next_task_reminder(session, due_at=due_at),
    )
    session.add(task)
    await session.flush()
    return ActionOutcome(type="create_task", outcome="created", entity_ids=[str(task.id)])


async def _execute_notify(
    session: AsyncSession,
    *,
    tenant_id: str,
    rule: AutomationRule,
    action: Mapping[str, Any],
    event_key: str,
    payload: Mapping[str, Any],
) -> ActionOutcome:
    raw_actor = payload.get("actor_id")
    recipients = await _resolve_recipients(
        session,
        tenant_id=tenant_id,
        action=action,
        actor_id=str(raw_actor) if raw_actor else None,
        payload=payload,
    )
    if not recipients:
        detail = "no recipients"
        if action.get("recipient_mode") == "person":
            # Разные причины пустоты (нет person_id, уволен, нет почты, нет входа)
            # намеренно сведены в один текст: подробность здесь рассказала бы о
            # человеке больше, чем видно на экране правил.
            detail = "no active user account for person from event"
        return ActionOutcome(type="notify", outcome="suppressed", detail=detail)
    title = render_template(str(action.get("title_template", "")), payload, limit=255)
    body = render_template(str(action.get("body_template", "")), payload, limit=2000)
    created: list[str] = []
    deduped = 0
    suppressed = 0
    for user_id in recipients:
        dedup_key = f"rules:{rule.id}:{short_key(event_key)}:{user_id}"
        # Пре-чек ДО send_notification: на dedup-hit он возвращает существующую
        # строку, и created/deduped были бы неотличимы post-hoc.
        existing = (
            await session.execute(
                select(Notification.id)
                .where(Notification.dedup_key == dedup_key, Notification.deleted_at.is_(None))
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            deduped += 1
            continue
        row = await send_notification(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            channel=NotificationChannel.INAPP,
            type=NotificationType.AUTOMATION_RULE,
            title=title or f"Правило: {rule.name}"[:255],
            body=body or title or rule.name,
            payload={"rule_id": rule.id, "event_key": event_key},
            dedup_key=dedup_key,
            priority=NotificationPriority(str(action.get("priority", "medium"))),
        )
        if row is None:  # opt-out канала у получателя
            suppressed += 1
        else:
            created.append(str(row.id))
    if created:
        outcome = "created"
    elif deduped:
        outcome = "deduped"
    else:
        outcome = "suppressed"
    return ActionOutcome(
        type="notify",
        outcome=outcome,
        detail=f"created={len(created)} deduped={deduped} suppressed={suppressed}",
        entity_ids=created,
    )


async def _execute_webhook(
    session: AsyncSession,
    *,
    tenant_id: str,
    rule: AutomationRule,
    event_key: str,
    payload: Mapping[str, Any],
) -> ActionOutcome:
    # Lazy-import: outbox.enqueue получит hook на engine (Task 5) — разрыв цикла.
    from app.services.outbox import OutboxService

    entries = await OutboxService(session).enqueue(
        tenant_id=tenant_id,
        event_type="rule.triggered",
        payload={
            "tenant_id": tenant_id,
            "actor_id": payload.get("actor_id"),
            "rule_id": rule.id,
            "rule_name": rule.name,
            "source_event_type": rule.event_type,
            "source_event_key": event_key,
            "source_payload": dict(payload),
        },
        idempotency_key=f"rule-triggered:{rule.id}:{short_key(event_key)}",
    )
    return ActionOutcome(type="webhook", outcome="created", entity_ids=[str(e.id) for e in entries])


async def execute_action(
    session: AsyncSession,
    *,
    tenant_id: str,
    rule: AutomationRule,
    action: Mapping[str, Any],
    event_key: str,
    payload: Mapping[str, Any],
    already_triggered: bool,
) -> ActionOutcome:
    a_type = str(action.get("type"))
    if a_type == "create_task":
        return await _execute_create_task(
            session,
            tenant_id=tenant_id,
            rule=rule,
            action=action,
            payload=payload,
            already_triggered=already_triggered,
        )
    if a_type == "notify":
        return await _execute_notify(
            session,
            tenant_id=tenant_id,
            rule=rule,
            action=action,
            event_key=event_key,
            payload=payload,
        )
    if a_type == "webhook":
        return await _execute_webhook(
            session, tenant_id=tenant_id, rule=rule, event_key=event_key, payload=payload
        )
    return ActionOutcome(type=a_type, outcome="error", detail="unknown action")
