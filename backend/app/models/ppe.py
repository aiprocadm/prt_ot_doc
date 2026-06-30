"""PPE-domain ORM models — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
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
        Person,
        Position,
    )
    from app.models.risk import RiskHazard


class PPENorm(TenantBaseModel):
    position_id: Mapped[str] = mapped_column(ForeignKey("position.id"), nullable=False, index=True)
    hazard_id: Mapped[str] = mapped_column(
        ForeignKey("risk_hazards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    item_id: Mapped[str | None] = mapped_column(
        ForeignKey("ppeitem.id", ondelete="SET NULL"), nullable=True, index=True
    )

    position: Mapped[Position] = relationship(backref="ppe_norms")
    hazard: Mapped["RiskHazard"] = relationship("RiskHazard")
    item: Mapped["PPEItem | None"] = relationship("PPEItem")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "position_id",
            "hazard_id",
            "item_name",
            name="uq_ppe_norm_position_hazard_item",
        ),
    )


class PPEItemCategory(str, enum.Enum):
    HEAD = "head"
    HANDS = "hands"
    RESPIRATORY = "respiratory"
    BODY = "body"
    FOOTWEAR = "footwear"
    FALL_PROTECTION = "fall_protection"
    OTHER = "other"


class PPEItem(TenantBaseModel, SoftDeleteMixin):
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[PPEItemCategory] = mapped_column(
        native_enum(PPEItemCategory), nullable=False, default=PPEItemCategory.OTHER
    )
    description: Mapped[str | None] = mapped_column(String(512))
    default_wear_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_ppe_item_name"),
        UniqueConstraint("tenant_id", "code", name="uq_ppe_item_code"),
    )


class PPEIssueStatus(str, enum.Enum):
    ISSUED = "issued"
    RETURNED = "returned"
    WRITTEN_OFF = "written_off"
    REPLACED = "replaced"
    LOST = "lost"


class PPEIssue(TenantBaseModel, SoftDeleteMixin):
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    item_id: Mapped[str | None] = mapped_column(
        ForeignKey("ppeitem.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wear_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # VARCHAR, not a native PG enum (sz01 converted the column; values are
    # the lowercase PPEIssueStatus .value strings — анти-грабли after the
    # PG enum incidents, same convention as medical/contractors).
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PPEIssueStatus.ISSUED.value
    )
    certificate_no: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wear_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    return_wear_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signature_doc_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    writeoff_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Plain string ref, no FK: the replacement chain must survive hard deletes
    # of old issues (same анти-грабли convention as contractor_documents.file_id).
    replaces_issue_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    person: Mapped[Person] = relationship(backref="ppe_issues")
    item: Mapped[PPEItem | None] = relationship("PPEItem", backref="issues")

    __table_args__ = (Index("ix_ppe_issue_item", "tenant_id", "item_id"),)


class PPEStockBatch(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "ppe_stock_batch"

    item_id: Mapped[str] = mapped_column(
        ForeignKey("ppeitem.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    certificate_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    certificate_expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    item: Mapped[PPEItem] = relationship("PPEItem")

    __table_args__ = (
        UniqueConstraint("tenant_id", "item_id", "batch_no", name="uq_ppe_stock_batch_item_no"),
        Index("ix_ppe_stock_batch_item", "tenant_id", "item_id"),
    )
