"""next37 immutable audit log and export jobs

Revision ID: 20260307_next37_audit_immutable_export
Revises: 20260306_next35_search_fts
Create Date: 2026-03-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260307_next37_audit_immutable_export"
down_revision = "20260306_next35_search_fts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auditlog", sa.Column("actor_type", sa.String(length=16), nullable=False, server_default="user"))
    op.add_column("auditlog", sa.Column("actor_email", sa.String(length=320), nullable=True))
    op.add_column("auditlog", sa.Column("parent_type", sa.String(length=64), nullable=True))
    op.add_column("auditlog", sa.Column("parent_id", sa.String(length=128), nullable=True))
    op.add_column("auditlog", sa.Column("before_hash", sa.String(length=64), nullable=True))
    op.add_column("auditlog", sa.Column("after_hash", sa.String(length=64), nullable=True))

    op.drop_index("ix_auditlog_action", table_name="auditlog")
    op.drop_index("ix_auditlog_object", table_name="auditlog")
    op.create_index("ix_auditlog_action", "auditlog", ["action", "when"], unique=False)
    op.create_index("ix_auditlog_object", "auditlog", ["object_type", "object_id", "when"], unique=False)
    op.create_index("ix_auditlog_actor", "auditlog", ["user_id", "when"], unique=False)

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_auditlog_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_auditlog_immutable
        BEFORE UPDATE OR DELETE ON auditlog
        FOR EACH ROW EXECUTE FUNCTION prevent_auditlog_mutation();
        """
    )

    op.create_table(
        "audit_export_job",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("signed_url", sa.String(length=2048), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_export_job_tenant_status", "audit_export_job", ["tenant_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_export_job_tenant_status", table_name="audit_export_job")
    op.drop_table("audit_export_job")

    op.execute("DROP TRIGGER IF EXISTS trg_auditlog_immutable ON auditlog")
    op.execute("DROP FUNCTION IF EXISTS prevent_auditlog_mutation")

    op.drop_index("ix_auditlog_actor", table_name="auditlog")
    op.drop_index("ix_auditlog_object", table_name="auditlog")
    op.drop_index("ix_auditlog_action", table_name="auditlog")
    op.create_index("ix_auditlog_object", "auditlog", ["object_type", "object_id"], unique=False)
    op.create_index("ix_auditlog_action", "auditlog", ["action"], unique=False)

    op.drop_column("auditlog", "after_hash")
    op.drop_column("auditlog", "before_hash")
    op.drop_column("auditlog", "parent_id")
    op.drop_column("auditlog", "parent_type")
    op.drop_column("auditlog", "actor_email")
    op.drop_column("auditlog", "actor_type")
