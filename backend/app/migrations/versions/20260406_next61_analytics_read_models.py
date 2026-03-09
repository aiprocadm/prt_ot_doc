"""NEXT-61 analytics read models, export center and portal requests.

Revision ID: 20260406_next61_analytics_read_models
Revises: 20260405_next60_incidents_inspections_capa_prep
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260406_next61_analytics_read_models"
down_revision = "20260405_next60_incidents_inspections_capa_prep"
branch_labels = None
depends_on = None


def _json():
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _search():
    return postgresql.TSVECTOR().with_variant(sa.Text(), "sqlite")


def upgrade() -> None:
    op.create_table("dashboard_kpi_snapshots", sa.Column("scope_type", sa.String(32), nullable=False), sa.Column("scope_id", sa.String(36), nullable=True), sa.Column("snapshot_date", sa.Date(), nullable=False), sa.Column("payload", _json(), nullable=False), sa.Column("id", sa.String(36), nullable=False), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("tenant_id", "scope_type", "scope_id", "snapshot_date", name="uq_dashboard_kpi_snapshot"))
    op.create_index(op.f("ix_dashboard_kpi_snapshots_tenant_id"), "dashboard_kpi_snapshots", ["tenant_id"])

    for table, extra in [
        ("package_read_models", [sa.Column("package_id", sa.String(36), nullable=False), sa.Column("package_code", sa.String(255), nullable=True), sa.Column("package_type", sa.String(64), nullable=True), sa.Column("client_company_id", sa.String(36), nullable=True), sa.Column("project_id", sa.String(36), nullable=True), sa.Column("site_id", sa.String(36), nullable=True), sa.Column("status", sa.String(64), nullable=False), sa.Column("progress_percent", sa.Numeric(5,2), nullable=False), sa.Column("required_items_count", sa.Integer(), nullable=False), sa.Column("completed_items_count", sa.Integer(), nullable=False), sa.Column("gaps_count", sa.Integer(), nullable=False), sa.Column("blocking_gaps_count", sa.Integer(), nullable=False), sa.Column("has_overdue_items", sa.Boolean(), nullable=False), sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True), sa.Column("search_text", _search(), nullable=True)],),
        ("person_compliance_read_models", [sa.Column("person_id", sa.String(36), nullable=False), sa.Column("company_id", sa.String(36), nullable=True), sa.Column("site_id", sa.String(36), nullable=True), sa.Column("position_id", sa.String(36), nullable=True), sa.Column("readiness_status", sa.String(32), nullable=False), sa.Column("overdue_trainings", sa.Integer(), nullable=False), sa.Column("overdue_briefings", sa.Integer(), nullable=False), sa.Column("expired_certificates", sa.Integer(), nullable=False), sa.Column("missing_permits", sa.Integer(), nullable=False), sa.Column("ppe_gaps", sa.Integer(), nullable=False), sa.Column("risk_level", sa.String(32), nullable=True), sa.Column("next_deadline_at", sa.DateTime(timezone=True), nullable=True), sa.Column("search_text", _search(), nullable=True)],),
        ("site_safety_read_models", [sa.Column("site_id", sa.String(36), nullable=False), sa.Column("company_id", sa.String(36), nullable=True), sa.Column("readiness_status", sa.String(32), nullable=False), sa.Column("active_people_count", sa.Integer(), nullable=False), sa.Column("blocked_people_count", sa.Integer(), nullable=False), sa.Column("overdue_items_count", sa.Integer(), nullable=False), sa.Column("open_inspections_count", sa.Integer(), nullable=False), sa.Column("open_incidents_count", sa.Integer(), nullable=False), sa.Column("high_risk_items_count", sa.Integer(), nullable=False), sa.Column("pending_packages_count", sa.Integer(), nullable=False), sa.Column("search_text", _search(), nullable=True)],),
        ("contractor_readiness_read_models", [sa.Column("contractor_id", sa.String(36), nullable=False), sa.Column("company_id", sa.String(36), nullable=True), sa.Column("readiness_status", sa.String(32), nullable=False), sa.Column("workers_total", sa.Integer(), nullable=False), sa.Column("workers_ready", sa.Integer(), nullable=False), sa.Column("workers_blocked", sa.Integer(), nullable=False), sa.Column("missing_docs_count", sa.Integer(), nullable=False), sa.Column("missing_training_count", sa.Integer(), nullable=False), sa.Column("overdue_items_count", sa.Integer(), nullable=False), sa.Column("active_packages_count", sa.Integer(), nullable=False)],),
    ]:
        op.create_table(table, *extra, sa.Column("id", sa.String(36), nullable=False), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]), sa.PrimaryKeyConstraint("id"))
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])

    op.create_unique_constraint("uq_package_read_model", "package_read_models", ["tenant_id", "package_id"])
    op.create_index("ix_package_read_models_tenant_status_client_updated", "package_read_models", ["tenant_id", "status", "client_company_id", "updated_at"])
    op.create_unique_constraint("uq_person_compliance_read_model", "person_compliance_read_models", ["tenant_id", "person_id"])
    op.create_index("ix_person_compliance_tenant_readiness_site_deadline", "person_compliance_read_models", ["tenant_id", "readiness_status", "site_id", "next_deadline_at"])
    op.create_unique_constraint("uq_site_safety_read_model", "site_safety_read_models", ["tenant_id", "site_id"])
    op.create_index("ix_site_safety_tenant_readiness", "site_safety_read_models", ["tenant_id", "readiness_status"])
    op.create_unique_constraint("uq_contractor_readiness_read_model", "contractor_readiness_read_models", ["tenant_id", "contractor_id"])
    op.create_index("ix_contractor_readiness_tenant_readiness", "contractor_readiness_read_models", ["tenant_id", "readiness_status"])

    op.create_table("search_index_entries", sa.Column("entity_type", sa.String(64), nullable=False), sa.Column("entity_id", sa.String(36), nullable=False), sa.Column("title", sa.String(512), nullable=False), sa.Column("subtitle", sa.String(512), nullable=True), sa.Column("status", sa.String(64), nullable=True), sa.Column("tags_json", _json(), nullable=True), sa.Column("permissions_json", _json(), nullable=True), sa.Column("route", sa.String(512), nullable=True), sa.Column("preview_payload", _json(), nullable=True), sa.Column("search_text", _search(), nullable=True), sa.Column("id", sa.String(36), nullable=False), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("tenant_id", "entity_type", "entity_id", name="uq_search_index_entry"))
    op.create_index(op.f("ix_search_index_entries_tenant_id"), "search_index_entries", ["tenant_id"])
    op.create_index("ix_search_index_entries_tenant_entity_updated", "search_index_entries", ["tenant_id", "entity_type", "updated_at"])

    op.create_table("client_portal_read_models", sa.Column("client_user_id", sa.String(36), nullable=True), sa.Column("client_company_id", sa.String(36), nullable=True), sa.Column("package_id", sa.String(36), nullable=True), sa.Column("order_id", sa.String(36), nullable=True), sa.Column("project_id", sa.String(36), nullable=True), sa.Column("title", sa.String(512), nullable=False), sa.Column("item_type", sa.String(64), nullable=False), sa.Column("status", sa.String(64), nullable=False), sa.Column("progress_percent", sa.Numeric(5,2), nullable=False), sa.Column("requires_action", sa.Boolean(), nullable=False), sa.Column("safe_payload", _json(), nullable=False), sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True), sa.Column("id", sa.String(36), nullable=False), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_client_portal_read_models_tenant_id"), "client_portal_read_models", ["tenant_id"])
    op.create_index("ix_client_portal_read_models_tenant_company_status_last", "client_portal_read_models", ["tenant_id", "client_company_id", "status", "last_event_at"])

    op.create_table("export_jobs", sa.Column("export_type", sa.String(64), nullable=False), sa.Column("scope_json", _json(), nullable=False), sa.Column("filters_json", _json(), nullable=False), sa.Column("file_id", sa.String(36), nullable=True), sa.Column("row_count", sa.Integer(), nullable=True), sa.Column("status", sa.String(32), nullable=False), sa.Column("error_payload", _json(), nullable=True), sa.Column("id", sa.String(36), nullable=False), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_export_jobs_tenant_id"), "export_jobs", ["tenant_id"])
    op.create_index("ix_export_jobs_tenant_status_updated", "export_jobs", ["tenant_id", "status", "updated_at"])

    op.create_table("portal_requests", sa.Column("client_company_id", sa.String(36), nullable=True), sa.Column("package_id", sa.String(36), nullable=True), sa.Column("project_id", sa.String(36), nullable=True), sa.Column("created_by_user_id", sa.String(36), nullable=True), sa.Column("title", sa.String(512), nullable=False), sa.Column("body", sa.Text(), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("priority", sa.String(16), nullable=False), sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True), sa.Column("id", sa.String(36), nullable=False), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_portal_requests_tenant_id"), "portal_requests", ["tenant_id"])

    op.create_table("portal_request_messages", sa.Column("portal_request_id", sa.String(36), nullable=False), sa.Column("author_user_id", sa.String(36), nullable=True), sa.Column("author_role", sa.String(16), nullable=False), sa.Column("body", sa.Text(), nullable=False), sa.Column("attachments_json", _json(), nullable=True), sa.Column("id", sa.String(36), nullable=False), sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_portal_request_messages_portal_request_id"), "portal_request_messages", ["portal_request_id"])
    op.create_index(op.f("ix_portal_request_messages_tenant_id"), "portal_request_messages", ["tenant_id"])


def downgrade() -> None:
    for table in ["portal_request_messages", "portal_requests", "export_jobs", "client_portal_read_models", "search_index_entries", "contractor_readiness_read_models", "site_safety_read_models", "person_compliance_read_models", "package_read_models", "dashboard_kpi_snapshots"]:
        op.drop_table(table)
