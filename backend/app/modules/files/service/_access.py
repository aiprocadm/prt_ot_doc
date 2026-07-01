"""FileService access-control mixin (ARCH-4 slice 10 split)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.security import AccessContext
from app.modules.files.models import (
    FileRecord,
)
from app.modules.files.service._base import (
    resolve_presign_ttl,
)
from app.services.audit import AuditService


class AccessMixin:
    """Role/company scoping, audit logging and signed-url TTL resolution."""

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
