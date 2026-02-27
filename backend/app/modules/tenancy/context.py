from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class TenantContext:
    tenant_id: str
    slug: str
    schema: str
    tenant_level: str
    s3_prefix: str
    plan: str
    limits: dict[str, int | bool | None] | None = None
    max_parallel_jobs: int | None = None
    max_storage_mb: int | None = None
    max_generations_per_month: int | None = None
    correlation_id: str | None = None
    actor_id: str | None = None
    roles: tuple[str, ...] = ()
    attributes: dict[str, str] | None = None


_TENANT_CONTEXT: ContextVar[TenantContext | None] = ContextVar("tenant_context", default=None)


def set_tenant_context(ctx: TenantContext | None) -> Token[TenantContext | None]:
    return _TENANT_CONTEXT.set(ctx)


def get_tenant_context() -> TenantContext | None:
    return _TENANT_CONTEXT.get()


def reset_tenant_context(token: Token[TenantContext | None]) -> None:
    _TENANT_CONTEXT.reset(token)
