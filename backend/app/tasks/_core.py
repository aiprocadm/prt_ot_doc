"""Реализация Celery-задач и async/sync bridge (бывший монолит ``tasks.py``).

Публичный импорт остаётся ``import app.tasks`` — см. :mod:`app.tasks` (пакет).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, TypeVar
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.metrics import get_metrics
from app.core.tenant import tenant_context
from app.db import AsyncSessionLocal, ensure_tenant_schema, session_scope
from app.db.tenant_row_guard import (
    assert_tenant_row_matches_session as _assert_tenant_row_matches_session,
)
from app.models.document import (
    DocumentVersion,
)
from app.models.job_engine import (
    DocumentArtifact,
    DocumentJob,
    DocumentJobStatus,
    DocumentJobStep,
    JobStepStatus,
    OutboxEvent,
    OutboxEventStatus,
)
from app.models.models import (
    EdoMessage,
    EdoStatus,
    EdoStatusHistory,
    Inspection,
    Person,
    PPEIssue,
    RoleEnum,
    Tenant,
    TrainingPlan,
    User,
    WebhookDelivery,
    WebhookEndpoint,
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
from app.modules.headers.engine import apply_headers_to_docx
from app.modules.headers.repo import get_preset_by_code
from app.services.audit import AuditService
from app.services.celery_app import celery_app
from app.services.events import EventType
from app.services.file_storage import FileStorageService
from app.services.idempotency import cleanup_idempotency_keys
from app.services.notifications import send_notification
from app.services.obligations import process_task_reminders
from app.services.outbox import OutboxProcessor, OutboxService
from app.services.reminders import evaluate_due_date

# ARCH-4: shared helpers moved to app.tasks._shared; domain ticks to app.tasks.domain_ticks;
# document-generation tasks to app.tasks.document_jobs.
from app.tasks._shared import (  # noqa: E402
    DOCX_MIME,
    RETRYABLE_EXCEPTIONS,
    _resolve_task_tenant_scope,
    _run_coroutine,
)

# Importing document_jobs registers its tasks with Celery and re-exposes them as
# ``app.tasks.*``. noqa F401: re-export only (back-compat for app.tasks._core.X).
from app.tasks.document_jobs import (  # noqa: E402, F401
    _assert_batch_item_scope,
    _assert_pipeline_run_matches_session_tenant,
    _company_snapshot,
    _generate_document_for_run,
    _mark_batch_item_failed,
    _sha256_bytes,
    generate_document_batch_item_task,
    generate_document_task,
    register_template_task,
)

# Importing domain_ticks registers its tasks with Celery and re-exposes them as
# ``app.tasks.*`` (via app.tasks.__init__ __getattr__). noqa F401: re-export only.
from app.tasks.domain_ticks import (  # noqa: E402, F401
    _contractors_documents_tick,
    _contractors_readiness_tick,
    _medical_contingent_tick,
    _permits_expiry_tick,
    _ppe_expiry_tick,
    _prescriptions_escalate_tick,
    contractors_documents_tick,
    contractors_readiness_tick,
    medical_contingent_tick,
    permits_expiry_tick,
    ppe_expiry_tick,
    prescriptions_escalate_tick,
    workflow_sla_tick,
    workflow_timers_tick,
)

settings = get_settings()
logger = logging.getLogger(__name__)

T = TypeVar("T")


@celery_app.task(
    name="outbox.dispatch",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=settings.celery.retry_backoff_seconds,
    retry_backoff_max=settings.celery.retry_backoff_max_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.celery.task_max_retries},
)
def dispatch_outbox_task(tenant_slug: str) -> int:
    """Dispatch pending outbox entries for a tenant."""

    async def _run() -> int:
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                processor = OutboxProcessor(session)
                return await processor.process_once()

    metrics = get_metrics()
    queue = celery_app.conf.task_default_queue or "default"
    task_name = "outbox.dispatch"
    metrics.record_celery_enqueue(queue=queue, task=task_name)
    started = perf_counter()
    try:
        result = _run_coroutine(_run())
    except Exception as exc:  # pragma: no cover - surfaced by Celery in production
        duration = perf_counter() - started
        metrics.record_celery_execution(
            queue=queue,
            task=task_name,
            status="failed",
            seconds=duration,
            error_code=str(exc) or exc.__class__.__name__,
        )
        logger.exception("dispatch_outbox_task failed", exc_info=exc)
        raise

    duration = perf_counter() - started
    metrics.record_celery_execution(
        queue=queue,
        task=task_name,
        status="succeeded",
        seconds=duration,
    )
    return result


@celery_app.task(
    name="tasks.reminders.dispatch",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=settings.celery.retry_backoff_seconds,
    retry_backoff_max=settings.celery.retry_backoff_max_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.celery.task_max_retries},
)
def dispatch_task_reminders() -> int:
    """Process reminder notifications for all active tenants."""

    async def _run() -> int:
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
                    processed += await process_task_reminders(tenant_session)
        return processed

    metrics = get_metrics()
    queue = celery_app.conf.task_default_queue or "default"
    task_name = "tasks.reminders.dispatch"
    metrics.record_celery_enqueue(queue=queue, task=task_name)
    started = perf_counter()
    try:
        result = _run_coroutine(_run())
    except Exception as exc:  # pragma: no cover - surfaced by Celery in production
        duration = perf_counter() - started
        metrics.record_celery_execution(
            queue=queue,
            task=task_name,
            status="failed",
            seconds=duration,
            error_code=str(exc) or exc.__class__.__name__,
        )
        logger.exception("dispatch_task_reminders failed", exc_info=exc)
        raise

    duration = perf_counter() - started
    metrics.record_celery_execution(
        queue=queue,
        task=task_name,
        status="succeeded",
        seconds=duration,
    )
    return result


@celery_app.task(
    name="idempotency.cleanup",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=settings.celery.retry_backoff_seconds,
    retry_backoff_max=settings.celery.retry_backoff_max_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.celery.task_max_retries},
)
def cleanup_idempotency_keys_task() -> int:
    """Purge stale idempotency records according to the configured TTL."""

    async def _run() -> int:
        async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
            tenants = list(
                (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
                .scalars()
                .all()
            )
        total_removed = 0
        for tenant in tenants:
            with tenant_context(tenant.slug):
                ensure_tenant_schema(tenant.slug)
                async with session_scope(tenant=tenant.slug) as tenant_session:
                    total_removed += await cleanup_idempotency_keys(
                        session=tenant_session,
                        ttl_days=settings.idempotency_ttl_days,
                    )
        return total_removed

    metrics = get_metrics()
    queue = celery_app.conf.task_default_queue or "default"
    task_name = "idempotency.cleanup"
    metrics.record_celery_enqueue(queue=queue, task=task_name)
    started = perf_counter()
    try:
        result = _run_coroutine(_run())
    except Exception as exc:  # pragma: no cover - surfaced by Celery in production
        duration = perf_counter() - started
        metrics.record_celery_execution(
            queue=queue,
            task=task_name,
            status="failed",
            seconds=duration,
            error_code=str(exc) or exc.__class__.__name__,
        )
        logger.exception("cleanup_idempotency_keys_task failed", exc_info=exc)
        raise

    duration = perf_counter() - started
    metrics.record_celery_execution(
        queue=queue,
        task=task_name,
        status="succeeded",
        seconds=duration,
    )
    return result


@celery_app.task(name="dispatch_outbox_events")
def dispatch_outbox_events(max_attempts: int | None = None, tenant_slug: str = "test") -> int:
    return _run_coroutine(
        _dispatch_outbox_events(max_attempts=max_attempts, tenant_slug=tenant_slug)
    )


def _compute_outbox_backoff(attempts: int) -> timedelta:
    base = max(int(settings.outbox_retry_backoff_seconds), 1)
    cap = max(int(settings.outbox_retry_backoff_max_seconds), base)
    jitter = min(attempts, 5)
    seconds = min((2 ** max(attempts - 1, 0)) * base + jitter, cap)
    return timedelta(seconds=seconds)


async def _dispatch_outbox_events(
    *, max_attempts: int | None = None, tenant_slug: str = "test"
) -> int:
    import hmac
    import json

    import httpx

    processed = 0
    now = datetime.now(tz=timezone.utc)
    limit = int(max_attempts or settings.outbox_max_attempts)
    async with session_scope(tenant=tenant_slug) as session:
        tenant_id, tenant_scope = await _resolve_task_tenant_scope(session, tenant_slug)
        pending = (
            (
                await session.execute(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.status.in_(
                            [OutboxEventStatus.PENDING.value, OutboxEventStatus.FAILED.value]
                        ),
                        (OutboxEvent.next_attempt_at.is_(None))
                        | (OutboxEvent.next_attempt_at <= now),
                    )
                    .order_by(OutboxEvent.created_at.asc())
                    .with_for_update(skip_locked=True)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        for event in pending:
            event.status = OutboxEventStatus.PROCESSING.value
        await session.flush()

        endpoints = (
            (
                await session.execute(
                    select(WebhookEndpoint).where(
                        WebhookEndpoint.tenant_id.in_(tenant_scope),
                        WebhookEndpoint.is_enabled.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            for event in pending:
                event.attempts += 1
                correlation_id = str(
                    (event.headers or {}).get("correlation_id")
                    or (event.payload or {}).get("correlation_id")
                    or event.id
                )
                if event.event_type in {
                    "DocumentGenerated",
                    "DocumentExported",
                    "DocumentSigned",
                    "RiskAssessed",
                    "PPEIssued",
                    "TrainingCompleted",
                }:
                    actor_id = str((event.payload or {}).get("actor_id") or "")
                    if actor_id:
                        mapped = {
                            "DocumentGenerated": NotificationType.DOCUMENT_GENERATED,
                            "DocumentExported": NotificationType.DOCUMENT_EXPORTED,
                            "DocumentSigned": NotificationType.DOCUMENT_SIGNED,
                            "TrainingCompleted": NotificationType.TRAINING_COMPLETED,
                            "PPEIssued": NotificationType.PPE_ISSUE_CREATED,
                            "RiskAssessed": NotificationType.CA_DUE_SOON,
                        }[event.event_type]
                        await send_notification(
                            session,
                            tenant_id=tenant_id,
                            user_id=actor_id,
                            channel=NotificationChannel.INAPP,
                            type=mapped,
                            title=event.event_type,
                            body="Событие из outbox",
                            payload={
                                "event_id": event.event_id,
                                "entity_type": "outbox_event",
                                "entity_id": event.id,
                            },
                            dedup_key=f"outbox:{event.event_id}:inapp",
                        )
                body = {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "tenant_id": event.tenant_id,
                    "payload": event.payload,
                    "headers": event.headers or {},
                    "correlation_id": correlation_id,
                }
                raw_body = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(
                    "utf-8"
                )
                matching = [
                    ep
                    for ep in endpoints
                    if not ep.subscribed_events or event.event_type in (ep.subscribed_events or [])
                ]
                success = not bool((event.payload or {}).get("force_fail"))
                for ep in matching:
                    delivered = WebhookDelivery(
                        tenant_id=event.tenant_id,
                        endpoint_id=ep.id,
                        event_id=event.event_id,
                        status="processing",
                        attempts=event.attempts,
                        started_at=datetime.now(tz=timezone.utc),
                    )
                    session.add(delivered)
                    ts = str(int(datetime.now(tz=timezone.utc).timestamp()))
                    signature = hmac.new(
                        (ep.secret or "").encode("utf-8"),
                        f"{ts}.".encode("utf-8") + raw_body,
                        hashlib.sha256,
                    ).hexdigest()
                    headers = {
                        "Content-Type": "application/json",
                        "X-Event-Id": event.event_id,
                        "X-Event-Type": event.event_type,
                        "X-Tenant": event.tenant_id,
                        "X-Correlation-Id": correlation_id,
                        "X-Signature": f"v1={signature}",
                        "X-Signature-Ts": ts,
                    }
                    try:
                        resp = await client.post(
                            ep.url,
                            content=raw_body,
                            headers=headers,
                            timeout=max(ep.timeout_ms / 1000, 0.1),
                        )
                        delivered.status = "success" if 200 <= resp.status_code < 300 else "failed"
                        delivered.last_status_code = resp.status_code
                        delivered.last_response_body = (resp.text or "")[:1000]
                        delivered.ended_at = datetime.now(tz=timezone.utc)
                        delivered.delivered_at = (
                            delivered.ended_at if delivered.status == "success" else None
                        )
                        if delivered.status != "success":
                            success = False
                    except Exception as exc:
                        delivered.status = "failed"
                        delivered.last_error = {"message": str(exc)}
                        delivered.ended_at = datetime.now(tz=timezone.utc)
                        success = False
                if success:
                    event.status = OutboxEventStatus.SENT.value
                    event.sent_at = datetime.now(tz=timezone.utc)
                    event.next_attempt_at = None
                    event.last_error = None
                    processed += 1
                elif event.attempts >= limit:
                    event.status = OutboxEventStatus.POISONED.value
                    event.next_attempt_at = None
                    event.last_error = "poisoned_after_max_attempts"
                else:
                    event.status = OutboxEventStatus.FAILED.value
                    event.next_attempt_at = datetime.now(tz=timezone.utc) + _compute_outbox_backoff(
                        event.attempts
                    )
                    event.last_error = "delivery_failed_retry_scheduled"
        await session.flush()
    return processed


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
        if notification is None:
            return 0
        if notification.status != NotificationStatus.QUEUED:
            return 0
        try:
            if notification.channel == NotificationChannel.INAPP:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.now(tz=timezone.utc)
            elif notification.channel == NotificationChannel.EMAIL:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.now(tz=timezone.utc)
            else:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.now(tz=timezone.utc)
            notification.attempts += 1
        except Exception as exc:  # pragma: no cover
            notification.attempts += 1
            notification.status = NotificationStatus.FAILED
            notification.last_error = str(exc)
        await session.flush()
    return 1


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


@celery_app.task(name="process_inbound_webhook")
def process_inbound_webhook(*, source: str, tenant_slug: str, payload: dict[str, Any]) -> int:
    return _run_coroutine(
        _process_inbound_webhook(source=source, tenant_slug=tenant_slug, payload=payload)
    )


async def _process_inbound_webhook(
    *, source: str, tenant_slug: str, payload: dict[str, Any]
) -> int:
    # Легаси-ветка EdoEnvelope удалена (ed02): таблица edo_envelopes дропнута,
    # живой путь — только EdoMessage.
    async with session_scope(tenant=tenant_slug) as session:
        tenant_id = str(session.info.get("tenant_id") or "").strip() or tenant_slug
        tenant_scope = (tenant_id, tenant_slug) if tenant_id != tenant_slug else (tenant_id,)
        if source != "edo":
            return 0
        external_id = str(payload.get("external_id") or "")
        status_value = str(payload.get("status") or "").lower()
        if not external_id or not status_value:
            return 0

        status_map = {
            "queued": EdoStatus.QUEUED,
            "sent": EdoStatus.SENT,
            "delivered": EdoStatus.DELIVERED,
            "signed": EdoStatus.ACCEPTED,
            "rejected": EdoStatus.REJECTED,
            "failed": EdoStatus.FAILED,
            "accepted": EdoStatus.ACCEPTED,
        }
        message_target = status_map.get(status_value)
        if message_target is None:
            return 0

        message = (
            await session.execute(
                select(EdoMessage).where(
                    EdoMessage.tenant_id.in_(tenant_scope), EdoMessage.external_id == external_id
                )
            )
        ).scalar_one_or_none()
        if message is None:
            return 0

        if message.status == message_target:
            return 0
        message.status = message_target
        session.add(
            EdoStatusHistory(
                tenant_id=tenant_id,
                edo_message_id=message.id,
                status=message_target,
                raw_payload_json=payload,
            )
        )

        await AuditService(session).log_event(
            tenant_id=tenant_id,
            action="edo_status_update",
            object_type="EdoMessage",
            object_id=message.id,
            actor_type="service",
            ip="system",
            request_id=str(payload.get("correlation_id") or payload.get("event_id") or uuid4()),
            changed_fields=None,
            details={"source": source, "status": message_target.value, "external_id": external_id},
        )
        return 1


@celery_app.task(name="app.tasks.apply_headers_job")
def apply_headers_job(*, job_id: str, tenant_slug: str) -> dict[str, str]:
    async def _run() -> dict[str, str]:
        storage = FileStorageService.default()
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                job = await session.get(DocumentJob, job_id)
                if job is None:
                    raise ValueError("Job not found")
                _assert_tenant_row_matches_session(
                    session,
                    job,
                    mismatch_event="document_job.tenant_scope_mismatch",
                    not_found_message="Job not found",
                )
                step = (
                    await session.execute(
                        select(DocumentJobStep).where(
                            DocumentJobStep.job_id == job.id,
                            DocumentJobStep.step_code == "apply_headers",
                        )
                    )
                ).scalar_one()
                payload = step.input_ref or {}
                version = await session.get(DocumentVersion, payload.get("document_version_id"))
                if version is None:
                    raise ValueError("Document version not found")
                _assert_tenant_row_matches_session(
                    session,
                    version,
                    mismatch_event="document_version.tenant_scope_mismatch",
                    not_found_message="Document version not found",
                )
                preset = await get_preset_by_code(
                    session, tenant_id=str(job.tenant_id), code=str(payload.get("preset_code"))
                )
                if preset is None:
                    raise ValueError("Preset not found")

                job.status = DocumentJobStatus.RUNNING.value
                step.status = JobStepStatus.RUNNING.value
                step.started_at = datetime.now(tz=timezone.utc)
                await session.flush()

                source = storage.get(version.file_key)
                output, report = apply_headers_to_docx(
                    docx_bytes=source,
                    preset=preset,
                    context=payload.get("context") or {},
                    watermark_override=payload.get("watermark_override"),
                )
                new_key = f"{version.file_key.rsplit('.', 1)[0]}_with_headers.docx"
                storage.put(new_key, output, content_type=DOCX_MIME)

                max_version = await session.scalar(
                    select(DocumentVersion.version_number)
                    .where(DocumentVersion.document_id == version.document_id)
                    .order_by(DocumentVersion.version_number.desc())
                    .limit(1)
                )
                new_version = DocumentVersion(
                    tenant_id=version.tenant_id,
                    document_id=version.document_id,
                    snapshot_id=version.snapshot_id,
                    template_version=version.template_version,
                    data_json=version.data_json,
                    file_key=new_key,
                    file_id=None,
                    template_version_id=version.template_version_id,
                    version_number=int(max_version or 1) + 1,
                )
                session.add(new_version)
                await session.flush()
                session.add(
                    DocumentArtifact(
                        tenant_id=str(job.tenant_id),
                        job_id=job.id,
                        step_code="apply_headers",
                        kind="docx",
                        file_id=None,
                        sha256=hashlib.sha256(output).hexdigest(),
                        meta={"file_key": new_key},
                    )
                )

                step.status = JobStepStatus.SUCCESS.value
                step.ended_at = datetime.now(tz=timezone.utc)
                step.output_ref = {
                    "document_version_id": new_version.id,
                    "report": report.model_dump(),
                }
                job.status = DocumentJobStatus.SUCCESS.value
                job.result_document_version_id = new_version.id
                job.ended_at = datetime.now(tz=timezone.utc)
                await session.flush()
                return {"job_id": job.id, "document_version_id": new_version.id}

    return _run_coroutine(_run())


@celery_app.task(name="app.tasks.convert_pdf_job")
def convert_pdf_job(
    *,
    tenant_id: str,
    input_file_id: str,
    pdf_run_id: str,
    options: dict,
    correlation_id: str | None = None,
) -> dict[str, object]:
    async def _run() -> dict[str, object]:
        from datetime import datetime, timezone

        from sqlalchemy import select

        from app.models.file import File
        from app.modules.pdf.convert import (
            build_pdf_file,
            convert_docx_bytes,
            load_source_bytes,
            map_failure,
            persist_pdf,
        )
        from app.modules.pdf.models import PdfConversionRun, PdfRunStatus
        from app.modules.pdf.service_pool import LibreOfficePool

        timeout_s = int((options or {}).get("timeout_s") or 45)
        pool = LibreOfficePool(workers=4)
        attempts = 0
        last_error: Exception | None = None

        with tenant_context(tenant_id):
            ensure_tenant_schema(tenant_id)
            async with session_scope(tenant=tenant_id) as session:
                run = await session.get(PdfConversionRun, pdf_run_id)
                if run is None:
                    return {"status": "missing_run"}
                try:
                    _assert_tenant_row_matches_session(
                        session,
                        run,
                        mismatch_event="pdf_conversion_run.tenant_scope_mismatch",
                        not_found_message="missing_run",
                    )
                except ValueError:
                    return {"status": "missing_run"}
                run.status = PdfRunStatus.RUNNING.value
                run.started_at = datetime.now(timezone.utc)
                await session.flush()

            for _ in range(2):
                attempts += 1
                try:
                    async with session_scope(tenant=tenant_id) as session:
                        source = await session.get(File, input_file_id)
                        run = await session.get(PdfConversionRun, pdf_run_id)
                        if source is None or run is None:
                            return {"status": "missing_input"}
                        try:
                            _assert_tenant_row_matches_session(
                                session,
                                run,
                                mismatch_event="pdf_conversion_run.tenant_scope_mismatch",
                                not_found_message="missing_input",
                            )
                            _assert_tenant_row_matches_session(
                                session,
                                source,
                                mismatch_event="file.tenant_scope_mismatch",
                                not_found_message="missing_input",
                            )
                        except ValueError:
                            return {"status": "missing_input"}

                        source_bytes = load_source_bytes(source)
                        pdf_bytes, sha256_hex = convert_docx_bytes(
                            source_bytes=source_bytes, timeout_s=timeout_s, pool=pool
                        )

                        existing = (
                            await session.execute(
                                select(File).where(
                                    File.tenant_id == tenant_id,
                                    File.sha256 == sha256_hex,
                                    File.mime == "application/pdf",
                                )
                            )
                        ).scalar_one_or_none()

                        if existing is None:
                            tenant_prefix = str(source.storage_key).split("/", 1)[0]
                            key, _ = persist_pdf(
                                tenant_prefix=tenant_prefix,
                                source=source,
                                pdf_bytes=pdf_bytes,
                                sha256_hex=sha256_hex,
                            )
                            existing = build_pdf_file(
                                tenant_id=tenant_id,
                                key=key,
                                sha256_hex=sha256_hex,
                                size=len(pdf_bytes),
                            )
                            session.add(existing)
                            await session.flush()

                        run.output_file_id = existing.id
                        run.attempts = attempts
                        run.status = PdfRunStatus.SUCCESS.value
                        run.ended_at = datetime.now(timezone.utc)
                        run.error_code = None
                        run.error_payload = {}
                        await session.flush()
                        index_file_content_job.apply_async(
                            kwargs={"tenant_slug": tenant_id, "file_id": existing.id}, countdown=0
                        )
                        return {
                            "status": "success",
                            "output_file_id": existing.id,
                            "attempts": attempts,
                        }
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    logger.exception(
                        "pdf.convert.failed",
                        extra={"attempt": attempts, "correlation_id": correlation_id},
                    )

            async with session_scope(tenant=tenant_id) as session:
                run = await session.get(PdfConversionRun, pdf_run_id)
                if run is not None:
                    try:
                        _assert_tenant_row_matches_session(
                            session,
                            run,
                            mismatch_event="pdf_conversion_run.tenant_scope_mismatch",
                            not_found_message="missing_run",
                        )
                    except ValueError:
                        pass
                    else:
                        run.attempts = attempts
                        run.status = PdfRunStatus.FAILED.value
                        run.ended_at = datetime.now(timezone.utc)
                        run.error_code = (
                            map_failure(last_error) if last_error else "PDF_CONVERSION_FAILED"
                        )
                        run.error_payload = {"error": str(last_error)[:500]} if last_error else {}
                        await session.flush()
            return {"status": "failed", "attempts": attempts}

    return _run_coroutine(_run())


@celery_app.task(name="files.index_content", bind=True, max_retries=3, default_retry_delay=30)
def index_file_content_job(
    self, tenant_slug: str, version_id: str | None = None, file_id: str | None = None
):
    async def _run() -> dict[str, str]:
        from app.modules.files.service import index_file_record, index_file_version

        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                tenant_id = str(session.info.get("tenant_id") or "")
                if not tenant_id:
                    tenant = (
                        await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
                    ).scalar_one_or_none()
                    if tenant is None:
                        return {"status": "tenant_missing"}
                    tenant_id = str(tenant.id)
                if version_id:
                    await index_file_version(session, tenant_id=tenant_id, version_id=version_id)
                if file_id:
                    await index_file_record(session, tenant_id=tenant_id, file_id=file_id)
                await session.flush()
                outbox = OutboxService(session)
                await outbox.enqueue(
                    tenant_id=tenant_id,
                    event_type=EventType.EDO_STATUS_CHANGED.value,
                    payload={
                        "tenant_id": tenant_id,
                        "occurred_at": datetime.now(timezone.utc),
                        "metadata": {
                            "event": "FileIndexed",
                            "version_id": version_id,
                            "file_id": file_id,
                        },
                    },
                )
                return {"status": "ok", "version_id": version_id or "", "file_id": file_id or ""}

    try:
        return _run_coroutine(_run())
    except RETRYABLE_EXCEPTIONS as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="files.av_scan_file_job")
def av_scan_file_job(tenant_id: str, file_id: str) -> str:
    from app.modules.files.tasks import av_scan_file_job as _delegate

    return _delegate(tenant_id, file_id)


@celery_app.task(name="billing.recompute_active_workers")
def recompute_active_workers_job(tenant_slug: str) -> dict[str, int | str]:
    async def _run() -> dict[str, int | str]:
        from sqlalchemy import func

        from app.models.models import EmploymentStatus
        from app.services.billing import BillingService, current_period_yyyymm

        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                tenant_id = str(session.info.get("tenant_id") or "")
                if not tenant_id:
                    tenant = (
                        await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
                    ).scalar_one_or_none()
                    if tenant is None:
                        return {"status": "tenant_missing", "active_workers": 0}
                    tenant_id = str(tenant.id)

                active_workers = int(
                    (
                        await session.execute(
                            select(func.count(Person.id)).where(
                                Person.tenant_id == tenant_id,
                                Person.deleted_at.is_(None),
                                Person.employment_status == EmploymentStatus.ACTIVE,
                            )
                        )
                    ).scalar_one()
                    or 0
                )
                service = BillingService(session)
                usage = await service.ensure_usage_row(
                    tenant_id=tenant_id,
                    period_yyyymm=current_period_yyyymm(),
                )
                usage.active_workers = active_workers
                await session.flush()
                return {
                    "status": "ok",
                    "tenant_id": tenant_id,
                    "active_workers": active_workers,
                    "period_yyyymm": usage.period_yyyymm,
                }

    return _run_coroutine(_run())


@celery_app.task(name="approval_deadline_sweeper_job")
def approval_deadline_sweeper_job(tenant_slug: str | None = None) -> dict[str, str]:
    return {"status": "ok", "tenant_slug": tenant_slug or "*"}


@celery_app.task(name="escalation_scan_job")
def escalation_scan_job(tenant_slug: str | None = None) -> dict[str, str]:
    return approval_deadline_sweeper_job(tenant_slug=tenant_slug)


@celery_app.task(name="refresh_signature_status_job")
def refresh_signature_status_job(*, request_id: str, tenant_id: str) -> dict[str, str]:
    return {"status": "queued", "request_id": request_id, "tenant_id": tenant_id}


@celery_app.task(name="verify_signature_job")
def verify_signature_job(*, request_id: str, tenant_id: str) -> dict[str, str]:
    return {"status": "verifying", "request_id": request_id, "tenant_id": tenant_id}


@celery_app.task(name="refresh_edo_status_job")
def refresh_edo_status_job(*, message_id: str, tenant_id: str) -> dict[str, str]:
    return {"status": "queued", "message_id": message_id, "tenant_id": tenant_id}


@celery_app.task(name="process_edo_webhook_job")
def process_edo_webhook_job(*, inbox_id: str, tenant_id: str) -> dict[str, str]:
    return {"status": "processed", "inbox_id": inbox_id, "tenant_id": tenant_id}


@celery_app.task(name="generate_edo_protocol_job")
def generate_edo_protocol_job(*, message_id: str, tenant_id: str) -> dict[str, str]:
    return {"status": "queued", "message_id": message_id, "tenant_id": tenant_id}


@celery_app.task(name="webhook_dispatch_job")
def webhook_dispatch_job(limit: int = 50, tenant_slug: str = "test") -> dict[str, int]:
    dispatched = dispatch_outbox_events(tenant_slug=tenant_slug)
    return {"dispatched": int(dispatched), "limit": int(limit)}
