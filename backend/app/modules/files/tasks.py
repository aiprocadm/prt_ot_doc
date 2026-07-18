from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import session_scope
from app.modules.files.models import FileRecord, FileStatus
from app.modules.files.service import FileService
from app.services.celery_app import celery_app


@celery_app.task(name="files.av_scan_file_job")
def av_scan_file_job(tenant_id: str, file_id: str) -> str:
    async def _run() -> None:
        async with session_scope(tenant=tenant_id) as session:
            svc = FileService(session=session, tenant_id=tenant_id)
            await svc.av_scan_file(file_id=file_id)
            await session.commit()

    asyncio.run(_run())
    return file_id


@celery_app.task(name="files.purge_temp_files")
def purge_temp_files(hours: int = 24) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async def _run() -> int:
        async with session_scope(tenant="test") as session:
            rows = (
                (
                    await session.execute(
                        select(FileRecord).where(
                            FileRecord.object_key.like("tmp/%"),
                            FileRecord.created_at < cutoff,
                            FileRecord.status != FileStatus.clean.value,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                row.status = FileStatus.deleted.value
                row.deleted_at = datetime.now(timezone.utc)
            await session.commit()
            return len(rows)

    return asyncio.run(_run())


@celery_app.task(name="files.index_file_content_job")
def index_file_content_job(version_id: str) -> str:
    return version_id
