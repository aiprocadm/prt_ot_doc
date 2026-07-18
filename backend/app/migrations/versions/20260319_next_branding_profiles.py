"""NEXT branding profiles for companies and sites

Revision ID: 20260319_next_branding_profiles
Revises: 20260330_next57
Create Date: 2026-03-19 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260319_next_branding_profiles"
down_revision = "20260330_next57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("company") as batch:
        batch.add_column(
            sa.Column("branding_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch.add_column(
            sa.Column("preferred_header_preset_code", sa.String(length=64), nullable=True)
        )
    with op.batch_alter_table("site") as batch:
        batch.add_column(
            sa.Column("branding_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )


def downgrade() -> None:
    with op.batch_alter_table("site") as batch:
        batch.drop_column("branding_payload")
    with op.batch_alter_table("company") as batch:
        batch.drop_column("preferred_header_preset_code")
        batch.drop_column("branding_payload")
