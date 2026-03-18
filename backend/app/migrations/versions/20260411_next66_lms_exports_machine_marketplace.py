"""next66 lms export machine marketplace foundation

Revision ID: 20260411_next66
Revises: 20260410_next65_search_memory
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa

revision = "20260411_next66"
down_revision = "20260410_next65_search_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_key", sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("api_key", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("api_key", sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True))

    op.add_column("training_modules", sa.Column("materials_json", sa.JSON(), nullable=True))
    op.create_table(
        "training_lessons",
        sa.Column("training_module_id", sa.String(length=36), sa.ForeignKey("training_modules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("lesson_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_type", sa.String(length=32), nullable=False, server_default="document"),
        sa.Column("content_ref", sa.Text(), nullable=True),
        sa.Column("materials_json", sa.JSON(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_lessons_module", "training_lessons", ["training_module_id"])

    op.add_column("training_enrollments", sa.Column("progress_percent", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("training_enrollments", sa.Column("completion_status", sa.String(length=32), nullable=False, server_default="assigned"))
    op.add_column("training_enrollments", sa.Column("completion_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("training_enrollments", sa.Column("completion_payload", sa.JSON(), nullable=True))
    op.add_column("training_enrollments", sa.Column("external_runtime_state", sa.JSON(), nullable=True))

    op.add_column("training_attempts", sa.Column("source_type", sa.String(length=32), nullable=False, server_default="manual"))
    op.add_column("training_attempts", sa.Column("external_session_ref", sa.String(length=255), nullable=True))
    op.add_column("training_attempts", sa.Column("provider_payload", sa.JSON(), nullable=True))

    op.add_column("export_jobs", sa.Column("dataset_code", sa.String(length=64), nullable=True))
    op.add_column("export_jobs", sa.Column("schema_version", sa.String(length=32), nullable=False, server_default="v1"))
    op.add_column("export_jobs", sa.Column("anonymized", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("export_jobs", sa.Column("target_type", sa.String(length=32), nullable=False, server_default="file"))
    op.add_column("export_jobs", sa.Column("target_config", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("export_jobs", sa.Column("progress_percent", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("export_jobs", sa.Column("delivery_history_json", sa.JSON(), nullable=False, server_default="[]"))

    op.create_table(
        "export_schedules",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dataset_code", sa.String(length=64), nullable=False),
        sa.Column("cron_expr", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False, server_default="file"),
        sa.Column("target_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("filters_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("anonymized", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_schedules_tenant_active", "export_schedules", ["tenant_id", "is_active", "updated_at"])

    op.create_table(
        "kpi_definitions",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dataset_code", sa.String(length=64), nullable=False),
        sa.Column("formula_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("threshold_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("locale_labels", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kpi_definitions_tenant_code", "kpi_definitions", ["tenant_id", "code"], unique=True)

    op.create_table(
        "marketplace_catalog_items",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("preview_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("compatibility_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("dependency_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "item_type", "code", "version_label", name="uq_marketplace_catalog_item"),
    )
    op.create_index("ix_marketplace_catalog_lookup", "marketplace_catalog_items", ["tenant_id", "item_type", "status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_marketplace_catalog_lookup", table_name="marketplace_catalog_items")
    op.drop_table("marketplace_catalog_items")
    op.drop_index("ix_kpi_definitions_tenant_code", table_name="kpi_definitions")
    op.drop_table("kpi_definitions")
    op.drop_index("ix_export_schedules_tenant_active", table_name="export_schedules")
    op.drop_table("export_schedules")
    for column in ["delivery_history_json", "progress_percent", "target_config", "target_type", "anonymized", "schema_version", "dataset_code"]:
        op.drop_column("export_jobs", column)
    for column in ["provider_payload", "external_session_ref", "source_type"]:
        op.drop_column("training_attempts", column)
    for column in ["external_runtime_state", "completion_payload", "completion_confirmed_at", "completion_status", "progress_percent"]:
        op.drop_column("training_enrollments", column)
    op.drop_index("ix_training_lessons_module", table_name="training_lessons")
    op.drop_table("training_lessons")
    op.drop_column("training_modules", "materials_json")
    for column in ["rate_limit_per_minute", "revoked_at", "usage_count"]:
        op.drop_column("api_key", column)
