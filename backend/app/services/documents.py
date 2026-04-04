from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar, Mapping

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus, DocumentVersion
from app.services.audit import AuditService
from app.services.domain_hooks import on_document_signed_create_followup_task
from app.services.events import EventType
from app.services.outbox import OutboxService

_ALLOWED_STATUS_TRANSITIONS: Mapping[
    DocumentStatus, frozenset[DocumentStatus]
] = {
    DocumentStatus.DRAFT: frozenset({DocumentStatus.GENERATED, DocumentStatus.REVOKED}),
    DocumentStatus.GENERATED: frozenset({DocumentStatus.REVIEW, DocumentStatus.REVOKED}),
    DocumentStatus.REVIEW: frozenset({DocumentStatus.APPROVED, DocumentStatus.REVOKED}),
    DocumentStatus.APPROVED: frozenset({DocumentStatus.SIGNED, DocumentStatus.REVOKED}),
    DocumentStatus.SIGNED: frozenset({DocumentStatus.ARCHIVED, DocumentStatus.REVOKED}),
    DocumentStatus.ARCHIVED: frozenset(),
    DocumentStatus.REVOKED: frozenset(),
}


def validate_transition(
    current_status: DocumentStatus, target_status: DocumentStatus
) -> bool:
    """Return ``True`` when a status transition is permitted."""

    if current_status == target_status:
        return True
    allowed_targets = _ALLOWED_STATUS_TRANSITIONS.get(
        current_status, frozenset()
    )
    return target_status in allowed_targets


class DocumentWorkflowError(Exception):
    """Base error for document workflow operations."""


class DocumentNotFoundError(DocumentWorkflowError):
    """Raised when the requested document does not exist."""

    def __init__(self, document_id: str) -> None:
        super().__init__(f"Document '{document_id}' not found")
        self.document_id = document_id


class InvalidStatusTransitionError(DocumentWorkflowError):
    """Raised when a status transition violates workflow rules."""

    def __init__(
        self,
        *,
        document_id: str,
        current_status: DocumentStatus,
        target_status: DocumentStatus,
    ) -> None:
        message = (
            "Cannot transition document "
            f"'{document_id}' from {current_status.value} to {target_status.value}"
        )
        super().__init__(message)
        self.document_id = document_id
        self.current_status = current_status
        self.target_status = target_status


class DocumentVersionDeletionError(DocumentWorkflowError):
    """Raised when attempting to delete an immutable document version."""

    def __init__(self) -> None:
        super().__init__("Document versions are immutable and cannot be deleted")


class DocumentVersionUpdateError(DocumentWorkflowError):
    """Raised when attempting to modify an immutable document version."""

    def __init__(self) -> None:
        super().__init__("Document versions are immutable and cannot be modified")


@dataclass(slots=True)
class DocumentWorkflowService:
    """Business logic around document lifecycle transitions."""

    session: AsyncSession

    _ALLOWED_TRANSITIONS: ClassVar[
        Mapping[DocumentStatus, frozenset[DocumentStatus]]
    ] = _ALLOWED_STATUS_TRANSITIONS

    @classmethod
    def validate_transition(
        cls,
        current_status: DocumentStatus,
        target_status: DocumentStatus,
    ) -> bool:
        """Return ``True`` if a transition between statuses is permitted."""

        return validate_transition(current_status, target_status)

    async def get_document(self, *, document_id: str, tenant_id: str) -> Document:
        """Return a document ensuring it belongs to the provided tenant."""

        stmt = select(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        document = result.scalar_one_or_none()
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    async def change_status(
        self,
        *,
        document_id: str,
        tenant_id: str,
        new_status: DocumentStatus,
        actor_id: str | None,
        ip: str,
        user_agent: str | None = None,
    ) -> Document:
        """Apply a status transition enforcing workflow rules and auditing."""

        document = await self.get_document(document_id=document_id, tenant_id=tenant_id)
        current_status = document.status

        if current_status == new_status:
            return document

        if not self.validate_transition(current_status, new_status):
            await self._log_status_change(
                document=document,
                previous_status=current_status,
                new_status=new_status,
                actor_id=actor_id,
                outcome="rejected",
                user_agent=user_agent,
                ip=ip,
            )
            raise InvalidStatusTransitionError(
                document_id=document_id,
                current_status=current_status,
                target_status=new_status,
            )

        document.status = new_status
        await self.session.flush()
        await self._log_status_change(
            document=document,
            previous_status=current_status,
            new_status=new_status,
            actor_id=actor_id,
            outcome="success",
            user_agent=user_agent,
            ip=ip,
        )
        return document

    async def forbid_version_deletion(self) -> None:
        """Provide a single entry point signaling that deletion is unsupported."""

        raise DocumentVersionDeletionError()

    async def _log_status_change(
        self,
        *,
        document: Document,
        previous_status: DocumentStatus,
        new_status: DocumentStatus,
        actor_id: str | None,
        outcome: str,
        metadata_changes: Mapping[str, Any] | None = None,
        user_agent: str | None = None,
        ip: str,
    ) -> None:
        audit_service = AuditService(self.session)
        details: dict[str, Any] = {
            "from": previous_status.value,
            "to": new_status.value,
            "outcome": outcome,
        }
        if metadata_changes:
            details["metadata"] = dict(metadata_changes)

        await audit_service.log_event(
            tenant_id=document.tenant_id,
            action="document.status_change",
            object_type="document",
            object_id=document.id,
            user_id=actor_id,
            ip=ip,
            user_agent=user_agent,
            changed_fields={"status": {"from": previous_status.value, "to": new_status.value}},
            details=details,
        )

        if outcome == "success" and new_status == DocumentStatus.SIGNED:
            version_id = await self._get_latest_version_id(document.id)
            await audit_service.log_event(
                tenant_id=document.tenant_id,
                action="sign",
                object_type="document",
                object_id=document.id,
                user_id=actor_id,
                ip=ip,
                user_agent=user_agent,
                changed_fields={"status": {"from": previous_status.value, "to": new_status.value}},
                details={"status": new_status.value},
            )
            outbox = OutboxService(self.session)
            await outbox.enqueue(
                tenant_id=document.tenant_id,
                event_type=EventType.DOCUMENT_SIGNED.value,
                payload={
                    "tenant_id": str(document.tenant_id),
                    "actor_id": actor_id,
                    "occurred_at": datetime.now(tz=timezone.utc),
                    "document_id": document.id,
                    "document_version_id": version_id,
                    "status": new_status.value,
                    "signed_at": datetime.now(tz=timezone.utc),
                    "signed_file_id": document.signed_file_id,
                },
            )
            await on_document_signed_create_followup_task(
                self.session,
                document=document,
                actor_id=actor_id,
            )

    async def _get_latest_version_id(self, document_id: str) -> str:
        stmt = (
            select(DocumentVersion.id)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.created_at.desc())
            .limit(1)
        )
        version_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if version_id is None:
            raise DocumentWorkflowError(
                f"Document version missing for document '{document_id}'"
            )
        return str(version_id)


@event.listens_for(DocumentVersion, "before_update", propagate=True)
def _prevent_document_version_update(*_args, **_kwargs) -> None:
    """Disallow in-place modifications for persisted document versions."""

    raise DocumentVersionUpdateError()
