"""Health check response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HealthCheckItem(BaseModel):
    """Single health check result."""

    name: str = Field(..., description="Check name (postgres, redis, workers, etc.)")
    status: str = Field(..., description="Status: ok, degraded, or failed")
    error: str | None = Field(None, description="Error message if failed")
    duration_ms: float = Field(..., description="Check execution time in milliseconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthCheckComprehensiveResponse(BaseModel):
    """Comprehensive health check response."""

    status: str = Field(
        ...,
        description="Overall status: ok (all checks pass), "
        "degraded (some checks fail), failed (critical checks fail)",
    )
    checks: dict[str, HealthCheckItem] = Field(
        default_factory=dict, description="Individual check results"
    )
    tenant_id: str | None = Field(None, description="Tenant ID for scoping")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
