from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db.session import SharedBase, TenantBase

__all__ = [
    "native_enum",
    "TenantBaseModel",
    "SharedModel",
    "TimestampMixin",
    "SoftDeleteMixin",
]


def native_enum(enum_cls, *, name=None, **kw):
    """Native PG enum column type that persists the member ``.value`` rather than
    SQLAlchemy's default member NAME.

    Most ``pg_enum`` types in this project were created by migrations with
    ``.value`` labels (lowercase, or CamelCase for ``NotificationType``). Without
    ``values_callable`` SQLAlchemy binds the member NAME (UPPER) and PG rejects the
    INSERT with ``InvalidTextRepresentationError``. This is the canonical
    extraction of the inline precedent at ``document.py`` / ``models.py`` (the
    7 pre-existing ``values_callable`` columns). Pinned by
    ``backend/tests/test_orm_enum_pg_label_parity.py`` (authoritative, live PG) and
    ``backend/tests/test_orm_enum_values_callable_parity.py`` (fast, no PG).

    Only apply to Group-A columns (pg type created with ``.value`` labels). Do NOT
    apply to Group-B columns whose pg type was created with UPPER member NAMES — see
    the spec Appendix.
    """
    # Forward ``name`` ONLY when explicitly given. SQLAlchemy derives the PG type
    # name from ``enum_cls.__name__`` only if "name" is absent from kwargs; passing
    # name=None suppresses that derivation, yielding an UNNAMED native enum that
    # crashes ``metadata.create_all`` on PostgreSQL ("AsyncPgEnum type requires a
    # name"). Guarded by backend/tests/test_native_enum_helper.py.
    if name is not None:
        kw["name"] = name
    return Enum(enum_cls, values_callable=lambda e: [m.value for m in e], **kw)


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
