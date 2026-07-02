"""ppe stock movement ledger (P10-06 / honest остатки / vNext §12.3)

Additive: creates ppe_stock_movement (append-only journal of stock deltas).
No column added to existing tables; no data backfill (existing ppe_stock_batch
rows keep their quantity as the opening balance). ``kind`` is VARCHAR, not a PG
enum (enum-parity convention). Chains off the branch-entity head (br01).

Revision ID: 20260702_wa04_ppe_stock_movement
Revises: 20260702_br01_branch_entity
Create Date: 2026-07-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260702_wa04_ppe_stock_movement"
down_revision = "20260702_br01_branch_entity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ppe_stock_movement",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("ref_type", sa.String(length=64), nullable=True),
        sa.Column("ref_id", sa.String(length=36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["ppeitem.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["ppe_stock_batch.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ppe_stock_movement_tenant_id"), "ppe_stock_movement", ["tenant_id"])
    op.create_index("ix_ppe_stock_movement_item", "ppe_stock_movement", ["tenant_id", "item_id"])
    op.create_index("ix_ppe_stock_movement_batch", "ppe_stock_movement", ["tenant_id", "batch_id"])


def downgrade() -> None:
    op.drop_index("ix_ppe_stock_movement_batch", table_name="ppe_stock_movement")
    op.drop_index("ix_ppe_stock_movement_item", table_name="ppe_stock_movement")
    op.drop_index(op.f("ix_ppe_stock_movement_tenant_id"), table_name="ppe_stock_movement")
    op.drop_table("ppe_stock_movement")
