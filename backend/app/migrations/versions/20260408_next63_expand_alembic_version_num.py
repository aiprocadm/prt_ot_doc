"""Expand alembic_version.version_num length to support long revision IDs.

Revision ID: 20260408_next63_expand_alembic_version_num
Revises: 20260407_next62_api_tokens
Create Date: 2026-04-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260408_next63_expand_alembic_version_num"
down_revision = "20260407_next62_api_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.Text(),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
