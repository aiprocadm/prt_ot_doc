from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class TenantContext:
    tenant_id: str
    slug: str
    schema: str
    s3_prefix: str
    plan: str
    max_parallel_jobs: int | None = None
    max_storage_mb: int | None = None
    max_generations_per_month: int | None = None
