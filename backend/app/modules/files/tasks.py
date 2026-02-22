from __future__ import annotations

from app.services.celery_app import celery_app


@celery_app.task(name="files.scan_file_job")
def scan_file_job(version_id: str) -> str:
    return version_id


@celery_app.task(name="files.index_file_content_job")
def index_file_content_job(version_id: str) -> str:
    return version_id
