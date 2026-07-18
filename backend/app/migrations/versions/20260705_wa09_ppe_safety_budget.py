"""ppe safety budget table + batch unit_cost (P10-06 §12.4 СИЗ scope).

Additive: creates ppe_safety_budget + adds nullable unit_cost to ppe_stock_batch.
No data backfill, no enum. Chains off wa08.

Revision ID: 20260705_wa09_ppe_safety_budget
Revises: 20260704_wa08_ppe_supplier
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260705_wa09_ppe_safety_budget"
down_revision = "20260704_wa08_ppe_supplier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ppe_safety_budget",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("planned_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ppe_safety_budget_tenant_id"), "ppe_safety_budget", ["tenant_id"])
    op.add_column("ppe_stock_batch", sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("ppe_stock_batch", "unit_cost")
    op.drop_index(op.f("ix_ppe_safety_budget_tenant_id"), table_name="ppe_safety_budget")
    op.drop_table("ppe_safety_budget")
