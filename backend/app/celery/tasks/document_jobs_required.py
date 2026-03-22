from __future__ import annotations

from app.core.tenant import tenant_context
from app.db.session import ensure_tenant_schema, session_scope
from app.services.celery_app import celery_app
from app.services.pipelines_orchestrator import PipelineOrchestrator

_INTERNAL_ORCHESTRATOR = "document_pipeline_orchestrator"
_RUNTIME_BRIDGE = "compatibility-execution-bridge"


def _job_step_response(
    *,
    tenant_slug: str,
    job_id: str,
    step_id: str,
    step_key: str,
    status: str,
    deferred: bool = False,
    handler: str = "job_steps_runner",
    bridge_mode: str = _RUNTIME_BRIDGE,
    detail: str | None = None,
    step_status: str | None = None,
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
    if step_status is not None:
        response["step_status"] = step_status
    return response


def _run_coroutine_step(*, tenant_slug: str, job_id: str, step_id: str, step_key: str) -> dict[str, str | bool]:
    from app.tasks import _run_coroutine

    async def _run() -> dict[str, str | bool]:
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                orchestrator = PipelineOrchestrator(session)
                step = await orchestrator.run_step(job_id=job_id, step_id=step_id)
                await orchestrator.continue_job(job_id=job_id)
                return _job_step_response(
                    tenant_slug=tenant_slug,
                    job_id=job_id,
                    step_id=step_id,
                    step_key=step_key,
                    status="completed",
                    step_status=str(step.status),
                )

    return _run_coroutine(_run())


@celery_app.task(name="app.tasks.render_docx_job")
def render_docx_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _run_coroutine_step(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key="render_docx",
    )


@celery_app.task(name="app.tasks.build_zip_job")
def build_zip_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _run_coroutine_step(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key="build_zip",
    )


@celery_app.task(name="app.tasks.send_edo_job")
def send_edo_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _run_coroutine_step(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key="send_edo",
    )


@celery_app.task(name="app.tasks.verify_signature_job")
def verify_signature_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _run_coroutine_step(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key="verify_signature",
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
    return _run_coroutine_step(
        tenant_slug=tenant_slug,
        job_id=job_id,
        step_id=step_id,
        step_key="index_file_content",
    )
