from __future__ import annotations

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.session import TenantBase
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin, VersionedMixin


class SearchDocument(TenantBase, TimestampMixin, SoftDeleteMixin, VersionedMixin, UUIDMixin):
    __tablename__ = "search_documents"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str] = mapped_column(String(32), nullable=False, default="russian")
    fts: Mapped[str | None] = mapped_column(TSVECTOR().with_variant(Text(), "sqlite"), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    source_file_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("files.id"), nullable=True)
    indexed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("ix_search_documents_tenant_entity", SearchDocument.tenant_id, SearchDocument.entity_type, SearchDocument.entity_id)
Index("ix_search_documents_tenant_updated", SearchDocument.tenant_id, SearchDocument.updated_at)
Index("ix_search_documents_meta_gin", SearchDocument.meta, postgresql_using="gin")
Index("ix_search_documents_fts_gin", SearchDocument.fts, postgresql_using="gin")
Index("ix_search_documents_source_file", SearchDocument.tenant_id, SearchDocument.source_file_id)


class SearchRecentQuery(TenantBase, TimestampMixin, SoftDeleteMixin, UUIDMixin):
    __tablename__ = "search_recent_queries"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    query_text: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_types: Mapped[list[str] | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    hit_count: Mapped[int] = mapped_column(nullable=False, default=1)
    last_used_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "query_text", name="uq_search_recent_queries_scope"),
        Index("ix_search_recent_queries_tenant_user_last_used", "tenant_id", "user_id", "last_used_at"),
    )


class SearchSavedQuery(TenantBase, TimestampMixin, SoftDeleteMixin, UUIDMixin):
    __tablename__ = "search_saved_queries"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    query_text: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_types: Mapped[list[str] | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    filters_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "name", name="uq_search_saved_queries_scope_name"),
        Index("ix_search_saved_queries_tenant_user_created", "tenant_id", "user_id", "created_at"),
    )
