"""Asset & equipment ORM models — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Enum,
    ForeignKey,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    TenantBaseModel,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    pass


class Asset(TenantBaseModel):
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(128))


class EquipmentStatus(str, enum.Enum):
    ACTIVE = "active"
    IN_SERVICE = "in_service"
    DECOMMISSIONED = "decommissioned"


class Equipment(TenantBaseModel):
    asset_id: Mapped[str] = mapped_column(ForeignKey("asset.id"), nullable=False, index=True)
    serial_number: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[EquipmentStatus] = mapped_column(
        Enum(EquipmentStatus), nullable=False, default=EquipmentStatus.ACTIVE
    )

    asset: Mapped[Asset] = relationship(backref="equipment")
