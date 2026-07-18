"""ppe supplier directory + batch/item provenance FKs (P10-06).

Additive: creates ppe_supplier (directory) + adds nullable supplier_id to
ppe_stock_batch (batch provenance) and preferred_supplier_id to ppeitem
(explicit reorder supplier). No data backfill, no enum. Chains off wa07.

Revision ID: 20260704_wa08_ppe_supplier
Revises: 20260704_wa07_ppe_stock_batch_location_unique
Create Date: 2026-07-04 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260704_wa08_ppe_supplier"
down_revision = "20260704_wa07_ppe_stock_batch_location_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ppe_supplier",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("inn", sa.String(length=12), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_ppe_supplier_name"),
    )
    op.create_index(op.f("ix_ppe_supplier_tenant_id"), "ppe_supplier", ["tenant_id"])

    op.add_column("ppe_stock_batch", sa.Column("supplier_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_ppe_stock_batch_supplier_id",
        "ppe_stock_batch",
        "ppe_supplier",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_ppe_stock_batch_supplier_id"), "ppe_stock_batch", ["supplier_id"])

    op.add_column(
        "ppeitem", sa.Column("preferred_supplier_id", sa.String(length=36), nullable=True)
    )
    op.create_foreign_key(
        "fk_ppeitem_preferred_supplier_id",
        "ppeitem",
        "ppe_supplier",
        ["preferred_supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_ppeitem_preferred_supplier_id"), "ppeitem", ["preferred_supplier_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_ppeitem_preferred_supplier_id"), table_name="ppeitem")
    op.drop_constraint("fk_ppeitem_preferred_supplier_id", "ppeitem", type_="foreignkey")
    op.drop_column("ppeitem", "preferred_supplier_id")

    op.drop_index(op.f("ix_ppe_stock_batch_supplier_id"), table_name="ppe_stock_batch")
    op.drop_constraint("fk_ppe_stock_batch_supplier_id", "ppe_stock_batch", type_="foreignkey")
    op.drop_column("ppe_stock_batch", "supplier_id")

    op.drop_index(op.f("ix_ppe_supplier_tenant_id"), table_name="ppe_supplier")
    op.drop_table("ppe_supplier")
