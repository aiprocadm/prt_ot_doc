"""FileService download/link/artifact/delete mixin (ARCH-4 slice 10 split)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete

from app.core.security import AccessContext
from app.domains.files import s3
from app.modules.files import storage
from app.modules.files.models import (
    FileDownloadLog,
    FileEntityType,
    FileLink,
    FileLinkRole,
    FileRecord,
    FileStatus,
)
from app.modules.files.service._base import (
    _safe_filename,
    _sha256_bytes,
    logger,
)


class FileOpsMixin:
    """Signed download URLs, link/unlink, abort, artifact-from-bytes and delete."""

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
