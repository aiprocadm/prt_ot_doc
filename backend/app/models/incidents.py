"""Incident-domain ORM models — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
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
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    from app.models.models import (
        Company,
        Person,
        Site,
        User,
    )
    from app.models.packages import DocumentPack


class IncidentSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IncidentType(str, enum.Enum):
    ACCIDENT = "accident"
    MICROTRAUMA = "microtrauma"
    NEAR_MISS = "near_miss"
    UNSAFE_CONDITION = "unsafe_condition"


class IncidentStatus(str, enum.Enum):
    REPORTED = "reported"
    INVESTIGATING = "investigating"
    ACTIONS = "corrective_actions"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class IncidentStage(str, enum.Enum):
    REGISTRATION = "registration"
    INVESTIGATION = "investigation"
    ACTION_PLAN = "action_plan"
    FOLLOW_UP = "follow_up"
    CLOSED = "closed"


class Incident(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "incident"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    incident_type: Mapped[IncidentType] = mapped_column(
        Enum(IncidentType, name="incidenttype"), nullable=False, default=IncidentType.ACCIDENT
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"), nullable=False, index=True)
    location_description: Mapped[str | None] = mapped_column(String(255))
    severity: Mapped[IncidentSeverity] = mapped_column(
        Enum(IncidentSeverity, name="incidentseverity"),
        nullable=False,
        default=IncidentSeverity.MEDIUM,
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incidentstatus"), nullable=False, default=IncidentStatus.REPORTED
    )
    investigation_stage: Mapped[IncidentStage] = mapped_column(
        Enum(IncidentStage, name="incidentstage"),
        nullable=False,
        default=IncidentStage.REGISTRATION,
    )
    pack_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_pack.id", ondelete="SET NULL"), nullable=True, index=True
    )

    company: Mapped[Company] = relationship(backref="incidents")
    site: Mapped[Site] = relationship(backref="incidents")
    pack: Mapped[DocumentPack | None] = relationship("DocumentPack", backref="incidents")
    logs: Mapped[list["IncidentLog"]] = relationship(
        "IncidentLog",
        back_populates="incident",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="IncidentLog.created_at",
    )
    participants: Mapped[list["IncidentPerson"]] = relationship(
        "app.models.incidents.IncidentPerson",
        back_populates="incident",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_incident_company", "tenant_id", "company_id"),
        Index("ix_incident_site", "tenant_id", "site_id"),
        Index("ix_incident_status", "tenant_id", "status"),
        Index("ix_incident_occurred_at", "occurred_at"),
    )


class IncidentPersonRole(str, enum.Enum):
    VICTIM = "victim"
    WITNESS = "witness"
    PARTICIPANT = "participant"


class IncidentPerson(TenantBaseModel):
    __tablename__ = "incident_person"

    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incident.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[IncidentPersonRole] = mapped_column(
        Enum(IncidentPersonRole, name="incidentpersonrole"),
        nullable=False,
        default=IncidentPersonRole.VICTIM,
    )

    incident: Mapped[Incident] = relationship("Incident", back_populates="participants")
    person: Mapped[Person] = relationship("Person", backref="incident_links")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "incident_id",
            "person_id",
            "role",
            name="uq_incident_person_role",
        ),
        Index("ix_incident_person_role", "role"),
    )


class IncidentLog(TenantBaseModel):
    __tablename__ = "incident_log"

    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incident.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stage: Mapped[IncidentStage] = mapped_column(
        Enum(IncidentStage, name="incidentlogstage"), nullable=False
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incidentlogstatus"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    incident: Mapped[Incident] = relationship("Incident", back_populates="logs")
    author: Mapped[User | None] = relationship("User")

    __table_args__ = (
        Index("ix_incident_log_incident", "tenant_id", "incident_id"),
        Index("ix_incident_log_stage", "tenant_id", "stage"),
    )
