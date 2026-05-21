"""NEXT-56 package presets/profiles/runs v2

Revision ID: 20260329_next56
Revises: 20260328_next55
Create Date: 2026-03-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260329_next56"
down_revision = "20260328_next55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    package_entity_status = postgresql.ENUM("draft", "active", "archived", name="package_entity_status", create_type=False)
    package_source_type = postgresql.ENUM("csv", "xlsx", "json", "mixed", name="package_source_type", create_type=False)
    package_preset_status = postgresql.ENUM("draft", "active", "archived", name="package_preset_status", create_type=False)
    replace_mode = postgresql.ENUM("none", "preview", "apply", name="replace_mode", create_type=False)
    package_output_format = postgresql.ENUM("docx", "pdf", "both", name="package_output_format", create_type=False)
    pack_run_source_type = postgresql.ENUM("csv", "xlsx", "json", "mixed", name="pack_run_source_type", create_type=False)
    pack_run_lifecycle_status = postgresql.ENUM(
        "queued", "running", "success", "failed", "canceled", "partial_success",
        name="pack_run_lifecycle_status", create_type=False,
    )
    pack_run_item_status = postgresql.ENUM("queued", "running", "success", "failed", "skipped", name="pack_run_item_status", create_type=False)
    pack_log_level = postgresql.ENUM("info", "warning", "error", name="pack_log_level", create_type=False)

    bind = op.get_bind()
    for enum_ in [
        package_entity_status,
        package_source_type,
        package_preset_status,
        replace_mode,
        package_output_format,
        pack_run_source_type,
        pack_run_lifecycle_status,
        pack_run_item_status,
        pack_log_level,
    ]:
        enum_.create(bind, checkfirst=True)

    op.create_table(
        "package_profiles_v2",
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pipeline_steps_json", sa.JSON(), nullable=False),
        sa.Column("concurrency_limit", sa.Integer(), nullable=True),
        sa.Column("status", package_entity_status, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_package_profiles_v2_tenant_code"),
    )
    op.create_index("ix_package_profiles_v2_tenant_status_updated", "package_profiles_v2", ["tenant_id", "status", "updated_at"])

    op.create_table(
        "package_presets_v2",
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("package_profile_id", sa.String(length=36), nullable=False),
        sa.Column("naming_rule", sa.String(length=512), nullable=False),
        sa.Column("source_type", package_source_type, nullable=False),
        sa.Column("mapping_json", sa.JSON(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("status", package_preset_status, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["package_profile_id"], ["package_profiles_v2.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_package_presets_v2_tenant_code"),
    )
    op.create_index("ix_package_presets_v2_tenant_status_updated", "package_presets_v2", ["tenant_id", "status", "updated_at"])

    op.create_table(
        "package_preset_items",
        sa.Column("package_preset_id", sa.String(length=36), nullable=False),
        sa.Column("order_no", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=True),
        sa.Column("template_version_id", sa.String(length=36), nullable=False),
        sa.Column("header_preset_json", sa.JSON(), nullable=True),
        sa.Column("replace_mode", replace_mode, nullable=False),
        sa.Column("replace_map_json", sa.JSON(), nullable=True),
        sa.Column("output_format", package_output_format, nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("conditions_json", sa.JSON(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["package_preset_id"], ["package_presets_v2.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["template.id"]),
        sa.ForeignKeyConstraint(["template_version_id"], ["templateversion.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_preset_id", "order_no", name="uq_package_preset_items_order"),
    )
    op.create_index("ix_package_preset_items_order", "package_preset_items", ["package_preset_id", "order_no"])

    op.create_table(
        "pack_runs",
        sa.Column("package_preset_id", sa.String(length=36), nullable=False),
        sa.Column("package_profile_id", sa.String(length=36), nullable=False),
        sa.Column("source_file_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", pack_run_source_type, nullable=False),
        sa.Column("source_rows_count", sa.Integer(), nullable=False),
        sa.Column("selected_rows_count", sa.Integer(), nullable=False),
        sa.Column("status", pack_run_lifecycle_status, nullable=False),
        sa.Column("result_zip_file_id", sa.String(length=36), nullable=True),
        sa.Column("stats_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_hash", sa.String(length=128), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["package_preset_id"], ["package_presets_v2.id"]),
        sa.ForeignKeyConstraint(["package_profile_id"], ["package_profiles_v2.id"]),
        sa.ForeignKeyConstraint(["result_zip_file_id"], ["file.id"]),
        sa.ForeignKeyConstraint(["source_file_id"], ["file.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", "request_hash", name="uq_pack_runs_idempotency"),
    )
    op.create_index("ix_pack_runs_status_created", "pack_runs", ["tenant_id", "status", "created_at"])
    op.create_index("ix_pack_runs_tenant_status_updated", "pack_runs", ["tenant_id", "status", "updated_at"])

    op.create_table(
        "pack_run_items",
        sa.Column("pack_run_id", sa.String(length=36), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("source_record_hash", sa.String(length=64), nullable=False),
        sa.Column("status", pack_run_item_status, nullable=False),
        sa.Column("document_job_id", sa.String(length=36), nullable=True),
        sa.Column("output_docx_file_id", sa.String(length=36), nullable=True),
        sa.Column("output_pdf_file_id", sa.String(length=36), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["pack_run_id"], ["pack_runs.id"]),
        sa.ForeignKeyConstraint(["output_docx_file_id"], ["file.id"]),
        sa.ForeignKeyConstraint(["output_pdf_file_id"], ["file.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pack_run_items_run_status", "pack_run_items", ["pack_run_id", "status"])

    op.create_table(
        "pack_run_logs",
        sa.Column("pack_run_id", sa.String(length=36), nullable=False),
        sa.Column("level", pack_log_level, nullable=False),
        sa.Column("step", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["pack_run_id"], ["pack_runs.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("pack_run_logs")
    op.drop_index("ix_pack_run_items_run_status", table_name="pack_run_items")
    op.drop_table("pack_run_items")
    op.drop_index("ix_pack_runs_tenant_status_updated", table_name="pack_runs")
    op.drop_index("ix_pack_runs_status_created", table_name="pack_runs")
    op.drop_table("pack_runs")
    op.drop_index("ix_package_preset_items_order", table_name="package_preset_items")
    op.drop_table("package_preset_items")
    op.drop_index("ix_package_presets_v2_tenant_status_updated", table_name="package_presets_v2")
    op.drop_table("package_presets_v2")
    op.drop_index("ix_package_profiles_v2_tenant_status_updated", table_name="package_profiles_v2")
    op.drop_table("package_profiles_v2")

    bind = op.get_bind()
    for name in [
        "pack_log_level",
        "pack_run_item_status",
        "pack_run_lifecycle_status",
        "pack_run_source_type",
        "package_output_format",
        "replace_mode",
        "package_preset_status",
        "package_source_type",
        "package_entity_status",
    ]:
        sa.Enum(name=name).drop(bind, checkfirst=True)
