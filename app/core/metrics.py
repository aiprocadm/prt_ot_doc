"""Prometheus metrics helpers for the document pipeline."""

from __future__ import annotations

import inspect
import logging
import math
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Any, Final, Iterable, Tuple

import redis.asyncio as redis_async
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

if TYPE_CHECKING:
    from app.core.config import Settings

__all__ = [
    "Metrics",
    "get_metrics",
    "reset_metrics",
    "render_metrics",
    "sanitize_label",
]


@dataclass(slots=True)
class Metrics:
    """Container for Prometheus collectors used by the service."""

    registry: CollectorRegistry
    pipeline_runs_total: Counter
    pipeline_stage_total: Counter
    pipeline_stage_duration_seconds: Histogram
    pipeline_pdf_duration_seconds: Histogram
    pdf_libreoffice_duration_seconds: Histogram
    pdf_libreoffice_attempts_total: Counter
    pipeline_errors_total: Counter
    celery_tasks_enqueued_total: Counter
    celery_task_duration_seconds: Histogram
    celery_tasks_in_progress: Gauge
    celery_queue_depth: Gauge
    celery_task_latency_p95_seconds: Gauge
    http_requests_total: Counter
    http_request_latency_seconds: Histogram
    http_request_latency_p95_seconds: Gauge
    http_request_errors_total: Counter
    outbox_enqueued_total: Counter
    outbox_routed_total: Counter
    outbox_no_destination_total: Counter
    _http_latency_tracker: "LatencyTracker" = field(
        default_factory=lambda: LatencyTracker(), repr=False
    )
    _celery_latency_tracker: "PercentileTracker" = field(
        default_factory=lambda: PercentileTracker(), repr=False
    )

    def observe_pipeline_run(self, *, template_id: str, status: str) -> None:
        self.pipeline_runs_total.labels(template_id=template_id, status=status).inc()

    def observe_pipeline_stage(self, *, stage: str, status: str, seconds: float) -> None:
        safe_seconds = seconds if seconds >= 0 else 0.0
        normalized_stage = sanitize_label(stage)
        normalized_status = sanitize_label(status)
        self.pipeline_stage_total.labels(stage=normalized_stage, status=normalized_status).inc()
        self.pipeline_stage_duration_seconds.labels(
            stage=normalized_stage, status=normalized_status
        ).observe(safe_seconds)

    def observe_pdf_duration(self, *, template_id: str, seconds: float) -> None:
        if seconds < 0:
            seconds = 0.0
        self.pipeline_pdf_duration_seconds.labels(template_id=template_id).observe(seconds)

    def observe_pdf_libreoffice(self, *, seconds: float, status: str) -> None:
        normalized_status = sanitize_label(status)
        safe_seconds = seconds if seconds >= 0 else 0.0
        self.pdf_libreoffice_duration_seconds.labels(status=normalized_status).observe(
            safe_seconds
        )
        self.pdf_libreoffice_attempts_total.labels(status=normalized_status).inc()

    def record_error(self, *, code: str) -> None:
        normalized = sanitize_label(code)
        self.pipeline_errors_total.labels(code=normalized).inc()

    def record_celery_enqueue(self, *, queue: str, task: str) -> None:
        self.celery_tasks_enqueued_total.labels(queue=queue, task=task).inc()
        self.celery_tasks_in_progress.labels(queue=queue, task=task).inc()

    def record_celery_execution(
        self,
        *,
        queue: str,
        task: str,
        status: str,
        seconds: float,
        error_code: str | None = None,
    ) -> None:
        if seconds < 0:
            seconds = 0.0
        self.celery_task_duration_seconds.labels(queue=queue, task=task, status=status).observe(seconds)
        self.celery_tasks_in_progress.labels(queue=queue, task=task).dec()
        if error_code:
            self.record_error(code=error_code)
        percentile = self._celery_latency_tracker.observe(
            key=(queue, task, status), value=seconds
        )
        self.celery_task_latency_p95_seconds.labels(
            queue=queue, task=task, status=status
        ).set(percentile)

    def set_celery_queue_depth(self, *, queue: str, depth: int) -> None:
        safe_depth = depth if depth >= 0 else 0
        self.celery_queue_depth.labels(queue=queue).set(safe_depth)

    def observe_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        method_label = method.upper()
        path_label = path or "/"
        duration = duration_seconds if duration_seconds >= 0 else 0.0
        status_label = str(status_code)
        self.http_requests_total.labels(
            method=method_label, path=path_label, status=status_label
        ).inc()
        self.http_request_latency_seconds.labels(
            method=method_label, path=path_label
        ).observe(duration)
        p95 = self._http_latency_tracker.observe(
            method=method_label, path=path_label, duration=duration
        )
        self.http_request_latency_p95_seconds.labels(
            method=method_label, path=path_label
        ).set(p95)
        if status_code >= 400:
            family = f"{status_code // 100}xx"
            self.http_request_errors_total.labels(
                method=method_label, path=path_label, status=family
            ).inc()

    def record_outbox_enqueued(
        self, *, event_type: str, destination: str, tenant_id: str
    ) -> None:
        self.outbox_enqueued_total.labels(
            event_type=sanitize_label(event_type),
            destination=sanitize_label(destination),
            tenant=tenant_id,
        ).inc()

    def record_outbox_sent(self, *, event_type: str, destination: str) -> None:
        self.outbox_sent_total.labels(
            event_type=sanitize_label(event_type),
            destination=sanitize_label(destination),
        ).inc()

    def record_outbox_failed(
        self,
        *,
        event_type: str,
        destination: str,
        error_class: str,
    ) -> None:
        self.outbox_failed_total.labels(
            event_type=sanitize_label(event_type),
            destination=sanitize_label(destination),
            error_class=sanitize_label(error_class),
        ).inc()

    def record_outbox_dead(self, *, event_type: str, destination: str) -> None:
        self.outbox_dead_total.labels(
            event_type=sanitize_label(event_type),
            destination=sanitize_label(destination),
        ).inc()

    def observe_outbox_attempts(
        self, *, event_type: str, destination: str, attempts: int
    ) -> None:
        safe_attempts = attempts if attempts >= 0 else 0
        self.outbox_attempts_histogram.labels(
            event_type=sanitize_label(event_type),
            destination=sanitize_label(destination),
        ).observe(safe_attempts)

    def observe_outbox_dispatch_latency(
        self, *, event_type: str, destination: str, seconds: float
    ) -> None:
        safe_seconds = seconds if seconds >= 0 else 0.0
        self.outbox_dispatch_latency_seconds.labels(
            event_type=sanitize_label(event_type),
            destination=sanitize_label(destination),
        ).observe(safe_seconds)

    def record_outbox_dispatcher_tick(self, *, processed: int) -> None:
        _ = processed
        self.outbox_dispatcher_tick_total.inc()

    def observe_outbox_dispatcher_duration(self, *, seconds: float) -> None:
        safe_seconds = seconds if seconds >= 0 else 0.0
        self.outbox_dispatcher_loop_duration_seconds.observe(safe_seconds)

    def record_outbox_routed(self, *, event_type: str, destination: str) -> None:
        self.outbox_routed_total.labels(
            event_type=sanitize_label(event_type),
            destination=sanitize_label(destination),
        ).inc()

    def record_outbox_no_destination(self, *, event_type: str) -> None:
        self.outbox_no_destination_total.labels(
            event_type=sanitize_label(event_type)
        ).inc()


_METRICS: Metrics | None = None


def _build_metrics() -> Metrics:
    registry = CollectorRegistry()

    pipeline_runs_total = Counter(
        "pipeline_runs_total",
        "Total pipeline runs grouped by template and status.",
        labelnames=("template_id", "status"),
        registry=registry,
    )
    pipeline_stage_total = Counter(
        "pipeline_stage_total",
        "Pipeline stage executions grouped by stage and status.",
        labelnames=("stage", "status"),
        registry=registry,
    )
    pipeline_stage_duration_seconds = Histogram(
        "pipeline_stage_duration_seconds",
        "Pipeline stage duration in seconds grouped by stage and status.",
        labelnames=("stage", "status"),
        registry=registry,
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
    )
    pipeline_pdf_duration_seconds = Histogram(
        "pipeline_pdf_duration_seconds",
        "PDF conversion duration in seconds by template.",
        labelnames=("template_id",),
        registry=registry,
        buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
    )
    pdf_libreoffice_duration_seconds = Histogram(
        "pipeline_pdf_libreoffice_duration_seconds",
        "Duration of LibreOffice PDF conversion subprocess attempts by outcome.",
        labelnames=("status",),
        registry=registry,
        buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
    )
    pdf_libreoffice_attempts_total = Counter(
        "pipeline_pdf_libreoffice_attempts_total",
        "LibreOffice subprocess attempts grouped by sanitized outcome code.",
        labelnames=("status",),
        registry=registry,
    )
    pipeline_errors_total = Counter(
        "pipeline_errors_total",
        "Pipeline error occurrences grouped by sanitized error code.",
        labelnames=("code",),
        registry=registry,
    )
    celery_tasks_enqueued_total = Counter(
        "celery_tasks_enqueued_total",
        "Celery tasks observed by queue and task name.",
        labelnames=("queue", "task"),
        registry=registry,
    )
    celery_task_duration_seconds = Histogram(
        "celery_task_duration_seconds",
        "Celery task execution duration grouped by queue, task and status.",
        labelnames=("queue", "task", "status"),
        registry=registry,
        buckets=(0.05, 0.1, 0.5, 1, 2, 5, 10, 30),
    )
    celery_tasks_in_progress = Gauge(
        "celery_tasks_in_progress",
        "Number of Celery tasks currently executing by queue and task.",
        labelnames=("queue", "task"),
        registry=registry,
    )
    celery_queue_depth = Gauge(
        "celery_queue_depth",
        "Approximate Redis-backed Celery queue depth by queue name.",
        labelnames=("queue",),
        registry=registry,
    )

    celery_task_latency_p95_seconds = Gauge(
        "celery_task_latency_p95_seconds",
        "Rolling p95 duration estimate for Celery tasks by queue, task and status.",
        labelnames=("queue", "task", "status"),
        registry=registry,
    )

    http_requests_total = Counter(
        "http_requests_total",
        "Total HTTP requests handled by method, path and status.",
        labelnames=("method", "path", "status"),
        registry=registry,
    )
    http_request_latency_seconds = Histogram(
        "http_request_latency_seconds",
        "Observed HTTP request latency in seconds by method and path.",
        labelnames=("method", "path"),
        registry=registry,
        buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
    )
    http_request_latency_p95_seconds = Gauge(
        "http_request_latency_p95_seconds",
        "Rolling p95 latency estimate for HTTP requests by method and path.",
        labelnames=("method", "path"),
        registry=registry,
    )
    http_request_errors_total = Counter(
        "http_request_errors_total",
        "HTTP request errors grouped by method, path and status family.",
        labelnames=("method", "path", "status"),
        registry=registry,
    )
    outbox_enqueued_total = Counter(
        "outbox_enqueued_total",
        "Total outbox events enqueued grouped by event type, destination, and tenant.",
        labelnames=("event_type", "destination", "tenant"),
        registry=registry,
    )
    outbox_sent_total = Counter(
        "outbox_sent_total",
        "Total outbox events sent grouped by event type and destination.",
        labelnames=("event_type", "destination"),
        registry=registry,
    )
    outbox_failed_total = Counter(
        "outbox_failed_total",
        "Total outbox events that failed grouped by event type, destination, and error class.",
        labelnames=("event_type", "destination", "error_class"),
        registry=registry,
    )
    outbox_dead_total = Counter(
        "outbox_dead_total",
        "Total outbox events moved to dead-letter grouped by event type and destination.",
        labelnames=("event_type", "destination"),
        registry=registry,
    )
    outbox_attempts_histogram = Histogram(
        "outbox_attempts_histogram",
        "Observed outbox attempt counts grouped by event type and destination.",
        labelnames=("event_type", "destination"),
        registry=registry,
        buckets=(1, 2, 3, 5, 8, 13, 21),
    )
    outbox_dispatch_latency_seconds = Histogram(
        "outbox_dispatch_latency_seconds",
        "Outbox dispatch latency from enqueue to sent grouped by event type and destination.",
        labelnames=("event_type", "destination"),
        registry=registry,
        buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 300, 600),
    )
    outbox_dispatcher_tick_total = Counter(
        "dispatcher_tick_total",
        "Total dispatcher ticks.",
        registry=registry,
    )
    outbox_dispatcher_loop_duration_seconds = Histogram(
        "dispatcher_loop_duration_seconds",
        "Dispatcher loop duration in seconds.",
        registry=registry,
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
    )
    outbox_routed_total = Counter(
        "outbox_routed_total",
        "Total outbox events routed grouped by event type and destination.",
        labelnames=("event_type", "destination"),
        registry=registry,
    )
    outbox_no_destination_total = Counter(
        "outbox_no_destination_total",
        "Total outbox events without a destination grouped by event type.",
        labelnames=("event_type",),
        registry=registry,
    )

    return Metrics(
        registry=registry,
        pipeline_runs_total=pipeline_runs_total,
        pipeline_stage_total=pipeline_stage_total,
        pipeline_stage_duration_seconds=pipeline_stage_duration_seconds,
        pipeline_pdf_duration_seconds=pipeline_pdf_duration_seconds,
        pdf_libreoffice_duration_seconds=pdf_libreoffice_duration_seconds,
        pdf_libreoffice_attempts_total=pdf_libreoffice_attempts_total,
        pipeline_errors_total=pipeline_errors_total,
        celery_tasks_enqueued_total=celery_tasks_enqueued_total,
        celery_task_duration_seconds=celery_task_duration_seconds,
        celery_tasks_in_progress=celery_tasks_in_progress,
        celery_queue_depth=celery_queue_depth,
        celery_task_latency_p95_seconds=celery_task_latency_p95_seconds,
        http_requests_total=http_requests_total,
        http_request_latency_seconds=http_request_latency_seconds,
        http_request_latency_p95_seconds=http_request_latency_p95_seconds,
        http_request_errors_total=http_request_errors_total,
        outbox_enqueued_total=outbox_enqueued_total,
        outbox_sent_total=outbox_sent_total,
        outbox_failed_total=outbox_failed_total,
        outbox_dead_total=outbox_dead_total,
        outbox_attempts_histogram=outbox_attempts_histogram,
        outbox_dispatch_latency_seconds=outbox_dispatch_latency_seconds,
        outbox_dispatcher_tick_total=outbox_dispatcher_tick_total,
        outbox_dispatcher_loop_duration_seconds=outbox_dispatcher_loop_duration_seconds,
        outbox_routed_total=outbox_routed_total,
        outbox_no_destination_total=outbox_no_destination_total,
    )


def get_metrics() -> Metrics:
    global _METRICS
    if _METRICS is None:
        _METRICS = _build_metrics()
    return _METRICS


def reset_metrics() -> Metrics:
    global _METRICS
    _METRICS = _build_metrics()
    return _METRICS


async def render_metrics(
    *,
    settings: "Settings" | None = None,
    redis_client: Any | None = None,
) -> tuple[bytes, str]:
    metrics = get_metrics()
    if settings is not None:
        await _refresh_celery_queue_depth(metrics, settings, redis_client=redis_client)
    return generate_latest(metrics.registry), CONTENT_TYPE_LATEST


_SANITIZE_ALLOWED: Final[set[str]] = {"_"}


class PercentileTracker:
    """Approximate percentile tracker for streaming numeric observations."""

    def __init__(
        self,
        *,
        max_samples: int = 200,
        percentile: float = 0.95,
    ) -> None:
        if not 0 < percentile <= 1:
            raise ValueError("percentile must be in the (0, 1] range")
        self._max_samples = max_samples
        self._percentile = percentile
        self._samples: dict[Tuple[str, ...], deque[float]] = {}
        self._lock = Lock()

    def observe(self, *, key: Tuple[str, ...], value: float) -> float:
        normalized = value if value >= 0 else 0.0
        with self._lock:
            bucket = self._samples.get(key)
            if bucket is None:
                bucket = deque(maxlen=self._max_samples)
                self._samples[key] = bucket
            bucket.append(normalized)
            snapshot = list(bucket)

        if not snapshot:
            return normalized

        snapshot.sort()
        index = max(math.ceil(self._percentile * len(snapshot)) - 1, 0)
        return snapshot[index]


class LatencyTracker(PercentileTracker):
    """HTTP-specific helper that stores samples by method and path."""

    def __init__(self, *, max_samples: int = 200) -> None:
        super().__init__(max_samples=max_samples, percentile=0.95)

    def observe(self, *, method: str, path: str, duration: float) -> float:  # type: ignore[override]
        return super().observe(key=(method, path), value=duration)


def sanitize_label(value: str) -> str:
    """Normalize label values for Prometheus metrics."""

    normalized = value.strip().lower()
    if not normalized:
        return "unknown_error"
    cleaned = []
    for char in normalized:
        if char.isalnum() or char in _SANITIZE_ALLOWED:
            cleaned.append(char)
        else:
            cleaned.append("_")
    collapsed = "".join(cleaned)
    while "__" in collapsed:
        collapsed = collapsed.replace("__", "_")
    collapsed = collapsed.strip("_")
    return collapsed or "unknown_error"


logger = logging.getLogger(__name__)


async def _refresh_celery_queue_depth(
    metrics: Metrics,
    settings: Settings,
    *,
    redis_client: Any | None,
) -> None:
    queues: Iterable[str] = settings.celery.worker_queues or ("default",)
    client = redis_client
    should_close = False

    if client is None:
        client = redis_async.from_url(settings.redis.broker_url)
        should_close = True

    try:
        for queue in queues:
            depth = await _read_queue_depth(client, queue)
            if depth is None:
                metrics.set_celery_queue_depth(queue=queue, depth=0)
                continue
            metrics.set_celery_queue_depth(queue=queue, depth=depth)
    except Exception:  # pragma: no cover - defensive guard
        logger.exception("metrics.celery.queue_depth_refresh_failed")
    finally:
        if should_close and client is not None:
            close = getattr(client, "close", None)
            if close is not None:
                try:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
                except Exception:  # pragma: no cover - defensive cleanup
                    logger.debug("metrics.celery.queue_depth_close_failed")


async def _read_queue_depth(client: Any, queue: str) -> int | None:
    length_getter = getattr(client, "llen", None)
    if length_getter is None:
        return None

    try:
        result = length_getter(queue)
        if inspect.isawaitable(result):
            result = await result
        depth = int(result)
    except Exception:  # pragma: no cover - defensive guard
        logger.debug(
            "metrics.celery.queue_depth_read_failed",
            extra={"queue": queue},
        )
        return None

    return depth if depth >= 0 else 0
