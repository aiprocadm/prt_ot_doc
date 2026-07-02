"""FileService upload-lifecycle mixin (ARCH-4 slice 10 split)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.config import get_settings
from app.modules.files import av, s3, storage
from app.modules.files.models import (
    AVStatus,
    FileRecord,
    FileScanResult,
    FileStatus,
    FileVersion,
    FileVersionStatus,
    TextIndexStatus,
)
from app.modules.files.service._base import (
    _reject_dangerous_double_extension,
    _safe_filename,
    _sha256_bytes,
    logger,
)
from app.modules.files.service._functions import index_file_record
from app.services.outbox import OutboxService
from app.tasks import av_scan_file_job, index_file_content_job

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import AccessContext


class UploadMixin:
    """Upload session create / new-version / finalize and AV scan."""

    if TYPE_CHECKING:
        # Mixin contract (no runtime effect): state from FileService.__init__
        # plus helpers provided by AccessMixin (_access.py). Signatures mirror
        # the AccessMixin definitions so the staged mypy gate checks call-sites.
        session: AsyncSession
        tenant_id: str

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
        ) -> None: ...

        async def _enforce_company_scope(
            self,
            *,
            record: FileRecord,
            action: str,
            actor_role: str | None,
            actor_company_id: str | None,
            access: AccessContext | None = None,
            on_deny_audit: dict[str, Any] | None = None,
        ) -> None: ...

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
        ) -> None: ...

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
