from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import TenantBase

# ARCH-2: re-export approval_runtime models moved to app.models.approval_runtime.
from app.models.approval_runtime import (
    ApprovalDecisionLog,
    ApprovalInstance,
    ApprovalInstanceStep,
    ApprovalProcess,
    ApprovalProcessStatus,
    ApprovalRouteStep,
    ApprovalTask,
    ApprovalTaskStatus,
    EdoStatusEvent,
    EdoWebhookInbox,
    Outbox,
    OutboxStatus,
    SignatureRequest,
    SignatureRequestStatus,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.models.approval_workflow import (
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalInstanceStatus,
    ApprovalInstanceStepStatus,
    ApprovalRequest,
    ApprovalRequestStatus,
    ApprovalRoute,
    ApprovalRouteAppliesTo,
    ApprovalRouteStatus,
    ApprovalStepType,
    EdoDirection,
    EdoMessage,
    EdoMessageStatus,
    EdoReceipt,
    EdoStatus,
    EdoStatusHistory,
    SignatureProviderStatus,
    SignatureType,
)

# ARCH-2: re-export assets models moved to app.models.assets.
from app.models.assets import (
    Asset,
    Equipment,
    EquipmentStatus,
)

# ARCH-2: re-export audit_log-domain models moved to app.models.audit_log.
from app.models.audit_log import (
    AuditExportJob,
    AuditLog,
    SecurityAuditLog,
)
from app.models.base import (
    SharedModel,
    SoftDeleteMixin,
    TenantBaseModel,
    TimestampMixin,
    UUIDMixin,
    VersionedMixin,
    native_enum,
)

# ARCH-2: re-export briefings-domain models moved to app.models.briefings.
from app.models.briefings import (
    BriefingEntry,
    BriefingJournal,
    BriefingSignature,
    BriefingTemplate,
)

# ARCH-2: re-export field_ops-domain models moved to app.models.field_ops.
from app.models.field_ops import (
    CalendarEvent,
    ComplianceDeadline,
    ExternalRegistryJob,
    OfflineMediaQueue,
    OfflineSyncBatch,
    Permit,
    PermitStatus,
)

# Re-export File (kept in __all__ so ruff F401 keeps it; some callers do
# ``from app.models.models import File``).
from app.models.file import File

# ARCH-2: re-export idempotency models moved to app.models.idempotency.
from app.models.idempotency import (
    IdempotencyKey,
    IdempotencyStatus,
)

# ARCH-2: re-export incidents-domain models moved to app.models.incidents.
from app.models.incidents import (
    Incident,
    IncidentLog,
    IncidentPerson,
    IncidentPersonRole,
    IncidentSeverity,
    IncidentStage,
    IncidentStatus,
    IncidentType,
)

# ARCH-2: re-export inspections-domain models moved to app.models.inspections.
from app.models.inspections import (
    Attestation,
    AttestationStatus,
    Inspection,
    InspectionResult,
    InspectionStatus,
    InspectionType,
    Prescription,
    PrescriptionStatus,
)

# ARCH-2: re-export journals-domain models moved to app.models.journals.
from app.models.journals import (
    Journal,
    JournalEntry,
    JournalType,
    PlanTask,
    PlanTaskStatus,
)

# ARCH-2: re-export marketplace models moved to app.models.marketplace.
from app.models.marketplace import (
    MarketplaceCatalogItem,
)

# ARCH-2: re-export master_data models moved to app.models.master_data.
from app.models.master_data import (
    Company,
    EmploymentStatus,
    Person,
    Position,
    Site,
    Workplace,
)

# ARCH-2: re-export medical-domain models moved to app.models.medical.
from app.models.medical import (
    MedicalExam,
    MedicalExamKind,
    MedicalFactor,
    MedicalFitness,
    MedicalNorm,
    MedicalReferral,
    MedicalReferralStatus,
    MedicalSuspension,
    MedicalSuspensionReason,
    MedicalSuspensionStatus,
)

# ARCH-2: re-export packages-domain models moved to app.models.packages.
from app.models.packages import (
    ClientPackagePreset,
    ClientPackageRun,
    ClientPortalToken,
    ClientRequestTicket,
    ClientRequestTicketStatus,
    DocumentPack,
    DocumentPackItem,
    DocumentPackModule,
    DocumentPackScenario,
    OutputFormat,
    PackageEntityStatus,
    PackageEvent,
    PackagePreset,
    PackagePresetConfig,
    PackagePresetItem,
    PackageProfile,
    PackageProfileConfig,
    PackageRequirement,
    PackageRequirementStatus,
    PackageRequirementType,
    PackageRunStatus,
    PackageSourceType,
    PackLogLevel,
    PackRun,
    PackRunItem,
    PackRunItemStatus,
    PackRunLifecycleStatus,
    PackRunLog,
    PipelineRun,
    PipelineRunStatus,
    ReplaceMode,
)

# ARCH-2: re-export ppe-domain models moved to app.models.ppe.
from app.models.ppe import (
    PPEIssue,
    PPEIssueStatus,
    PPEItem,
    PPEItemCategory,
    PPENorm,
    PPEStockBatch,
)

# ARCH-2: re-export risk_register models moved to app.models.risk_register.
from app.models.risk_register import (
    NPA,
    NPABinding,
    NpaBindingTarget,
    NPAStatus,
    PositionHazardLink,
    RiskMap,
    RiskMethodology,
    WorkplaceHazardLink,
)

# ARCH-2: re-export templates-domain models moved to app.models.templates.
from app.models.templates import (
    Template,
    TemplateStatus,
    TemplateUsage,
    TemplateVersion,
    TemplateVersionStatus,
)

# ARCH-2: Training-domain models moved to app.models.training; re-exported
# here so ``from app.models.models import Training...`` keeps working. All names
# are listed in __all__ below so ruff (F401) does not strip these re-exports.
from app.models.training import (
    Training,
    TrainingAttempt,
    TrainingCertificate,
    TrainingCourse,
    TrainingEnrollment,
    TrainingGroup,
    TrainingLesson,
    TrainingModule,
    TrainingPlan,
    TrainingProgram,
    TrainingProtocol,
    TrainingProtocolItem,
    TrainingSession,
    TrainingSessionStatus,
    TrainingStatus,
    TrainingTest,
    TrainingTestQuestion,
)

if TYPE_CHECKING:  # pragma: no cover - used for type checkers only
    pass

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
    "MedicalExamKind",
    "MedicalFitness",
    "MedicalReferralStatus",
    "MedicalSuspensionStatus",
    "MedicalSuspensionReason",
    "MedicalNorm",
    "MedicalReferral",
    "MedicalSuspension",
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
    "ApiToken",
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
    "TrainingProgram",
    "TrainingModule",
    "TrainingLesson",
    "TrainingTest",
    "TrainingTestQuestion",
    "TrainingGroup",
    "TrainingEnrollment",
    "TrainingAttempt",
    "TrainingProtocol",
    "TrainingProtocolItem",
    "User",
    "RefreshSession",
    "UserRole",
    "UserAttribute",
    "AuthzRole",
    "AuthzPermission",
    "AuthzRolePermission",
    "AuthzUserRole",
    "WebhookSubscription",
    "WebhookEndpoint",
    "WebhookDelivery",
    "ApprovalRoute",
    "ApprovalRouteAppliesTo",
    "ApprovalRouteStatus",
    "ApprovalRouteStep",
    "ApprovalInstance",
    "ApprovalInstanceStep",
    "ApprovalInstanceStatus",
    "ApprovalInstanceStepStatus",
    "ApprovalStepType",
    "SignatureProviderStatus",
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalRequestStatus",
    "ApprovalDecisionType",
    "SignatureType",
    "EdoMessage",
    "EdoReceipt",
    "EdoStatusHistory",
    "EdoDirection",
    "EdoStatus",
    "EdoMessageStatus",
]

# ARCH-2 batch 4 re-exports (kept in __all__ so ruff F401 keeps the imports).
__all__ += [
    "OutboxStatus",
    "ApprovalProcessStatus",
    "ApprovalTaskStatus",
    "ApprovalProcess",
    "ApprovalTask",
    "ApprovalDecisionLog",
    "ApprovalRouteStep",
    "ApprovalInstance",
    "ApprovalInstanceStep",
    "EdoStatusEvent",
    "EdoWebhookInbox",
    "SignatureRequestStatus",
    "SignatureRequest",
    "Outbox",
    "WebhookDelivery",
    "WebhookEndpoint",
]

# ARCH-2 batch 3 re-exports (kept in __all__ so ruff F401 keeps the imports).
__all__ += [
    "File",
    "Company",
    "Position",
    "EmploymentStatus",
    "Person",
    "Site",
    "Workplace",
    "MarketplaceCatalogItem",
    "IdempotencyStatus",
    "IdempotencyKey",
    "RiskMethodology",
    "RiskMap",
    "WorkplaceHazardLink",
    "PositionHazardLink",
    "NPAStatus",
    "NPA",
    "NpaBindingTarget",
    "NPABinding",
    "Asset",
    "EquipmentStatus",
    "Equipment",
]

# ARCH-2 batch 2 re-exports (kept in __all__ so ruff F401 keeps the imports).
__all__ += [
    "PackageEntityStatus",
    "PackageSourceType",
    "ReplaceMode",
    "OutputFormat",
    "PackRunLifecycleStatus",
    "PackRunItemStatus",
    "PackLogLevel",
    "PackageProfileConfig",
    "PackagePresetConfig",
    "PackagePresetItem",
    "PackRun",
    "PackRunItem",
    "PackRunLog",
    "PackageProfile",
    "PackagePreset",
    "DocumentPackModule",
    "DocumentPackScenario",
    "DocumentPack",
    "DocumentPackItem",
    "PipelineRunStatus",
    "PipelineRun",
    "PackageRunStatus",
    "PackageRequirementType",
    "PackageRequirementStatus",
    "ClientRequestTicketStatus",
    "ClientPackagePreset",
    "ClientPackageRun",
    "PackageRequirement",
    "ClientPortalToken",
    "ClientRequestTicket",
    "PackageEvent",
    "AuditLog",
    "AuditExportJob",
    "SecurityAuditLog",
    "JournalType",
    "Journal",
    "JournalEntry",
    "PlanTaskStatus",
    "PlanTask",
    "IncidentSeverity",
    "IncidentType",
    "IncidentStatus",
    "IncidentStage",
    "Incident",
    "IncidentPersonRole",
    "IncidentPerson",
    "IncidentLog",
    "InspectionStatus",
    "InspectionType",
    "Inspection",
    "InspectionResult",
    "AttestationStatus",
    "Attestation",
    "PrescriptionStatus",
    "Prescription",
]

# ARCH-2 batch 1 re-exports (kept in __all__ so ruff F401 keeps the imports).
__all__ += [
    "MedicalExamKind",
    "MedicalFitness",
    "MedicalReferralStatus",
    "MedicalSuspensionStatus",
    "MedicalSuspensionReason",
    "MedicalExam",
    "MedicalNorm",
    "MedicalFactor",
    "MedicalReferral",
    "MedicalSuspension",
    "BriefingTemplate",
    "BriefingJournal",
    "BriefingEntry",
    "BriefingSignature",
    "ComplianceDeadline",
    "CalendarEvent",
    "OfflineSyncBatch",
    "OfflineMediaQueue",
    "ExternalRegistryJob",
    "PermitStatus",
    "Permit",
    "PPENorm",
    "PPEItemCategory",
    "PPEItem",
    "PPEIssueStatus",
    "PPEIssue",
    "PPEStockBatch",
    "TemplateStatus",
    "Template",
    "TemplateVersionStatus",
    "TemplateVersion",
    "TemplateUsage",
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
    # ORM↔миграция drift fix: PG-схема создаёт `code` как NOT NULL
    # (миграция 20250601 batch.alter_column). Приводим ORM к реальной схеме.
    # Контекстный default воспроизводит продакшен-конвенцию `code = slug`, чтобы
    # конструкторы без явного `code` (тесты, seed) не падали на flush; продакшен
    # задаёт `code` явно — тогда default не срабатывает.
    code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda ctx: ctx.get_current_parameters()["slug"],
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(
        Enum("customer", "branch", "contractor", name="tenantkind"),
        nullable=False,
        default="customer",
    )
    # Аналогично `code`: PG-схема NOT NULL (миграция 20250601). Default
    # `tenant_<slug>` по продакшен-конвенции.
    schema_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        default=lambda ctx: f"tenant_{ctx.get_current_parameters()['slug']}",
    )
    # s3_prefix: дрейфа НЕТ — миграция next11 оставляет колонку nullable
    # (alter_column к NOT NULL отсутствует), поэтому ORM тоже nullable=True.
    s3_prefix: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    settings: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenant_slug"),
        UniqueConstraint("code", name="uq_tenants_code"),
        Index("ix_tenants_parent_id", "parent_id"),
        Index("ix_tenants_kind", "kind"),
    )


class TenantQuota(SharedModel):
    __tablename__ = "tenant_quotas"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, unique=True
    )
    max_parallel_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    max_doc_generations_per_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5000
    )
    max_storage_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=10240)
    monthly_edo_outgoing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enforce_billing_gate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TenantSettings(SharedModel):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, unique=True
    )
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    s3_prefix: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retention_policy: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    integration_keys: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )


class TenantCounter(SharedModel):
    __tablename__ = "tenant_counters"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    yyyymm: Mapped[str] = mapped_column(String(6), nullable=False)
    doc_generations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("tenant_id", "yyyymm", name="uq_tenant_counter_period"),)


class TenantIntegrationKey(SharedModel):
    __tablename__ = "tenant_integrations_keys"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    meta_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider", name="uq_tenant_integrations_keys_tenant_provider"
        ),
    )


class TenantQuotaCounter(SharedModel):
    __tablename__ = "tenant_quotas_counters"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
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
    limits: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    features: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    price: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )


class BillingSubscription(SharedModel, SoftDeleteMixin):
    __tablename__ = "subscriptions"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), nullable=False)
    status: Mapped[BillingSubscriptionStatus] = mapped_column(
        native_enum(BillingSubscriptionStatus),
        nullable=False,
        default=BillingSubscriptionStatus.ACTIVE,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_provider: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
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

    __table_args__ = (
        UniqueConstraint("tenant_id", "period_yyyymm", name="uq_usage_counters_tenant_period"),
    )


class BillingInvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


class BillingInvoice(SharedModel):
    __tablename__ = "invoices"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    period_yyyymm: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    status: Mapped[BillingInvoiceStatus] = mapped_column(
        native_enum(BillingInvoiceStatus), nullable=False, default=BillingInvoiceStatus.DRAFT
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

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

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    type: Mapped[BillingEventType] = mapped_column(
        native_enum(BillingEventType), nullable=False, index=True
    )
    ref_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_billing_events_tenant_created", "tenant_id", "created_at"),
        UniqueConstraint("tenant_id", "type", "ref_type", "ref_id", name="uq_billing_event_dedup"),
    )


class TenantRateLimit(SharedModel):
    __tablename__ = "tenant_rate_limits"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, unique=True
    )
    concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    burst: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    rps: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    queues: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )


class ApiToken(SharedModel, SoftDeleteMixin):
    __tablename__ = "api_tokens"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    scopes_json: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_api_tokens_tenant_created", "tenant_id", "created_at"),)


class TenantLimitOverride(SharedModel):
    __tablename__ = "tenant_limits_override"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, unique=True
    )
    limits: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    features: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )


class WebhookSubscription(SharedModel):
    __tablename__ = "webhook_subscription"

    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    headers: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (Index("ix_webhook_subscription_tenant_event", "tenant_id", "event_type"),)


class User(TenantBaseModel, SoftDeleteMixin):
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(native_enum(RoleEnum), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped[Company | None] = relationship("Company", backref="users", lazy="joined")
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


class RefreshSession(TenantBaseModel):
    __tablename__ = "refresh_session"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token_jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    parent_token_jti: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replaced_by_token_jti: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_refresh_session_user_family", "tenant_id", "user_id", "family_id"),
        Index("ix_refresh_session_family_active", "tenant_id", "family_id", "revoked_at"),
    )


class UserRole(TenantBaseModel):
    __tablename__ = "user_role"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[RoleEnum] = mapped_column(native_enum(RoleEnum), nullable=False)

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
    company_ids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    site_ids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    project_ids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    contractor_ids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )

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

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_authz_roles_tenant_code"),)


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
        UniqueConstraint(
            "tenant_id",
            "role_id",
            "permission_code",
            name="uq_authz_role_permissions_tenant_role_code",
        ),
    )


class AuthzUserRole(AuthzBaseModel):
    __tablename__ = "authz_user_roles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("authz_roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "role_id", name="uq_authz_user_roles_tenant_user_role"
        ),
        Index("ix_authz_user_roles_user", "tenant_id", "user_id"),
        Index("ix_authz_user_roles_role", "tenant_id", "role_id"),
    )


class AuthzPolicy(AuthzBaseModel):
    __tablename__ = "authz_policies"

    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    effect: Mapped[str] = mapped_column(String(8), nullable=False)
    conditions_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
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
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_api_key_tenant_name"),)

    @property
    def scope_list(self) -> list[str]:
        return [scope for scope in self.scopes.split() if scope]
