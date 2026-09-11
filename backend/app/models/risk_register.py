"""Legacy risk-register & NPA ORM models — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    TenantBaseModel,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    from app.models.file import File
    from app.models.models import (
        Company,
        Position,
        Site,
        Workplace,
    )
    from app.models.packages import DocumentPack
    from app.models.risk import RiskHazard
    from app.models.templates import TemplateVersion


class RiskMethodology(TenantBaseModel):
    """Risk calculation methodology including severity/likelihood scales."""

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_risk_methodology_name"),
        UniqueConstraint("tenant_id", "code", name="uq_risk_methodology_code"),
    )


class RiskMap(TenantBaseModel):
    methodology_id: Mapped[str] = mapped_column(
        ForeignKey("riskmethodology.id"), nullable=False, index=True
    )
    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("site.id"), nullable=True, index=True)
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id"), nullable=True, index=True
    )
    document_pack_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_pack.id"), nullable=True, index=True
    )
    matrix: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)
    recalculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    methodology: Mapped[RiskMethodology] = relationship(backref="risk_maps")
    company: Mapped[Company] = relationship(backref="risk_maps")
    site: Mapped[Site | None] = relationship(backref="risk_maps")
    position: Mapped[Position | None] = relationship(backref="risk_maps")
    document_pack: Mapped["DocumentPack | None"] = relationship(backref="risk_maps")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "site_id",
            "position_id",
            "methodology_id",
            name="uq_riskmap_scope",
        ),
    )


class WorkplaceHazardLink(TenantBaseModel):
    __tablename__ = "workplace_hazard"

    workplace_id: Mapped[str] = mapped_column(
        ForeignKey("workplace.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hazard_id: Mapped[str] = mapped_column(
        ForeignKey("risk_hazards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )

    workplace: Mapped[Workplace] = relationship(
        backref="hazard_links", overlaps="hazards,workplaces"
    )
    hazard: Mapped["RiskHazard"] = relationship("RiskHazard", overlaps="hazards,workplaces")
    document_file: Mapped["File | None"] = relationship("File")

    __table_args__ = (
        UniqueConstraint("tenant_id", "workplace_id", "hazard_id", name="uq_workplace_hazard_link"),
    )


class PositionHazardLink(TenantBaseModel):
    __tablename__ = "position_hazard"

    position_id: Mapped[str] = mapped_column(
        ForeignKey("position.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hazard_id: Mapped[str] = mapped_column(
        ForeignKey("risk_hazards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )

    position: Mapped[Position] = relationship(backref="hazard_links", overlaps="hazards,positions")
    hazard: Mapped["RiskHazard"] = relationship("RiskHazard", overlaps="hazards,positions")
    document_file: Mapped["File | None"] = relationship("File")

    __table_args__ = (
        UniqueConstraint("tenant_id", "position_id", "hazard_id", name="uq_position_hazard_link"),
    )


class NpaBindingTarget(str, enum.Enum):
    """Entities that can be linked to an NPA."""

    TEMPLATE_VERSION = "template_version"
    DOCUMENT = "document"
    PACK = "pack"


class NPABinding(TenantBaseModel):
    """Связь акта общего реестра с сущностью арендатора — то, что читает оценка влияния.

    Срез-142: ``npa_id`` указывает в общий реестр ``npa_act`` (SharedModel), а не в
    арендаторскую таблицу ``npa`` контура risk_register, как было с начальной схемы.
    Расхождение не стреляло только потому, что связей никто не заводил: оценка
    влияния (``NpaImpactService``) всегда сравнивала ``npa_id`` с ``npa_act.id``.
    Модель ``NPA`` (арендаторские акты) удалена — в неё не писал и её не читал
    никто, кроме этой связи и поискового снимка; таблица ``npa`` в базе оставлена
    (``RLS_MODEL_LESS_TABLES``). В ORM ``npa_id`` — простой столбец без
    ``ForeignKey``, как ``FeatureEnablement.feature_id``: ссылку из tenant-базы в
    shared-базу SQLAlchemy не разрешает при ``create_all`` до регистрации зеркала.
    Настоящий внешний ключ на ``npa_act.id`` держит PostgreSQL — его заводит
    миграция ``20260910_b18_npabinding_npa_act``.

    Срез-144 (разд. 19.4): ``reviewed_revision_id`` — редакция акта, по которой
    арендатор в последний раз сверил цель связи. Ставится при создании связи
    (действующая на тот момент редакция) и кнопкой «Пересмотрено». Когда
    владелец платформы публикует новую редакцию, а здесь всё ещё старая — связь
    «не пересмотрена»: это и есть уведомление арендатору (Центр внимания) и
    основание для задач актуализации. Столбец тоже без ``ForeignKey`` — ссылка
    в shared-таблицу ``npa_revision``.
    """

    template_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("templateversion.id"), nullable=True, index=True
    )
    npa_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reviewed_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ref: Mapped[str | None] = mapped_column(String(255))
    entity_type: Mapped[NpaBindingTarget] = mapped_column(
        Enum(
            NpaBindingTarget,
            name="npabindingtarget",
            # iter-19 RB-002h cohort closure: PG type `npabindingtarget` was
            # created lowercase by migration 8d2c1a6c5e24:59-62. Member names
            # are uppercase ("TEMPLATE_VERSION"), so default SQLAlchemy binding
            # sends the name → asyncpg rejects. Force `.value` via callable.
            # Pinned by `backend/tests/test_npabinding_target_enum_values.py`.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=NpaBindingTarget.TEMPLATE_VERSION,
    )
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    template_version: Mapped[TemplateVersion | None] = relationship(backref="npa_bindings")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "npa_id", "entity_type", "entity_id", name="uq_npabinding_target"
        ),
    )
