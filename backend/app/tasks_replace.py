from __future__ import annotations

from app.services.celery_app import celery_app


@celery_app.task(name="app.tasks.replace_dry_run_job")
def replace_dry_run_job(*, tenant: str, document_version_id: str, replace_map_id: str, options: dict, correlation_id: str | None = None) -> dict:
    return {
        "tenant": tenant,
        "document_version_id": document_version_id,
        "replace_map_id": replace_map_id,
        "options": options,
        "correlation_id": correlation_id,
        "status": "queued",
    }


@celery_app.task(name="app.tasks.replace_apply_job")
def replace_apply_job(*, tenant: str, document_version_id: str, replace_map_id: str, options: dict, correlation_id: str | None = None) -> dict:
    return {
        "tenant": tenant,
        "document_version_id": document_version_id,
        "replace_map_id": replace_map_id,
        "options": options,
        "correlation_id": correlation_id,
        "status": "queued",
    }


@celery_app.task(name="app.tasks.replace_rollback_job")
def replace_rollback_job(*, replace_run_id: str, correlation_id: str | None = None) -> dict:
    return {"replace_run_id": replace_run_id, "correlation_id": correlation_id, "status": "queued"}
