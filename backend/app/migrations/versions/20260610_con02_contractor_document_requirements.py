"""con02: contractor document requirements policy (TZ B.14 Срез-3).

Additive. One new table, VARCHAR doc_type/scope (no enum types), no cross-base FK.
Round-trip-safe: downgrade drops the index then the table; no orphan enum types.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260610_con02_contractor_document_requirements"
down_revision = "20260609_con01_contractor_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contractor_document_requirement",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_contractor_doc_req_tenant_type",
        "contractor_document_requirement",
        ["tenant_id", "doc_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_contractor_doc_req_tenant_type", table_name="contractor_document_requirement")
    op.drop_table("contractor_document_requirement")
