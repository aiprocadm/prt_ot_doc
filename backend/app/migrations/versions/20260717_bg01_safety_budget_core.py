"""safety budget core §12.4 срез-1: budgets + expense articles + expense journal.

Additive: 3 new tables (safety_budget, budget_expense_article, budget_expense).
No data backfill, no enum (domains are VARCHAR + code whitelist). Chains off re01.
Honest downgrade: drops in FK-safe order (expense -> budget -> article).

Revision ID: 20260717_bg01_safety_budget_core
Revises: 20260715_re01_automation_rules
Create Date: 2026-07-17 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260717_bg01_safety_budget_core"
down_revision = "20260715_re01_automation_rules"
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
        "budget_expense_article",
        *_base_columns(),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_budget_expense_article_tenant_code"),
    )
    op.create_index(
        op.f("ix_budget_expense_article_tenant_id"), "budget_expense_article", ["tenant_id"]
    )

    op.create_table(
        "safety_budget",
        *_base_columns(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("planned_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_safety_budget_tenant_id"), "safety_budget", ["tenant_id"])
    op.create_index("ix_safety_budget_tenant_domain", "safety_budget", ["tenant_id", "domain"])

    op.create_table(
        "budget_expense",
        *_base_columns(),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("article_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("branch_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["article_id"], ["budget_expense_article.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["branch_id"], ["branch.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_budget_expense_tenant_id"), "budget_expense", ["tenant_id"])
    op.create_index(
        "ix_budget_expense_tenant_domain_occurred",
        "budget_expense",
        ["tenant_id", "domain", "occurred_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_budget_expense_tenant_domain_occurred", table_name="budget_expense")
    op.drop_index(op.f("ix_budget_expense_tenant_id"), table_name="budget_expense")
    op.drop_table("budget_expense")
    op.drop_index("ix_safety_budget_tenant_domain", table_name="safety_budget")
    op.drop_index(op.f("ix_safety_budget_tenant_id"), table_name="safety_budget")
    op.drop_table("safety_budget")
    op.drop_index(op.f("ix_budget_expense_article_tenant_id"), table_name="budget_expense_article")
    op.drop_table("budget_expense_article")
