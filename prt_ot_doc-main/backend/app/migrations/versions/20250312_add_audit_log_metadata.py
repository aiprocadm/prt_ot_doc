"""Add audit log metadata fields and immutability guards

Revision ID: 20250312_add_audit_log_metadata
Revises: 20250305_add_outbox_delivery_metadata
Create Date: 2025-03-12 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20250312_add_audit_log_metadata"
down_revision: str | tuple[str, ...] = "20250305_add_outbox_delivery_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("auditlog", schema=None) as batch:
        batch.add_column(sa.Column("request_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("session_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("user_agent", sa.String(length=256), nullable=True))
        batch.add_column(
            sa.Column(
                "changed_fields",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch.alter_column("changed_fields", server_default=None)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION prevent_auditlog_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'auditlog is append-only';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER auditlog_no_update
            BEFORE UPDATE ON auditlog
            FOR EACH ROW EXECUTE FUNCTION prevent_auditlog_mutation();
            """
        )
        op.execute(
            """
            CREATE TRIGGER auditlog_no_delete
            BEFORE DELETE ON auditlog
            FOR EACH ROW EXECUTE FUNCTION prevent_auditlog_mutation();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS auditlog_no_update ON auditlog")
        op.execute("DROP TRIGGER IF EXISTS auditlog_no_delete ON auditlog")
        op.execute("DROP FUNCTION IF EXISTS prevent_auditlog_mutation")

    with op.batch_alter_table("auditlog", schema=None) as batch:
        batch.drop_column("changed_fields")
        batch.drop_column("user_agent")
        batch.drop_column("session_id")
        batch.drop_column("request_id")
