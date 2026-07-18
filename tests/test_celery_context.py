from __future__ import annotations

from types import SimpleNamespace

from app.core.correlation_id import CorrelationIDManager
from app.core.task_context import get_task_id
from app.core.tracing import get_trace_id
from app.services.celery_app import _on_task_postrun, _on_task_prerun


def test_celery_task_prerun_uses_correlation_header_and_cleans_up() -> None:
    CorrelationIDManager.clear()
    fake_task = SimpleNamespace(
        request=SimpleNamespace(
            headers={
                "X-Correlation-Id": "corr-123",
            }
        )
    )

    _on_task_prerun(task_id="task-123", task=fake_task)

    assert get_task_id() == "task-123"
    assert get_trace_id() == "corr-123"
    assert CorrelationIDManager.get() == "corr-123"

    _on_task_postrun(task_id="task-123")

    assert get_task_id() is None
    assert get_trace_id() == "unknown"
    assert CorrelationIDManager.get() is None


def test_celery_task_prerun_prefers_trace_header_when_present() -> None:
    CorrelationIDManager.clear()
    fake_task = SimpleNamespace(
        request=SimpleNamespace(
            headers={
                "X-Trace-Id": "trace-123",
                "X-Correlation-Id": "corr-456",
            }
        )
    )

    _on_task_prerun(task_id="task-456", task=fake_task)

    assert get_trace_id() == "trace-123"
    assert CorrelationIDManager.get() == "corr-456"

    _on_task_postrun(task_id="task-456")
