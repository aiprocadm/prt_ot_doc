from __future__ import annotations

from typing import Literal

from pydantic import Field

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
