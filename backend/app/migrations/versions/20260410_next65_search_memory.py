"""search recent/saved queries foundation

Revision ID: 20260410_next65
Revises: 20260409_next64
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision = "20260410_next65"
down_revision: Union[str, None] = "20260409_next64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_recent_queries",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("query_text", sa.String(length=255), nullable=False),
        sa.Column("entity_types", sa.JSON(), nullable=True),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "query_text", name="uq_search_recent_queries_scope"
        ),
    )
    op.create_index(
        "ix_search_recent_queries_tenant_user_last_used",
        "search_recent_queries",
        ["tenant_id", "user_id", "last_used_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_recent_queries_tenant_id"),
        "search_recent_queries",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_recent_queries_user_id"), "search_recent_queries", ["user_id"], unique=False
    )

    op.create_table(
        "search_saved_queries",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("query_text", sa.String(length=255), nullable=False),
        sa.Column("entity_types", sa.JSON(), nullable=True),
        sa.Column("filters_json", sa.JSON(), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "name", name="uq_search_saved_queries_scope_name"
        ),
    )
    op.create_index(
        "ix_search_saved_queries_tenant_user_created",
        "search_saved_queries",
        ["tenant_id", "user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_saved_queries_tenant_id"),
        "search_saved_queries",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_saved_queries_user_id"), "search_saved_queries", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_search_saved_queries_user_id"), table_name="search_saved_queries")
    op.drop_index(op.f("ix_search_saved_queries_tenant_id"), table_name="search_saved_queries")
    op.drop_index("ix_search_saved_queries_tenant_user_created", table_name="search_saved_queries")
    op.drop_table("search_saved_queries")

    op.drop_index(op.f("ix_search_recent_queries_user_id"), table_name="search_recent_queries")
    op.drop_index(op.f("ix_search_recent_queries_tenant_id"), table_name="search_recent_queries")
    op.drop_index(
        "ix_search_recent_queries_tenant_user_last_used", table_name="search_recent_queries"
    )
    op.drop_table("search_recent_queries")
