from __future__ import annotations

import hashlib
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
from typing import Any

import logging

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domains.files import s3
from app.modules.files import av, extractors, storage
from app.modules.search.models import SearchDocument
from app.modules.files.models import (
    AVStatus,
    DownloadLog,
    FileDownloadLog,
    FileEntityType,
    FileLink,
    FileLinkRole,
    FileObject,
    FileRecord,
    FileStatus,
    FileTextIndex,
    FileContentIndex,
    FileContentIndexStatus,
    FileScanResult,
    FileVersion,
    FileVersionStatus,
    TextIndexStatus,
)
from app.tasks import index_file_content_job, av_scan_file_job


MAX_INDEX_BYTES = 25 * 1024 * 1024
MAX_INDEX_CHARS = 500_000

logger = logging.getLogger(__name__)


def _sha256_bytes(payload: bytes) -> str:
    h = hashlib.sha256()
    h.update(payload)
    return h.hexdigest()


def compute_sha256_stream(chunks: list[bytes]) -> str:
    h = hashlib.sha256()
    for chunk in chunks:
        h.update(chunk)
    return h.hexdigest()


def _safe_filename(filename: str | None, fallback: str = "artifact.bin") -> str:
    candidate = (filename or fallback).strip().replace("/", "_").replace("..", "_")
    return candidate or fallback


def _normalize_name_part(value: Any, fallback: str) -> str:
    raw = str(value).strip() if value is not None else ""
    if not raw:
        return fallback
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw)
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized.lower() or fallback


def build_artifact_name(payload: dict[str, Any] | None, ext: str) -> str:
    data = payload or {}
    org = _normalize_name_part(data.get("org"), "org")
    unit = _normalize_name_part(data.get("unit"), "unit")
    project = _normalize_name_part(data.get("project"), "project")
    client = _normalize_name_part(data.get("client"), "client")
    doc = _normalize_name_part(data.get("doc"), "doc")
    topic = _normalize_name_part(data.get("topic"), "topic")
    version = int(data.get("version") or 1)
    if data.get("date"):
        date_str = str(data["date"]).replace("-", "")[:8]
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    parts = [org, unit, project, client, doc, topic, f"v{version:02d}", date_str]
    flags = data.get("flags") or []
    if isinstance(flags, str):
        flags = [flags]
    if isinstance(flags, list):
        for flag in flags:
            normalized_flag = _normalize_name_part(flag, "")
            if normalized_flag:
                parts.append(normalized_flag)
    base = "_".join(parts)
    normalized_ext = ext if ext.startswith(".") else f".{ext}"
    return f"{base}{normalized_ext}"


class FileService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def create_upload_session(
        self,
        *,
        filename: str,
        content_type: str,
        size_bytes: int,
        metadata_json: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> tuple[FileRecord, str, int]:
        settings = get_settings()
        if size_bytes > settings.max_upload_size:
            raise HTTPException(status_code=413, detail="max_upload_size_exceeded")
        if content_type not in settings.file_allowed_mime:
            raise HTTPException(status_code=415, detail="unsupported_content_type")
        lower_name = filename.lower()
        if lower_name.endswith((".docm", ".xlsm")):
            raise HTTPException(status_code=400, detail="macro_enabled_documents_are_forbidden")
        object_id = str(uuid4())
        object_key = f"tenants/{self.tenant_id}/uploads/{datetime.now(timezone.utc):%Y/%m/%d}/{object_id}/{_safe_filename(filename)}"
        record = FileRecord(
            id=object_id,
            tenant_id=self.tenant_id,
            bucket="main",
            object_key=object_key,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256="",
            status=FileStatus.uploaded.value,
            av_vendor="clamav",
            av_result_json={},
            original_name=_safe_filename(filename),
            original_filename=_safe_filename(filename),
            is_public=False,
            tags=metadata_json or {},
            metadata_json=metadata_json or {},
            created_by=created_by,
        )
        self.session.add(record)
        await self.session.flush()
        ttl = settings.presign_download_ttl_seconds
        upload_url = s3.generate_presigned_put_url(object_key, expires_in=ttl, content_type=content_type)
        return record, upload_url, ttl



    async def create_new_version_upload_session(
        self,
        *,
        file_id: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        metadata_json: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> tuple[FileVersion, str, int]:
        record = await self.session.get(FileRecord, file_id)
        if record is None or record.tenant_id != self.tenant_id or record.deleted_at is not None:
            raise HTTPException(status_code=404, detail="file_not_found")
        settings = get_settings()
        if size_bytes > settings.max_upload_size:
            raise HTTPException(status_code=413, detail="max_upload_size_exceeded")
        if content_type not in settings.file_allowed_mime:
            raise HTTPException(status_code=415, detail="unsupported_content_type")

        latest = (
            await self.session.execute(
                select(func.max(FileVersion.version_no)).where(
                    FileVersion.tenant_id == self.tenant_id,
                    FileVersion.file_id == file_id,
                )
            )
        ).scalar_one()
        version_no = int(latest or 0) + 1
        key = storage.build_tenant_key(
            tenant_id=self.tenant_id,
            entity="files",
            entity_id=file_id,
            file_id=file_id,
            filename=filename,
            version_no=version_no,
        )
        version = FileVersion(
            tenant_id=self.tenant_id,
            file_id=file_id,
            version_no=version_no,
            filename=_safe_filename(filename),
            s3_key=key,
            size=size_bytes,
            mime=content_type,
            sha256="",
            status=FileVersionStatus.uploaded.value,
            av_status=AVStatus.pending.value,
            text_index_status=TextIndexStatus.pending.value,
            created_by=created_by,
        )
        self.session.add(version)
        if metadata_json:
            merged = dict(record.metadata_json or {})
            merged.update(metadata_json)
            record.metadata_json = merged
            record.tags = merged
        await self.session.flush()
        ttl = settings.presign_download_ttl_seconds
        upload_url = s3.generate_presigned_put_url(key, expires_in=ttl, content_type=content_type)
        return version, upload_url, ttl

    async def finalize_upload(self, *, file_id: str) -> FileRecord:
        record = await self.session.get(FileRecord, file_id)
        if record is None or record.tenant_id != self.tenant_id:
            raise HTTPException(status_code=404, detail="file_not_found")
        metadata = s3.head_object(key=record.object_key)
        if metadata is None:
            raise HTTPException(status_code=409, detail="object_not_found")
        with s3.stream_object(key=record.object_key) as body:
            data = body.read()
        record.size_bytes = int(metadata.get("size") or len(data))
        record.content_type = str(metadata.get("content_type") or record.content_type)
        record.sha256 = _sha256_bytes(data)
        record.status = FileStatus.scanning.value
        await self.session.flush()
        try:
            av_scan_file_job.delay(self.tenant_id, file_id)
        except Exception:
            await self.av_scan_file(file_id=file_id)
        return record

    async def av_scan_file(self, *, file_id: str) -> FileRecord:
        record = await self.session.get(FileRecord, file_id)
        if record is None or record.tenant_id != self.tenant_id:
            raise HTTPException(status_code=404, detail="file_not_found")
        try:
            with s3.stream_object(key=record.object_key) as body:
                data = body.read()
        except Exception:
            logger.warning("files.av.unavailable", extra={"file_id": file_id})
            record.status = FileStatus.scanning.value
            record.av_result_json = {"status": "unavailable"}
            await self.session.flush()
            return record

        with NamedTemporaryFile(delete=True) as tmp:
            tmp.write(data)
            tmp.flush()
            verdict = av.scan_file(Path(tmp.name))

        if verdict.status == "infected":
            quarantine_key = f"quarantine/{datetime.now(timezone.utc):%Y/%m/%d}/{record.id}/{Path(record.object_key).name}"
            s3.put_object(data=data, mime=record.content_type, key=quarantine_key)
            record.object_key = quarantine_key
            record.status = FileStatus.quarantined.value
            record.av_result_json = {"status": "infected", "signature": verdict.signature}
        else:
            record.status = FileStatus.ready.value
            record.av_result_json = {"status": "clean"}
        record.av_vendor = "clamav"

        self.session.add(
            FileScanResult(
                tenant_id=self.tenant_id,
                file_id=record.id,
                engine="clamav",
                status="infected" if verdict.status == "infected" else "clean",
                signature=verdict.signature,
                scanned_at=datetime.now(timezone.utc),
                raw={"status": verdict.status},
            )
        )
        await self.session.flush()
        if record.status in {FileStatus.clean.value, FileStatus.ready.value}:
            try:
                index_file_content_job.apply_async(kwargs={"tenant_slug": self.session.info.get("tenant"), "file_id": record.id}, countdown=0)
            except Exception:
                await index_file_record(self.session, tenant_id=self.tenant_id, file_id=record.id)
        return record

    async def get_signed_download_url(self, *, file_id: str, purpose: str, ttl: int = 600, actor_id: str | None = None, ip: str | None = None, user_agent: str | None = None) -> str:
        record = await self.session.get(FileRecord, file_id)
        if record is None or record.tenant_id != self.tenant_id:
            raise HTTPException(status_code=404, detail="file_not_found")
        if record.status not in {FileStatus.clean.value, FileStatus.ready.value}:
            raise HTTPException(status_code=409, detail="file_not_ready")
        url = storage.presign_get(key=record.object_key, expires_in=ttl)
        self.session.add(
            FileDownloadLog(
                tenant_id=self.tenant_id,
                file_id=file_id,
                actor_id=actor_id,
                ip=ip,
                user_agent=user_agent,
                purpose=purpose,
            )
        )
        await self.session.flush()
        return url

    async def link_file(self, *, file_id: str, entity_type: str, entity_id: str, role: str) -> FileLink:
        link = FileLink(
            tenant_id=self.tenant_id,
            file_id=file_id,
            entity_type=entity_type,
            entity_id=entity_id,
            role=role,
        )
        self.session.add(link)
        record = await self.session.get(FileRecord, file_id)
        if record is not None and record.tenant_id == self.tenant_id:
            record.entity_type = entity_type
            record.entity_id = entity_id
        await self.session.flush()
        return link

    async def unlink_file(self, *, file_id: str, entity_type: str, entity_id: str, role: str | None = None) -> None:
        stmt = delete(FileLink).where(
            FileLink.tenant_id == self.tenant_id,
            FileLink.file_id == file_id,
            FileLink.entity_type == entity_type,
            FileLink.entity_id == entity_id,
        )
        if role:
            stmt = stmt.where(FileLink.role == role)
        await self.session.execute(stmt)

    async def create_artifact_from_bytes(
        self,
        *,
        payload: bytes,
        filename: str,
        content_type: str,
        job_id: str | None = None,
        step_key: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        created_by: str | None = None,
        entity_type: str = FileEntityType.other.value,
        entity_id: str | None = None,
        role: str = FileLinkRole.artifact.value,
    ) -> FileRecord:
        sha256 = _sha256_bytes(payload)
        ext = Path(filename).suffix or ".bin"
        record_id = str(uuid4())
        display_name = _safe_filename(filename, fallback=f"artifact{ext}")
        if job_id and step_key:
            object_key = f"artifacts/jobs/{job_id}/{step_key}/{record_id}{ext}"
        else:
            object_key = f"artifacts/{datetime.now(timezone.utc):%Y/%m/%d}/{record_id}{ext}"
        s3.put_object(data=payload, mime=content_type, key=object_key)
        metadata = dict(metadata_json or {})
        metadata.setdefault("display_name", display_name)
        resolved_entity_id = entity_id or record_id
        record = FileRecord(
            id=record_id,
            tenant_id=self.tenant_id,
            bucket="main",
            object_key=object_key,
            content_type=content_type,
            size_bytes=len(payload),
            sha256=sha256,
            status=FileStatus.clean.value,
            av_vendor="internal",
            av_result_json={"status": "skipped_internal_artifact"},
            original_filename=display_name,
            entity_type=entity_type,
            entity_id=resolved_entity_id,
            tags=metadata,
            metadata_json=metadata,
            created_by=created_by,
        )
        self.session.add(record)
        await self.session.flush()
        await self.link_file(file_id=record.id, entity_type=entity_type, entity_id=resolved_entity_id, role=role)
        return record

    async def delete_file(self, *, file_id: str) -> FileRecord:
        record = await self.session.get(FileRecord, file_id)
        if record is None or record.tenant_id != self.tenant_id:
            raise HTTPException(status_code=404, detail="file_not_found")
        record.status = FileStatus.deleted.value
        record.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
        return record


# legacy NEXT29 API kept for compatibility
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
        s3_key=storage.build_tenant_key(tenant_id=tenant_id, entity=str(payload.owner_entity_type or "files"), entity_id=str(payload.owner_entity_id or obj.id), file_id=obj.id, filename=payload.filename),
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


async def index_file_record(session: AsyncSession, *, tenant_id: str, file_id: str) -> None:
    record = await session.get(FileRecord, file_id)
    if record is None or record.tenant_id != tenant_id or record.status not in {FileStatus.clean.value, FileStatus.ready.value}:
        return

    file_hash = record.sha256
    existing = (await session.execute(select(FileContentIndex).where(FileContentIndex.file_id == file_id))).scalar_one_or_none()
    if existing is not None and existing.content_sha256 == file_hash and existing.status == FileContentIndexStatus.indexed.value:
        return

    if existing is None:
        existing = FileContentIndex(tenant_id=tenant_id, file_id=file_id, content_sha256=file_hash, mime_type=record.content_type)
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
    existing.status = FileContentIndexStatus.indexed.value if text else FileContentIndexStatus.failed.value
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
        await session.execute(select(FileLink).where(FileLink.tenant_id == tenant_id, FileLink.file_id == file_record.id))
    ).scalars().all()
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


async def issue_download_url(*, session: AsyncSession, tenant_id: str, file_id: str, version_id: str, user_id: str | None, ip: str | None, user_agent: str | None) -> str:
    version = await session.get(FileVersion, version_id)
    if version is None or version.file_id != file_id or version.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="version_not_found")
    if version.status != FileVersionStatus.ready.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="file_not_ready")
    try:
        storage.assert_tenant_key(tenant_id=tenant_id, key=version.s3_key)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden") from exc
    url = storage.presign_get(key=version.s3_key, expires_in=600)
    session.add(DownloadLog(tenant_id=tenant_id, user_id=user_id, file_id=file_id, version_id=version_id, ip=ip, user_agent=user_agent))
    await session.flush()
    return url
