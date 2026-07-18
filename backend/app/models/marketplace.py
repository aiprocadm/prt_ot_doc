"""Marketplace-catalog ORM models — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    SoftDeleteMixin,
    TenantBaseModel,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    pass


class MarketplaceCatalogItem(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "marketplace_catalog_items"

    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags_json: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    compatibility_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    dependency_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "item_type", "code", "version_label", name="uq_marketplace_catalog_item"
        ),
        Index("ix_marketplace_catalog_lookup", "tenant_id", "item_type", "status", "updated_at"),
    )
