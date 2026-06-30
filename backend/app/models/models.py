from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.db.session import TenantBase
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
from app.models.file import File

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


class Company(TenantBaseModel, SoftDeleteMixin):
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str | None] = mapped_column("tax_id", String(32), nullable=True)
    kpp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ogrn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    activity_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    okved_codes: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    legal_address: Mapped[str | None] = mapped_column("address", String(255))
    actual_address: Mapped[str | None] = mapped_column(String(255))
    director: Mapped[str | None] = mapped_column(String(255))
    bank_name: Mapped[str | None] = mapped_column(String(255))
    bank_bik: Mapped[str | None] = mapped_column(String(32))
    bank_account: Mapped[str | None] = mapped_column(String(32))
    phone_numbers: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
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
    branding_payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    preferred_header_preset_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_types: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    hazardous_factors: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    is_hazardous_production_facility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    has_dangerous_objects: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # CRM-статус карточки компании (draft/active/archived) — VARCHAR, не PG-enum
    # (снимает класс enum-parity). tags — свободные метки; nullable, чтобы add_column
    # на существующую таблицу не требовал server_default на JSON.
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    tags: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(JSON), nullable=True, default=list
    )

    logo_file: Mapped["File | None"] = relationship(
        "File", foreign_keys=[logo_file_id], lazy="selectin"
    )
    stamp_file: Mapped["File | None"] = relationship(
        "File", foreign_keys=[stamp_file_id], lazy="selectin"
    )

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_company_tenant_name"),)

    tax_id = synonym("inn")
    address = synonym("legal_address")


class Position(TenantBaseModel, SoftDeleteMixin):
    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    safety_category: Mapped[str | None] = mapped_column(String(64))
    working_conditions_class: Mapped[str | None] = mapped_column(String(32))
    hazardous_factors: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )

    company: Mapped[Company] = relationship(backref="positions")
    hazards: Mapped[list["RiskHazard"]] = relationship(
        "RiskHazard",
        secondary="position_hazard",
        lazy="selectin",
        back_populates="positions",
        overlaps="hazard_links,position,hazard",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "name", name="uq_position_company_name"),
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
    qualifications: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    snils: Mapped[str | None] = mapped_column(String(32))
    passport: Mapped[str | None] = mapped_column(String(64))
    current_ppe: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    # 766н: рост и размеры СИЗ работника (одежда/обувь/головной убор/СИЗОД/
    # перчатки/рукавицы). JSON: состав ключей зависит от выдаваемых СИЗ.
    ppe_sizes: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    working_conditions_class: Mapped[str | None] = mapped_column(String(32))
    hazardous_factors: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    # Свободнотекстовая должность (то, что вводит пользователь во фронте). Отдельно
    # от структурного position_id/relationship `position` (каталог Position) — имя
    # `position` занято связью, поэтому колонка называется position_title.
    position_title: Mapped[str | None] = mapped_column(String(255))
    # values_callable: SQLAlchemy ``Enum`` defaults to sending the Python
    # enum member *name* ("ACTIVE"), but the PG type ``employmentstatus``
    # was created with lowercase *values* ("active") in migration
    # 8d2c1a6c5e24. Override to send ``.value`` so INSERTs satisfy the
    # enum's accepted-value set. Without this, demo bootstrap fails with
    # ``InvalidTextRepresentationError: invalid input value for enum
    # employmentstatus: "ACTIVE"``.
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        Enum(
            EmploymentStatus,
            name="employmentstatus",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=EmploymentStatus.ACTIVE,
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
    geo_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    hazard_class: Mapped[str | None] = mapped_column(String(32))
    site_type: Mapped[str | None] = mapped_column(String(64))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    is_hazardous_production_facility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    opo_register_number: Mapped[str | None] = mapped_column(String(64))
    branding_payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

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
        overlaps="hazard_links,workplace,hazard",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "name", name="uq_workplace_company_name"),
    )


class MarketplaceCatalogItem(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "marketplace_catalog_items"

    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags_json: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    compatibility_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    dependency_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "item_type", "code", "version_label", name="uq_marketplace_catalog_item"
        ),
        Index("ix_marketplace_catalog_lookup", "tenant_id", "item_type", "status", "updated_at"),
    )


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
    response_headers: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    response_body: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "endpoint", "key", name="uq_idempotency_keys"),
        Index("ix_idempotency_keys_lookup", "tenant_id", "endpoint", "key"),
    )


class RiskMethodology(TenantBaseModel):
    """Risk calculation methodology including severity/likelihood scales."""

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_risk_methodology_name"),
        UniqueConstraint("tenant_id", "code", name="uq_risk_methodology_code"),
    )


class RiskMap(TenantBaseModel):
    methodology_id: Mapped[str] = mapped_column(
        ForeignKey("riskmethodology.id"), nullable=False, index=True
    )
    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("site.id"), nullable=True, index=True)
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id"), nullable=True, index=True
    )
    document_pack_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_pack.id"), nullable=True, index=True
    )
    matrix: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)
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

    workplace: Mapped[Workplace] = relationship(
        backref="hazard_links", overlaps="hazards,workplaces"
    )
    hazard: Mapped["RiskHazard"] = relationship("RiskHazard", overlaps="hazards,workplaces")
    document_file: Mapped["File | None"] = relationship("File")

    __table_args__ = (
        UniqueConstraint("tenant_id", "workplace_id", "hazard_id", name="uq_workplace_hazard_link"),
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

    position: Mapped[Position] = relationship(backref="hazard_links", overlaps="hazards,positions")
    hazard: Mapped["RiskHazard"] = relationship("RiskHazard", overlaps="hazards,positions")
    document_file: Mapped["File | None"] = relationship("File")

    __table_args__ = (
        UniqueConstraint("tenant_id", "position_id", "hazard_id", name="uq_position_hazard_link"),
    )


class NPAStatus(str, enum.Enum):
    ACTIVE = "active"
    OBSOLETE = "obsolete"


class NPA(TenantBaseModel):
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    edition_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[NPAStatus] = mapped_column(
        Enum(NPAStatus), nullable=False, default=NPAStatus.ACTIVE
    )

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_npa_code"),)


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
        Enum(
            NpaBindingTarget,
            name="npabindingtarget",
            # iter-19 RB-002h cohort closure: PG type `npabindingtarget` was
            # created lowercase by migration 8d2c1a6c5e24:59-62. Member names
            # are uppercase ("TEMPLATE_VERSION"), so default SQLAlchemy binding
            # sends the name → asyncpg rejects. Force `.value` via callable.
            # Pinned by `backend/tests/test_npabinding_target_enum_values.py`.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=NpaBindingTarget.TEMPLATE_VERSION,
    )
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    template_version: Mapped[TemplateVersion | None] = relationship(backref="npa_bindings")
    npa: Mapped[NPA] = relationship(backref="bindings")


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
    status: Mapped[EquipmentStatus] = mapped_column(
        Enum(EquipmentStatus), nullable=False, default=EquipmentStatus.ACTIVE
    )

    asset: Mapped[Asset] = relationship(backref="equipment")


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SENT = "SENT"
    FAILED = "FAILED"
    DEAD = "DEAD"


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
    route_id: Mapped[str] = mapped_column(
        ForeignKey("approval_routes.id"), nullable=False, index=True
    )
    status: Mapped[ApprovalProcessStatus] = mapped_column(
        native_enum(ApprovalProcessStatus), nullable=False, default=ApprovalProcessStatus.PENDING
    )
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

    process_id: Mapped[str] = mapped_column(
        ForeignKey("approval_processes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    assignee_type: Mapped[str] = mapped_column(String(16), nullable=False)
    assignee_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ApprovalTaskStatus] = mapped_column(
        native_enum(ApprovalTaskStatus), nullable=False, default=ApprovalTaskStatus.OPEN
    )
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

    process_id: Mapped[str] = mapped_column(
        ForeignKey("approval_processes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("approval_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))


class ApprovalRouteStep(TenantBaseModel, SoftDeleteMixin, VersionedMixin):
    __tablename__ = "approval_route_steps"

    approval_route_id: Mapped[str] = mapped_column(
        ForeignKey("approval_routes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[ApprovalStepType] = mapped_column(
        Enum(ApprovalStepType), nullable=False, default=ApprovalStepType.APPROVE
    )
    role_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    can_delegate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deadline_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_role_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    escalation_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    conditions_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("approval_route_id", "order_no", name="uq_approval_route_steps_order"),
        Index("ix_approval_route_steps_route_order", "approval_route_id", "order_no"),
    )


class ApprovalInstance(TenantBaseModel, SoftDeleteMixin, VersionedMixin):
    __tablename__ = "approval_instances"

    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    approval_route_id: Mapped[str] = mapped_column(
        ForeignKey("approval_routes.id"), nullable=False, index=True
    )
    status: Mapped[ApprovalInstanceStatus] = mapped_column(
        Enum(ApprovalInstanceStatus), nullable=False, default=ApprovalInstanceStatus.DRAFT
    )
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

    approval_instance_id: Mapped[str] = mapped_column(
        ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    route_step_id: Mapped[str] = mapped_column(
        ForeignKey("approval_route_steps.id"), nullable=False, index=True
    )
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    assignee_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    assignee_role_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    delegated_from_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[ApprovalInstanceStepStatus] = mapped_column(
        Enum(ApprovalInstanceStepStatus), nullable=False, default=ApprovalInstanceStepStatus.PENDING
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )

    __table_args__ = (
        Index("ix_approval_instance_steps_lookup", "approval_instance_id", "status", "order_no"),
    )


class EdoStatusEvent(TenantBaseModel):
    __tablename__ = "edo_status_events"

    edo_message_id: Mapped[str] = mapped_column(
        ForeignKey("edo_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )
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
    headers_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="received")
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class SignatureRequestStatus(str, enum.Enum):
    CREATED = "created"
    REQUESTED = "requested"
    SIGNED = "signed"
    FAILED = "failed"
    AWAITING_CODE = "awaiting_code"
    DECLINED = "declined"
    EXPIRED = "expired"


class SignatureRequest(TenantBaseModel):
    __tablename__ = "signature_requests"

    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approval_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("approval_instances.id"), nullable=True, index=True
    )
    signature_type: Mapped[str] = mapped_column(String(16), nullable=False, default="kep")
    provider_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SignatureProviderStatus.PENDING.value
    )
    external_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    certificate_thumbprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_result_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))

    # --- PEP (простая электронная подпись, ed01) ---
    # Plain string — no FK (user ids come from external auth; pattern follows requested_by).
    signer_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    signer_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confirm_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirm_code_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirm_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        Index("ix_signature_requests_status", "tenant_id", "status"),
        Index("ix_signature_requests_object", "tenant_id", "object_type", "object_id"),
        Index(
            "ix_signature_requests_entity_status", "tenant_id", "object_type", "object_id", "status"
        ),
    )


class Outbox(TenantBaseModel):
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    destination: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    headers: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus),
        nullable=False,
        default=OutboxStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
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
    request_headers: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    response_headers: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
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
    subscribed_events: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    headers: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )

    __table_args__ = (Index("ix_webhook_endpoint_tenant_enabled", "tenant_id", "is_enabled"),)
