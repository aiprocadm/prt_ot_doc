"""Database utilities and session helpers."""

from __future__ import annotations

from app.db.session import (  # noqa: F401
    AsyncSessionLocal,
    SessionLocal,
    SharedBase,
    TenantBase,
    engine,
    ensure_tenant_schema,
    get_session,
    session_scope,
)

# Compatibility alias used across tests and alembic scripts.
Base = TenantBase

__all__ = [
    "AsyncSessionLocal",
    "Base",
    "SessionLocal",
    "SharedBase",
    "TenantBase",
    "Base",
    "engine",
    "ensure_tenant_schema",
    "get_session",
    "session_scope",
]
