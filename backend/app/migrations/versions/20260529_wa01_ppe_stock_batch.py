"""ppe stock batch skeleton (W-A / TZ-3.2-V11-01 / vNext §12.3)

Additive: creates ppe_stock_batch (PPE warehouse batches with certificate
metadata). Mirrors TenantBaseModel + SoftDeleteMixin columns. No data
backfill. The legacy orphan `warehouseppe` table is intentionally left
untouched.

Chains off one of the iter-cohort heads (capstone iter48). The repo runs
``alembic upgrade heads`` (plural — many heads by design), so this additive
table applies regardless of the other parallel branches; consolidating the
heads is a separate operational merge, not part of this change.

Revision ID: 20260529_wa01_ppe_stock_batch
Revises: 20260529_iter48_outbox_events_last_error
Create Date: 2026-05-29 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260529_wa01_ppe_stock_batch"
down_revision = "20260529_iter48_outbox_events_last_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ppe_stock_batch",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("batch_no", sa.String(length=128), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_at", sa.Date(), nullable=True),
        sa.Column("certificate_no", sa.String(length=128), nullable=True),
        sa.Column("certificate_expires_at", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["ppeitem.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "item_id", "batch_no", name="uq_ppe_stock_batch_item_no"
        ),
    )
    op.create_index(
        op.f("ix_ppe_stock_batch_tenant_id"), "ppe_stock_batch", ["tenant_id"]
    )
    op.create_index(
        "ix_ppe_stock_batch_item", "ppe_stock_batch", ["tenant_id", "item_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ppe_stock_batch_item", table_name="ppe_stock_batch")
    op.drop_index(op.f("ix_ppe_stock_batch_tenant_id"), table_name="ppe_stock_batch")
    op.drop_table("ppe_stock_batch")
