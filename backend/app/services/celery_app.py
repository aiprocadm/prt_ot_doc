from __future__ import annotations

import contextvars
import logging
from typing import Optional

from celery import Celery, signals
from celery.schedules import crontab
from kombu import Queue

from app.core.config import get_settings
from app.core.correlation_id import CorrelationIDManager
from app.core.task_context import reset_task_id, set_task_id
from app.core.tracing import reset_trace_id, set_trace_id

settings = get_settings()

logger = logging.getLogger(__name__)


def tenant_queue_name(tenant_id: str) -> str:
    return f"tenant.{tenant_id}"


celery_app = Celery(
    settings.app_name,
    broker=settings.redis.broker_url,
    backend=settings.redis.result_url,
)
default_queue = settings.celery.worker_queues[0] if settings.celery.worker_queues else "default"
pdf_queue = settings.celery.pdf_queue

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_max_tasks_per_child=settings.celery_worker_max_tasks_per_child,
    # SEC-64: порог в КИЛОБАЙТАХ (так его понимает Celery), настройка — в мегабайтах.
    # 0 = без ограничения, поэтому отрицательные/нулевые значения не превращаем в
    # «перезапускать после каждой задачи».
    worker_max_memory_per_child=(
        settings.celery_worker_max_memory_mb * 1024
        if settings.celery_worker_max_memory_mb > 0
        else 0
    ),
    task_always_eager=settings.celery_eager,
    task_eager_propagates=settings.celery_eager,
    broker_transport_options={"visibility_timeout": max(settings.celery.task_time_limit * 2, 600)},
    beat_scheduler="celery.beat:PersistentScheduler",
    task_default_queue=default_queue,
    task_default_exchange="app.tasks",
    task_default_routing_key=default_queue,
    task_soft_time_limit=settings.celery.task_soft_time_limit,
    task_time_limit=settings.celery.task_time_limit,
)

celery_app.conf.beat_schedule = {
    "tasks-reminders-daily": {
        "task": "tasks.reminders.dispatch",
        "schedule": crontab(hour=2, minute=0),
    },
    "reminders-scan-hourly": {
        "task": "reminders.scan",
        "schedule": crontab(minute=0),
    },
    "notifications-dispatch-pending": {
        "task": "notifications.dispatch_pending",
        "schedule": crontab(minute="*/5"),
    },
    "prescriptions-escalate-daily": {
        "task": "prescriptions.escalate.tick",
        "schedule": crontab(hour=2, minute=0),
    },
    "medical-contingent-daily": {
        "task": "medical.contingent.tick",
        "schedule": crontab(hour=3, minute=0),
    },
    "contractors-readiness-daily": {
        "task": "contractors.readiness.tick",
        "schedule": crontab(hour=3, minute=30),
    },
    "contractors-documents-daily": {
        "task": "contractors.documents.tick",
        "schedule": crontab(hour=3, minute=45),
    },
    "ppe-expiry-daily": {
        "task": "ppe.expiry.tick",
        "schedule": crontab(hour=4, minute=15),
    },
    "permits-expiry-daily": {
        "task": "permits.expiry.tick",
        "schedule": crontab(hour=4, minute=30),
    },
}

if settings.outbox_dispatch_schedule_enabled:
    # SEC-65 fan-out. Opt-in (OUTBOX_DISPATCH_SCHEDULE_ENABLED): nothing scheduled an
    # outbox drain before, so an existing deployment may hold a backlog that the first
    # tick would flush to subscriber endpoints all at once. Enable deliberately, after
    # checking the pending counts.
    _outbox_every = max(int(settings.outbox_dispatch_schedule_minutes), 1)
    celery_app.conf.beat_schedule["outbox-dispatch-all"] = {
        "task": "outbox.dispatch_all",
        "schedule": crontab(minute=f"*/{_outbox_every}") if _outbox_every < 60 else crontab(minute=0),
    }

celery_app.conf.task_queues = (
    Queue(default_queue, routing_key=default_queue),
    Queue(pdf_queue, routing_key=pdf_queue),
)


def route_task_by_tenant(name, args, kwargs, options, task=None, **kw):
    tenant_id = None
    if isinstance(kwargs, dict):
        tenant_id = kwargs.get("tenant_id") or kwargs.get("tenant_slug")
    headers = options.get("headers") if isinstance(options, dict) else None
    if not tenant_id and isinstance(headers, dict):
        tenant_id = headers.get("tenant_id")

    has_tenant_scope = bool(tenant_id)
    if tenant_id:
        queue = tenant_queue_name(str(tenant_id))
        registered = celery_app.conf.task_queues
        known_names: set[str] = set()
        for q in registered or ():
            qname = getattr(q, "name", None)
            if qname:
                known_names.add(str(qname))
        if queue in known_names:
            return {"queue": queue, "routing_key": queue}
        logger.info(
            "celery.route.tenant_queue_fallback",
            extra={
                "task": name,
                "computed_queue": queue,
                "reason": "queue_not_in_task_queues",
            },
        )

    if name in {"pipeline.run", "documents.generate"} and not has_tenant_scope:
        raise ValueError("missing_tenant")
    return None


celery_app.conf.task_routes = (
    route_task_by_tenant,
    {
        "app.tasks.*": {"queue": default_queue},
        "worker.tasks.*": {"queue": default_queue},
    },
)


_TASK_CONTEXT_TOKENS: dict[
    str,
    tuple[
        contextvars.Token[Optional[str]],
        contextvars.Token[str],
        contextvars.Token[Optional[str]],
    ],
] = {}


@signals.task_prerun.connect
def _on_task_prerun(
    sender=None,
    task_id: Optional[str] = None,
    task=None,
    **kwargs,
) -> None:
    if not task_id:
        return

    try:
        task_token = set_task_id(task_id)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("celery.context.set_task_id_failed", extra={"task_id": task_id})
        task_token = set_task_id(None)

    trace_header_value: Optional[str] = None
    correlation_header_value: Optional[str] = None
    request = getattr(task, "request", None)
    if request is not None:
        headers = getattr(request, "headers", None)
        if isinstance(headers, dict):
            trace_header_value = headers.get("trace_id") or headers.get("X-Trace-Id")
            correlation_header_value = (
                headers.get("correlation_id")
                or headers.get("x-correlation-id")
                or headers.get("X-Correlation-Id")
                or headers.get("x-request-id")
                or headers.get("X-Request-Id")
            )

    trace_identifier = (
        trace_header_value or correlation_header_value or task_id
    ).strip() or task_id
    trace_token = set_trace_id(trace_identifier)
    correlation_token = CorrelationIDManager.set(
        (correlation_header_value or trace_identifier).strip() or trace_identifier
    )
    _TASK_CONTEXT_TOKENS[task_id] = (task_token, trace_token, correlation_token)


@signals.task_postrun.connect
def _on_task_postrun(
    sender=None,
    task_id: Optional[str] = None,
    **kwargs,
) -> None:
    if not task_id:
        return

    tokens = _TASK_CONTEXT_TOKENS.pop(task_id, None)
    if not tokens:
        return

    task_token, trace_token, correlation_token = tokens
    try:
        reset_task_id(task_token)
    except LookupError:  # pragma: no cover - defensive cleanup
        logger.debug("celery.context.reset_task_id_missing", extra={"task_id": task_id})

    try:
        reset_trace_id(trace_token)
    except LookupError:  # pragma: no cover - defensive cleanup
        logger.debug("celery.context.reset_trace_id_missing", extra={"task_id": task_id})

    try:
        CorrelationIDManager.reset(correlation_token)
    except LookupError:  # pragma: no cover - defensive cleanup
        logger.debug("celery.context.reset_correlation_id_missing", extra={"task_id": task_id})


@signals.worker_ready.connect
def _verify_rls_runtime_role(**_kwargs) -> None:
    """SEC-65: refuse to process tasks under a role that bypasses row security.

    Celery workers hold the same tenant-isolation obligations as the API: a
    ``SUPERUSER``/``BYPASSRLS`` role makes all 264 policies inert. Mirrors the
    check in the API lifespan (``app.api.app``).
    """

    import asyncio

    from app.db.rls_runtime import UnsafeDatabaseRoleError, verify_runtime_role_for_url

    try:
        asyncio.run(
            verify_runtime_role_for_url(
                settings.database_url,
                enforce=settings.rls_enforce_unprivileged_db_role,
                component="celery-worker",
            )
        )
    except UnsafeDatabaseRoleError:
        logger.exception("celery.startup.unsafe-db-role")
        raise
    except Exception:  # pragma: no cover - probe must never mask worker startup
        logger.warning("celery.startup.db-role-probe-failed", exc_info=True)
