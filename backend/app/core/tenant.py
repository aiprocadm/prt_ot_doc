"""Tenant context management and helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.core.config import get_settings

__all__ = [
    "TENANT_HEADER",
    "TENANT_HEADER_ALIASES",
    "TenantInfo",
    "get_current_tenant",
    "set_current_tenant",
    "tenant_schema",
    "tenant_prefix_path",
    "tenant_required",
    "tenant_context",
]

TENANT_HEADER = "x-tenant"
TENANT_HEADER_ALIASES = (TENANT_HEADER, "x-tenant-slug")
_settings = get_settings()
_TENANT_VAR: ContextVar[str] = ContextVar(
    "tenant_slug", default=_settings.default_tenant_slug
)
_ALLOWED_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-_")


def _normalize_slug(raw: str) -> str:
    slug = raw.strip().lower()
    if not slug:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tenant slug is required")
    if len(slug) > 64:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tenant slug is too long")
    if any(ch not in _ALLOWED_CHARS for ch in slug):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Tenant slug has invalid characters",
        )
    return slug


@dataclass(slots=True, frozen=True)
class TenantInfo:
    slug: str

    @property
    def schema(self) -> str:
        return tenant_schema(self.slug)

    @property
    def s3_prefix(self) -> str:
        return tenant_prefix_path(self.slug)


def tenant_schema(slug: str) -> str:
    return f"tenant_{slug}"


def tenant_prefix_path(slug: str) -> str:
    return f"tenants/{slug}"


def get_current_tenant() -> TenantInfo:
    slug = _TENANT_VAR.get()
    return TenantInfo(slug=slug)


def set_current_tenant(slug: str) -> TenantInfo:
    normalized = _normalize_slug(slug)
    _TENANT_VAR.set(normalized)
    return TenantInfo(slug=normalized)


def tenant_required(slug: str | None) -> TenantInfo:
    if slug is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {"code": "TENANT_REQUIRED", "type": "validation", "message": "X-Tenant header is required"},
        )
    return set_current_tenant(slug)


@contextmanager
def tenant_context(slug: str) -> Iterator[TenantInfo]:
    token: Token[str] | None = None
    try:
        token = _TENANT_VAR.set(_normalize_slug(slug))
        yield get_current_tenant()
    finally:
        if token is not None:
            _TENANT_VAR.reset(token)
