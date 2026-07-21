from __future__ import annotations

from typing import Literal

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema


class TenantQuotaRead(BaseSchema):
    tenant_id: str
    max_parallel_jobs: int
    max_doc_generations_per_month: int
    max_storage_mb: int
    monthly_edo_outgoing: int
    enforce_billing_gate: bool


class TenantRead(BaseSchema):
    id: str
    name: str
    slug: str
    code: str | None = None
    contact_email: str
    is_active: bool
    parent_id: str | None = None
    kind: Literal["customer", "branch", "contractor"] | None = None
    schema_name: str | None = None


class TenantPage(BaseSchema):
    items: list[TenantRead]
    total: int


class TenantCreate(BaseSchema):
    slug: str
    name: str
    contact_email: str
    code: str | None = None
    parent_id: str | None = None
    kind: Literal["customer", "branch", "contractor"] = "customer"


class TenantQuotaPatch(BaseSchema):
    max_parallel_jobs: int | None = Field(default=None, ge=1)
    max_doc_generations_per_month: int | None = Field(default=None, ge=1)
    max_storage_mb: int | None = Field(default=None, ge=1)
    monthly_edo_outgoing: int | None = Field(default=None, ge=0)
    enforce_billing_gate: bool | None = None


# The slug becomes a Postgres schema name (``tenant_<slug>``), so it is restricted to a
# safe identifier alphabet instead of the free-form string ``TenantCreate`` accepts.
TENANT_SLUG_PATTERN = r"^[a-z][a-z0-9_-]{1,30}$"


class TenantProvisionRequest(BaseSchema):
    slug: str = Field(pattern=TENANT_SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    owner_password: str = Field(min_length=8, max_length=128)
    kind: Literal["customer", "branch", "contractor"] = "customer"
    demo_data: bool = False


class TenantProvisionResult(BaseSchema):
    tenant: TenantRead
    created: list[str] = Field(default_factory=list)
    reused: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TenantStatusPatch(BaseSchema):
    is_active: bool


class TenantFeatureRead(BaseSchema):
    code: str
    title: str
    on: bool


class TenantFleetItem(BaseSchema):
    tenant: TenantRead
    quotas: TenantQuotaRead | None = None
    # ``plan`` is derived from the enabled feature set: a known tier code, or ``None``
    # for a hand-tweaked ("custom") tenant / one that never had a plan applied.
    plan: str | None = None
    features: list[TenantFeatureRead] = Field(default_factory=list)


class TenantFleetPage(BaseSchema):
    items: list[TenantFleetItem]
    total: int
    managing_tenant_slug: str


class FeatureCatalogEntry(BaseSchema):
    code: str
    title: str


class SubscriptionPlanRead(BaseSchema):
    code: str
    title: str
    feature_codes: list[str]
    quotas: dict[str, int] = Field(default_factory=dict)


class PlanCatalog(BaseSchema):
    plans: list[SubscriptionPlanRead]
    features: list[FeatureCatalogEntry]


class TenantPlanPatch(BaseSchema):
    plan: str
