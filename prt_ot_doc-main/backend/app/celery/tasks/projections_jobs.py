from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Callable, Coroutine

from app.db.session import AsyncSessionLocal
from app.modules.projections.services import ProjectionOrchestrator
from app.services.celery_app import celery_app


def _run_projection_job(tenant_id: str, runner: Callable[[ProjectionOrchestrator], Coroutine[Any, Any, Any]]) -> dict[str, Any]:
    async def _execute() -> Any:
        async with AsyncSessionLocal(tenant=tenant_id) as session:
            orchestrator = ProjectionOrchestrator(session, tenant_id=tenant_id)
            return await runner(orchestrator)

    rebuilt = asyncio.run(_execute())
    return {"status": "ok", "tenant_id": tenant_id, "rebuilt": rebuilt, "finished_at": datetime.now(UTC).isoformat()}


@celery_app.task(name="app.rebuild_dashboard_snapshots_job")
def rebuild_dashboard_snapshots_job(*, tenant_id: str, snapshot_date: str | None = None, **kwargs):
    date_value = datetime.fromisoformat(snapshot_date).date() if snapshot_date else datetime.now(UTC).date()
    return _run_projection_job(tenant_id, lambda orchestrator: orchestrator.rebuild_dashboard_snapshot(date_value))


@celery_app.task(name="app.rebuild_package_projection_job")
def rebuild_package_projection_job(*, tenant_id: str, **kwargs):
    return _run_projection_job(tenant_id, lambda orchestrator: orchestrator.rebuild_package_projection())


@celery_app.task(name="app.rebuild_person_compliance_projection_job")
def rebuild_person_compliance_projection_job(*, tenant_id: str, **kwargs):
    return _run_projection_job(tenant_id, lambda orchestrator: orchestrator.rebuild_person_compliance_projection())


@celery_app.task(name="app.rebuild_site_safety_projection_job")
def rebuild_site_safety_projection_job(*, tenant_id: str, **kwargs):
    return _run_projection_job(tenant_id, lambda orchestrator: orchestrator.rebuild_site_safety_projection())


@celery_app.task(name="app.rebuild_contractor_readiness_projection_job")
def rebuild_contractor_readiness_projection_job(*, tenant_id: str, **kwargs):
    return _run_projection_job(tenant_id, lambda orchestrator: orchestrator.rebuild_contractor_readiness_projection())


@celery_app.task(name="app.reindex_search_entity_job")
def reindex_search_entity_job(*, tenant_id: str, **kwargs):
    return _run_projection_job(tenant_id, lambda orchestrator: orchestrator.rebuild_search_index())


@celery_app.task(name="app.rebuild_client_portal_projection_job")
def rebuild_client_portal_projection_job(*, tenant_id: str, **kwargs):
    return _run_projection_job(tenant_id, lambda orchestrator: orchestrator.rebuild_client_portal_projection())
