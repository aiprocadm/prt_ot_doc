from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db.session import SharedBase, TenantBase

__all__ = [
    "TenantBaseModel",
    "SharedModel",
    "TimestampMixin",
    "SoftDeleteMixin",
]


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        onupdate=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VersionedMixin:
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    @declared_attr.directive
    def __mapper_args__(cls):  # type: ignore[override]
        return {"version_id_col": cls.version}


class UUIDMixin:
    id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: str(uuid.uuid4()), nullable=False
    )


class TenantBaseModel(TenantBase, TimestampMixin, VersionedMixin, UUIDMixin):
    __abstract__ = True
    __tenant_model__ = True

    @declared_attr.directive
    def __tablename__(cls) -> str:  # type: ignore[override]
        return cls.__name__.lower()

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )


class SharedModel(SharedBase, TimestampMixin, VersionedMixin, UUIDMixin):
    __abstract__ = True

    @declared_attr.directive
    def __tablename__(cls) -> str:  # type: ignore[override]
        return cls.__name__.lower()
