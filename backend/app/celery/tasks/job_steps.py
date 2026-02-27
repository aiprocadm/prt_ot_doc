from __future__ import annotations

from app.core.tenant import tenant_context
from app.db.session import ensure_tenant_schema, session_scope
from app.services.celery_app import celery_app
from app.services.pipelines_orchestrator import PipelineOrchestrator


@celery_app.task(name="app.tasks.run_job_step", bind=True, max_retries=2, default_retry_delay=10)
def run_job_step(self, *, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str]:
    from app.tasks import _run_coroutine

    async def _run() -> dict[str, str]:
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                orchestrator = PipelineOrchestrator(session)
                step = await orchestrator.run_step(job_id=job_id, step_id=step_id)
                await orchestrator.continue_job(job_id=job_id)
                return {"job_id": job_id, "step_id": step.id, "status": str(step.status)}

    try:
        return _run_coroutine(_run())
    except Exception as exc:  # noqa: BLE001
        countdown = 30 if self.request.retries >= 1 else 10
        raise self.retry(exc=exc, countdown=countdown)


__all__ = ["run_job_step"]
