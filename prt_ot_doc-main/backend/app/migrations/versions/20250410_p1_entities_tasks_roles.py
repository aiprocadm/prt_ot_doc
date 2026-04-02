"""Add P1 roles, core entities, and obligations tasks."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20250410_p1_entities_tasks_roles"
down_revision = "20250325_outbox_outbound_traffic"
branch_labels = None
depends_on = None


_ROLE_VALUES = [
    "owner",
    "admin",
    "ot_pb_lead",
    "ot_specialist",
    "pb_engineer",
    "ecologist",
    "hr",
    "lawyer",
    "accountant",
    "line_manager",
    "worker",
    "contractor_inspector",
    "employee",
    "client_admin",
    "client_user",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in _ROLE_VALUES:
            op.execute(f"ALTER TYPE roleenum ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "user_role",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.Enum(*_ROLE_VALUES, name="roleenum"), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", "role", name="uq_user_role"),
    )
    op.create_index("ix_user_role_user", "user_role", ["tenant_id", "user_id"], unique=False)

    op.create_table(
        "department",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "company_id", "name", name="uq_department_company_name"),
    )
    op.create_index("ix_department_company", "department", ["tenant_id", "company_id"], unique=False)

    op.create_table(
        "contract",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("counterparty_name", sa.String(length=255), nullable=False),
        sa.Column("contract_number", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "closed", "terminated", name="contractstatus"),
            nullable=False,
        ),
        sa.Column("signed_at", sa.Date(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contract_company", "contract", ["tenant_id", "company_id"], unique=False)

    op.create_table(
        "order",
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("order_number", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "confirmed", "fulfilled", "cancelled", name="orderstatus"),
            nullable=False,
        ),
        sa.Column("ordered_at", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["contract.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "contract_id", "order_number", name="uq_order_number"),
    )
    op.create_index("ix_order_contract", "order", ["tenant_id", "contract_id"], unique=False)

    op.create_table(
        "invoice",
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("invoice_number", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum("issued", "paid", "void", name="invoicestatus"),
            nullable=False,
        ),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("due_at", sa.Date(), nullable=True),
        sa.Column("paid_at", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["contract.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "contract_id", "invoice_number", name="uq_invoice_number"),
    )
    op.create_index("ix_invoice_contract", "invoice", ["tenant_id", "contract_id"], unique=False)

    op.create_table(
        "task",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "in_progress", "done", "cancelled", name="taskstatus"),
            nullable=False,
        ),
        sa.Column("assignee_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column(
            "priority",
            sa.Enum("low", "medium", "high", "critical", name="taskpriority"),
            nullable=False,
        ),
        sa.Column("next_remind_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reminder_channel",
            sa.Enum("in_app", "email", name="taskreminderchannel"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["assignee_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_due", "task", ["tenant_id", "due_at"], unique=False)
    op.create_index("ix_task_status", "task", ["tenant_id", "status"], unique=False)

    op.add_column("document", sa.Column("department_id", sa.String(length=36), nullable=True))
    op.add_column("document", sa.Column("contract_id", sa.String(length=36), nullable=True))
    op.add_column("document", sa.Column("order_id", sa.String(length=36), nullable=True))
    op.add_column("document", sa.Column("invoice_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_document_department", "document", "department", ["department_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_document_contract", "document", "contract", ["contract_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_document_order", "document", "order", ["order_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_document_invoice", "document", "invoice", ["invoice_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_document_invoice", "document", type_="foreignkey")
    op.drop_constraint("fk_document_order", "document", type_="foreignkey")
    op.drop_constraint("fk_document_contract", "document", type_="foreignkey")
    op.drop_constraint("fk_document_department", "document", type_="foreignkey")
    op.drop_column("document", "invoice_id")
    op.drop_column("document", "order_id")
    op.drop_column("document", "contract_id")
    op.drop_column("document", "department_id")

    op.drop_index("ix_task_status", table_name="task")
    op.drop_index("ix_task_due", table_name="task")
    op.drop_table("task")

    op.drop_index("ix_invoice_contract", table_name="invoice")
    op.drop_table("invoice")

    op.drop_index("ix_order_contract", table_name="order")
    op.drop_table("order")

    op.drop_index("ix_contract_company", table_name="contract")
    op.drop_table("contract")

    op.drop_index("ix_department_company", table_name="department")
    op.drop_table("department")

    op.drop_index("ix_user_role_user", table_name="user_role")
    op.drop_table("user_role")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="taskreminderchannel").drop(bind, checkfirst=True)
        sa.Enum(name="taskpriority").drop(bind, checkfirst=True)
        sa.Enum(name="taskstatus").drop(bind, checkfirst=True)
        sa.Enum(name="invoicestatus").drop(bind, checkfirst=True)
        sa.Enum(name="orderstatus").drop(bind, checkfirst=True)
        sa.Enum(name="contractstatus").drop(bind, checkfirst=True)
