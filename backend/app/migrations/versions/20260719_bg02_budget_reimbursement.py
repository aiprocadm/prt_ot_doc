"""budget reimbursement §12.4 срез-2: claims + claim items (expense links).

Additive: 2 new tables (budget_reimbursement, budget_reimbursement_item).
No data backfill, no enum (status is VARCHAR + FSM whitelist in code). Chains off bg01.
Honest downgrade: drops in FK-safe order (item -> reimbursement).

Revision ID: 20260719_bg02_budget_reimbursement
Revises: 20260717_bg01_safety_budget_core
Create Date: 2026-07-19 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260719_bg02_budget_reimbursement"
down_revision = "20260717_bg01_safety_budget_core"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "budget_reimbursement",
        *_base_columns(),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("requested_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("approved_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("reference", sa.String(length=64), nullable=True),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("decision_reason", sa.String(length=1000), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_budget_reimbursement_tenant_id"), "budget_reimbursement", ["tenant_id"]
    )
    op.create_index(
        "ix_budget_reimbursement_tenant_status", "budget_reimbursement", ["tenant_id", "status"]
    )

    op.create_table(
        "budget_reimbursement_item",
        *_base_columns(),
        sa.Column("reimbursement_id", sa.String(length=36), nullable=False),
        sa.Column("expense_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["reimbursement_id"], ["budget_reimbursement.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["expense_id"], ["budget_expense.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "reimbursement_id", "expense_id", name="uq_budget_reimbursement_item_pair"
        ),
    )
    op.create_index(
        op.f("ix_budget_reimbursement_item_tenant_id"), "budget_reimbursement_item", ["tenant_id"]
    )
    op.create_index(
        "ix_budget_reimbursement_item_tenant_claim",
        "budget_reimbursement_item",
        ["tenant_id", "reimbursement_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_budget_reimbursement_item_tenant_claim", table_name="budget_reimbursement_item"
    )
    op.drop_index(
        op.f("ix_budget_reimbursement_item_tenant_id"), table_name="budget_reimbursement_item"
    )
    op.drop_table("budget_reimbursement_item")
    op.drop_index("ix_budget_reimbursement_tenant_status", table_name="budget_reimbursement")
    op.drop_index(op.f("ix_budget_reimbursement_tenant_id"), table_name="budget_reimbursement")
    op.drop_table("budget_reimbursement")
