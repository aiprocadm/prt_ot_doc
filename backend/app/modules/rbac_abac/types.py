from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Subject:
    user_id: str | None
    tenant_id: str | None
    roles: tuple[str, ...] = ()
    company_ids: tuple[str, ...] = ()
    site_ids: tuple[str, ...] = ()
    project_ids: tuple[str, ...] = ()
    contractor_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Resource:
    resource_type: str
    resource_id: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PolicyContext:
    tenant_id: str | None = None
    request_ip: str | None = None
    user_agent: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    allow: bool
    reason: str
    obligations: dict[str, Any] = field(default_factory=dict)
