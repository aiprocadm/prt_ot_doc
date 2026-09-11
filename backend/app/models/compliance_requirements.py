"""Реестр требований (B.18 разд. 19.2, срез-145): что арендатор ОБЯЗАН делать по НПА.

* :class:`ComplianceRequirement` — одна строка = одно требование: откуда оно
  (акт и, если известно, пункт общего реестра НПА), к кому или к чему
  относится (роль / площадка / процесс), кто отвечает, как часто и до какой
  даты надо исполнять, и насколько серьёзно неисполнение. Это то самое
  «обязательное ядро» из ТЗ: без него оценка влияния (разд. 19.3) знает, какие
  ДОКУМЕНТЫ зависят от акта, но не знает, какие ОБЯЗАННОСТИ из него следуют.
* :class:`ComplianceRequirementEvidence` — доказательство исполнения:
  документ и/или заметка, кто и когда подтвердил. Подтверждение сдвигает
  контрольную дату на период; у разового требования — закрывает его.

Ссылки на общий реестр (``npa_id`` → ``npa_act.id``, ``clause_id`` →
``npa_clause.id``) — простые столбцы без ``ForeignKey`` в ORM: ключ из
tenant-базы в shared-базу ломает ``create_all`` (прецедент
``NPABinding.npa_id``); настоящий ключ держит PostgreSQL миграцией.

Обе таблицы tenant-scoped и армируются RLS (SEC-65) — см.
``app/core/rls_policy.py`` и миграцию ``20260911_b18_compliance_requirements``.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBaseModel

__all__ = [
    "ComplianceRequirement",
    "ComplianceRequirementEvidence",
    "REQUIREMENT_SEVERITIES",
    "REQUIREMENT_STATUSES",
]

#: Серьёзность неисполнения (разд. 19.2 «severity of non-compliance»). Порядок —
#: от лёгкой к тяжёлой; Центр внимания переводит её в свою тяжесть записи.
REQUIREMENT_SEVERITIES: tuple[str, ...] = ("low", "medium", "high", "critical")

#: ``active`` — на контроле; ``fulfilled`` — разовое требование исполнено;
#: ``retired`` — снято с контроля (акт отменён, процесс закрыт). Удаления нет:
#: история доказательств нужна на проверке дольше, чем само требование.
REQUIREMENT_STATUSES: tuple[str, ...] = ("active", "fulfilled", "retired")


class ComplianceRequirement(TenantBaseModel):
    __tablename__ = "compliance_requirement"

    #: Код внутри арендатора («ОТ-12»); естественный ключ для импорта и ссылок.
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Откуда требование: акт общего реестра и, если известно, его пункт.
    npa_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    clause_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    #: К кому/чему относится (разд. 19.2 «роль / объект / процесс»). Все три
    #: необязательны: требование бывает общим для арендатора.
    role_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    process_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    #: Ответственный — пользователь арендатора; ему требование показывается в
    #: Центре внимания даже без обзора по всему арендатору.
    owner_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )

    #: Периодичность в днях (365 — ежегодно); пусто — разовое требование.
    periodicity_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Контрольная дата: до неё надо исполнить (и подтвердить доказательством).
    next_due_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Когда подтверждали в последний раз — чтобы видеть «давно не исполняли».
    last_confirmed_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    evidence: Mapped[list["ComplianceRequirementEvidence"]] = relationship(
        "ComplianceRequirementEvidence",
        back_populates="requirement",
        cascade="all, delete-orphan",
        order_by="ComplianceRequirementEvidence.confirmed_at.desc()",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_compliance_requirement_code"),
        Index("ix_compliance_requirement_tenant_status", "tenant_id", "status"),
        Index("ix_compliance_requirement_tenant_due", "tenant_id", "next_due_at"),
    )


class ComplianceRequirementEvidence(TenantBaseModel):
    __tablename__ = "compliance_requirement_evidence"

    requirement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("compliance_requirement.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Документ арендатора как доказательство (приказ, протокол, журнал) — или
    #: только заметка, если бумага живёт вне системы.
    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("document.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[date] = mapped_column(Date, nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    requirement: Mapped[ComplianceRequirement] = relationship(
        "ComplianceRequirement", back_populates="evidence"
    )
