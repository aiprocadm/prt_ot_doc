from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

from app.db.session import TenantBase
from app.models.base import (
    SharedModel,
    SoftDeleteMixin,
    TenantBaseModel,
    TimestampMixin,
    UUIDMixin,
    VersionedMixin,
)
from app.models.file import File
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

if TYPE_CHECKING:  # pragma: no cover - used for type checkers only
    from app.models.file import File
    from app.models.risk import RiskHazard

__all__ = [
    "AuditLog",
    "AuditExportJob",
    "ApiKey",
    "Company",
    "PipelineRun",
    "PipelineRunStatus",
    "IdempotencyKey",
    "IdempotencyStatus",
    "Equipment",
    "Incident",
    "IncidentLog",
    "IncidentPerson",
    "IncidentPersonRole",
    "IncidentStatus",
    "IncidentType",
    "IncidentStage",
    "JournalEntry",
    "NPA",
    "NPABinding",
    "NpaBindingTarget",
    "Inspection",
    "InspectionStatus",
    "InspectionType",
    "InspectionResult",
    "Attestation",
    "AttestationStatus",
    "Prescription",
    "PrescriptionStatus",
    "Outbox",
    "OutboxStatus",
    "PackagePreset",
    "PackageProfile",
    "Site",
    "MedicalExam",
    "DocumentPack",
    "DocumentPackItem",
    "DocumentPackModule",
    "DocumentPackScenario",
    "Permit",
    "Person",
    "EmploymentStatus",
    "PlanTask",
    "Position",
    "PPENorm",
    "PPEItemCategory",
    "PPEItem",
    "PPEIssue",
    "JournalType",
    "RiskMap",
    "RiskMethodology",
    "Workplace",
    "WorkplaceHazardLink",
    "PositionHazardLink",
    "Journal",
    "JournalEntry",
    "Tenant",
    "TenantQuota",
    "TenantCounter",
    "TenantSettings",
    "TenantIntegrationKey",
    "TenantQuotaCounter",
    "BillingPlan",
    "BillingSubscription",
    "BillingSubscriptionStatus",
    "BillingUsageCounter",
    "BillingInvoice",
    "BillingInvoiceStatus",
    "BillingEvent",
    "BillingEventType",
    "TenantRateLimit",
    "TenantLimitOverride",
    "Template",
    "TemplateStatus",
    "TemplateVersion",
    "TemplateUsage",
    "Training",
    "TrainingStatus",
    "TrainingCourse",
    "TrainingPlan",
    "TrainingSession",
    "TrainingSessionStatus",
    "TrainingCertificate",
    "User",
    "UserRole",
    "UserAttribute",
    "AuthzRole",
    "AuthzPermission",
    "AuthzRolePermission",
    "AuthzUserRole",
    "WarehousePPE",
    "WebhookSubscription",
    "WebhookEndpoint",
    "WebhookDelivery",
    "ApprovalRoute",
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalRequestStatus",
    "ApprovalDecisionType",
    "Signature",
    "SignatureStatus",
    "SignatureType",
    "EdoMessage",
    "EdoReceipt",
    "EdoStatusHistory",
    "EdoDirection",
    "EdoStatus",
]


class RoleEnum(str, enum.Enum):
    """Supported access roles within a tenant."""

    OWNER = "owner"
    ADMIN = "admin"
    OT_PB_LEAD = "ot_pb_lead"
    OT_SPECIALIST = "ot_specialist"
    PB_ENGINEER = "pb_engineer"
    ECOLOGIST = "ecologist"
    HR = "hr"
    LAWYER = "lawyer"
    ACCOUNTANT = "accountant"
    LINE_MANAGER = "line_manager"
    WORKER = "worker"
    CONTRACTOR_INSPECTOR = "contractor_inspector"
    EMPLOYEE = "employee"
    CLIENT_ADMIN = "client_admin"
    CLIENT_USER = "client_user"
    OT_HEAD = "ot_head"
    CLERK = "clerk"
    TEACHER = "teacher"
    STUDENT = "student"
    MANAGER = "manager"
    EXECUTOR = "executor"
    CLIENT = "client"
    AUDITOR_RO = "auditor_ro"
    INSPECTOR_CONTRACTOR = "inspector_contractor"


class Tenant(SharedModel):
    code: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=True)
    kind: Mapped[str] = mapped_column(
        Enum("customer", "branch", "contractor", name="tenantkind"),
        nullable=False,
        default="customer",
    )
    schema_name: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    s3_prefix: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenant_slug"),
        UniqueConstraint("code", name="uq_tenants_code"),
        Index("ix_tenants_parent_id", "parent_id"),
        Index("ix_tenants_kind", "kind"),
    )


class TenantQuota(SharedModel):
    __tablename__ = "tenant_quotas"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, unique=True)
    max_parallel_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    max_doc_generations_per_month: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    max_storage_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=10240)
    monthly_edo_outgoing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enforce_billing_gate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TenantSettings(SharedModel):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, unique=True)
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    s3_prefix: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retention_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    integration_keys: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class TenantCounter(SharedModel):
    __tablename__ = "tenant_counters"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    yyyymm: Mapped[str] = mapped_column(String(6), nullable=False)
    doc_generations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("tenant_id", "yyyymm", name="uq_tenant_counter_period"),)




class TenantIntegrationKey(SharedModel):
    __tablename__ = "tenant_integrations_keys"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    meta_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_integrations_keys_tenant_provider"),
    )


class TenantQuotaCounter(SharedModel):
    __tablename__ = "tenant_quotas_counters"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    counter_name: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("tenant_id", "counter_name", "period", name="uq_tenant_quota_counter"),
    )


class BillingSubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIAL = "trial"
    PAST_DUE = "past_due"
    SUSPENDED = "suspended"
    CANCELED = "canceled"


class BillingPlan(SharedModel, SoftDeleteMixin):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    limits: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    price: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class BillingSubscription(SharedModel, SoftDeleteMixin):
    __tablename__ = "subscriptions"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), nullable=False)
    status: Mapped[BillingSubscriptionStatus] = mapped_column(Enum(BillingSubscriptionStatus), nullable=False, default=BillingSubscriptionStatus.ACTIVE)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_provider: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    external_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_subscriptions_tenant_status", "tenant_id", "status"),
        Index("ix_subscriptions_tenant_period_end", "tenant_id", "period_end"),
    )


class BillingUsageCounter(SharedModel, SoftDeleteMixin):
    __tablename__ = "usage_counters"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False)
    period_yyyymm: Mapped[int] = mapped_column(Integer, nullable=False)
    docs_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edo_outgoing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    s3_bytes_used: Mapped[int] = mapped_column(Numeric(20, 0), nullable=False, default=0)
    active_workers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("tenant_id", "period_yyyymm", name="uq_usage_counters_tenant_period"),)


class BillingInvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


class BillingInvoice(SharedModel):
    __tablename__ = "invoices"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    period_yyyymm: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    status: Mapped[BillingInvoiceStatus] = mapped_column(Enum(BillingInvoiceStatus), nullable=False, default=BillingInvoiceStatus.DRAFT)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (Index("ix_invoices_tenant_status", "tenant_id", "status"),)


class BillingEventType(str, enum.Enum):
    GENERATION_COMPLETED = "generation_completed"
    EDO_SENT = "edo_sent"
    FILE_UPLOADED = "file_uploaded"
    WORKER_ACTIVATED = "worker_activated"
    PLAN_CHANGED = "plan_changed"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_SUCCEEDED = "payment_succeeded"


class BillingEvent(SharedModel):
    __tablename__ = "billing_events"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    type: Mapped[BillingEventType] = mapped_column(Enum(BillingEventType), nullable=False, index=True)
    ref_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_billing_events_tenant_created", "tenant_id", "created_at"),
        UniqueConstraint("tenant_id", "type", "ref_type", "ref_id", name="uq_billing_event_dedup"),
    )


class TenantRateLimit(SharedModel):
    __tablename__ = "tenant_rate_limits"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, unique=True)
    concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    burst: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    rps: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    queues: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class TenantLimitOverride(SharedModel):
    __tablename__ = "tenant_limits_override"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, unique=True)
    limits: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))


class WebhookSubscription(SharedModel):
    __tablename__ = "webhook_subscription"

    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    headers: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_webhook_subscription_tenant_event", "tenant_id", "event_type"),
    )
class User(TenantBaseModel, SoftDeleteMixin):
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped[Company | None] = relationship(
        "Company", backref="users", lazy="joined"
    )
    roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_user_email", "tenant_id", "email", unique=True),
        Index("ix_user_company", "tenant_id", "company_id"),
    )


class UserRole(TenantBaseModel):
    __tablename__ = "user_role"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), nullable=False)

    user: Mapped[User] = relationship("User", back_populates="roles")

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "role", name="uq_user_role"),
        Index("ix_user_role_user", "tenant_id", "user_id"),
    )


class UserAttribute(TenantBaseModel):
    __tablename__ = "user_attribute"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    site_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    project_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    contractor_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_user_attribute"),
        Index("ix_user_attribute_user", "tenant_id", "user_id"),
    )




class AuthzBaseModel(TenantBase, TimestampMixin, VersionedMixin, UUIDMixin):
    __abstract__ = True

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )


class AuthzRole(AuthzBaseModel):
    __tablename__ = "authz_roles"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_authz_roles_tenant_code"),
    )


class AuthzPermission(AuthzBaseModel):
    __tablename__ = "authz_permissions"

    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        UniqueConstraint("resource", "action", name="uq_authz_permission_resource_action"),
    )


class AuthzRolePermission(AuthzBaseModel):
    __tablename__ = "authz_role_permissions"

    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("authz_roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("authz_permissions.id", ondelete="CASCADE"), nullable=True
    )
    permission_code: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "role_id", "permission_code", name="uq_authz_role_permissions_tenant_role_code"),
    )


class AuthzUserRole(AuthzBaseModel):
    __tablename__ = "authz_user_roles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("authz_roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "role_id", name="uq_authz_user_roles_tenant_user_role"),
        Index("ix_authz_user_roles_user", "tenant_id", "user_id"),
        Index("ix_authz_user_roles_role", "tenant_id", "role_id"),
    )


class AuthzPolicy(AuthzBaseModel):
    __tablename__ = "authz_policies"

    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    effect: Mapped[str] = mapped_column(String(8), nullable=False)
    conditions_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_authz_policy_lookup", "tenant_id", "resource", "action", "enabled", "priority"),
    )


class ApiKey(TenantBaseModel):
    __tablename__ = "api_key"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes: Mapped[str] = mapped_column(String(255), nullable=False, default="api:read")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_api_key_tenant_name"),
    )

    @property
    def scope_list(self) -> list[str]:
        return [scope for scope in self.scopes.split() if scope]


class Company(TenantBaseModel, SoftDeleteMixin):
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str | None] = mapped_column("tax_id", String(32), nullable=True)
    kpp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ogrn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    activity_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    okved_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    legal_address: Mapped[str | None] = mapped_column("address", String(255))
    actual_address: Mapped[str | None] = mapped_column(String(255))
    director: Mapped[str | None] = mapped_column(String(255))
    bank_name: Mapped[str | None] = mapped_column(String(255))
    bank_bik: Mapped[str | None] = mapped_column(String(32))
    bank_account: Mapped[str | None] = mapped_column(String(32))
    phone_numbers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    contact_person: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    email: Mapped[str | None] = mapped_column(String(320))
    logo_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    stamp_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    work_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    hazardous_factors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_hazardous_production_facility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    has_dangerous_objects: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    logo_file: Mapped["File | None"] = relationship(
        "File", foreign_keys=[logo_file_id], lazy="selectin"
    )
    stamp_file: Mapped["File | None"] = relationship(
        "File", foreign_keys=[stamp_file_id], lazy="selectin"
    )


    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_company_tenant_name"),
    )

    tax_id = synonym("inn")
    address = synonym("legal_address")


class Position(TenantBaseModel, SoftDeleteMixin):
    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    safety_category: Mapped[str | None] = mapped_column(String(64))
    working_conditions_class: Mapped[str | None] = mapped_column(String(32))
    hazardous_factors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    company: Mapped[Company] = relationship(backref="positions")
    hazards: Mapped[list["RiskHazard"]] = relationship(
        "RiskHazard",
        secondary="position_hazard",
        lazy="selectin",
        back_populates="positions",
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "name", name="uq_position_company_name"
        ),
    )


class EmploymentStatus(str, enum.Enum):
    """Employment state for personnel records."""

    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class Person(TenantBaseModel, SoftDeleteMixin):
    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    position_id: Mapped[str | None] = mapped_column(ForeignKey("position.id"))
    workplace_id: Mapped[str | None] = mapped_column(ForeignKey("workplace.id"))
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100))
    birth_date: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))
    personnel_number: Mapped[str | None] = mapped_column(String(32), index=True)
    hired_at: Mapped[date | None] = mapped_column(Date)
    qualifications: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    snils: Mapped[str | None] = mapped_column(String(32))
    passport: Mapped[str | None] = mapped_column(String(64))
    current_ppe: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    working_conditions_class: Mapped[str | None] = mapped_column(String(32))
    hazardous_factors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        Enum(EmploymentStatus), nullable=False, default=EmploymentStatus.ACTIVE
    )

    company: Mapped[Company] = relationship(backref="people")
    position: Mapped[Position | None] = relationship(backref="people")
    workplace: Mapped["Workplace | None"] = relationship(backref="people")

    __table_args__ = (
        UniqueConstraint("tenant_id", "personnel_number", name="uq_person_tenant_tab_number"),
    )


class Site(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "site"

    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))
    geo_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    hazard_class: Mapped[str | None] = mapped_column(String(32))
    site_type: Mapped[str | None] = mapped_column(String(64))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    is_hazardous_production_facility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    opo_register_number: Mapped[str | None] = mapped_column(String(64))

    company: Mapped[Company] = relationship(backref="sites")


class Workplace(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "workplace"

    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("site.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    working_conditions_class: Mapped[str | None] = mapped_column(String(32))

    company: Mapped[Company] = relationship(backref="workplaces")
    site: Mapped[Site | None] = relationship(backref="workplaces")
    hazards: Mapped[list["RiskHazard"]] = relationship(
        "RiskHazard",
        secondary="workplace_hazard",
        lazy="selectin",
        back_populates="workplaces",
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "name", name="uq_workplace_company_name"
        ),
    )


class MedicalExam(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "medical_exam"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    exam_type: Mapped[str] = mapped_column(String(128), nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    conclusion: Mapped[str | None] = mapped_column(String(255))
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)

    person: Mapped[Person] = relationship(backref="medical_exams")


class TrainingStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"


class Training(TenantBaseModel):
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    course_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TrainingStatus] = mapped_column(Enum(TrainingStatus), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    person: Mapped[Person] = relationship(backref="trainings")


class TrainingCourse(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_course"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text)
    duration_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "title", name="uq_training_course_title"),
        Index("ix_training_course_code", "tenant_id", "code"),
    )


class TrainingPlan(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_plan"

    company_id: Mapped[str] = mapped_column(
        ForeignKey("company.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id", ondelete="SET NULL"), nullable=True, index=True
    )
    person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("training_course.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    company: Mapped[Company] = relationship(backref="training_plans")
    position: Mapped[Position | None] = relationship(backref="training_plans")
    person: Mapped[Person | None] = relationship(backref="training_plans")
    course: Mapped[TrainingCourse] = relationship(backref="training_plans")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "course_id",
            "company_id",
            "position_id",
            "person_id",
            name="uq_training_plan_target",
        ),
    )


class TrainingSessionStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TrainingSession(TenantBaseModel):
    __tablename__ = "training_session"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("training_course.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_plan.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[TrainingSessionStatus] = mapped_column(
        Enum(TrainingSessionStatus), nullable=False, default=TrainingSessionStatus.SCHEDULED
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    person: Mapped[Person] = relationship(backref="training_sessions")
    course: Mapped[TrainingCourse] = relationship(backref="training_sessions")
    plan: Mapped[TrainingPlan | None] = relationship(backref="sessions")

    __table_args__ = (
        Index("ix_training_session_status", "tenant_id", "status"),
    )


class TrainingCertificate(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_certificate"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("training_course.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_session.id", ondelete="SET NULL"), nullable=True, index=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_plan.id", ondelete="SET NULL"), nullable=True, index=True
    )
    file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True, index=True
    )
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issued_at: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    person: Mapped[Person] = relationship(backref="training_certificates")
    course: Mapped[TrainingCourse] = relationship(backref="training_certificates")
    session: Mapped[TrainingSession | None] = relationship(backref="certificate")
    plan: Mapped[TrainingPlan | None] = relationship(backref="certificates")
    file: Mapped[File | None] = relationship("File", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_training_certificate_number"),
        Index("ix_training_certificate_valid", "tenant_id", "valid_until"),
    )


class TrainingProgram(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_programs"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    duration_hours: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    validity_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_registry_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_training_programs_code"),)


class TrainingModule(TenantBaseModel):
    __tablename__ = "training_modules"

    training_program_id: Mapped[str] = mapped_column(
        ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    module_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TrainingTest(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_tests"

    training_program_id: Mapped[str] = mapped_column(
        ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    passing_score: Mapped[int] = mapped_column(Integer, nullable=False)
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    randomize_questions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TrainingTestQuestion(TenantBaseModel):
    __tablename__ = "training_test_questions"

    training_test_id: Mapped[str] = mapped_column(
        ForeignKey("training_tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    question_type: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    correct_answer_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=1)


class TrainingGroup(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_groups"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    training_program_id: Mapped[str] = mapped_column(
        ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    teacher_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    site_id: Mapped[str | None] = mapped_column(ForeignKey("site.id", ondelete="SET NULL"), nullable=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("company.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_training_groups_code"),)


class TrainingEnrollment(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_enrollments"

    training_group_id: Mapped[str | None] = mapped_column(ForeignKey("training_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    training_program_id: Mapped[str] = mapped_column(ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id: Mapped[str | None] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assignment_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="assigned")
    score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    certificate_id: Mapped[str | None] = mapped_column(ForeignKey("training_certificates.id", ondelete="SET NULL"), nullable=True)
    protocol_id: Mapped[str | None] = mapped_column(ForeignKey("training_protocols.id", ondelete="SET NULL"), nullable=True)


class TrainingAttempt(TenantBaseModel):
    __tablename__ = "training_attempts"

    training_enrollment_id: Mapped[str] = mapped_column(ForeignKey("training_enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answers_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class TrainingProtocol(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_protocols"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    training_program_id: Mapped[str] = mapped_column(ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    training_group_id: Mapped[str | None] = mapped_column(ForeignKey("training_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    protocol_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    file_id: Mapped[str | None] = mapped_column(ForeignKey("file.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_training_protocols_code"),)


class TrainingProtocolItem(TenantBaseModel):
    __tablename__ = "training_protocol_items"

    training_protocol_id: Mapped[str] = mapped_column(ForeignKey("training_protocols.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id: Mapped[str | None] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"), nullable=True)
    fio_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    enrollment_id: Mapped[str | None] = mapped_column(ForeignKey("training_enrollments.id", ondelete="SET NULL"), nullable=True)


class BriefingTemplate(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "briefing_templates"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    briefing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    validity_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_briefing_templates_code"),)


class BriefingJournal(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "briefing_journals"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("site.id", ondelete="SET NULL"), nullable=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id", ondelete="SET NULL"), nullable=True)
    journal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_briefing_journals_code"),)


class BriefingEntry(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "briefing_entries"

    briefing_journal_id: Mapped[str] = mapped_column(ForeignKey("briefing_journals.id", ondelete="CASCADE"), nullable=False, index=True)
    briefing_template_id: Mapped[str | None] = mapped_column(ForeignKey("briefing_templates.id", ondelete="SET NULL"), nullable=True)
    person_id: Mapped[str | None] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True)
    instructor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("site.id", ondelete="SET NULL"), nullable=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id", ondelete="SET NULL"), nullable=True)
    workplace_id: Mapped[str | None] = mapped_column(ForeignKey("workplace.id", ondelete="SET NULL"), nullable=True)
    briefing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    briefing_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class BriefingSignature(TenantBaseModel):
    __tablename__ = "briefing_signatures"

    briefing_entry_id: Mapped[str] = mapped_column(ForeignKey("briefing_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    signer_type: Mapped[str] = mapped_column(String(16), nullable=False)
    signer_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    signer_person_id: Mapped[str | None] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"), nullable=True)
    signature_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="internal_simple")
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))
    signature_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ComplianceDeadline(TenantBaseModel):
    __tablename__ = "compliance_deadlines"

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    person_id: Mapped[str | None] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("site.id", ondelete="SET NULL"), nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="upcoming")
    reminder_policy: Mapped[str | None] = mapped_column(Text, nullable=True)


class CalendarEvent(TenantBaseModel):
    __tablename__ = "calendar_events"

    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("site.id", ondelete="SET NULL"), nullable=True)
    assigned_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class OfflineSyncBatch(TenantBaseModel):
    __tablename__ = "offline_sync_batches"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class OfflineMediaQueue(TenantBaseModel):
    __tablename__ = "offline_media_queue"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    local_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("file.id", ondelete="SET NULL"), nullable=True)
    upload_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ExternalRegistryJob(TenantBaseModel):
    __tablename__ = "external_registry_jobs"

    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    registry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class PermitStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class Permit(TenantBaseModel):
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id", ondelete="SET NULL"), nullable=True, index=True
    )
    permit_type: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[PermitStatus] = mapped_column(Enum(PermitStatus), nullable=False, default=PermitStatus.ACTIVE)

    position: Mapped[Position | None] = relationship(backref="permits")
    person: Mapped[Person] = relationship(backref="permits")

    __table_args__ = (
        Index("ix_permit_position", "tenant_id", "position_id"),
    )


class PPENorm(TenantBaseModel):
    position_id: Mapped[str] = mapped_column(ForeignKey("position.id"), nullable=False, index=True)
    hazard_id: Mapped[str] = mapped_column(
        ForeignKey("risk_hazards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)

    position: Mapped[Position] = relationship(backref="ppe_norms")
    hazard: Mapped["RiskHazard"] = relationship("RiskHazard")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "position_id",
            "hazard_id",
            "item_name",
            name="uq_ppe_norm_position_hazard_item",
        ),
    )


class PPEItemCategory(str, enum.Enum):
    HEAD = "head"
    HANDS = "hands"
    RESPIRATORY = "respiratory"
    BODY = "body"
    FOOTWEAR = "footwear"
    FALL_PROTECTION = "fall_protection"
    OTHER = "other"


class PPEItem(TenantBaseModel, SoftDeleteMixin):
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[PPEItemCategory] = mapped_column(Enum(PPEItemCategory), nullable=False, default=PPEItemCategory.OTHER)
    description: Mapped[str | None] = mapped_column(String(512))
    default_wear_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_ppe_item_name"),
        UniqueConstraint("tenant_id", "code", name="uq_ppe_item_code"),
    )


class PPEIssueStatus(str, enum.Enum):
    ISSUED = "issued"
    RETURNED = "returned"
    LOST = "lost"


class PPEIssue(TenantBaseModel, SoftDeleteMixin):
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    item_id: Mapped[str | None] = mapped_column(
        ForeignKey("ppeitem.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wear_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[PPEIssueStatus] = mapped_column(
        Enum(PPEIssueStatus), nullable=False, default=PPEIssueStatus.ISSUED
    )

    person: Mapped[Person] = relationship(backref="ppe_issues")
    item: Mapped[PPEItem | None] = relationship("PPEItem", backref="issues")

    __table_args__ = (
        Index("ix_ppe_issue_item", "tenant_id", "item_id"),
    )


class TemplateStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Template(TenantBaseModel):
    code: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1024))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    status: Mapped[TemplateStatus] = mapped_column(
        Enum(TemplateStatus), nullable=False, default=TemplateStatus.DRAFT
    )
    current_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("templateversion.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_templates_tenant_code"),
        Index("ix_template_status_updated", "tenant_id", "status", "updated_at"),
        Index("ix_template_updated", "tenant_id", "updated_at"),
    )


class TemplateVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    UPLOADED = "uploaded"
    LINTED = "linted"
    READY = "ready"
    DEPRECATED = "deprecated"


class TemplateVersion(TenantBaseModel):
    template_id: Mapped[str] = mapped_column(ForeignKey("template.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[TemplateVersionStatus] = mapped_column(
        Enum(TemplateVersionStatus), nullable=False, default=TemplateVersionStatus.UPLOADED
    )
    payload_key: Mapped[str] = mapped_column(String(512), nullable=False)
    file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    placeholder_index: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    linter_report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(255))
    required_fields_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    applicability_rules: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_types: Mapped[list[str] | None] = mapped_column(JSON)
    profile: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    template: Mapped[Template] = relationship(backref="versions", foreign_keys=[template_id])

    __mapper_args__ = {
        "version_id_generator": False,
    }

    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_template_version"),
        Index("ix_template_version_status", "tenant_id", "status"),
        Index("ix_template_version_updated", "tenant_id", "updated_at"),
    )


class TemplateUsage(TenantBaseModel):
    template_version_id: Mapped[str] = mapped_column(
        ForeignKey("templateversion.id"), nullable=False, index=True
    )
    used_by_type: Mapped[str] = mapped_column(String(64), nullable=False)
    used_by_id: Mapped[str] = mapped_column(String(36), nullable=False)

    template_version: Mapped[TemplateVersion] = relationship(backref="usages")

    __table_args__ = (
        UniqueConstraint(
            "template_version_id",
            "used_by_type",
            "used_by_id",
            name="uq_template_usage_target",
        ),
        Index("ix_template_usage_lookup", "tenant_id", "template_version_id"),
    )


class PackageEntityStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class PackageSourceType(str, enum.Enum):
    CSV = "csv"
    XLSX = "xlsx"
    JSON = "json"
    MIXED = "mixed"


class ReplaceMode(str, enum.Enum):
    NONE = "none"
    PREVIEW = "preview"
    APPLY = "apply"


class OutputFormat(str, enum.Enum):
    DOCX = "docx"
    PDF = "pdf"
    BOTH = "both"


class PackRunLifecycleStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"
    PARTIAL_SUCCESS = "partial_success"


class PackRunItemStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class PackLogLevel(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class PackageProfileConfig(TenantBaseModel):
    __tablename__ = "package_profiles_v2"

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    pipeline_steps_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    concurrency_limit: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[PackageEntityStatus] = mapped_column(
        Enum(PackageEntityStatus, name="package_entity_status"),
        nullable=False,
        default=PackageEntityStatus.DRAFT,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_package_profiles_v2_tenant_code"),
        Index("ix_package_profiles_v2_tenant_status_updated", "tenant_id", "status", "updated_at"),
    )


class PackagePresetConfig(TenantBaseModel):
    __tablename__ = "package_presets_v2"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    package_profile_id: Mapped[str] = mapped_column(ForeignKey("package_profiles_v2.id"), nullable=False, index=True)
    naming_rule: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[PackageSourceType] = mapped_column(
        Enum(PackageSourceType, name="package_source_type"), nullable=False, default=PackageSourceType.CSV
    )
    mapping_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    options_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[PackageEntityStatus] = mapped_column(
        Enum(PackageEntityStatus, name="package_preset_status"),
        nullable=False,
        default=PackageEntityStatus.DRAFT,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped[PackageProfileConfig] = relationship(backref="presets_v2")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_package_presets_v2_tenant_code"),
        Index("ix_package_presets_v2_tenant_status_updated", "tenant_id", "status", "updated_at"),
    )


class PackagePresetItem(TenantBaseModel):
    __tablename__ = "package_preset_items"

    package_preset_id: Mapped[str] = mapped_column(ForeignKey("package_presets_v2.id"), nullable=False, index=True)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[str | None] = mapped_column(ForeignKey("template.id"), nullable=True, index=True)
    template_version_id: Mapped[str] = mapped_column(ForeignKey("templateversion.id"), nullable=False, index=True)
    header_preset_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    replace_mode: Mapped[ReplaceMode] = mapped_column(
        Enum(ReplaceMode, name="replace_mode"), nullable=False, default=ReplaceMode.NONE
    )
    replace_map_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_format: Mapped[OutputFormat] = mapped_column(
        Enum(OutputFormat, name="package_output_format"), nullable=False, default=OutputFormat.BOTH
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    conditions_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    preset: Mapped[PackagePresetConfig] = relationship(backref="items")
    template: Mapped[Template | None] = relationship("Template", backref="package_preset_items")
    template_version: Mapped[TemplateVersion] = relationship("TemplateVersion", backref="package_preset_items_v2")

    __table_args__ = (
        UniqueConstraint("package_preset_id", "order_no", name="uq_package_preset_items_order"),
        Index("ix_package_preset_items_order", "package_preset_id", "order_no"),
    )


class PackRun(TenantBaseModel):
    __tablename__ = "pack_runs"

    package_preset_id: Mapped[str] = mapped_column(ForeignKey("package_presets_v2.id"), nullable=False, index=True)
    package_profile_id: Mapped[str] = mapped_column(ForeignKey("package_profiles_v2.id"), nullable=False, index=True)
    source_file_id: Mapped[str | None] = mapped_column(ForeignKey("file.id"), nullable=True)
    source_type: Mapped[PackageSourceType] = mapped_column(Enum(PackageSourceType, name="pack_run_source_type"), nullable=False)
    source_rows_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected_rows_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[PackRunLifecycleStatus] = mapped_column(
        Enum(PackRunLifecycleStatus, name="pack_run_lifecycle_status"), nullable=False, default=PackRunLifecycleStatus.QUEUED
    )
    result_zip_file_id: Mapped[str | None] = mapped_column(ForeignKey("file.id"), nullable=True)
    stats_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approval_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signature_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    edo_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index("ix_pack_runs_status_created", "tenant_id", "status", "created_at"),
        Index("ix_pack_runs_tenant_status_updated", "tenant_id", "status", "updated_at"),
        UniqueConstraint("tenant_id", "idempotency_key", "request_hash", name="uq_pack_runs_idempotency"),
    )


class PackRunItem(TenantBaseModel):
    __tablename__ = "pack_run_items"

    pack_run_id: Mapped[str] = mapped_column(ForeignKey("pack_runs.id"), nullable=False, index=True)
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    source_record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[PackRunItemStatus] = mapped_column(
        Enum(PackRunItemStatus, name="pack_run_item_status"), nullable=False, default=PackRunItemStatus.QUEUED
    )
    document_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    output_docx_file_id: Mapped[str | None] = mapped_column(ForeignKey("file.id"), nullable=True)
    output_pdf_file_id: Mapped[str | None] = mapped_column(ForeignKey("file.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        Index("ix_pack_run_items_run_status", "pack_run_id", "status"),
    )


class PackRunLog(TenantBaseModel):
    __tablename__ = "pack_run_logs"

    pack_run_id: Mapped[str] = mapped_column(ForeignKey("pack_runs.id"), nullable=False, index=True)
    level: Mapped[PackLogLevel] = mapped_column(Enum(PackLogLevel, name="pack_log_level"), nullable=False)
    step: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class PackageProfile(TenantBaseModel):
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024))
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_package_profile_name"),
    )


class PackagePreset(TenantBaseModel):
    profile_id: Mapped[str] = mapped_column(ForeignKey("packageprofile.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    profile: Mapped[PackageProfile] = relationship(backref="presets")


class DocumentPackModule(str, enum.Enum):
    """High-level grouping for document packs."""

    OT = "ot"
    FIRE_SAFETY = "fire_safety"
    HEALTH = "health"
    CUSTOM = "custom"


class DocumentPackScenario(str, enum.Enum):
    """Execution scenario describing how a pack runs."""

    DOCUMENT_BATCH = "document_batch"
    REPORT = "report"
    WORKFLOW = "workflow"


class DocumentPack(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "document_pack"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    module: Mapped[DocumentPackModule] = mapped_column(
        Enum(DocumentPackModule), nullable=False, default=DocumentPackModule.OT
    )
    scenario_type: Mapped[DocumentPackScenario] = mapped_column(
        Enum(DocumentPackScenario),
        nullable=False,
        default=DocumentPackScenario.DOCUMENT_BATCH,
    )

    items: Mapped[list["DocumentPackItem"]] = relationship(
        back_populates="pack",
        cascade="all, delete-orphan",
        order_by="DocumentPackItem.order",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_document_pack_code"),
    )


class DocumentPackItem(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "document_pack_item"

    pack_id: Mapped[str] = mapped_column(ForeignKey("document_pack.id"), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("template.id"), nullable=False, index=True)
    template_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("templateversion.id"), nullable=True, index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    condition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    pack: Mapped[DocumentPack] = relationship(back_populates="items")
    template: Mapped[Template] = relationship(backref="document_pack_items")
    template_version: Mapped[TemplateVersion | None] = relationship(
        "TemplateVersion", backref="document_pack_items"
    )


class PipelineRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class PipelineRun(TenantBaseModel):
    __tablename__ = "pipeline_runs"

    template_id: Mapped[str] = mapped_column(ForeignKey("template.id"), nullable=False, index=True)
    template_version_id: Mapped[str] = mapped_column(
        ForeignKey("templateversion.id"), nullable=False, index=True
    )
    status: Mapped[PipelineRunStatus] = mapped_column(
        Enum(PipelineRunStatus), nullable=False, default=PipelineRunStatus.QUEUED
    )
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    outputs: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    docx_storage_key: Mapped[str | None] = mapped_column(String(512))
    pdf_storage_key: Mapped[str | None] = mapped_column(String(512))
    result_s3_key: Mapped[str | None] = mapped_column(String(512))
    error: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[Template] = relationship(backref="pipeline_runs")
    template_version: Mapped[TemplateVersion] = relationship(backref="pipeline_runs")

    __table_args__ = (
        Index(
            "ix_pipeline_runs_tenant_idempotency",
            "tenant_id",
            "idempotency_key",
            unique=True,
        ),
    )


class PackageRunStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


class PackageRequirementType(str, enum.Enum):
    FILE = "file"
    TEXT = "text"
    TABLE = "table"


class PackageRequirementStatus(str, enum.Enum):
    MISSING = "missing"
    PROVIDED = "provided"
    APPROVED = "approved"
    REJECTED = "rejected"


class ClientRequestTicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ClientPackagePreset(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "package_presets"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    steps_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    required_inputs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_package_presets_code"),
        Index("ix_package_presets_code", "tenant_id", "code"),
    )


class ClientPackageRun(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "package_runs"

    preset_id: Mapped[str] = mapped_column(ForeignKey("package_presets.id"), nullable=False, index=True)
    initiated_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user.id"), nullable=True, index=True)
    client_company_id: Mapped[str | None] = mapped_column(ForeignKey("company.id"), nullable=True, index=True)
    status: Mapped[PackageRunStatus] = mapped_column(
        Enum(PackageRunStatus), nullable=False, default=PackageRunStatus.DRAFT
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output_zip_s3_key: Mapped[str | None] = mapped_column(String(512))
    output_pdf_s3_key: Mapped[str | None] = mapped_column(String(512))
    qc_report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    preset: Mapped[ClientPackagePreset] = relationship(backref="runs")

    __table_args__ = (
        Index("ix_package_runs_status_updated", "tenant_id", "status", "updated_at"),
    )


class PackageRequirement(TenantBaseModel):
    __tablename__ = "package_requirements"

    package_run_id: Mapped[str] = mapped_column(ForeignKey("package_runs.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[PackageRequirementType] = mapped_column(
        Enum(PackageRequirementType), nullable=False, default=PackageRequirementType.FILE
    )
    status: Mapped[PackageRequirementStatus] = mapped_column(
        Enum(PackageRequirementStatus), nullable=False, default=PackageRequirementStatus.MISSING
    )
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ClientPortalToken(TenantBaseModel):
    __tablename__ = "client_portal_tokens"

    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    package_run_id: Mapped[str] = mapped_column(ForeignKey("package_runs.id"), nullable=False, index=True)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_client_portal_tokens_expires_hash", "tenant_id", "expires_at", "token_hash"),
    )


class ClientRequestTicket(TenantBaseModel):
    __tablename__ = "client_request_tickets"

    package_run_id: Mapped[str] = mapped_column(ForeignKey("package_runs.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ClientRequestTicketStatus] = mapped_column(
        Enum(ClientRequestTicketStatus), nullable=False, default=ClientRequestTicketStatus.OPEN
    )
    created_by: Mapped[str | None] = mapped_column(String(128))


class PackageEvent(TenantBaseModel):
    __tablename__ = "package_events"

    package_run_id: Mapped[str] = mapped_column(ForeignKey("package_runs.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class IdempotencyStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IdempotencyKey(TenantBaseModel):
    __tablename__ = "idempotency_keys"

    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[IdempotencyStatus] = mapped_column(
        Enum(IdempotencyStatus), nullable=False, default=IdempotencyStatus.PENDING
    )
    request_hash: Mapped[str | None] = mapped_column(String(128))
    path: Mapped[str | None] = mapped_column(String(512))
    method: Mapped[str | None] = mapped_column(String(16))
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_headers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "endpoint", "key", name="uq_idempotency_keys"),
        UniqueConstraint("tenant_id", "key", name="uq_idempotency_key_per_tenant"),
        Index("ix_idempotency_keys_lookup", "tenant_id", "endpoint", "key"),
    )


class RiskMethodology(TenantBaseModel):
    """Risk calculation methodology including severity/likelihood scales."""

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_risk_methodology_name"),
        UniqueConstraint("tenant_id", "code", name="uq_risk_methodology_code"),
    )


class RiskMap(TenantBaseModel):
    methodology_id: Mapped[str] = mapped_column(
        ForeignKey("riskmethodology.id"), nullable=False, index=True
    )
    company_id: Mapped[str] = mapped_column(
        ForeignKey("company.id"), nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id"), nullable=True, index=True
    )
    document_pack_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_pack.id"), nullable=True, index=True
    )
    matrix: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    recalculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    methodology: Mapped[RiskMethodology] = relationship(backref="risk_maps")
    company: Mapped[Company] = relationship(backref="risk_maps")
    site: Mapped[Site | None] = relationship(backref="risk_maps")
    position: Mapped[Position | None] = relationship(backref="risk_maps")
    document_pack: Mapped["DocumentPack | None"] = relationship(backref="risk_maps")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "site_id",
            "position_id",
            "methodology_id",
            name="uq_riskmap_scope",
        ),
    )


class WorkplaceHazardLink(TenantBaseModel):
    __tablename__ = "workplace_hazard"

    workplace_id: Mapped[str] = mapped_column(
        ForeignKey("workplace.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hazard_id: Mapped[str] = mapped_column(
        ForeignKey("risk_hazards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )

    workplace: Mapped[Workplace] = relationship(backref="hazard_links")
    hazard: Mapped["RiskHazard"] = relationship("RiskHazard")
    document_file: Mapped["File | None"] = relationship("File")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "workplace_id", "hazard_id", name="uq_workplace_hazard_link"
        ),
    )


class PositionHazardLink(TenantBaseModel):
    __tablename__ = "position_hazard"

    position_id: Mapped[str] = mapped_column(
        ForeignKey("position.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hazard_id: Mapped[str] = mapped_column(
        ForeignKey("risk_hazards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )

    position: Mapped[Position] = relationship(backref="hazard_links")
    hazard: Mapped["RiskHazard"] = relationship("RiskHazard")
    document_file: Mapped["File | None"] = relationship("File")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "position_id", "hazard_id", name="uq_position_hazard_link"
        ),
    )


class NPAStatus(str, enum.Enum):
    ACTIVE = "active"
    OBSOLETE = "obsolete"


class NPA(TenantBaseModel):
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    edition_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[NPAStatus] = mapped_column(Enum(NPAStatus), nullable=False, default=NPAStatus.ACTIVE)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_npa_code"),
    )


class NpaBindingTarget(str, enum.Enum):
    """Entities that can be linked to an NPA."""

    TEMPLATE_VERSION = "template_version"
    DOCUMENT = "document"
    PACK = "pack"


class NPABinding(TenantBaseModel):
    template_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("templateversion.id"), nullable=True, index=True
    )
    npa_id: Mapped[str] = mapped_column(ForeignKey("npa.id"), nullable=False, index=True)
    ref: Mapped[str | None] = mapped_column(String(255))
    entity_type: Mapped[NpaBindingTarget] = mapped_column(
        Enum(NpaBindingTarget), nullable=False, default=NpaBindingTarget.TEMPLATE_VERSION
    )
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    template_version: Mapped[TemplateVersion | None] = relationship(backref="npa_bindings")
    npa: Mapped[NPA] = relationship(backref="bindings")


class AuditLog(TenantBaseModel):
    """Immutable audit trail entry capturing key security events."""

    when: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    request_id: Mapped[str | None] = mapped_column(String(128))
    session_id: Mapped[str | None] = mapped_column(String(128))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    resource_attrs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    changed_fields: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    actor_role_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_auditlog_action", "action", "when"),
        Index("ix_auditlog_object", "object_type", "object_id", "when"),
        Index("ix_auditlog_actor", "user_id", "when"),
        Index("ix_auditlog_corr", "correlation_id"),
        Index("ix_auditlog_when", "when"),
    )


@event.listens_for(AuditLog, "before_update", propagate=True)
def _prevent_auditlog_update(*_args, **_kwargs) -> None:
    raise RuntimeError("Audit logs are append-only")


@event.listens_for(AuditLog, "before_delete", propagate=True)
def _prevent_auditlog_delete(*_args, **_kwargs) -> None:
    raise RuntimeError("Audit logs are append-only")




class AuditExportJob(TenantBaseModel):
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    signed_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_audit_export_job_tenant_status", "tenant_id", "status"),)

class SecurityAuditLog(TenantBaseModel):
    """Authorization decision log (allow/deny) for RBAC+ABAC enforcement."""

    when: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    user_agent: Mapped[str | None] = mapped_column(String(256))
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_security_auditlog_action", "action"),
        Index("ix_security_auditlog_decision", "decision"),
        Index("ix_security_auditlog_resource", "resource_type", "resource_id"),
        Index("ix_security_auditlog_when", "when"),
    )


class WarehousePPE(TenantBaseModel):
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    location: Mapped[str | None] = mapped_column(String(255))


class JournalType(str, enum.Enum):
    INTRODUCTORY = "introductory"
    PRIMARY = "primary"
    REPEATED = "repeated"
    TARGET = "target"
    FIRE_SAFETY = "fire_safety"
    UNSCHEDULED = "unscheduled"


class Journal(TenantBaseModel, SoftDeleteMixin):
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("company.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255))
    journal_type: Mapped[JournalType] = mapped_column(Enum(JournalType), nullable=False)
    started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    company: Mapped[Company | None] = relationship("Company", backref="journals")

    __table_args__ = (
        Index("ix_journal_company", "tenant_id", "company_id"),
    )


class JournalEntry(TenantBaseModel, SoftDeleteMixin):
    journal_id: Mapped[str] = mapped_column(ForeignKey("journal.id"), nullable=False, index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    entry_type: Mapped[JournalType] = mapped_column(Enum(JournalType), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    instructor: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    journal: Mapped[Journal] = relationship(backref="entries")
    person: Mapped[Person] = relationship(backref="journal_entries")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "journal_id",
            "person_id",
            "entry_type",
            "entry_date",
            name="uq_journal_entry_unique_person_date",
        ),
        Index("ix_journal_entry_type", "tenant_id", "entry_type"),
    )


class PlanTaskStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class PlanTask(TenantBaseModel):
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[PlanTaskStatus] = mapped_column(Enum(PlanTaskStatus), nullable=False, default=PlanTaskStatus.OPEN)


class IncidentSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IncidentType(str, enum.Enum):
    ACCIDENT = "accident"
    MICROTRAUMA = "microtrauma"
    NEAR_MISS = "near_miss"
    UNSAFE_CONDITION = "unsafe_condition"


class IncidentStatus(str, enum.Enum):
    REPORTED = "reported"
    INVESTIGATING = "investigating"
    ACTIONS = "corrective_actions"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class IncidentStage(str, enum.Enum):
    REGISTRATION = "registration"
    INVESTIGATION = "investigation"
    ACTION_PLAN = "action_plan"
    FOLLOW_UP = "follow_up"
    CLOSED = "closed"


class Incident(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "incident"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    incident_type: Mapped[IncidentType] = mapped_column(
        Enum(IncidentType, name="incidenttype"), nullable=False, default=IncidentType.ACCIDENT
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"), nullable=False, index=True)
    location_description: Mapped[str | None] = mapped_column(String(255))
    severity: Mapped[IncidentSeverity] = mapped_column(
        Enum(IncidentSeverity, name="incidentseverity"), nullable=False, default=IncidentSeverity.MEDIUM
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incidentstatus"), nullable=False, default=IncidentStatus.REPORTED
    )
    investigation_stage: Mapped[IncidentStage] = mapped_column(
        Enum(IncidentStage, name="incidentstage"), nullable=False, default=IncidentStage.REGISTRATION
    )
    pack_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_pack.id", ondelete="SET NULL"), nullable=True, index=True
    )

    company: Mapped[Company] = relationship(backref="incidents")
    site: Mapped[Site] = relationship(backref="incidents")
    pack: Mapped[DocumentPack | None] = relationship("DocumentPack", backref="incidents")
    logs: Mapped[list["IncidentLog"]] = relationship(
        "IncidentLog",
        back_populates="incident",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="IncidentLog.created_at",
    )
    participants: Mapped[list["IncidentPerson"]] = relationship(
        "IncidentPerson",
        back_populates="incident",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_incident_company", "tenant_id", "company_id"),
        Index("ix_incident_site", "tenant_id", "site_id"),
        Index("ix_incident_status", "tenant_id", "status"),
        Index("ix_incident_occurred_at", "occurred_at"),
    )


class IncidentPersonRole(str, enum.Enum):
    VICTIM = "victim"
    WITNESS = "witness"
    PARTICIPANT = "participant"


class IncidentPerson(TenantBaseModel):
    __tablename__ = "incident_person"

    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incident.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[IncidentPersonRole] = mapped_column(
        Enum(IncidentPersonRole, name="incidentpersonrole"), nullable=False, default=IncidentPersonRole.VICTIM
    )

    incident: Mapped[Incident] = relationship("Incident", back_populates="participants")
    person: Mapped[Person] = relationship("Person", backref="incident_links")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "incident_id",
            "person_id",
            "role",
            name="uq_incident_person_role",
        ),
        Index("ix_incident_person_role", "role"),
    )


class IncidentLog(TenantBaseModel):
    __tablename__ = "incident_log"

    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incident.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stage: Mapped[IncidentStage] = mapped_column(Enum(IncidentStage, name="incidentlogstage"), nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incidentlogstatus"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    incident: Mapped[Incident] = relationship("Incident", back_populates="logs")
    author: Mapped[User | None] = relationship("User")

    __table_args__ = (
        Index("ix_incident_log_incident", "tenant_id", "incident_id"),
        Index("ix_incident_log_stage", "tenant_id", "stage"),
    )


class InspectionStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InspectionType(str, enum.Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class Inspection(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "regulatory_inspection"

    company_id: Mapped[str] = mapped_column(
        ForeignKey("company.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id", ondelete="SET NULL"), nullable=True, index=True
    )
    inspection_type: Mapped[InspectionType] = mapped_column(
        Enum(InspectionType, name="inspectiontype"),
        nullable=False,
        default=InspectionType.INTERNAL,
    )
    responsible_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recurrence_rule: Mapped[str | None] = mapped_column(String(128))
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(255))
    scheduled_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus, name="regulatoryinspectionstatus"),
        nullable=False,
        default=InspectionStatus.PLANNED,
    )
    result_summary: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(backref="inspections")
    site: Mapped[Site | None] = relationship(backref="inspections")
    responsible: Mapped[User | None] = relationship("User")
    results: Mapped[list["InspectionResult"]] = relationship(
        "InspectionResult",
        back_populates="inspection",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_regulatory_inspection_company", "tenant_id", "company_id"),
        Index("ix_regulatory_inspection_site", "tenant_id", "site_id"),
        Index("ix_regulatory_inspection_responsible", "tenant_id", "responsible_id"),
        Index("ix_regulatory_inspection_status", "tenant_id", "status"),
        Index("ix_regulatory_inspection_type", "tenant_id", "inspection_type"),
    )


class InspectionResult(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "inspection_result"

    inspection_id: Mapped[str] = mapped_column(
        ForeignKey("regulatory_inspection.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[date | None] = mapped_column(Date)
    file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )

    inspection: Mapped[Inspection] = relationship("Inspection", back_populates="results")
    file: Mapped[File | None] = relationship("File")

    __table_args__ = (
        Index("ix_inspection_result_inspection", "tenant_id", "inspection_id"),
        Index("ix_inspection_result_issued_at", "issued_at"),
    )


class AttestationStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class Attestation(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "attestation"

    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issued_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[AttestationStatus] = mapped_column(
        Enum(AttestationStatus, name="attestationstatus"),
        nullable=False,
        default=AttestationStatus.ACTIVE,
    )
    responsible_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    person: Mapped[Person] = relationship("Person")
    position: Mapped[Position | None] = relationship("Position")
    responsible: Mapped[User | None] = relationship("User")

    __table_args__ = (
        Index("ix_attestation_person", "tenant_id", "person_id"),
        Index("ix_attestation_status", "tenant_id", "status"),
        Index("ix_attestation_expires", "tenant_id", "expires_at"),
    )


class PrescriptionStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Prescription(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "inspection_prescription"

    inspection_id: Mapped[str] = mapped_column(
        ForeignKey("regulatory_inspection.id", ondelete="CASCADE"), nullable=False, index=True
    )
    incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("incident.id", ondelete="SET NULL"), nullable=True, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[PrescriptionStatus] = mapped_column(
        Enum(PrescriptionStatus, name="prescriptionstatus"),
        nullable=False,
        default=PrescriptionStatus.OPEN,
    )
    assignee_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )

    inspection: Mapped[Inspection] = relationship("Inspection")
    incident: Mapped[Incident | None] = relationship("Incident")
    assignee: Mapped[User | None] = relationship("User")

    __table_args__ = (
        Index("ix_prescription_inspection", "tenant_id", "inspection_id"),
        Index("ix_prescription_status", "tenant_id", "status"),
        Index("ix_prescription_due", "tenant_id", "due_at"),
        Index("ix_prescription_assignee", "tenant_id", "assignee_id"),
    )


class Asset(TenantBaseModel):
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(128))


class EquipmentStatus(str, enum.Enum):
    ACTIVE = "active"
    IN_SERVICE = "in_service"
    DECOMMISSIONED = "decommissioned"


class Equipment(TenantBaseModel):
    asset_id: Mapped[str] = mapped_column(ForeignKey("asset.id"), nullable=False, index=True)
    serial_number: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[EquipmentStatus] = mapped_column(Enum(EquipmentStatus), nullable=False, default=EquipmentStatus.ACTIVE)

    asset: Mapped[Asset] = relationship(backref="equipment")


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SENT = "SENT"
    FAILED = "FAILED"
    DEAD = "DEAD"


class ApprovalRequestStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"


class ApprovalDecisionType(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    DELEGATE = "delegate"


class SignatureType(str, enum.Enum):
    KEP = "KEP"
    UNEP = "UNEP"
    INTERNAL = "INTERNAL"


class SignatureStatus(str, enum.Enum):
    PENDING = "pending"
    SIGNED = "signed"
    FAILED = "failed"


class EdoDirection(str, enum.Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"


class EdoStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"


class ApprovalRouteAppliesTo(str, enum.Enum):
    DOCUMENT = "document"
    PACK = "pack"
    BOTH = "both"


class ApprovalRouteStatus(str, enum.Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"


class ApprovalStepType(str, enum.Enum):
    APPROVE = "approve"
    SIGN = "sign"
    REVIEW = "review"


class ApprovalInstanceStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"
    EXPIRED = "expired"


class ApprovalInstanceStepStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    EXPIRED = "expired"
    DELEGATED = "delegated"


class SignatureProviderStatus(str, enum.Enum):
    PENDING = "pending"
    SIGNED = "signed"
    FAILED = "failed"
    CANCELED = "canceled"
    VERIFYING = "verifying"
    VERIFIED = "verified"


class EdoMessageStatus(str, enum.Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    VIEWED = "viewed"
    SIGNED = "signed"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class ApprovalRoute(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "approval_routes"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    applies_to: Mapped[ApprovalRouteAppliesTo] = mapped_column(Enum(ApprovalRouteAppliesTo), nullable=False, default=ApprovalRouteAppliesTo.DOCUMENT)
    conditions_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[ApprovalRouteStatus] = mapped_column(Enum(ApprovalRouteStatus), nullable=False, default=ApprovalRouteStatus.DRAFT)
    rules_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", "version", name="uq_approval_route_code_version"),
        Index("ix_approval_routes_code", "tenant_id", "code"),
    )


class ApprovalRequest(TenantBaseModel):
    __tablename__ = "approval_requests"

    document_version_id: Mapped[str] = mapped_column(ForeignKey("documentversion.id"), nullable=False, index=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("approval_routes.id"), nullable=False, index=True)
    status: Mapped[ApprovalRequestStatus] = mapped_column(
        Enum(ApprovalRequestStatus), nullable=False, default=ApprovalRequestStatus.DRAFT
    )
    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    route: Mapped[ApprovalRoute] = relationship("ApprovalRoute")

    __table_args__ = (
        Index("ix_approval_requests_status", "tenant_id", "status"),
        Index("ix_approval_requests_created", "tenant_id", "created_at"),
    )


class ApprovalDecision(TenantBaseModel):
    __tablename__ = "approval_decisions"

    request_id: Mapped[str | None] = mapped_column(ForeignKey("approval_requests.id"), nullable=True, index=True)
    approval_instance_id: Mapped[str | None] = mapped_column(ForeignKey("approval_instances.id"), nullable=True, index=True)
    approval_instance_step_id: Mapped[str | None] = mapped_column(ForeignKey("approval_instance_steps.id"), nullable=True, index=True)
    step_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    request: Mapped[ApprovalRequest | None] = relationship("ApprovalRequest", backref="decisions")


class Signature(TenantBaseModel):
    __tablename__ = "signatures"

    document_version_id: Mapped[str] = mapped_column(ForeignKey("documentversion.id"), nullable=False, index=True)
    type: Mapped[SignatureType] = mapped_column(Enum(SignatureType), nullable=False)
    status: Mapped[SignatureStatus] = mapped_column(Enum(SignatureStatus), nullable=False, default=SignatureStatus.PENDING)
    signer_user_id: Mapped[str | None] = mapped_column(ForeignKey("user.id"), nullable=True, index=True)
    cert_info_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipts_s3_key: Mapped[str | None] = mapped_column(String(512))

    __table_args__ = (
        Index("ix_signatures_document", "tenant_id", "document_version_id"),
        Index("ix_signatures_status", "tenant_id", "status"),
    )


class EdoMessage(TenantBaseModel):
    __tablename__ = "edo_messages"

    direction: Mapped[EdoDirection] = mapped_column(Enum(EdoDirection), nullable=False)
    document_version_id: Mapped[str | None] = mapped_column(ForeignKey("documentversion.id"), nullable=True, index=True)
    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    operator_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    roaming_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_status_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    protocol_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=EdoMessageStatus.DRAFT.value)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_edo_messages_created", "tenant_id", "created_at"),
        Index("ix_edo_messages_provider_external", "tenant_id", "provider_code", "external_id"),
    )


class EdoReceipt(TenantBaseModel):
    __tablename__ = "edo_receipts"

    edo_message_id: Mapped[str] = mapped_column(ForeignKey("edo_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    receipt_type: Mapped[str] = mapped_column(String(64), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)


class EdoStatusHistory(TenantBaseModel):
    __tablename__ = "edo_status_history"

    edo_message_id: Mapped[str] = mapped_column(ForeignKey("edo_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[EdoStatus] = mapped_column(Enum(EdoStatus), nullable=False)
    raw_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ApprovalProcessStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"
    EXPIRED = "expired"


class ApprovalTaskStatus(str, enum.Enum):
    OPEN = "open"
    DONE = "done"
    CANCELED = "canceled"
    EXPIRED = "expired"


class ApprovalProcess(TenantBaseModel):
    __tablename__ = "approval_processes"

    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    route_id: Mapped[str] = mapped_column(ForeignKey("approval_routes.id"), nullable=False, index=True)
    status: Mapped[ApprovalProcessStatus] = mapped_column(Enum(ApprovalProcessStatus), nullable=False, default=ApprovalProcessStatus.PENDING)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("user.id"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_approval_processes_status", "tenant_id", "status"),
        Index("ix_approval_processes_object", "tenant_id", "object_type", "object_id"),
    )


class ApprovalTask(TenantBaseModel):
    __tablename__ = "approval_tasks"

    process_id: Mapped[str] = mapped_column(ForeignKey("approval_processes.id", ondelete="CASCADE"), nullable=False, index=True)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    assignee_type: Mapped[str] = mapped_column(String(16), nullable=False)
    assignee_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ApprovalTaskStatus] = mapped_column(Enum(ApprovalTaskStatus), nullable=False, default=ApprovalTaskStatus.OPEN)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    delegated_from: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        Index("ix_approval_tasks_status", "tenant_id", "status"),
        Index("ix_approval_tasks_assignee", "tenant_id", "assignee_type", "assignee_id"),
    )


class ApprovalDecisionLog(TenantBaseModel):
    __tablename__ = "approval_decision_logs"

    process_id: Mapped[str] = mapped_column(ForeignKey("approval_processes.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("approval_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))




class ApprovalRouteStep(TenantBaseModel, SoftDeleteMixin, VersionedMixin):
    __tablename__ = "approval_route_steps"

    approval_route_id: Mapped[str] = mapped_column(ForeignKey("approval_routes.id", ondelete="CASCADE"), nullable=False, index=True)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[ApprovalStepType] = mapped_column(Enum(ApprovalStepType), nullable=False, default=ApprovalStepType.APPROVE)
    role_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    can_delegate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deadline_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_role_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    escalation_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    conditions_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("approval_route_id", "order_no", name="uq_approval_route_steps_order"),
        Index("ix_approval_route_steps_route_order", "approval_route_id", "order_no"),
    )


class ApprovalInstance(TenantBaseModel, SoftDeleteMixin, VersionedMixin):
    __tablename__ = "approval_instances"

    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    approval_route_id: Mapped[str] = mapped_column(ForeignKey("approval_routes.id"), nullable=False, index=True)
    status: Mapped[ApprovalInstanceStatus] = mapped_column(Enum(ApprovalInstanceStatus), nullable=False, default=ApprovalInstanceStatus.DRAFT)
    started_by: Mapped[str] = mapped_column(String(36), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_step_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_approval_instances_entity", "tenant_id", "entity_type", "entity_id"),
        Index("ix_approval_instances_status", "tenant_id", "status"),
    )


class ApprovalInstanceStep(TenantBaseModel):
    __tablename__ = "approval_instance_steps"

    approval_instance_id: Mapped[str] = mapped_column(ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    route_step_id: Mapped[str] = mapped_column(ForeignKey("approval_route_steps.id"), nullable=False, index=True)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    assignee_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    assignee_role_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    delegated_from_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[ApprovalInstanceStepStatus] = mapped_column(Enum(ApprovalInstanceStepStatus), nullable=False, default=ApprovalInstanceStepStatus.PENDING)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_approval_instance_steps_lookup", "approval_instance_id", "status", "order_no"),
    )


class EdoStatusEvent(TenantBaseModel):
    __tablename__ = "edo_status_events"

    edo_message_id: Mapped[str] = mapped_column(ForeignKey("edo_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_edo_status_events_message_received", "edo_message_id", "received_at"),
    )


class EdoWebhookInbox(TenantBaseModel):
    __tablename__ = "edo_webhook_inbox"

    operator_code: Mapped[str] = mapped_column(String(64), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    headers_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="received")
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class SignatureRequestStatus(str, enum.Enum):
    CREATED = "created"
    REQUESTED = "requested"
    SIGNED = "signed"
    FAILED = "failed"


class SignatureRequest(TenantBaseModel):
    __tablename__ = "signature_requests"

    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approval_instance_id: Mapped[str | None] = mapped_column(ForeignKey("approval_instances.id"), nullable=True, index=True)
    signature_type: Mapped[str] = mapped_column(String(16), nullable=False, default="kep")
    provider_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SignatureProviderStatus.PENDING.value)
    external_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    certificate_thumbprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        Index("ix_signature_requests_status", "tenant_id", "status"),
        Index("ix_signature_requests_object", "tenant_id", "object_type", "object_id"),
        Index("ix_signature_requests_entity_status", "tenant_id", "object_type", "object_id", "status"),
    )


class EdoEnvelopeStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    SIGNED = "signed"
    REJECTED = "rejected"
    FAILED = "failed"


class EdoEnvelope(TenantBaseModel):
    __tablename__ = "edo_envelopes"

    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[EdoEnvelopeStatus] = mapped_column(Enum(EdoEnvelopeStatus), nullable=False, default=EdoEnvelopeStatus.QUEUED)
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_edo_envelopes_status", "tenant_id", "status"),
        Index("ix_edo_envelopes_object", "tenant_id", "object_type", "object_id"),
    )


class Outbox(TenantBaseModel):
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    destination: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    headers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus),
        nullable=False,
        default=OutboxStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_outbox_status_next_attempt", "status", "next_attempt_at"),
        Index("ix_outbox_event_type", "event_type"),
        Index("ix_outbox_idempotency_key", "idempotency_key"),
        UniqueConstraint(
            "tenant_id",
            "destination",
            "idempotency_key",
            name="uq_outbox_idempotency",
        ),
    )


class WebhookDelivery(TenantBaseModel):
    __tablename__ = "webhook_deliveries"

    endpoint_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_headers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_headers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("endpoint_id", "event_id", name="uq_webhook_delivery_endpoint_event"),
        Index("ix_webhook_delivery_lookup", "tenant_id", "endpoint_id", "event_id"),
    )


class WebhookEndpoint(TenantBaseModel):
    __tablename__ = "webhook_endpoints"

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    subscribed_events: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    headers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_webhook_endpoint_tenant_enabled", "tenant_id", "is_enabled"),
    )
