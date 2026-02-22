from __future__ import annotations

from app.services.celery_app import celery_app
from app.db.session import ensure_tenant_schema, session_scope, tenant_context
from app.services.pipelines_orchestrator import DocumentPipelineOrchestrator


@celery_app.task(name="app.tasks.pipeline_run_job")
def pipeline_run_job(*, tenant_slug: str, job_id: str) -> dict[str, str]:
    from app.tasks import _run_coroutine

    async def _run() -> dict[str, str]:
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                orchestrator = DocumentPipelineOrchestrator(session)
                job = await orchestrator.run_job(job_id=job_id)
                return {"job_id": job.id, "status": str(job.status)}

    return _run_coroutine(_run())


__all__ = ["pipeline_run_job"]
