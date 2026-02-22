from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.files import s3
from app.modules.files import av, extractors, storage
from app.modules.files.models import AVStatus, DownloadLog, FileObject, FileTextIndex, FileVersion, FileVersionStatus, TextIndexStatus
from sqlalchemy import select
from app.tasks import index_file_content_job


MAX_INDEX_BYTES = 25 * 1024 * 1024
MAX_INDEX_CHARS = 500_000

logger = logging.getLogger(__name__)


async def create_upload_session(*, session: AsyncSession, tenant_id: str, payload, user_id: str | None) -> tuple[FileObject, FileVersion, str]:
    obj = FileObject(
        tenant_id=tenant_id,
        kind=payload.kind,
        owner_entity_type=payload.owner_entity_type,
        owner_entity_id=payload.owner_entity_id,
        tags=payload.tags,
    )
    session.add(obj)
    await session.flush()
    version = FileVersion(
        tenant_id=tenant_id,
        file_id=obj.id,
        version_no=1,
        filename=payload.filename,
        s3_key=storage.build_tenant_key(tenant_id=tenant_id, file_id=obj.id, version_no=1, filename=payload.filename),
        size=0,
        mime="application/octet-stream",
        sha256="",
        status=FileVersionStatus.uploaded.value,
        av_status=AVStatus.pending.value,
        text_index_status=TextIndexStatus.pending.value,
        created_by=user_id,
    )
    session.add(version)
    await session.flush()
    url = storage.presign_put(key=version.s3_key, expires_in=600)
    return obj, version, url


async def complete_upload(*, session: AsyncSession, tenant_id: str, file_id: str, version_id: str) -> FileVersion:
    version = await session.get(FileVersion, version_id)
    if version is None or version.tenant_id != tenant_id or version.file_id != file_id:
        raise HTTPException(status_code=404, detail="version_not_found")

    metadata = s3.head_object(key=version.s3_key)
    if not metadata:
        raise HTTPException(status_code=409, detail="object_not_found")

    with s3.stream_object(key=version.s3_key) as body:
        data = body.read()

    version.sha256 = hashlib.sha256(data).hexdigest()
    version.size = len(data)
    version.mime = str(metadata.get("content_type") or "application/octet-stream")
    version.status = FileVersionStatus.scanning.value

    with NamedTemporaryFile(delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        verdict = av.scan_file(Path(tmp.name))

    if verdict.status == "infected":
        version.av_status = AVStatus.infected.value
        version.status = FileVersionStatus.quarantined.value
    else:
        version.av_status = AVStatus.clean.value
        version.status = FileVersionStatus.ready.value

    await session.flush()
    if version.status == FileVersionStatus.ready.value:
        index_file_content_job.apply_async(kwargs={"tenant_slug": session.info.get("tenant"), "version_id": version.id}, countdown=0)
    return version


async def index_file_content(*, session: AsyncSession, tenant_id: str, version: FileVersion, data: bytes) -> None:
    started = perf_counter()
    if version.size > MAX_INDEX_BYTES:
        version.text_index_status = TextIndexStatus.skipped.value
        logger.info("files.index_content.skipped_too_large", extra={"version_id": version.id, "size": version.size})
        return
    text = ""
    with NamedTemporaryFile(delete=True, suffix=Path(version.filename).suffix) as tmp:
        tmp.write(data)
        tmp.flush()
        suffix = Path(version.filename).suffix.lower()
        if suffix == ".pdf":
            text = extractors.extract_text_pdf(Path(tmp.name))
        elif suffix == ".docx":
            text = extractors.extract_text_docx(Path(tmp.name))
        else:
            version.text_index_status = TextIndexStatus.skipped.value
            return
    if not text:
        version.text_index_status = TextIndexStatus.skipped.value
        logger.info("files.index_content.not_indexable", extra={"version_id": version.id, "mime": version.mime})
        return
    truncated = False
    if len(text) > MAX_INDEX_CHARS:
        text = text[:MAX_INDEX_CHARS]
        truncated = True
    version.text_index_status = TextIndexStatus.indexed.value

    existing = (await session.execute(select(FileTextIndex).where(FileTextIndex.file_version_id == version.id))).scalar_one_or_none()
    if existing is None:
        existing = FileTextIndex(tenant_id=tenant_id, file_version_id=version.id)
        session.add(existing)

    existing.raw_text = text
    existing.excerpt = text[:400]
    existing.content_tsv = text
    existing.lang = "russian"

    logger.info("files.index_content.done", extra={"version_id": version.id, "bytes": len(data), "duration_ms": int((perf_counter()-started)*1000), "extracted_chars": len(text), "truncated": truncated})


async def index_file_version(session: AsyncSession, *, tenant_id: str, version_id: str) -> None:
    version = await session.get(FileVersion, version_id)
    if version is None or version.tenant_id != tenant_id or version.status != FileVersionStatus.ready.value:
        return
    if version.text_index_status == TextIndexStatus.indexed.value:
        existing = (await session.execute(select(FileTextIndex).where(FileTextIndex.file_version_id == version.id))).scalar_one_or_none()
        if existing is not None:
            return
    with s3.stream_object(key=version.s3_key) as body:
        data = body.read()
    await index_file_content(session=session, tenant_id=tenant_id, version=version, data=data)


async def issue_download_url(*, session: AsyncSession, tenant_id: str, file_id: str, version_id: str, user_id: str | None, ip: str | None, user_agent: str | None) -> str:
    version = await session.get(FileVersion, version_id)
    if version is None or version.file_id != file_id or version.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="version_not_found")
    if version.status != FileVersionStatus.ready.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="file_not_ready")
    url = storage.presign_get(key=version.s3_key, expires_in=600)
    session.add(DownloadLog(tenant_id=tenant_id, user_id=user_id, file_id=file_id, version_id=version_id, ip=ip, user_agent=user_agent))
    await session.flush()
    return url
