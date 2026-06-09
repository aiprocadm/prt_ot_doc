"""con01: contractor documents registry (TZ B.14 Срез-2).

Additive. One new table, VARCHAR doc_type/status (no enum types), no cross-base FK
on file. Round-trip-safe: downgrade drops indexes then the table; no orphan enum types.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260609_con01_contractor_documents"
down_revision = "20260607_med01_medical_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contractor_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "contractor_id", sa.String(length=36),
            sa.ForeignKey("contractor_registry.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "employee_id", sa.String(length=36),
            sa.ForeignKey("contractor_employees.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("number", sa.String(length=128), nullable=True),
        sa.Column("issuing_org", sa.String(length=255), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.create_index("ix_contractor_documents_tenant_contractor", "contractor_documents", ["tenant_id", "contractor_id"])
    op.create_index("ix_contractor_documents_tenant_employee", "contractor_documents", ["tenant_id", "employee_id"])
    op.create_index("ix_contractor_documents_tenant_valid", "contractor_documents", ["tenant_id", "valid_until"])
    op.create_index("ix_contractor_documents_tenant_type", "contractor_documents", ["tenant_id", "doc_type"])


def downgrade() -> None:
    op.drop_index("ix_contractor_documents_tenant_type", table_name="contractor_documents")
    op.drop_index("ix_contractor_documents_tenant_valid", table_name="contractor_documents")
    op.drop_index("ix_contractor_documents_tenant_employee", table_name="contractor_documents")
    op.drop_index("ix_contractor_documents_tenant_contractor", table_name="contractor_documents")
    op.drop_table("contractor_documents")
