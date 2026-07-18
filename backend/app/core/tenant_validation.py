"""
Tenant context validation and enforcement helpers.

Ensures every operation maintains tenant safety and isolation.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERROR_CODES, api_problem_detail
from app.models.models import Tenant


class TenantContextValidator:
    """Validates and enforces tenant context in all operations."""

    @staticmethod
    def ensure_tenant_context(tenant: Tenant | None, operation: str = "access") -> Tenant:
        """
        Ensure tenant context is available.

        Args:
            tenant: Tenant from dependencies
            operation: Name of operation (for error message)

        Returns:
            Tenant record

        Raises:
            ValueError: If tenant context missing
        """
        if tenant is None:
            raise ValueError(f"Tenant context required for {operation}")
        if not tenant.is_active:
            raise ValueError(f"Tenant {tenant.slug} is inactive")
        return tenant

    @staticmethod
    def ensure_session_tenant(session: AsyncSession, expected_tenant: str) -> None:
        """
        Ensure session is scoped to correct tenant.

        Args:
            session: Database session
            expected_tenant: Expected tenant slug

        Raises:
            ValueError: If session tenant mismatch
        """
        session_info = getattr(session, "info", {}) or {}
        session_tenant = session_info.get("tenant")
        if session_tenant != expected_tenant:
            raise ValueError(
                f"Session tenant mismatch: session={session_tenant}, expected={expected_tenant}"
            )

    @staticmethod
    def build_tenant_error(
        error_code: str,
        correlation_id: str | None = None,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Build standardized tenant error response.

        Args:
            error_code: Error code from ERROR_CODES
            correlation_id: Deprecated for detail body; final ``trace_id`` comes from request handlers.
            field: Field name (if applicable)
            details: Additional details

        Returns:
            Error detail dict
        """
        status_code, default_message = ERROR_CODES.get(error_code, (500, "Unknown error"))
        return api_problem_detail(
            code=error_code,
            message=default_message,
            details=details,
            field=field,
        )


def validate_tenant_in_operation(tenant: Tenant, expected_tenant_id: str | None = None) -> None:
    """
    Validate tenant in business operation.

    Args:
        tenant: Current tenant
        expected_tenant_id: If provided, verify tenant.id matches

    Raises:
        ValueError: If tenant validation fails
    """
    if tenant is None or not tenant.is_active:
        raise ValueError("Invalid or inactive tenant")
    if expected_tenant_id and str(tenant.id) != expected_tenant_id:
        raise ValueError(f"Tenant mismatch: {tenant.id} != {expected_tenant_id}")
