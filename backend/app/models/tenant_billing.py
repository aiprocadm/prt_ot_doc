"""Tenant control-plane, billing & role-enum ORM models — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py.
"""

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
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    SharedModel,
    SoftDeleteMixin,
    native_enum,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    from app.models.models import (
        Tenant,
    )


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
    # `reseller` добавлен волной BIZ-52 (разд. 52.1): вид арендатора — это его
    # уровень в иерархии продажи платформы, а не ярлык. Правила уровней живут в
    # `app.domains.reseller.hierarchy`; в БД значение доезжает миграцией rs01
    # (ALTER TYPE ... ADD VALUE, старые строки не трогаются).
    kind: Mapped[str] = mapped_column(
        Enum("customer", "branch", "contractor", "reseller", name="tenantkind"),
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

    # Lives in the shared schema but is tenant-scoped: opt into the before_flush guard
    # (``db/session.py::_apply_default_tenant``) so tenant_id is auto-stamped from the
    # session and a slug in that column raises instead of silently becoming invisible
    # under the SEC-65 policy, which compares against the tenant UUID.
    __tenant_model__ = True

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
