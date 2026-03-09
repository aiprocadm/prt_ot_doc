"""Add API tokens table for public API authentication.

Revision ID: 20260407_next62_api_tokens
Revises: 20260406_next61_analytics_read_models
Create Date: 2026-04-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260407_next62_api_tokens"
down_revision = "20260406_next61_analytics_read_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("scopes_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_api_tokens_tenant_id", "api_tokens", ["tenant_id"])
    op.create_index("ix_api_tokens_token_hash", "api_tokens", ["token_hash"])
    op.create_index("ix_api_tokens_tenant_created", "api_tokens", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_api_tokens_tenant_created", table_name="api_tokens")
    op.drop_index("ix_api_tokens_token_hash", table_name="api_tokens")
    op.drop_index("ix_api_tokens_tenant_id", table_name="api_tokens")
    op.drop_table("api_tokens")
