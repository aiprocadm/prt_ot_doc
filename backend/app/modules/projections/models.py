from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import TenantBaseModel


def _json_type():
    return JSONB().with_variant(JSON(), "sqlite")


def _search_type():
    return TSVECTOR().with_variant(Text(), "sqlite")


class DashboardKpiSnapshot(TenantBaseModel):
    __tablename__ = "dashboard_kpi_snapshots"
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(_json_type(), nullable=False, default=dict)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "scope_type", "scope_id", "snapshot_date", name="uq_dashboard_kpi_snapshot"
        ),
    )


class PackageReadModel(TenantBaseModel):
    __tablename__ = "package_read_models"
    package_id: Mapped[str] = mapped_column(String(36), nullable=False)
    package_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    package_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_company_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    site_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="new")
    progress_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    required_items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gaps_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_gaps_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_overdue_items: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_text: Mapped[str | None] = mapped_column(_search_type(), nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "package_id", name="uq_package_read_model"),
        Index(
            "ix_package_read_models_tenant_status_client_updated",
            "tenant_id",
            "status",
            "client_company_id",
            "updated_at",
        ),
    )


class PersonComplianceReadModel(TenantBaseModel):
    __tablename__ = "person_compliance_read_models"
    person_id: Mapped[str] = mapped_column(String(36), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    site_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    position_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    readiness_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    overdue_trainings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overdue_briefings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expired_certificates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_permits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ppe_gaps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    next_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    search_text: Mapped[str | None] = mapped_column(_search_type(), nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "person_id", name="uq_person_compliance_read_model"),
        Index(
            "ix_person_compliance_tenant_readiness_site_deadline",
            "tenant_id",
            "readiness_status",
            "site_id",
            "next_deadline_at",
        ),
    )


class SiteSafetyReadModel(TenantBaseModel):
    __tablename__ = "site_safety_read_models"
    site_id: Mapped[str] = mapped_column(String(36), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    readiness_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    active_people_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_people_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overdue_items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_inspections_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_incidents_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_risk_items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_packages_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    search_text: Mapped[str | None] = mapped_column(_search_type(), nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "site_id", name="uq_site_safety_read_model"),
        Index("ix_site_safety_tenant_readiness", "tenant_id", "readiness_status"),
    )


class ContractorReadinessReadModel(TenantBaseModel):
    __tablename__ = "contractor_readiness_read_models"
    contractor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    readiness_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    workers_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workers_ready: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workers_blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_docs_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_training_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overdue_items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_packages_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("tenant_id", "contractor_id", name="uq_contractor_readiness_read_model"),
        Index("ix_contractor_readiness_tenant_readiness", "tenant_id", "readiness_status"),
    )


class SearchIndexEntry(TenantBaseModel):
    __tablename__ = "search_index_entries"
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags_json: Mapped[dict[str, Any] | None] = mapped_column(_json_type(), nullable=True)
    permissions_json: Mapped[dict[str, Any] | None] = mapped_column(_json_type(), nullable=True)
    route: Mapped[str | None] = mapped_column(String(512), nullable=True)
    preview_payload: Mapped[dict[str, Any] | None] = mapped_column(_json_type(), nullable=True)
    search_text: Mapped[str | None] = mapped_column(_search_type(), nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", "entity_id", name="uq_search_index_entry"),
        Index(
            "ix_search_index_entries_tenant_entity_updated",
            "tenant_id",
            "entity_type",
            "updated_at",
        ),
    )


class ClientPortalReadModel(TenantBaseModel):
    __tablename__ = "client_portal_read_models"
    client_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    client_company_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    package_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    item_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    progress_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    requires_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    safe_payload: Mapped[dict[str, Any]] = mapped_column(_json_type(), nullable=False, default=dict)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index(
            "ix_client_portal_read_models_tenant_company_status_last",
            "tenant_id",
            "client_company_id",
            "status",
            "last_event_at",
        ),
    )


class ExportJob(TenantBaseModel):
    __tablename__ = "export_jobs"
    export_type: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    anonymized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, default="file")
    target_config: Mapped[dict[str, Any]] = mapped_column(
        _json_type(), nullable=False, default=dict
    )
    scope_json: Mapped[dict[str, Any]] = mapped_column(_json_type(), nullable=False, default=dict)
    filters_json: Mapped[dict[str, Any]] = mapped_column(_json_type(), nullable=False, default=dict)
    file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    delivery_history_json: Mapped[list[dict[str, Any]]] = mapped_column(
        _json_type(), nullable=False, default=list
    )
    error_payload: Mapped[dict[str, Any] | None] = mapped_column(_json_type(), nullable=True)
    __table_args__ = (
        Index("ix_export_jobs_tenant_status_updated", "tenant_id", "status", "updated_at"),
    )


class ExportSchedule(TenantBaseModel):
    __tablename__ = "export_schedules"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    cron_expr: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, default="file")
    target_config: Mapped[dict[str, Any]] = mapped_column(
        _json_type(), nullable=False, default=dict
    )
    filters_json: Mapped[dict[str, Any]] = mapped_column(_json_type(), nullable=False, default=dict)
    anonymized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_export_schedules_tenant_active", "tenant_id", "is_active", "updated_at"),
    )


class KpiDefinition(TenantBaseModel):
    __tablename__ = "kpi_definitions"

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    formula_json: Mapped[dict[str, Any]] = mapped_column(_json_type(), nullable=False, default=dict)
    threshold_json: Mapped[dict[str, Any]] = mapped_column(
        _json_type(), nullable=False, default=dict
    )
    locale_labels: Mapped[dict[str, Any]] = mapped_column(
        _json_type(), nullable=False, default=dict
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (Index("ix_kpi_definitions_tenant_code", "tenant_id", "code", unique=True),)


class PortalRequest(TenantBaseModel):
    __tablename__ = "portal_requests"
    client_company_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    package_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PortalRequestMessage(TenantBaseModel):
    __tablename__ = "portal_request_messages"
    portal_request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    author_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    author_role: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    attachments_json: Mapped[dict[str, Any] | None] = mapped_column(_json_type(), nullable=True)
