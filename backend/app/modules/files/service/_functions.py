"""FileService module-level functions kept for compatibility (ARCH-4 slice 10 split).

Independent of the FileService class (no cycle): upload session helpers, content/version/
record indexing, search-document upsert and download-url issuance.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files import av, extractors, s3, storage
from app.modules.files.models import (
    AVStatus,
    DownloadLog,
    FileContentIndex,
    FileContentIndexStatus,
    FileLink,
    FileObject,
    FileRecord,
    FileStatus,
    FileTextIndex,
    FileVersion,
    FileVersionStatus,
    TextIndexStatus,
)
from app.modules.files.service._base import (
    MAX_INDEX_BYTES,
    MAX_INDEX_CHARS,
    _mask_pii,
    logger,
    resolve_presign_ttl,
)
from app.modules.search.models import SearchDocument
from app.tasks import index_file_content_job


# legacy NEXT29 API kept for compatibility
async def create_upload_session(
    *, session: AsyncSession, tenant_id: str, payload, user_id: str | None
) -> tuple[FileObject, FileVersion, str]:
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
        s3_key=storage.build_tenant_key(
            tenant_id=tenant_id,
            entity=str(payload.owner_entity_type or "files"),
            entity_id=str(payload.owner_entity_id or obj.id),
            file_id=obj.id,
            filename=payload.filename,
        ),
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
    url = storage.presign_put(key=version.s3_key, expires_in=resolve_presign_ttl())
    return obj, version, url


async def complete_upload(
    *, session: AsyncSession, tenant_id: str, file_id: str, version_id: str
) -> FileVersion:
    version = await session.get(FileVersion, version_id)
    if version is None or version.tenant_id != tenant_id or version.file_id != file_id:
        raise HTTPException(status_code=404, detail="version_not_found")

    try:
        storage.assert_tenant_key(tenant_id=tenant_id, key=version.s3_key)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden") from exc

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
    elif verdict.status == "error":
        # SEC-64: непроверенный файл НЕ считается безопасным. Раньше любая ошибка
        # сканера (недоступный clamd, таймаут) попадала в ветку else и объявляла
        # файл чистым — fail-open ровно там, где нужен fail-closed.
        version.av_status = AVStatus.error.value
        version.status = FileVersionStatus.quarantined.value
    else:
        version.av_status = AVStatus.clean.value
        version.status = FileVersionStatus.ready.value

    await session.flush()
    if version.status == FileVersionStatus.ready.value:
        index_file_content_job.apply_async(
            kwargs={"tenant_slug": session.info.get("tenant"), "version_id": version.id},
            countdown=0,
        )
    return version


async def index_file_content(
    *, session: AsyncSession, tenant_id: str, version: FileVersion, data: bytes
) -> None:
    started = perf_counter()
    if version.size > MAX_INDEX_BYTES:
        version.text_index_status = TextIndexStatus.skipped.value
        logger.info(
            "files.index_content.skipped_too_large",
            extra={"version_id": version.id, "size": version.size},
        )
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
        logger.info(
            "files.index_content.not_indexable",
            extra={"version_id": version.id, "mime": version.mime},
        )
        return
    truncated = False
    text = _mask_pii(text)
    if len(text) > MAX_INDEX_CHARS:
        text = text[:MAX_INDEX_CHARS]
        truncated = True
    version.text_index_status = TextIndexStatus.indexed.value

    existing = (
        await session.execute(
            select(FileTextIndex).where(FileTextIndex.file_version_id == version.id)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = FileTextIndex(tenant_id=tenant_id, file_version_id=version.id)
        session.add(existing)

    existing.raw_text = text
    existing.excerpt = text[:400]
    existing.content_tsv = text
    existing.lang = "russian"

    logger.info(
        "files.index_content.done",
        extra={
            "version_id": version.id,
            "bytes": len(data),
            "duration_ms": int((perf_counter() - started) * 1000),
            "extracted_chars": len(text),
            "truncated": truncated,
        },
    )


async def index_file_version(session: AsyncSession, *, tenant_id: str, version_id: str) -> None:
    version = await session.get(FileVersion, version_id)
    if (
        version is None
        or version.tenant_id != tenant_id
        or version.status != FileVersionStatus.ready.value
    ):
        return
    if version.text_index_status == TextIndexStatus.indexed.value:
        existing = (
            await session.execute(
                select(FileTextIndex).where(FileTextIndex.file_version_id == version.id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
    with s3.stream_object(key=version.s3_key) as body:
        data = body.read()
    await index_file_content(session=session, tenant_id=tenant_id, version=version, data=data)


async def index_file_record(session: AsyncSession, *, tenant_id: str, file_id: str) -> None:
    record = await session.get(FileRecord, file_id)
    if (
        record is None
        or record.tenant_id != tenant_id
        or record.status not in {FileStatus.clean.value, FileStatus.ready.value}
    ):
        return

    file_hash = record.sha256
    existing = (
        await session.execute(select(FileContentIndex).where(FileContentIndex.file_id == file_id))
    ).scalar_one_or_none()
    if (
        existing is not None
        and existing.content_sha256 == file_hash
        and existing.status == FileContentIndexStatus.indexed.value
    ):
        return

    if existing is None:
        existing = FileContentIndex(
            tenant_id=tenant_id,
            file_id=file_id,
            content_sha256=file_hash,
            mime_type=record.content_type,
        )
        session.add(existing)

    existing.attempts = int(existing.attempts or 0) + 1
    existing.status = FileContentIndexStatus.queued.value
    existing.mime_type = record.content_type

    with s3.stream_object(key=record.object_key) as body:
        data = body.read()
    if len(data) > MAX_INDEX_BYTES:
        existing.status = FileContentIndexStatus.failed.value
        existing.last_error = "max_size_exceeded"
        return

    text = ""
    suffix = Path(record.object_key).suffix.lower()
    with NamedTemporaryFile(delete=True, suffix=suffix or ".bin") as tmp:
        tmp.write(data)
        tmp.flush()
        if suffix == ".pdf":
            text = extractors.extract_text_pdf(Path(tmp.name))
        elif suffix == ".docx":
            text = extractors.extract_text_docx(Path(tmp.name))

    if len(text) > MAX_INDEX_CHARS:
        text = text[:MAX_INDEX_CHARS]

    existing.raw_text = text
    existing.content_sha256 = file_hash
    existing.status = (
        FileContentIndexStatus.indexed.value if text else FileContentIndexStatus.failed.value
    )
    existing.last_error = None if text else "not_indexable"
    existing.language = "ru"

    await _upsert_file_search_document(session, tenant_id=tenant_id, file_record=record, text=text)


async def _upsert_file_search_document(
    session: AsyncSession,
    *,
    tenant_id: str,
    file_record: FileRecord,
    text: str,
) -> None:
    links = (
        (
            await session.execute(
                select(FileLink).where(
                    FileLink.tenant_id == tenant_id, FileLink.file_id == file_record.id
                )
            )
        )
        .scalars()
        .all()
    )
    meta = dict(file_record.metadata_json or {})
    if links:
        primary = links[0]
        meta.setdefault("entity_type", primary.entity_type)
        meta.setdefault("entity_id", primary.entity_id)
    existing = (
        await session.execute(
            select(SearchDocument).where(
                SearchDocument.tenant_id == tenant_id,
                SearchDocument.entity_type == "file",
                SearchDocument.entity_id == file_record.id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = SearchDocument(
            tenant_id=tenant_id,
            entity_type="file",
            entity_id=file_record.id,
            source_file_id=file_record.id,
        )
        session.add(existing)
    existing.title = Path(file_record.object_key).name
    text_content = text.strip()
    if not text_content:
        text_content = "no text extracted"
    existing.summary = f"{file_record.content_type} • {file_record.size_bytes} bytes"
    existing.text_content = text_content
    existing.lang = "russian"
    existing.meta = meta
    existing.indexed_at = datetime.now(timezone.utc)
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        existing.fts = func.to_tsvector("russian", text_content)
    else:
        existing.fts = text_content


async def issue_download_url(
    *,
    session: AsyncSession,
    tenant_id: str,
    file_id: str,
    version_id: str,
    user_id: str | None,
    ip: str | None,
    user_agent: str | None,
) -> str:
    version = await session.get(FileVersion, version_id)
    if version is None or version.file_id != file_id or version.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="version_not_found")
    if version.status != FileVersionStatus.ready.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="file_not_ready")
    try:
        storage.assert_tenant_key(tenant_id=tenant_id, key=version.s3_key)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden") from exc
    url = storage.presign_get(key=version.s3_key, expires_in=resolve_presign_ttl())
    session.add(
        DownloadLog(
            tenant_id=tenant_id,
            user_id=user_id,
            file_id=file_id,
            version_id=version_id,
            ip=ip,
            user_agent=user_agent,
        )
    )
    await session.flush()
    return url
