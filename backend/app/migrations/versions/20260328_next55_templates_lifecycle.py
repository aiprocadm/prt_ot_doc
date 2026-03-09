"""NEXT-55 templates lifecycle and usage table

Revision ID: 20260328_next55
Revises: 20260327_next54_files_core_hardening
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260328_next55"
down_revision = "20260327_next54"
branch_labels = None
depends_on = None


def upgrade() -> None:
    template_status = sa.Enum("DRAFT", "ACTIVE", "ARCHIVED", name="templatestatus")
    template_version_status = sa.Enum(
        "DRAFT", "ACTIVE", "ARCHIVED", "UPLOADED", "LINTED", "READY", "DEPRECATED", name="templateversionstatus"
    )
    template_status.create(op.get_bind(), checkfirst=True)
    template_version_status.drop(op.get_bind(), checkfirst=True)
    template_version_status.create(op.get_bind(), checkfirst=True)

    op.add_column("template", sa.Column("status", template_status, nullable=True))
    op.add_column("template", sa.Column("current_version_id", sa.String(length=36), nullable=True))
    op.execute("UPDATE template SET status = 'DRAFT' WHERE status IS NULL")
    op.alter_column("template", "status", nullable=False)
    op.create_foreign_key(
        "fk_template_current_version", "template", "templateversion", ["current_version_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_template_current_version_id", "template", ["current_version_id"], unique=False)
    op.create_index("ix_template_status_updated", "template", ["tenant_id", "status", "updated_at"], unique=False)
    op.create_index("ix_template_updated", "template", ["tenant_id", "updated_at"], unique=False)

    op.add_column("templateversion", sa.Column("size_bytes", sa.Integer(), nullable=True))
    op.add_column("templateversion", sa.Column("linter_report_json", sa.JSON(), nullable=True))
    op.add_column("templateversion", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE templateversion SET status = 'UPLOADED'")
    op.create_index("ix_template_version_status", "templateversion", ["tenant_id", "status"], unique=False)
    op.create_index("ix_template_version_updated", "templateversion", ["tenant_id", "updated_at"], unique=False)

    op.create_table(
        "templateusage",
        sa.Column("template_version_id", sa.String(length=36), nullable=False),
        sa.Column("used_by_type", sa.String(length=64), nullable=False),
        sa.Column("used_by_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["template_version_id"], ["templateversion.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_version_id", "used_by_type", "used_by_id", name="uq_template_usage_target"),
    )
    op.create_index("ix_templateusage_template_version_id", "templateusage", ["template_version_id"], unique=False)
    op.create_index("ix_templateusage_tenant_id", "templateusage", ["tenant_id"], unique=False)
    op.create_index("ix_template_usage_lookup", "templateusage", ["tenant_id", "template_version_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_template_usage_lookup", table_name="templateusage")
    op.drop_index("ix_templateusage_tenant_id", table_name="templateusage")
    op.drop_index("ix_templateusage_template_version_id", table_name="templateusage")
    op.drop_table("templateusage")

    op.drop_index("ix_template_version_updated", table_name="templateversion")
    op.drop_index("ix_template_version_status", table_name="templateversion")
    op.drop_column("templateversion", "deleted_at")
    op.drop_column("templateversion", "linter_report_json")
    op.drop_column("templateversion", "size_bytes")

    op.drop_index("ix_template_updated", table_name="template")
    op.drop_index("ix_template_status_updated", table_name="template")
    op.drop_index("ix_template_current_version_id", table_name="template")
    op.drop_constraint("fk_template_current_version", "template", type_="foreignkey")
    op.drop_column("template", "current_version_id")
    op.drop_column("template", "status")
