from __future__ import annotations

import pytest

from app.core import metrics as metrics_module


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    metrics_module.reset_metrics()
    yield
    metrics_module.reset_metrics()


def test_sanitize_label_normalizes_values() -> None:
    assert metrics_module.sanitize_label("  SOME-Error ") == "some_error"
    assert metrics_module.sanitize_label(" ") == "unknown_error"
    assert metrics_module.sanitize_label("bad@@value!!") == "bad_value"


def test_metrics_recording_pipeline_and_errors() -> None:
    metrics = metrics_module.get_metrics()
    metrics.observe_pipeline_run(template_id="tpl", status="success")
    metrics.observe_pipeline_run(template_id="tpl", status="failure")
    metrics.observe_pdf_duration(template_id="tpl", seconds=-1)
    metrics.observe_pdf_libreoffice(seconds=-5, status=" Timeout ")
    metrics.record_error(code="ValueError")

    samples = metrics.pipeline_runs_total.collect()[0].samples
    assert {sample.labels["status"] for sample in samples} == {"success", "failure"}

    histogram = metrics.pipeline_pdf_duration_seconds.collect()[0]
    sum_sample = next(
        sample
        for sample in histogram.samples
        if sample.name.endswith("_sum")
    )
    # The histogram sum should be clamped to zero when observing negative durations.
    assert sum_sample.value == pytest.approx(0.0)

    pdf_histogram = metrics.pdf_libreoffice_duration_seconds.collect()[0]
    pdf_sum = next(
        sample for sample in pdf_histogram.samples if sample.name.endswith("_sum")
    )
    assert pdf_sum.value == pytest.approx(0.0)

    attempt_samples = metrics.pdf_libreoffice_attempts_total.collect()[0].samples
    assert attempt_samples[0].labels["status"] == "timeout"
    assert attempt_samples[0].value == 1.0

    error_samples = metrics.pipeline_errors_total.collect()[0].samples
    assert error_samples[0].labels["code"] == "valueerror"


def test_metrics_recording_celery_flow() -> None:
    metrics = metrics_module.get_metrics()

    metrics.record_celery_enqueue(queue="default", task="worker.process")
    metrics.record_celery_execution(
        queue="default",
        task="worker.process",
        status="ok",
        seconds=-5,
        error_code="TaskError",
    )

    enqueue_counter = metrics.celery_tasks_enqueued_total.collect()[0].samples[0]
    assert enqueue_counter.value == 1

    in_progress = metrics.celery_tasks_in_progress.collect()[0].samples[0]
    assert in_progress.value == 0

    duration_histogram = metrics.celery_task_duration_seconds.collect()[0]
    duration_sum = next(
        sample for sample in duration_histogram.samples if sample.name.endswith("_sum")
    )
    assert duration_sum.value == pytest.approx(0.0)

    latency_samples = metrics.celery_task_latency_p95_seconds.collect()[0].samples
    assert latency_samples[0].labels == {
        "queue": "default",
        "task": "worker.process",
        "status": "ok",
    }
    assert latency_samples[0].value == pytest.approx(0.0)

    error_labels = metrics.pipeline_errors_total.collect()[0].samples[0].labels
    assert error_labels["code"] == "taskerror"


@pytest.mark.asyncio()
async def test_render_metrics_returns_payload() -> None:
    payload, content_type = await metrics_module.render_metrics()
    assert isinstance(payload, (bytes, bytearray))
    assert content_type == metrics_module.CONTENT_TYPE_LATEST
