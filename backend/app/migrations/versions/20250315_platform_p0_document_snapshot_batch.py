"""Add document snapshots, batch runs, and template metadata.

Revision ID: 20250315_platform_p0_document_snapshot_batch
Revises: 20250312_add_audit_log_metadata
Create Date: 2025-03-15 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20250315_platform_p0_document_snapshot_batch"
down_revision: str | tuple[str, ...] = "20250312_add_audit_log_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in ("generated", "approved", "revoked"):
            op.execute(f"ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "document_snapshot",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("document.id"), nullable=False),
        sa.Column("template_id", sa.String(length=36), sa.ForeignKey("template.id"), nullable=False),
        sa.Column(
            "template_version_id",
            sa.String(length=36),
            sa.ForeignKey("templateversion.id"),
            nullable=True,
        ),
        sa.Column("template_code", sa.String(length=255), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=True),
        sa.Column("company_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("compliance_refs", sa.JSON(), nullable=False),
        sa.Column("render_log", sa.JSON(), nullable=False),
        sa.Column("integrity_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("user.id"), nullable=False),
    )
    op.create_index("ix_document_snapshot_document", "document_snapshot", ["document_id"])
    op.create_index(
        "ix_document_snapshot_template",
        "document_snapshot",
        ["tenant_id", "template_id"],
    )

    with op.batch_alter_table("documentversion", schema=None) as batch:
        batch.add_column(sa.Column("snapshot_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_document_version_snapshot",
            "document_snapshot",
            ["snapshot_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "document_batch_run",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("template_id", sa.String(length=36), sa.ForeignKey("template.id"), nullable=False),
        sa.Column(
            "template_version_id",
            sa.String(length=36),
            sa.ForeignKey("templateversion.id"),
            nullable=False,
        ),
        sa.Column("company_id", sa.String(length=36), sa.ForeignKey("company.id"), nullable=False),
        sa.Column("naming_pattern", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "done",
                "failed",
                name="documentbatchstatus",
            ),
            nullable=False,
        ),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("processed", sa.Integer(), nullable=False),
        sa.Column("succeeded", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("error_report", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_document_batch_run_tenant_created",
        "document_batch_run",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "document_batch_item",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "batch_id",
            sa.String(length=36),
            sa.ForeignKey("document_batch_run.id"),
            nullable=False,
        ),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=True),
        sa.Column("output_name", sa.String(length=255), nullable=True),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("document_version_id", sa.String(length=36), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "succeeded",
                "failed",
                name="documentbatchitemstatus",
            ),
            nullable=False,
        ),
        sa.Column("error", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_document_batch_item_batch",
        "document_batch_item",
        ["batch_id"],
    )
    op.create_index(
        "ix_document_batch_item_status",
        "document_batch_item",
        ["tenant_id", "status"],
    )

    with op.batch_alter_table("templateversion", schema=None) as batch:
        batch.add_column(sa.Column("document_type", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("required_fields_schema", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("applicability_rules", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("output_types", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("profile", sa.JSON(), nullable=True))

    with op.batch_alter_table("idempotency_keys", schema=None) as batch:
        batch.create_unique_constraint(
            "uq_idempotency_key_per_tenant",
            ["tenant_id", "key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("idempotency_keys", schema=None) as batch:
        batch.drop_constraint("uq_idempotency_key_per_tenant", type_="unique")

    with op.batch_alter_table("templateversion", schema=None) as batch:
        batch.drop_column("profile")
        batch.drop_column("output_types")
        batch.drop_column("applicability_rules")
        batch.drop_column("required_fields_schema")
        batch.drop_column("document_type")

    op.drop_index("ix_document_batch_item_status", table_name="document_batch_item")
    op.drop_index("ix_document_batch_item_batch", table_name="document_batch_item")
    op.drop_table("document_batch_item")

    op.drop_index("ix_document_batch_run_tenant_created", table_name="document_batch_run")
    op.drop_table("document_batch_run")

    op.drop_index("ix_document_snapshot_template", table_name="document_snapshot")
    op.drop_index("ix_document_snapshot_document", table_name="document_snapshot")
    op.drop_table("document_snapshot")

    with op.batch_alter_table("documentversion", schema=None) as batch:
        batch.drop_constraint("fk_document_version_snapshot", type_="foreignkey")
        batch.drop_column("snapshot_id")
