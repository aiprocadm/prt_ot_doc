"""Alembic metadata aggregator ensuring all ORM models are imported."""

from __future__ import annotations

from sqlalchemy import MetaData

from app.db.session import SharedBase, TenantBase
from app.models import (
    checks,  # noqa: F401  # import side-effects for metadata registration
    document,  # noqa: F401
    feature,  # noqa: F401
    file,  # noqa: F401
    job_engine,  # noqa: F401
    models,  # noqa: F401
    npa,  # noqa: F401
    risk,  # noqa: F401
)

Base = TenantBase


def _merge_metadata(*sources: MetaData) -> MetaData:
    merged = MetaData()
    for source in sources:
        for table in source.tables.values():
            if table.key in merged.tables:
                continue
            table.tometadata(merged)
    return merged


ALEMBIC_METADATA = _merge_metadata(SharedBase.metadata, TenantBase.metadata)
TARGET_METADATA = (ALEMBIC_METADATA,)

__all__ = ["Base", "TARGET_METADATA", "ALEMBIC_METADATA", "SharedBase", "TenantBase"]
