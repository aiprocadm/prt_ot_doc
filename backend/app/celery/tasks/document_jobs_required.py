from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from app.core.tenant import tenant_context
from app.db.session import ensure_tenant_schema, session_scope
from app.services.celery_app import celery_app
from app.services.pipelines_orchestrator import PipelineOrchestrator

_INTERNAL_ORCHESTRATOR = "document_pipeline_orchestrator"
_RUNTIME_BRIDGE = "compatibility-execution-bridge"
_COMPATIBILITY_BRIDGES: dict[str, Callable[..., Awaitable[dict[str, str | bool]] | dict[str, str | bool]]] = {}
_KNOWN_BRIDGES = frozenset({"export_report", "sync_integration"})


def list_compatibility_bridges() -> tuple[str, ...]:
    return tuple(sorted(_KNOWN_BRIDGES))


def register_compatibility_bridge(
    bridge_name: str,
    handler: Callable[..., Awaitable[dict[str, str | bool]] | dict[str, str | bool]],
) -> None:
    normalized = bridge_name.strip()
    if normalized not in _KNOWN_BRIDGES:
        known = ", ".join(sorted(_KNOWN_BRIDGES))
        raise ValueError(f"Unknown compatibility bridge '{bridge_name}'. Expected one of: {known}.")
    _COMPATIBILITY_BRIDGES[normalized] = handler


def unregister_compatibility_bridge(bridge_name: str) -> None:
    _COMPATIBILITY_BRIDGES.pop(bridge_name.strip(), None)


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


def _run_named_bridge(*, tenant_slug: str, bridge_name: str, payload: dict[str, str]) -> dict[str, str | bool]:
    from app.tasks import _run_coroutine

    async def _run() -> dict[str, str | bool]:
        handler = _COMPATIBILITY_BRIDGES.get(bridge_name)
        if handler is None:
            response: dict[str, str | bool] = {
                "tenant": tenant_slug,
                **payload,
                "status": "accepted",
                "deferred": True,
                "handler": f"{bridge_name}_bridge",
                "bridge_mode": "compatibility-wrapper",
                "orchestrator": _INTERNAL_ORCHESTRATOR,
                "detail": "No internal bridge configured; compatibility envelope preserved for backward compatibility.",
            }
            return response

        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            result = handler(tenant_slug=tenant_slug, **payload)
            if inspect.isawaitable(result):
                result = await result
            return {
                "tenant": tenant_slug,
                **payload,
                "status": "completed",
                "deferred": False,
                "handler": f"{bridge_name}_bridge",
                "bridge_mode": _RUNTIME_BRIDGE,
                "orchestrator": _INTERNAL_ORCHESTRATOR,
                **result,
            }

    return _run_coroutine(_run())


@celery_app.task(name="app.tasks.render_docx_job")
def render_docx_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _run_coroutine_step(tenant_slug=tenant_slug, job_id=job_id, step_id=step_id, step_key="render_docx")


@celery_app.task(name="app.tasks.build_zip_job")
def build_zip_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _run_coroutine_step(tenant_slug=tenant_slug, job_id=job_id, step_id=step_id, step_key="build_zip")


@celery_app.task(name="app.tasks.send_edo_job")
def send_edo_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _run_coroutine_step(tenant_slug=tenant_slug, job_id=job_id, step_id=step_id, step_key="send_edo")


@celery_app.task(name="app.tasks.verify_signature_job")
def verify_signature_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _run_coroutine_step(tenant_slug=tenant_slug, job_id=job_id, step_id=step_id, step_key="verify_signature")


@celery_app.task(name="app.tasks.export_report_job")
def export_report_job(*, tenant_slug: str, report_id: str) -> dict[str, str | bool]:
    return _run_named_bridge(tenant_slug=tenant_slug, bridge_name="export_report", payload={"report_id": report_id})


@celery_app.task(name="app.tasks.sync_integration_job")
def sync_integration_job(*, tenant_slug: str, integration_key: str) -> dict[str, str | bool]:
    return _run_named_bridge(tenant_slug=tenant_slug, bridge_name="sync_integration", payload={"integration_key": integration_key})


@celery_app.task(name="app.tasks.index_file_content_job")
def index_file_content_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str | bool]:
    return _run_coroutine_step(tenant_slug=tenant_slug, job_id=job_id, step_id=step_id, step_key="index_file_content")
