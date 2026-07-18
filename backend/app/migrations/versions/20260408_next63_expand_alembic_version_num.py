"""Expand alembic_version.version_num length to support long revision IDs.

Revision ID: 20260408_next63_expand_alembic_version_num
Revises: 20260407_next62_api_tokens
Create Date: 2026-04-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

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
    # Intentional no-op. ``upgrade`` widens alembic_version.version_num
    # (VARCHAR(32) -> TEXT) precisely so revision IDs longer than 32 chars fit —
    # and such IDs now exist (this revision's own ID is 42 chars). By the time a
    # downgrade reaches this step, version_num holds the current >32-char
    # revision, so ``ALTER ... TYPE VARCHAR(32)`` always raises
    # StringDataRightTruncationError, making ``downgrade base`` impossible.
    # Widening alembic's own bookkeeping column is forward-compatible, so it is
    # safe (and necessary) to leave the wider type in place on downgrade.
    pass
