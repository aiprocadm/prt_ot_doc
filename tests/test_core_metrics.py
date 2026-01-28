from __future__ import annotations

import pytest

from app.core import metrics as metrics_module
from app.core.metrics import PipelineStage, PipelineType, StageResult


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
    metrics.record_pipeline_stage_start(
        pipeline=PipelineType.DOCUMENT,
        stage=PipelineStage.DOCX_GENERATED,
    )
    metrics.record_pipeline_stage_end(
        pipeline=PipelineType.DOCUMENT,
        stage=PipelineStage.DOCX_GENERATED,
        result=StageResult.SUCCESS,
        seconds=-1,
    )
    metrics.record_pipeline_stage_start(
        pipeline=PipelineType.DOCUMENT,
        stage=PipelineStage.PDF_CONVERTED,
    )
    metrics.record_pipeline_stage_end(
        pipeline=PipelineType.DOCUMENT,
        stage=PipelineStage.PDF_CONVERTED,
        result=StageResult.FAILED,
        seconds=1.2,
        error_class="ValueError",
    )
    metrics.observe_pipeline_total_duration(pipeline=PipelineType.DOCUMENT, seconds=-1)
    metrics.observe_pdf_duration(template_id="tpl", seconds=-1)
    metrics.observe_pdf_libreoffice(seconds=-5, status=" Timeout ")

    samples = metrics.pipeline_runs_total.collect()[0].samples
    assert {sample.labels["status"] for sample in samples} == {"success", "failure"}

    requests_samples = metrics.pipeline_requests_total.collect()[0].samples
    request_results = {sample.labels["result"] for sample in requests_samples}
    assert StageResult.STARTED.value in request_results
    assert StageResult.SUCCESS.value in request_results
    assert StageResult.FAILED.value in request_results

    stage_histogram = metrics.pipeline_stage_duration_seconds.collect()[0]
    stage_sum = next(
        sample
        for sample in stage_histogram.samples
        if sample.name.endswith("_sum")
        and sample.labels["pipeline"] == PipelineType.DOCUMENT.value
        and sample.labels["stage"] == PipelineStage.DOCX_GENERATED.value
    )
    assert stage_sum.value == pytest.approx(0.0)

    total_histogram = metrics.pipeline_total_duration_seconds.collect()[0]
    total_sum = next(
        sample
        for sample in total_histogram.samples
        if sample.name.endswith("_sum")
        and sample.labels["pipeline"] == PipelineType.DOCUMENT.value
    )
    assert total_sum.value == pytest.approx(0.0)

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
    assert error_samples[0].labels["error_class"] == "valueerror"
    assert error_samples[0].labels["pipeline"] == PipelineType.DOCUMENT.value
    assert error_samples[0].labels["stage"] == PipelineStage.PDF_CONVERTED.value


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
    assert error_labels["error_class"] == "taskerror"
    assert error_labels["pipeline"] == PipelineType.UNKNOWN.value
    assert error_labels["stage"] == PipelineStage.UNKNOWN.value


def test_metrics_recording_outbox_flow() -> None:
    metrics = metrics_module.get_metrics()

    metrics.record_outbox_enqueued(
        event_type="DocumentCreated",
        destination="https://example.test/hooks",
        tenant_id="tenant-1",
    )
    metrics.record_outbox_sent(event_type="DocumentCreated", destination="https://example.test/hooks")
    metrics.record_outbox_failed(
        event_type="DocumentCreated",
        destination="https://example.test/hooks",
        error_class="timeout",
    )
    metrics.record_outbox_dead(event_type="DocumentCreated", destination="https://example.test/hooks")
    metrics.observe_outbox_attempts(
        event_type="DocumentCreated",
        destination="https://example.test/hooks",
        attempts=2,
    )
    metrics.observe_outbox_dispatch_latency(
        event_type="DocumentCreated",
        destination="https://example.test/hooks",
        seconds=1.5,
    )
    metrics.record_outbox_dispatcher_tick(processed=1)
    metrics.observe_outbox_dispatcher_duration(seconds=0.2)

    enqueued_samples = metrics.outbox_enqueued_total.collect()[0].samples
    assert enqueued_samples[0].value == 1

    sent_samples = metrics.outbox_sent_total.collect()[0].samples
    assert sent_samples[0].value == 1

    failed_samples = metrics.outbox_failed_total.collect()[0].samples
    assert failed_samples[0].labels["error_class"] == "timeout"
    assert failed_samples[0].value == 1

    dead_samples = metrics.outbox_dead_total.collect()[0].samples
    assert dead_samples[0].value == 1


@pytest.mark.asyncio()
async def test_render_metrics_returns_payload() -> None:
    payload, content_type = await metrics_module.render_metrics()
    assert isinstance(payload, (bytes, bytearray))
    assert content_type == metrics_module.CONTENT_TYPE_LATEST
