"""Journal & plan-task ORM models — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

import enum
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Date,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    SoftDeleteMixin,
    TenantBaseModel,
    native_enum,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    from app.models.models import (
        Company,
        Person,
    )


class JournalType(str, enum.Enum):
    INTRODUCTORY = "introductory"
    PRIMARY = "primary"
    REPEATED = "repeated"
    TARGET = "target"
    FIRE_SAFETY = "fire_safety"
    UNSCHEDULED = "unscheduled"


class Journal(TenantBaseModel, SoftDeleteMixin):
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("company.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255))
    journal_type: Mapped[JournalType] = mapped_column(native_enum(JournalType), nullable=False)
    started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    company: Mapped[Company | None] = relationship("Company", backref="journals")

    __table_args__ = (Index("ix_journal_company", "tenant_id", "company_id"),)


class JournalEntry(TenantBaseModel, SoftDeleteMixin):
    journal_id: Mapped[str] = mapped_column(ForeignKey("journal.id"), nullable=False, index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    entry_type: Mapped[JournalType] = mapped_column(native_enum(JournalType), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    instructor: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    journal: Mapped[Journal] = relationship(backref="entries")
    person: Mapped[Person] = relationship(backref="journal_entries")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "journal_id",
            "person_id",
            "entry_type",
            "entry_date",
            name="uq_journal_entry_unique_person_date",
        ),
        Index("ix_journal_entry_type", "tenant_id", "entry_type"),
    )


class PlanTaskStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class PlanTask(TenantBaseModel):
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[PlanTaskStatus] = mapped_column(
        Enum(PlanTaskStatus), nullable=False, default=PlanTaskStatus.OPEN
    )
