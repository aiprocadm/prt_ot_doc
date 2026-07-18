"""ppe inventory count (stocktake) tables (P10-06 / honest остатки).

Additive: creates ppe_inventory_count (header) + ppe_inventory_count_line
(per-batch snapshot). No column added to existing tables, no data backfill.
``status`` is VARCHAR, not a PG enum (enum-parity convention). Chains off wa05.

Revision ID: 20260703_wa06_ppe_inventory_count
Revises: 20260703_wa05_ppeitem_min_stock
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260703_wa06_ppe_inventory_count"
down_revision = "20260703_wa05_ppeitem_min_stock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ppe_inventory_count",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("scope_item_id", sa.String(length=36), nullable=True),
        sa.Column("scope_location", sa.String(length=255), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["scope_item_id"], ["ppeitem.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ppe_inventory_count_tenant_id"), "ppe_inventory_count", ["tenant_id"])
    op.create_table(
        "ppe_inventory_count_line",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("count_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("system_qty", sa.Integer(), nullable=False),
        sa.Column("counted_qty", sa.Integer(), nullable=True),
        sa.Column("adjustment_movement_id", sa.String(length=36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["count_id"], ["ppe_inventory_count.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["ppeitem.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["ppe_stock_batch.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "count_id", "batch_id", name="uq_ppe_inv_count_line_batch"
        ),
    )
    op.create_index(
        op.f("ix_ppe_inventory_count_line_tenant_id"),
        "ppe_inventory_count_line",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ppe_inventory_count_line_count",
        "ppe_inventory_count_line",
        ["tenant_id", "count_id"],
    )
    op.create_index(
        "ix_ppe_inventory_count_line_batch",
        "ppe_inventory_count_line",
        ["tenant_id", "batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ppe_inventory_count_line_batch", table_name="ppe_inventory_count_line")
    op.drop_index("ix_ppe_inventory_count_line_count", table_name="ppe_inventory_count_line")
    op.drop_index(
        op.f("ix_ppe_inventory_count_line_tenant_id"),
        table_name="ppe_inventory_count_line",
    )
    op.drop_table("ppe_inventory_count_line")
    op.drop_index(op.f("ix_ppe_inventory_count_tenant_id"), table_name="ppe_inventory_count")
    op.drop_table("ppe_inventory_count")
