"""next67 public api rotation and export schedule schema version

Revision ID: 20260318_next67
Revises: 20260418_next66_notifications_templates_foundation
Create Date: 2026-03-18
"""

import sqlalchemy as sa
from alembic import op

revision = "20260318_next67"
# iter-15g: promoted depends_on to a real down_revision tuple parent.
# 20260411_next66 created export_schedules; this migration alters it.
# Two-mechanism overlap (depends_on + next69 explicit merge) broke
# alembic head_maintainer; single down_revision edge is the fix.
down_revision = ("20260418_next66_notifications_templates_foundation", "20260411_next66")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_key", sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "export_schedules",
        sa.Column("schema_version", sa.String(length=32), nullable=False, server_default="v1"),
    )


def downgrade() -> None:
    op.drop_column("export_schedules", "schema_version")
    op.drop_column("api_key", "last_rotated_at")
