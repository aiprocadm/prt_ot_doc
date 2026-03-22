from __future__ import annotations

from app.services.celery_app import celery_app


_INTERNAL_ORCHESTRATOR = "document_pipeline_orchestrator"


def _job_step_response(
    *,
    tenant_slug: str,
    job_id: str,
    step_id: str,
    step_key: str,
    status: str = "accepted",
    deferred: bool = False,
    handler: str = "job_steps_runner",
    bridge_mode: str = "compatibility-wrapper",
    detail: str | None = None,
) -> dict[str, str | bool]:
    response: dict[str, str | bool] = {
        "tenant": tenant_slug,
        "job_id": job_id,
        "step_id": step_id,
        "step_key": step_key,
        "status": status,
        "deferred": deferred,
        "handler": handler,
        "bridge_mode": bridge_mode,
        "orchestrator": _INTERNAL_ORCHESTRATOR,
    }
    if detail:
        response["detail"] = detail
    return response


def _accepted_step_response(*, tenant_slug: str, job_id: str, step_id: str, step_key: str) -> dict[str, str | bool]:
    return _job_step_response(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key=step_key,
    )


def _deferred_bridge_response(
    *, tenant_slug: str, job_id: str, step_id: str, step_key: str, handler: str, detail: str
) -> dict[str, str | bool]:
    return _job_step_response(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key=step_key,
        status="accepted",
        deferred=True,
        handler=handler,
        detail=detail,
    )


@celery_app.task(name="app.tasks.render_docx_job")
def render_docx_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _accepted_step_response(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key="render_docx",
    )


@celery_app.task(name="app.tasks.build_zip_job")
def build_zip_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _accepted_step_response(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key="build_zip",
    )


@celery_app.task(name="app.tasks.send_edo_job")
def send_edo_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _deferred_bridge_response(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key="send_edo",
        handler="edo_orchestrator_bridge_pending",
        detail="Compatibility wrapper kept until canonical EDO pipeline jobs are fully converged.",
    )


@celery_app.task(name="app.tasks.verify_signature_job")
def verify_signature_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _deferred_bridge_response(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key="verify_signature",
        handler="signature_orchestrator_bridge_pending",
        detail="Compatibility wrapper kept until canonical signature verification jobs are fully converged.",
    )


@celery_app.task(name="app.tasks.export_report_job")
def export_report_job(*, tenant_slug: str, report_id: str) -> dict[str, str]:
    return {
        "tenant": tenant_slug,
        "report_id": report_id,
        "status": "accepted",
        "bridge_mode": "compatibility-wrapper",
        "orchestrator": _INTERNAL_ORCHESTRATOR,
    }


@celery_app.task(name="app.tasks.sync_integration_job")
def sync_integration_job(*, tenant_slug: str, integration_key: str) -> dict[str, str]:
    return {
        "tenant": tenant_slug,
        "integration_key": integration_key,
        "status": "accepted",
        "bridge_mode": "compatibility-wrapper",
        "orchestrator": _INTERNAL_ORCHESTRATOR,
    }


@celery_app.task(name="app.tasks.index_file_content_job")
def index_file_content_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _accepted_step_response(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key="index_file_content",
    )
