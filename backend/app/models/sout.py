"""СОУТ (специальная оценка условий труда, ФЗ-426) ORM models (P10-04 срез-1, TZ B.10).

Bounded context kept OUT of the 3000-line ``models.py`` to avoid the
duplicate-class hazards documented there. Native enums use the project
``native_enum`` helper (``.value`` labels, explicit ``name=``) per
enum-pg-label-parity discipline.

Срез-1 scope: campaign → workplace (assessed class of working conditions) →
identified factors + resulting guarantees/compensations. File import and
auto-cascade to PPE norms / medical exams are deferred to срез-2+.
"""
from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum


class SoutCampaignStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DECLARED = "declared"  # подана декларация соответствия (классы 1 и 2)
    CANCELLED = "cancelled"


class SoutClass(str, enum.Enum):
    """Класс (подкласс) условий труда по ФЗ-426 ст. 14."""

    OPTIMAL = "optimal"  # 1 — оптимальный
    ACCEPTABLE = "acceptable"  # 2 — допустимый
    HARMFUL_3_1 = "harmful_3_1"  # 3.1 — вредный
    HARMFUL_3_2 = "harmful_3_2"  # 3.2
    HARMFUL_3_3 = "harmful_3_3"  # 3.3
    HARMFUL_3_4 = "harmful_3_4"  # 3.4
    DANGEROUS = "dangerous"  # 4 — опасный


class SoutGuaranteeKind(str, enum.Enum):
    """Гарантии и компенсации, вытекающие из класса условий труда."""

    ADDITIONAL_LEAVE = "additional_leave"  # доп. отпуск
    EXTRA_PAY = "extra_pay"  # повышенная оплата
    REDUCED_HOURS = "reduced_hours"  # сокращённая рабочая неделя
    MILK = "milk"  # молоко / лечебно-профилактическое питание
    EARLY_PENSION = "early_pension"  # досрочная пенсия
    MEDICAL_EXAM = "medical_exam"  # обязательный медосмотр


# ``SoutClass`` backs two columns (workplace.assessed_class + factor.measured_class).
# Reuse ONE shared native-enum instance so ``metadata.create_all`` emits a single
# ``CREATE TYPE soutclass`` instead of colliding on a duplicate type — the canonical
# SQLAlchemy dedup for a named enum shared across tables.
_SOUT_CLASS_ENUM = native_enum(SoutClass, name="soutclass")


class SoutCampaign(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "sout_campaign"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    expert_org_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    report_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[SoutCampaignStatus] = mapped_column(
        native_enum(SoutCampaignStatus, name="soutcampaignstatus"),
        nullable=False,
        default=SoutCampaignStatus.PLANNED,
    )
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class SoutWorkplace(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "sout_workplace"

    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sout_campaign.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workplace_code: Mapped[str] = mapped_column(String(100), nullable=False)
    position_name: Mapped[str] = mapped_column(String(255), nullable=False)
    person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    assessed_class: Mapped[SoutClass | None] = mapped_column(_SOUT_CLASS_ENUM, nullable=True)
    assessment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_assessment_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class SoutFactor(TenantBaseModel):
    __tablename__ = "sout_factor"

    workplace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sout_workplace.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    measured_class: Mapped[SoutClass | None] = mapped_column(_SOUT_CLASS_ENUM, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SoutGuarantee(TenantBaseModel):
    __tablename__ = "sout_guarantee"

    workplace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sout_workplace.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[SoutGuaranteeKind] = mapped_column(
        native_enum(SoutGuaranteeKind, name="soutguaranteekind"), nullable=False
    )
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
