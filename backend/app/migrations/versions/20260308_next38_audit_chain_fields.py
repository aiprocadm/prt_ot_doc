"""next38 audit chain fields and correlation indexes

Revision ID: 20260308_next38_audit_chain_fields
Revises: 20260307_next37_audit_immutable_export
Create Date: 2026-03-08 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260308_next38_audit_chain_fields"
down_revision = "20260307_next37_audit_immutable_export"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auditlog", sa.Column("correlation_id", sa.String(length=128), nullable=False, server_default="unknown"))
    op.add_column("auditlog", sa.Column("resource_attrs", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("auditlog", sa.Column("hash", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("auditlog", sa.Column("prev_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_auditlog_corr", "auditlog", ["correlation_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_auditlog_corr", table_name="auditlog")
    op.drop_column("auditlog", "prev_hash")
    op.drop_column("auditlog", "hash")
    op.drop_column("auditlog", "resource_attrs")
    op.drop_column("auditlog", "correlation_id")
