"""next67 public api rotation and export schedule schema version

Revision ID: 20260318_next67
Revises: 20260418_next66_notifications_templates_foundation
Create Date: 2026-03-18
"""

import sqlalchemy as sa
from alembic import op

revision = "20260318_next67"
down_revision = "20260418_next66_notifications_templates_foundation"
branch_labels = None
# Cross-branch dependency: alters export_schedules created on a parallel
# branch in 20260411_next66_lms_exports_machine_marketplace.
depends_on = "20260411_next66"


def upgrade() -> None:
    op.add_column("api_key", sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "export_schedules",
        sa.Column("schema_version", sa.String(length=32), nullable=False, server_default="v1"),
    )


def downgrade() -> None:
    op.drop_column("export_schedules", "schema_version")
    op.drop_column("api_key", "last_rotated_at")
