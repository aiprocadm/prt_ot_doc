from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Subject:
    user_id: str | None
    tenant_id: str | None
    roles: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    company_ids: tuple[str, ...] = ()
    site_ids: tuple[str, ...] = ()
    project_ids: tuple[str, ...] = ()
    contractor_ids: tuple[str, ...] = ()
    risk_level_max: int | None = None


@dataclass(frozen=True, slots=True)
class Resource:
    resource_type: str
    resource_id: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PolicyContext:
    tenant_id: str | None = None
    user_id: str | None = None
    roles: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    abac_scopes: dict[str, Any] = field(default_factory=dict)
    request_attrs: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    allow: bool
    reason: str
    audit_fields: dict[str, Any] = field(default_factory=dict)
