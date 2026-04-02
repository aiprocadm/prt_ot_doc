from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class UserContext:
    user_id: str
    roles: tuple[str, ...] = field(default_factory=tuple)
    company_id: str | None = None
    contractor_id: str | None = None
    site_ids: tuple[str, ...] = field(default_factory=tuple)
    permissions: tuple[str, ...] = field(default_factory=tuple)
    tenant_id: str | None = None
