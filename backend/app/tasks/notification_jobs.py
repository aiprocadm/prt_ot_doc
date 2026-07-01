"""Notification & reminder-scan Celery jobs (ARCH-4 decomposition; RC-011 delivery).

Explicit ``name=`` is preserved for the existing tasks, so the ``reminders.scan``
beat-schedule entry keeps resolving by name; re-exported from ``_core`` for back-compat
(``from app.tasks import scan_reminders_job`` etc.).

Covers the reminder-rule scan (training / PPE / inspection due-date evaluation -> in-app
notifications + plan tasks) and, since RC-011, real notification delivery: single-message
dispatch and the ``notifications.dispatch_pending`` beat scan both hand off to
:mod:`app.modules.notifications.delivery` (per-channel providers + honest status +
channel-tier escalation) instead of stubbing ``status=SENT``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenant import tenant_context
from app.db import AsyncSessionLocal, ensure_tenant_schema, session_scope
from app.models.models import (
    Inspection,
    PPEIssue,
    RoleEnum,
    Tenant,
    TrainingPlan,
    User,
)
from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    PlanTask,
    PlanTaskStatus,
    ReminderEntityType,
    ReminderRule,
)
from app.modules.notifications.delivery import (
    deliver_notification,
    scan_pending_notifications,
)
from app.services.celery_app import celery_app
from app.services.notifications import send_notification
from app.services.reminders import evaluate_due_date
from app.tasks._shared import _run_coroutine

settings = get_settings()


@celery_app.task(name="notifications.dispatch")
def dispatch_notification_job(notification_id: str, tenant_slug: str = "test") -> int:
    return _run_coroutine(
        _dispatch_notification_job(notification_id=notification_id, tenant_slug=tenant_slug)
    )


async def _dispatch_notification_job(*, notification_id: str, tenant_slug: str = "test") -> int:
    async with session_scope(tenant=tenant_slug) as session:
        notification = (
            await session.execute(select(Notification).where(Notification.id == notification_id))
        ).scalar_one_or_none()
        if notification is None or notification.status != NotificationStatus.QUEUED:
            return 0
        # RC-011: real provider delivery + honest status + channel-tier escalation
        # (replaces the former stub that set status=SENT without calling any provider).
        await deliver_notification(session, notification)
    return 1


@celery_app.task(name="notifications.dispatch_pending")
def dispatch_pending_notifications_job() -> int:
    """Beat job: deliver all due QUEUED notifications for every active tenant (RC-011)."""
    return _run_coroutine(_dispatch_pending_notifications_job())


async def _dispatch_pending_notifications_job() -> int:
    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
            .scalars()
            .all()
        )
    processed = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as tenant_session:
                processed += await scan_pending_notifications(tenant_session)
    return processed


@celery_app.task(name="reminders.scan")
def scan_reminders_job() -> int:
    return _run_coroutine(_scan_reminders_job())


async def _resolve_rule_recipients(
    *, session: AsyncSession, tenant_id: str, rule: ReminderRule, default_user_id: str | None
) -> list[str]:
    recipients = rule.recipients or {}
    mode = str(recipients.get("mode") or "assignees")
    resolved: set[str] = set()
    if mode in {"assignees", "managers"} and default_user_id:
        resolved.add(default_user_id)
    if mode in {"role", "managers"}:
        roles = [str(role).lower() for role in recipients.get("roles", [])]
        if mode == "managers" and not roles:
            roles = [RoleEnum.ADMIN.value]
        if roles:
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
            resolved.update(user.id for user in users)
    if mode == "explicit":
        explicit = [str(user_id) for user_id in recipients.get("user_ids", [])]
        resolved.update(explicit)
    return list(resolved)


async def _scan_reminders_for_tenant(*, tenant_slug: str, now: datetime) -> int:
    processed = 0
    async with session_scope(tenant=tenant_slug) as session:
        rules = (
            (
                await session.execute(
                    select(ReminderRule).where(
                        ReminderRule.is_enabled.is_(True), ReminderRule.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        for rule in rules:
            entity_type_value = (
                rule.entity_type.value
                if hasattr(rule.entity_type, "value")
                else str(rule.entity_type)
            )
            offsets = [int(x) for x in (rule.schedule or {}).get("offsets_days", [30, 14, 7, 1, 0])]
            escalation_days = int(
                ((rule.schedule or {}).get("escalation") or {}).get("after_days", 3)
            )
            if entity_type_value == ReminderEntityType.TRAINING.value:
                rows = (
                    (
                        await session.execute(
                            select(TrainingPlan).where(
                                TrainingPlan.due_date.is_not(None),
                                TrainingPlan.deleted_at.is_(None),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for training in rows:
                    if not training.due_date:
                        continue
                    evaluation = evaluate_due_date(
                        due_date=training.due_date, today=now.date(), offsets_days=offsets
                    )
                    if evaluation is None:
                        continue
                    due_dt = datetime.combine(
                        training.due_date, datetime.min.time(), tzinfo=timezone.utc
                    )
                    recipients = await _resolve_rule_recipients(
                        session=session,
                        tenant_id=rule.tenant_id,
                        rule=rule,
                        default_user_id=training.person_id or training.created_by,
                    )
                    status = (
                        PlanTaskStatus.OVERDUE if evaluation.is_overdue else PlanTaskStatus.OPEN
                    )
                    if bool((rule.action or {}).get("create_task", True)) and recipients:
                        assignee = recipients[0]
                        task = (
                            await session.execute(
                                select(PlanTask).where(
                                    PlanTask.tenant_id == rule.tenant_id,
                                    PlanTask.entity_type == "training",
                                    PlanTask.entity_id == training.id,
                                    PlanTask.assignee_id == assignee,
                                    PlanTask.deleted_at.is_(None),
                                )
                            )
                        ).scalar_one_or_none()
                        if task is None:
                            session.add(
                                PlanTask(
                                    tenant_id=rule.tenant_id,
                                    title=f"Training due: {training.id}",
                                    description="Autogenerated from reminder rule",
                                    entity_type="training",
                                    entity_id=training.id,
                                    assignee_id=assignee,
                                    status=status,
                                    due_at=due_dt,
                                )
                            )
                        else:
                            task.status = status
                            task.due_at = due_dt
                    if bool((rule.action or {}).get("notify", True)):
                        for user_id in recipients:
                            n_type = (
                                NotificationType.TRAINING_OVERDUE
                                if evaluation.is_overdue
                                else NotificationType.TRAINING_DUE_SOON
                            )
                            effective_offset = (
                                -escalation_days if evaluation.is_overdue else evaluation.offset_day
                            )
                            dedup_key = f"{rule.tenant_id}:{rule.code}:{training.id}:{due_dt.date().isoformat()}:{effective_offset}:inapp:{user_id}"
                            await send_notification(
                                session,
                                tenant_id=rule.tenant_id,
                                user_id=user_id,
                                channel=NotificationChannel.INAPP,
                                type=n_type,
                                title="Контрольная дата обучения",
                                body="Проверьте дедлайн обучения",
                                payload={
                                    "entity_type": "training",
                                    "entity_id": training.id,
                                    "deeplink": f"/training?id={training.id}",
                                },
                                dedup_key=dedup_key,
                            )
                    processed += 1
            elif entity_type_value == ReminderEntityType.PPE.value:
                rows = (
                    (
                        await session.execute(
                            select(PPEIssue).where(
                                PPEIssue.expires_at.is_not(None), PPEIssue.deleted_at.is_(None)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for issue in rows:
                    due_date = issue.expires_at.date() if issue.expires_at else None
                    if not due_date:
                        continue
                    evaluation = evaluate_due_date(
                        due_date=due_date, today=now.date(), offsets_days=offsets
                    )
                    if evaluation is None:
                        continue
                    recipients = await _resolve_rule_recipients(
                        session=session,
                        tenant_id=rule.tenant_id,
                        rule=rule,
                        default_user_id=issue.created_by,
                    )
                    for user_id in recipients:
                        dedup_key = f"{rule.tenant_id}:{rule.code}:{issue.id}:{due_date.isoformat()}:{evaluation.offset_day}:inapp:{user_id}"
                        await send_notification(
                            session,
                            tenant_id=rule.tenant_id,
                            user_id=user_id,
                            channel=NotificationChannel.INAPP,
                            type=NotificationType.PPE_EXPIRY_SOON,
                            title="Срок действия СИЗ",
                            body="Требуется продление или переоформление СИЗ",
                            payload={
                                "entity_type": "ppe",
                                "entity_id": issue.id,
                                "deeplink": f"/ppe?issue={issue.id}",
                            },
                            dedup_key=dedup_key,
                        )
                    processed += 1
            elif entity_type_value == ReminderEntityType.INSPECTION.value:
                rows = (
                    (
                        await session.execute(
                            select(Inspection).where(
                                Inspection.scheduled_at.is_not(None),
                                Inspection.deleted_at.is_(None),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for inspection in rows:
                    if not inspection.scheduled_at:
                        continue
                    evaluation = evaluate_due_date(
                        due_date=inspection.scheduled_at, today=now.date(), offsets_days=offsets
                    )
                    if evaluation is None:
                        continue
                    recipients = await _resolve_rule_recipients(
                        session=session,
                        tenant_id=rule.tenant_id,
                        rule=rule,
                        default_user_id=inspection.responsible_id,
                    )
                    ntype = (
                        NotificationType.INSPECTION_OVERDUE
                        if evaluation.is_overdue
                        else NotificationType.INSPECTION_PLANNED
                    )
                    for user_id in recipients:
                        dedup_key = f"{rule.tenant_id}:{rule.code}:{inspection.id}:{inspection.scheduled_at.isoformat()}:{evaluation.offset_day}:inapp:{user_id}"
                        await send_notification(
                            session,
                            tenant_id=rule.tenant_id,
                            user_id=user_id,
                            channel=NotificationChannel.INAPP,
                            type=ntype,
                            title="Проверка по графику",
                            body="Контрольная дата проверки",
                            payload={
                                "entity_type": "inspection",
                                "entity_id": inspection.id,
                                "deeplink": f"/inspections?id={inspection.id}",
                            },
                            dedup_key=dedup_key,
                        )
                    processed += 1
        await session.flush()
    return processed


async def _scan_reminders_job() -> int:
    now = datetime.now(tz=timezone.utc)
    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
            .scalars()
            .all()
        )
    processed = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            processed += await _scan_reminders_for_tenant(tenant_slug=tenant.slug, now=now)
    return processed
