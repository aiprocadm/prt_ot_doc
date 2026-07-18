"""ORM models describing normative legal acts and their clauses."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SharedModel

__all__ = ["NpaAct", "NpaClause", "NpaRevision"]


class NpaAct(SharedModel):
    """Normative legal act shared between tenants."""

    __tablename__ = "npa_act"

    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    edition: Mapped[str] = mapped_column(String(128), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    revisions: Mapped[list["NpaRevision"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="NpaRevision.effective_from"
    )

    clauses: Mapped[list["NpaClause"]] = relationship(
        back_populates="act",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="NpaClause.code",
    )


class NpaRevision(SharedModel):
    """Revision history for a normative legal act."""

    __tablename__ = "npa_revision"

    act_id: Mapped[str] = mapped_column(
        ForeignKey("npa_act.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("act_id", "revision_code", name="uq_npa_revision_per_act"),)


class NpaClause(SharedModel):
    """Article or clause belonging to a normative legal act."""

    __tablename__ = "npa_clause"

    act_id: Mapped[str] = mapped_column(
        ForeignKey("npa_act.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    act: Mapped[NpaAct] = relationship(back_populates="clauses")

    __table_args__ = (UniqueConstraint("act_id", "code", name="uq_npa_clause_code_per_act"),)
