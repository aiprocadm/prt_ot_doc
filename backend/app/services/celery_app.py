from __future__ import annotations

import contextvars
import logging
from typing import Optional

from celery import Celery, signals
from celery.schedules import crontab
from kombu import Queue

from app.core.config import get_settings
from app.core.task_context import reset_task_id, set_task_id
from app.core.tracing import reset_trace_id, set_trace_id

settings = get_settings()

logger = logging.getLogger(__name__)

celery_app = Celery(
    settings.app_name,
    broker=settings.redis.broker_url,
    backend=settings.redis.result_url,
)
default_queue = (
    settings.celery.worker_queues[0]
    if settings.celery.worker_queues
    else "default"
)
pdf_queue = settings.celery.pdf_queue

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_max_tasks_per_child=100,
    broker_transport_options={
        "visibility_timeout": max(settings.celery.task_time_limit * 2, 600)
    },
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
    }
}

celery_app.conf.task_queues = (
    Queue(default_queue, routing_key=default_queue),
    Queue(pdf_queue, routing_key=pdf_queue),
)

celery_app.conf.task_routes = {
    "app.tasks.*": {"queue": default_queue},
    "worker.tasks.*": {"queue": default_queue},
    "pipeline.run": {"queue": pdf_queue},
    "documents.generate": {"queue": pdf_queue},
}


_TASK_CONTEXT_TOKENS: dict[str, tuple[contextvars.Token[Optional[str]], contextvars.Token[str]]] = {}


@signals.task_prerun.connect
def _on_task_prerun(  # type: ignore[misc]
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
    request = getattr(task, "request", None)
    if request is not None:
        headers = getattr(request, "headers", None)
        if isinstance(headers, dict):
            trace_header_value = headers.get("trace_id") or headers.get("X-Trace-Id")

    trace_identifier = (trace_header_value or task_id).strip() or task_id
    trace_token = set_trace_id(trace_identifier)
    _TASK_CONTEXT_TOKENS[task_id] = (task_token, trace_token)


@signals.task_postrun.connect
def _on_task_postrun(  # type: ignore[misc]
    sender=None,
    task_id: Optional[str] = None,
    **kwargs,
) -> None:
    if not task_id:
        return

    tokens = _TASK_CONTEXT_TOKENS.pop(task_id, None)
    if not tokens:
        return

    task_token, trace_token = tokens
    try:
        reset_task_id(task_token)
    except LookupError:  # pragma: no cover - defensive cleanup
        logger.debug("celery.context.reset_task_id_missing", extra={"task_id": task_id})

    try:
        reset_trace_id(trace_token)
    except LookupError:  # pragma: no cover - defensive cleanup
        logger.debug("celery.context.reset_trace_id_missing", extra={"task_id": task_id})
