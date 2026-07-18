"""next49 low-code pipeline builder core

Revision ID: 20260320_next49
Revises: 20260319_next48
Create Date: 2026-03-20 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260320_next49"
down_revision = "20260319_next48_billing_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pipeline_profiles", sa.Column("description", sa.String(length=2048), nullable=True)
    )
    op.add_column(
        "pipeline_profiles",
        sa.Column("graph", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "pipeline_profiles",
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("pipeline_profiles", "profile_version")
    op.drop_column("pipeline_profiles", "graph")
    op.drop_column("pipeline_profiles", "description")
