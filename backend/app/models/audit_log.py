"""Audit-log ORM models (incl. AuditLog event listeners) — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    TenantBaseModel,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    pass


class AuditLog(TenantBaseModel):
    """Immutable audit trail entry capturing key security events."""

    when: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    request_id: Mapped[str | None] = mapped_column(String(128))
    session_id: Mapped[str | None] = mapped_column(String(128))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    resource_attrs: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    before_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    after_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    changed_fields: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    actor_role_codes: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_auditlog_action", "action", "when"),
        Index("ix_auditlog_object", "object_type", "object_id", "when"),
        Index("ix_auditlog_actor", "user_id", "when"),
        Index("ix_auditlog_corr", "correlation_id"),
        Index("ix_auditlog_when", "when"),
    )


@event.listens_for(AuditLog, "before_update", propagate=True)
def _prevent_auditlog_update(*_args, **_kwargs) -> None:
    raise RuntimeError("Audit logs are append-only")


@event.listens_for(AuditLog, "before_delete", propagate=True)
def _prevent_auditlog_delete(*_args, **_kwargs) -> None:
    raise RuntimeError("Audit logs are append-only")


class AuditExportJob(TenantBaseModel):
    __tablename__ = "audit_export_job"

    filters: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    signed_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_audit_export_job_tenant_status", "tenant_id", "status"),)


class SecurityAuditLog(TenantBaseModel):
    """Authorization decision log (allow/deny) for RBAC+ABAC enforcement."""

    when: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    user_agent: Mapped[str | None] = mapped_column(String(256))
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    __table_args__ = (
        Index("ix_security_auditlog_action", "action"),
        Index("ix_security_auditlog_decision", "decision"),
        Index("ix_security_auditlog_resource", "resource_type", "resource_id"),
        Index("ix_security_auditlog_when", "when"),
    )


# WarehousePPE ORM class was removed in СИЗ Срез-1 (2026-06-11): dead orphan
# from initial_schema (item_name+quantity+location) without endpoints/services/
# relationships. Its table (warehouseppe) was dropped by migration sz02
# (20260611_sz02_drop_ppe_family_b_tables).
