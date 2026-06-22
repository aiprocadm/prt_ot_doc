from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import AccessContext
from app.domains.files import s3
from app.modules.files import av, extractors, storage
from app.modules.files.models import (
    AVStatus,
    DownloadLog,
    FileContentIndex,
    FileContentIndexStatus,
    FileDownloadLog,
    FileEntityType,
    FileLink,
    FileLinkRole,
    FileObject,
    FileRecord,
    FileScanResult,
    FileStatus,
    FileTextIndex,
    FileVersion,
    FileVersionStatus,
    TextIndexStatus,
)
from app.modules.search.models import SearchDocument
from app.services.audit import AuditService
from app.services.outbox import OutboxService
from app.tasks import av_scan_file_job, index_file_content_job

MAX_INDEX_BYTES = 25 * 1024 * 1024
MAX_INDEX_CHARS = 500_000

logger = logging.getLogger(__name__)

_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE), "[masked_email]"),
    (
        re.compile(r"(?:\+7|8)?[\s\-()]?\d{3}[\s\-()]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"),
        "[masked_phone]",
    ),
    (re.compile(r"\b\d{4}\s?\d{6}\b"), "[masked_passport]"),
)


def resolve_presign_ttl(requested_ttl: int | None = None) -> int:
    settings = get_settings()
    policy_ttl = int(getattr(settings, "presign_download_ttl_seconds", 600))
    policy_ttl = max(60, min(policy_ttl, 900))
    if requested_ttl is None:
        return policy_ttl
    return max(60, min(int(requested_ttl), policy_ttl))


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


_DANGEROUS_TRAILING_EXTENSIONS = {
    "bat",
    "cmd",
    "com",
    "exe",
    "hta",
    "jar",
    "js",
    "jse",
    "lnk",
    "msi",
    "ps1",
    "scr",
    "vbe",
    "vbs",
}


def _reject_dangerous_double_extension(filename: str, *, allowed_extensions: set[str]) -> None:
    suffixes = [part.lower() for part in Path(filename).suffixes if part]
    if len(suffixes) < 2:
        return
    normalized = [part.lstrip(".") for part in suffixes]
    if normalized[-1] not in _DANGEROUS_TRAILING_EXTENSIONS:
        return
    if normalized[-2] in allowed_extensions:
        raise HTTPException(status_code=400, detail="dangerous_double_extension")


def _mask_pii(text: str) -> str:
    masked = text
    for pattern, replacement in _PII_PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked


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

    @staticmethod
    def _is_client_role(role: str | None) -> bool:
        return role in {"client_admin", "client_user"}

    @staticmethod
    def _extract_company_id(record: FileRecord) -> str | None:
        metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
        tags = record.tags if isinstance(record.tags, dict) else {}
        return str(metadata.get("company_id") or tags.get("company_id") or "").strip() or None

    async def _audit_file_action(
        self,
        *,
        action: str,
        object_id: str,
        user_id: str | None,
        ip: str | None,
        user_agent: str | None,
        request_id: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        await AuditService(self.session).log_event(
            tenant_id=self.tenant_id,
            action=action,
            object_type="file",
            object_id=object_id,
            user_id=user_id,
            ip=ip or "unknown",
            request_id=request_id,
            user_agent=user_agent,
            details=details or {},
        )

    def _enforce_client_company_scope(
        self,
        *,
        record: FileRecord,
        access: AccessContext | None = None,
        actor_role: str | None = None,
        actor_company_id: str | None = None,
    ) -> None:
        role = getattr(access, "role", None) if access is not None else actor_role
        company_id = access.company_id if access is not None else actor_company_id
        if not self._is_client_role(role):
            return
        record_company_id = self._extract_company_id(record)
        if not record_company_id:
            return
        if not company_id or str(company_id) != str(record_company_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="file_company_forbidden"
            )

    async def _enforce_company_scope(
        self,
        *,
        record: FileRecord,
        action: str,
        actor_role: str | None,
        actor_company_id: str | None,
        access: AccessContext | None = None,
        on_deny_audit: dict[str, Any] | None = None,
    ) -> None:
        record_company_id = self._extract_company_id(record)
        if not record_company_id:
            return
        deny_exc: HTTPException | None = None
        role = actor_role or (access.role if access is not None else None)
        if self._is_client_role(role):
            if not actor_company_id or str(actor_company_id) != str(record_company_id):
                deny_exc = HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="file_company_forbidden"
                )

        if deny_exc is None and access is not None and self._is_client_role(access.role):
            try:
                access.ensure_company_access(record_company_id, action=action)
            except HTTPException as exc:
                deny_exc = exc

        if deny_exc is not None:
            if on_deny_audit:
                await self._audit_file_action(**on_deny_audit)
            raise deny_exc

    async def _enforce_client_company_scope_with_audit(
        self,
        *,
        record: FileRecord,
        deny_action: str | None,
        actor_id: str | None,
        ip: str | None,
        user_agent: str | None,
        request_id: str | None,
        details: dict[str, Any] | None = None,
        access: AccessContext | None = None,
        actor_role: str | None = None,
        actor_company_id: str | None = None,
    ) -> None:
        try:
            self._enforce_client_company_scope(
                record=record,
                access=access,
                actor_role=actor_role,
                actor_company_id=actor_company_id,
            )
        except HTTPException:
            if deny_action:
                await self._audit_file_action(
                    action=deny_action,
                    object_id=record.id,
                    user_id=actor_id,
                    ip=ip,
                    user_agent=user_agent,
                    request_id=request_id,
                    details=details or {"reason": "company_scope_mismatch"},
                )
            raise

    async def ensure_record_access(
        self,
        *,
        record: FileRecord,
        actor_role: str | None,
        actor_company_id: str | None,
    ) -> None:
        self._enforce_client_company_scope(
            record=record, actor_role=actor_role, actor_company_id=actor_company_id
        )
        await self._enforce_company_scope(
            record=record,
            action="read file",
            actor_role=actor_role,
            actor_company_id=actor_company_id,
        )

    def _resolve_signed_url_ttl(self, requested_ttl: int | None = None) -> int:
        return resolve_presign_ttl(requested_ttl)

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
        _reject_dangerous_double_extension(
            filename,
            allowed_extensions={
                ext.lower().lstrip(".") for ext in settings.file_allowed_extensions
            },
        )
        lower_name = filename.lower()
        if lower_name.endswith((".docm", ".xlsm")):
            raise HTTPException(status_code=400, detail="macro_enabled_documents_are_forbidden")
        declared_sha = (
            (metadata_json or {}).get("sha256") if isinstance(metadata_json, dict) else None
        )
        if declared_sha:
            dedupe = (
                await self.session.execute(
                    select(FileRecord)
                    .where(
                        FileRecord.tenant_id == self.tenant_id,
                        FileRecord.sha256 == declared_sha,
                        FileRecord.status == FileStatus.clean.value,
                        FileRecord.deleted_at.is_(None),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if dedupe is not None:
                if metadata_json:
                    merged = dict(dedupe.metadata_json or {})
                    merged.update(metadata_json)
                    dedupe.metadata_json = merged
                    dedupe.tags = merged
                    await self.session.flush()
                return dedupe, "", 0
        object_id = str(uuid4())
        object_key = storage.build_tenant_key(
            tenant_id=self.tenant_id, file_id=object_id, filename=_safe_filename(filename)
        )
        record = FileRecord(
            id=object_id,
            tenant_id=self.tenant_id,
            bucket="ptd",
            object_key=object_key,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256="",
            status="uploading",
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
        upload_url = s3.generate_presigned_put_url(
            object_key, expires_in=ttl, content_type=content_type
        )
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
        _reject_dangerous_double_extension(
            filename,
            allowed_extensions={
                ext.lower().lstrip(".") for ext in settings.file_allowed_extensions
            },
        )

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

    async def finalize_upload(
        self,
        *,
        file_id: str,
        actor_id: str | None = None,
        actor_role: str | None = None,
        actor_company_id: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> FileRecord:
        record = await self.session.get(FileRecord, file_id)
        if record is None or record.tenant_id != self.tenant_id:
            raise HTTPException(status_code=404, detail="file_not_found")
        await self._enforce_client_company_scope_with_audit(
            record=record,
            deny_action="file.finalize.denied",
            actor_id=actor_id,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
            details={"reason": "company_scope_mismatch"},
            actor_role=actor_role,
            actor_company_id=actor_company_id,
        )
        await self._enforce_company_scope(
            record=record,
            action="finalize file upload",
            actor_role=actor_role,
            actor_company_id=actor_company_id,
            on_deny_audit={
                "action": "file.finalize.denied",
                "object_id": file_id,
                "user_id": actor_id,
                "ip": ip,
                "user_agent": user_agent,
                "request_id": request_id,
                "details": {"reason": "company_scope_mismatch"},
            },
        )
        metadata = s3.head_object(key=record.object_key)
        if metadata is None:
            raise HTTPException(status_code=409, detail="object_not_found")
        with s3.stream_object(key=record.object_key) as body:
            data = body.read()
        record.size_bytes = int(metadata.get("size") or len(data))
        record.content_type = str(metadata.get("content_type") or record.content_type)
        record.sha256 = _sha256_bytes(data)
        record.status = "scanning"
        await self.session.flush()
        await OutboxService(self.session).add_event(
            tenant_id=self.tenant_id,
            event_type="FileUploaded",
            aggregate_type="file",
            aggregate_id=record.id,
            payload={
                "tenant_id": self.tenant_id,
                "file_id": record.id,
                "sha256": record.sha256,
                "status": record.status,
                "object_key": record.object_key,
            },
        )
        try:
            av_scan_file_job.delay(self.tenant_id, file_id)
        except Exception:
            await self.av_scan_file(file_id=file_id)
        await self._audit_file_action(
            action="file.finalize.success",
            object_id=record.id,
            user_id=actor_id,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
            details={"status": record.status, "object_key": record.object_key},
        )
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
            record.status = "scanning"
            record.av_result_json = {"status": "unavailable"}
            await self.session.flush()
            return record

        try:
            with NamedTemporaryFile(delete=True) as tmp:
                tmp.write(data)
                tmp.flush()
                verdict = av.scan_file(Path(tmp.name))
        except Exception as exc:
            logger.exception(
                "files.av.scan_failed",
                extra={"file_id": file_id, "error_class": exc.__class__.__name__},
            )
            record.status = FileStatus.scanning.value
            record.av_result_json = {"status": "error", "error_class": exc.__class__.__name__}
            self.session.add(
                FileScanResult(
                    tenant_id=self.tenant_id,
                    file_id=record.id,
                    engine="clamav",
                    status="error",
                    signature=None,
                    scanned_at=datetime.now(timezone.utc),
                    raw={"status": "error", "error_class": exc.__class__.__name__},
                )
            )
            await self.session.flush()
            return record

        if verdict.status == "infected":
            record.status = FileStatus.infected.value
            record.av_result_json = {"status": "infected", "signature": verdict.signature}
        else:
            record.status = FileStatus.clean.value
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
        await OutboxService(self.session).add_event(
            tenant_id=self.tenant_id,
            event_type="FileScanned",
            aggregate_type="file",
            aggregate_id=record.id,
            payload={
                "tenant_id": self.tenant_id,
                "file_id": record.id,
                "status": record.status,
                "scan_status": verdict.status,
                "signature": verdict.signature,
            },
        )
        await self.session.flush()
        if record.status in {FileStatus.clean.value}:
            try:
                index_file_content_job.apply_async(
                    kwargs={"tenant_slug": self.session.info.get("tenant"), "file_id": record.id},
                    countdown=0,
                )
            except Exception:
                await index_file_record(self.session, tenant_id=self.tenant_id, file_id=record.id)
        return record

    async def get_signed_download_url(
        self,
        *,
        file_id: str,
        purpose: str,
        ttl: int = 600,
        actor_id: str | None = None,
        actor_role: str | None = None,
        actor_company_id: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        access: AccessContext | None = None,
    ) -> str:
        record = await self.session.get(FileRecord, file_id)
        if record is None or record.tenant_id != self.tenant_id:
            raise HTTPException(status_code=404, detail="file_not_found")
        await self._enforce_client_company_scope_with_audit(
            record=record,
            deny_action="file.download_url.denied",
            actor_id=actor_id,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
            details={"reason": "company_scope_mismatch", "purpose": purpose},
            access=access,
            actor_role=actor_role,
            actor_company_id=actor_company_id,
        )
        await self._enforce_company_scope(
            record=record,
            action="read file",
            actor_role=actor_role,
            actor_company_id=actor_company_id,
            access=access,
            on_deny_audit={
                "action": "file.download_url.denied",
                "object_id": file_id,
                "user_id": actor_id,
                "ip": ip,
                "user_agent": user_agent,
                "request_id": request_id,
                "details": {"reason": "company_scope_mismatch", "purpose": purpose},
            },
        )
        if record.status != FileStatus.clean.value:
            await self._audit_file_action(
                action="file.download_url.denied",
                object_id=file_id,
                user_id=actor_id,
                ip=ip,
                user_agent=user_agent,
                request_id=request_id,
                details={"reason": "file_not_clean", "purpose": purpose, "status": record.status},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="file_not_clean")
        if "/" in (record.object_key or ""):
            try:
                storage.assert_tenant_key(tenant_id=self.tenant_id, key=record.object_key)
            except PermissionError as exc:
                await self._audit_file_action(
                    action="file.download_url.denied",
                    object_id=file_id,
                    user_id=actor_id,
                    ip=ip,
                    user_agent=user_agent,
                    request_id=request_id,
                    details={"reason": "tenant_key_mismatch", "purpose": purpose},
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
                ) from exc
        ttl = self._resolve_signed_url_ttl(ttl)
        url = storage.presign_get(key=record.object_key, expires_in=ttl)
        self.session.add(
            FileDownloadLog(
                tenant_id=self.tenant_id,
                file_id=file_id,
                actor_id=actor_id,
                ip=ip,
                user_agent=user_agent,
                purpose=purpose,
                action="presigned_url_issued",
            )
        )
        await self._audit_file_action(
            action="file.download_url.issued",
            object_id=file_id,
            user_id=actor_id,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
            details={"purpose": purpose, "ttl_seconds": ttl},
        )
        await self.session.flush()
        return url

    async def link_file(
        self,
        *,
        file_id: str,
        entity_type: str,
        entity_id: str,
        role: str,
        actor_id: str | None = None,
        actor_role: str | None = None,
        actor_company_id: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        access: AccessContext | None = None,
    ) -> FileLink:
        guarded_roles = {"output", "signature", "receipt"}
        record = await self.session.get(FileRecord, file_id)
        if record is None or record.tenant_id != self.tenant_id:
            raise HTTPException(status_code=404, detail="file_not_found")
        await self._enforce_client_company_scope_with_audit(
            record=record,
            deny_action="file.link.denied",
            actor_id=actor_id,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
            details={"reason": "company_scope_mismatch", "role": role},
            access=access,
            actor_role=actor_role,
            actor_company_id=actor_company_id,
        )
        await self._enforce_company_scope(
            record=record,
            action="link file",
            actor_role=actor_role,
            actor_company_id=actor_company_id,
            access=access,
            on_deny_audit={
                "action": "file.link.denied",
                "object_id": file_id,
                "user_id": actor_id,
                "ip": ip,
                "user_agent": user_agent,
                "request_id": request_id,
                "details": {
                    "reason": "company_scope_mismatch",
                    "role": role,
                    "entity_type": entity_type,
                },
            },
        )
        if role in guarded_roles and record.status != FileStatus.clean.value:
            await self._audit_file_action(
                action="file.link.denied",
                object_id=file_id,
                user_id=actor_id,
                ip=ip,
                user_agent=user_agent,
                request_id=request_id,
                details={"reason": "file_not_clean", "role": role, "status": record.status},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="file_not_clean")
        link = FileLink(
            tenant_id=self.tenant_id,
            file_id=file_id,
            entity_type=entity_type,
            entity_id=entity_id,
            role=role,
        )
        self.session.add(link)
        record.entity_type = entity_type
        record.entity_id = entity_id
        await self.session.flush()
        return link

    async def unlink_file_by_id(self, *, file_id: str, link_id: str) -> None:
        await self.session.execute(
            delete(FileLink).where(
                FileLink.tenant_id == self.tenant_id,
                FileLink.file_id == file_id,
                FileLink.id == link_id,
            )
        )

    async def abort_upload(self, *, file_id: str) -> None:
        record = await self.session.get(FileRecord, file_id)
        if record is None or record.tenant_id != self.tenant_id:
            raise HTTPException(status_code=404, detail="file_not_found")
        if record.status not in {FileStatus.uploading.value, FileStatus.uploaded.value}:
            raise HTTPException(status_code=409, detail="upload_not_abortable")
        try:
            s3.delete_object(key=record.object_key)
        except Exception:
            logger.warning("files.abort_upload.cleanup_failed", extra={"file_id": file_id})
        record.status = FileStatus.deleted.value
        record.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def unlink_file(
        self, *, file_id: str, entity_type: str, entity_id: str, role: str | None = None
    ) -> None:
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
        object_key = storage.build_tenant_key(
            tenant_id=self.tenant_id, file_id=record_id, filename=f"{record_id}{ext}"
        )
        s3.put_object(data=payload, mime=content_type, key=object_key)
        metadata = dict(metadata_json or {})
        metadata.setdefault("display_name", display_name)
        resolved_entity_id = entity_id or record_id
        record = FileRecord(
            id=record_id,
            tenant_id=self.tenant_id,
            bucket="ptd",
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
        await self.link_file(
            file_id=record.id, entity_type=entity_type, entity_id=resolved_entity_id, role=role
        )
        return record

    async def delete_file(
        self,
        *,
        file_id: str,
        actor_id: str | None = None,
        actor_role: str | None = None,
        actor_company_id: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        access: AccessContext | None = None,
    ) -> FileRecord:
        record = await self.session.get(FileRecord, file_id)
        if record is None or record.tenant_id != self.tenant_id:
            raise HTTPException(status_code=404, detail="file_not_found")
        await self._enforce_client_company_scope_with_audit(
            record=record,
            deny_action="file.delete.denied",
            actor_id=actor_id,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
            details={"reason": "company_scope_mismatch"},
            access=access,
            actor_role=actor_role,
            actor_company_id=actor_company_id,
        )
        await self._enforce_company_scope(
            record=record,
            action="delete file",
            actor_role=actor_role,
            actor_company_id=actor_company_id,
            access=access,
            on_deny_audit={
                "action": "file.delete.denied",
                "object_id": file_id,
                "user_id": actor_id,
                "ip": ip,
                "user_agent": user_agent,
                "request_id": request_id,
                "details": {"reason": "company_scope_mismatch"},
            },
        )
        record.status = FileStatus.deleted.value
        record.deleted_at = datetime.now(timezone.utc)
        await self._audit_file_action(
            action="file.delete.success",
            object_id=record.id,
            user_id=actor_id,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
            details={"object_key": record.object_key},
        )
        await self.session.flush()
        return record


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
