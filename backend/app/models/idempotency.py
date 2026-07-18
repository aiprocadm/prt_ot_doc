"""Idempotency-key ORM models — extracted from models.py (ARCH-2 decomposition).

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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    TenantBaseModel,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    pass


class IdempotencyStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IdempotencyKey(TenantBaseModel):
    __tablename__ = "idempotency_keys"

    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[IdempotencyStatus] = mapped_column(
        Enum(IdempotencyStatus), nullable=False, default=IdempotencyStatus.PENDING
    )
    request_hash: Mapped[str | None] = mapped_column(String(128))
    path: Mapped[str | None] = mapped_column(String(512))
    method: Mapped[str | None] = mapped_column(String(16))
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_headers: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    response_body: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "endpoint", "key", name="uq_idempotency_keys"),
        Index("ix_idempotency_keys_lookup", "tenant_id", "endpoint", "key"),
    )
