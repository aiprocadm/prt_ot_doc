from __future__ import annotations

from app.services.celery_app import celery_app


@celery_app.task(name="app.tasks.render_docx_job")
def render_docx_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str]:
    return {"tenant": tenant_slug, "job_id": job_id, "step_id": step_id, "status": "accepted"}


@celery_app.task(name="app.tasks.build_zip_job")
def build_zip_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str]:
    return {"tenant": tenant_slug, "job_id": job_id, "step_id": step_id, "status": "accepted"}


@celery_app.task(name="app.tasks.send_edo_job")
def send_edo_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str]:
    return {"tenant": tenant_slug, "job_id": job_id, "step_id": step_id, "status": "stub"}


@celery_app.task(name="app.tasks.verify_signature_job")
def verify_signature_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str]:
    return {"tenant": tenant_slug, "job_id": job_id, "step_id": step_id, "status": "stub"}


@celery_app.task(name="app.tasks.export_report_job")
def export_report_job(*, tenant_slug: str, report_id: str) -> dict[str, str]:
    return {"tenant": tenant_slug, "report_id": report_id, "status": "accepted"}


@celery_app.task(name="app.tasks.sync_integration_job")
def sync_integration_job(*, tenant_slug: str, integration_key: str) -> dict[str, str]:
    return {"tenant": tenant_slug, "integration_key": integration_key, "status": "accepted"}


@celery_app.task(name="app.tasks.index_file_content_job")
def index_file_content_job(*, tenant_slug: str, job_id: str, step_id: str) -> dict[str, str]:
    return {"tenant": tenant_slug, "job_id": job_id, "step_id": step_id, "status": "accepted"}
