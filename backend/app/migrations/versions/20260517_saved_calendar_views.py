"""saved calendar views (vNext-CAL-01 / Phase 4.1)

Per-user Smart Calendar filter presets. JSON payload stores the entire
filter state (sources, person_id, site_id, include_fact, include_sla,
sla_bands, include_load, load_dim) so future toggles do not require a
new migration.

Revision ID: 20260517_saved_calendar_views
Revises: 20260416_next69_merge_heads
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260517_saved_calendar_views"
down_revision = "20260416_next69_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_calendar_views",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "name",
            name="uq_saved_calendar_views_name",
        ),
    )
    op.create_index(
        op.f("ix_saved_calendar_views_tenant_id"),
        "saved_calendar_views",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_saved_calendar_views_user_id"),
        "saved_calendar_views",
        ["user_id"],
    )
    op.create_index(
        "ix_saved_calendar_views_user",
        "saved_calendar_views",
        ["tenant_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_saved_calendar_views_user", table_name="saved_calendar_views")
    op.drop_index(op.f("ix_saved_calendar_views_user_id"), table_name="saved_calendar_views")
    op.drop_index(op.f("ix_saved_calendar_views_tenant_id"), table_name="saved_calendar_views")
    op.drop_table("saved_calendar_views")
