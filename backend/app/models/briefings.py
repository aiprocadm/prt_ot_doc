"""Briefing-domain ORM models — extracted from models.py (ARCH-2 decomposition).

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
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    SoftDeleteMixin,
    TenantBaseModel,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    pass


class BriefingTemplate(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "briefing_templates"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    briefing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    validity_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    require_signature_code: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_briefing_templates_code"),)


class BriefingJournal(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "briefing_journals"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("department.id", ondelete="SET NULL"), nullable=True
    )
    journal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_briefing_journals_code"),)


class BriefingEntry(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "briefing_entries"

    briefing_journal_id: Mapped[str] = mapped_column(
        ForeignKey("briefing_journals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    briefing_template_id: Mapped[str | None] = mapped_column(
        ForeignKey("briefing_templates.id", ondelete="SET NULL"), nullable=True
    )
    person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True
    )
    instructor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("department.id", ondelete="SET NULL"), nullable=True
    )
    workplace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workplace.id", ondelete="SET NULL"), nullable=True
    )
    briefing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    briefing_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class BriefingSignature(TenantBaseModel):
    __tablename__ = "briefing_signatures"
    __table_args__ = (
        # Анти-гонка: один signer_type на briefing_entry (миграция ed03).
        Index(
            "uq_briefing_signatures_entry_signer",
            "briefing_entry_id",
            "signer_type",
            unique=True,
        ),
    )

    briefing_entry_id: Mapped[str] = mapped_column(
        ForeignKey("briefing_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    signer_type: Mapped[str] = mapped_column(String(16), nullable=False)
    signer_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    signer_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    signature_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="internal_simple"
    )
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )
    signature_payload: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
