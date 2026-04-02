"""Add client portal package entities.

Revision ID: 20250430_client_portal_packages_mvp
Revises: 20250425_edo_approval_signature_mvp
Create Date: 2025-04-30 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20250430_client_portal_packages_mvp"
down_revision: str | tuple[str, ...] = "20250425_edo_approval_signature_mvp"
branch_labels: str | None = None
depends_on: str | None = None

package_run_status = sa.Enum("draft", "running", "success", "failed", "canceled", name="packagerunstatus")
package_requirement_type = sa.Enum("file", "text", "table", name="packagerequirementtype")
package_requirement_status = sa.Enum("missing", "provided", "approved", "rejected", name="packagerequirementstatus")
client_request_ticket_status = sa.Enum("open", "in_progress", "resolved", "closed", name="clientrequestticketstatus")


def upgrade() -> None:
    bind = op.get_bind()
    package_run_status.create(bind, checkfirst=True)
    package_requirement_type.create(bind, checkfirst=True)
    package_requirement_status.create(bind, checkfirst=True)
    client_request_ticket_status.create(bind, checkfirst=True)

    op.create_table(
        "package_presets",
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("steps_json", sa.JSON(), nullable=False),
        sa.Column("required_inputs_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_package_presets_code"),
    )
    op.create_index("ix_package_presets_code", "package_presets", ["tenant_id", "code"])

    op.create_table(
        "package_runs",
        sa.Column("preset_id", sa.String(length=36), nullable=False),
        sa.Column("initiated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("client_company_id", sa.String(length=36), nullable=True),
        sa.Column("status", package_run_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output_zip_s3_key", sa.String(length=512), nullable=True),
        sa.Column("output_pdf_s3_key", sa.String(length=512), nullable=True),
        sa.Column("qc_report_json", sa.JSON(), nullable=True),
        sa.Column("error_payload_json", sa.JSON(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["preset_id"], ["package_presets.id"]),
        sa.ForeignKeyConstraint(["initiated_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["client_company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_package_runs_status_updated", "package_runs", ["tenant_id", "status", "updated_at"])

    op.create_table(
        "package_requirements",
        sa.Column("package_run_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("type", package_requirement_type, nullable=False),
        sa.Column("status", package_requirement_status, nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["package_run_id"], ["package_runs.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "client_portal_tokens",
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("package_run_id", sa.String(length=36), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["package_run_id"], ["package_runs.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_client_portal_tokens_expires_hash",
        "client_portal_tokens",
        ["tenant_id", "expires_at", "token_hash"],
    )

    op.create_table(
        "client_request_tickets",
        sa.Column("package_run_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", client_request_ticket_status, nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["package_run_id"], ["package_runs.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "package_events",
        sa.Column("package_run_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["package_run_id"], ["package_runs.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("package_events")
    op.drop_table("client_request_tickets")
    op.drop_index("ix_client_portal_tokens_expires_hash", table_name="client_portal_tokens")
    op.drop_table("client_portal_tokens")
    op.drop_table("package_requirements")
    op.drop_index("ix_package_runs_status_updated", table_name="package_runs")
    op.drop_table("package_runs")
    op.drop_index("ix_package_presets_code", table_name="package_presets")
    op.drop_table("package_presets")

    bind = op.get_bind()
    client_request_ticket_status.drop(bind, checkfirst=True)
    package_requirement_status.drop(bind, checkfirst=True)
    package_requirement_type.drop(bind, checkfirst=True)
    package_run_status.drop(bind, checkfirst=True)
