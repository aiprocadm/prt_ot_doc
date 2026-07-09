"""Medical-domain ORM models — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    SoftDeleteMixin,
    TenantBaseModel,
    native_enum,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    from app.models.models import (
        Person,
        Position,
    )


class MedicalExamKind(str, enum.Enum):
    """Types of occupational medical examination."""

    PERIODIC = "periodic"
    PRELIMINARY = "preliminary"
    PSYCHIATRIC = "psychiatric"
    FLUOROGRAPHY = "fluorography"
    HEALTH_BOOK = "health_book"


class MedicalFitness(str, enum.Enum):
    """Medical fitness verdict for a person."""

    FIT = "fit"
    FIT_WITH_RESTRICTIONS = "fit_with_restrictions"
    UNFIT = "unfit"


class MedicalReferralStatus(str, enum.Enum):
    """Lifecycle state of a medical-exam referral (направление)."""

    ISSUED = "issued"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MedicalSuspensionStatus(str, enum.Enum):
    """State of a medical suspension (отстранение) record."""

    ACTIVE = "active"
    LIFTED = "lifted"


class MedicalSuspensionReason(str, enum.Enum):
    """Why a person is medically suspended from work."""

    UNFIT = "unfit"
    CONTRAINDICATION = "contraindication"


class MedicalExam(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "medical_exam"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    exam_type: Mapped[str] = mapped_column(String(128), nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    conclusion: Mapped[str | None] = mapped_column(String(255))
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    # --- additive (TZ B.8) ---
    exam_kind: Mapped[MedicalExamKind | None] = mapped_column(
        native_enum(MedicalExamKind), nullable=True
    )
    fitness: Mapped[MedicalFitness | None] = mapped_column(
        native_enum(MedicalFitness), nullable=True
    )
    restrictions: Mapped[str | None] = mapped_column(Text)
    contraindications: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    referral_id: Mapped[str | None] = mapped_column(
        ForeignKey("medical_referral.id"), nullable=True, index=True
    )
    medical_org_name: Mapped[str | None] = mapped_column(String(255))
    # --- additive (342н psychiatric assessment) ---
    psychiatric_protocol_no: Mapped[str | None] = mapped_column(String(128))
    psychiatric_activity_codes: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )

    person: Mapped[Person] = relationship(backref="medical_exams")


class MedicalNorm(TenantBaseModel):
    __tablename__ = "medical_norm"

    position_id: Mapped[str] = mapped_column(ForeignKey("position.id"), nullable=False, index=True)
    hazard_id: Mapped[str | None] = mapped_column(
        ForeignKey("risk_hazards.id", ondelete="CASCADE"), nullable=True, index=True
    )
    exam_kind: Mapped[MedicalExamKind] = mapped_column(native_enum(MedicalExamKind), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    working_conditions_class: Mapped[str | None] = mapped_column(String(32))

    position: Mapped[Position] = relationship(backref="medical_norms")

    # hazard_id is nullable (position-level "general" norms). NULL != NULL in a
    # unique constraint, so duplicate general norms are tolerated; the contingent
    # resolver dedups required kinds via set union, so this is functionally benign.
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "position_id",
            "hazard_id",
            "exam_kind",
            name="uq_medical_norm_position_hazard_kind",
        ),
    )


class MedicalFactor(TenantBaseModel):
    """29н reference catalog: harmful factor / kind of work mandating periodic exams.

    VARCHAR ``category`` (no PG enum — enum-label-parity anti-pattern). Linked from
    ``RiskHazard.medical_factor_code`` (string, no cross-base FK). Optional norm overrides.
    """

    __tablename__ = "medical_factor"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="factor")
    exam_kinds: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    periodicity_months: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    participants: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(JSON), nullable=True
    )
    lab_tests: Mapped[list[str] | None] = mapped_column(MutableList.as_mutable(JSON), nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_medical_factor_tenant_code"),)


class MedicalReferral(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "medical_referral"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    exam_kind: Mapped[MedicalExamKind] = mapped_column(native_enum(MedicalExamKind), nullable=False)
    due_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[MedicalReferralStatus] = mapped_column(
        native_enum(MedicalReferralStatus), nullable=False, default=MedicalReferralStatus.ISSUED
    )
    medical_org_name: Mapped[str | None] = mapped_column(String(255))
    issued_by: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    result_exam_id: Mapped[str | None] = mapped_column(
        ForeignKey("medical_exam.id", ondelete="SET NULL"), nullable=True
    )

    person: Mapped[Person] = relationship(backref="medical_referrals")


class MedicalSuspension(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "medical_suspension"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    reason: Mapped[MedicalSuspensionReason] = mapped_column(
        native_enum(MedicalSuspensionReason),
        nullable=False,  # no default — service always sets reason explicitly
    )
    source_exam_id: Mapped[str | None] = mapped_column(
        ForeignKey("medical_exam.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[MedicalSuspensionStatus] = mapped_column(
        native_enum(MedicalSuspensionStatus), nullable=False, default=MedicalSuspensionStatus.ACTIVE
    )
    lifted_by: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )

    person: Mapped[Person] = relationship(backref="medical_suspensions")


class PsychiatricActivityType(TenantBaseModel):
    """342н reference catalog: вид деятельности (перечень ПП РФ № 695) mandating обязательное
    психиатрическое освидетельствование. Tenant-scoped; unique by code. interval_days overrides
    the 1825-day (5y) default periodicity per activity. VARCHAR-only, no cross-base FK."""

    __tablename__ = "psychiatric_activity_type"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1825)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_psychiatric_activity_type_tenant_code"),
    )


class PsychiatricPositionActivity(TenantBaseModel):
    """Mapping должность → вид деятельности 695 — the psychiatry contingent axis, parallel to
    RiskHazard.medical_factor_code for 29н. A position subject to ОПО has ≥1 mapped activity."""

    __tablename__ = "psychiatric_position_activity"

    position_id: Mapped[str] = mapped_column(
        ForeignKey("position.id"), nullable=False, index=True
    )
    activity_code: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "position_id",
            "activity_code",
            name="uq_psychiatric_position_activity",
        ),
    )
