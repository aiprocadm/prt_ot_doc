"""
Unified permission checking helpers.

Standardizes permission enforcement across all endpoints.
"""

from enum import Enum
from typing import Callable

from fastapi import HTTPException, status

from app.core.errors import ErrorBuilder


class PermissionAction(str, Enum):
    """Standard permission actions."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"
    EXPORT = "export"
    BULK = "bulk"


class PermissionChecker:
    """Unified permission checking."""

    @staticmethod
    def check(
        has_permission: bool,
        action: PermissionAction | str = "access",
        resource: str = "resource",
        correlation_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """
        Check permission and raise if denied.

        Args:
            has_permission: True if permission granted
            action: Permission action (read, write, delete, etc.)
            resource: Resource name
            correlation_id: Request correlation ID
            metadata: Additional metadata for error

        Raises:
            HTTPException: 403 Forbidden if check fails
        """
        if has_permission:
            return

        error = (
            ErrorBuilder()
            .with_code("PERMISSION_DENIED")
            .with_message(f"Permission denied for {action} on {resource}")
            .with_correlation_id(correlation_id)
        )

        if metadata:
            error = error.with_details(metadata)

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error.build().model_dump(),
        )

    @staticmethod
    def check_any(
        permissions: list[bool],
        action: str = "access",
        resource: str = "resource",
        correlation_id: str | None = None,
    ) -> None:
        """
        Check if any permission is granted (OR logic).

        Args:
            permissions: List of permission checks
            action: Permission action
            resource: Resource name
            correlation_id: Request correlation ID

        Raises:
            HTTPException: 403 Forbidden if all checks fail
        """
        if any(permissions):
            return

        error = (
            ErrorBuilder()
            .with_code("PERMISSION_DENIED")
            .with_message(f"Permission denied for {action} on {resource}")
            .with_correlation_id(correlation_id)
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error.build().model_dump(),
        )

    @staticmethod
    def check_all(
        permissions: list[bool],
        action: str = "access",
        resource: str = "resource",
        correlation_id: str | None = None,
    ) -> None:
        """
        Check if all permissions are granted (AND logic).

        Args:
            permissions: List of permission checks
            action: Permission action
            resource: Resource name
            correlation_id: Request correlation ID

        Raises:
            HTTPException: 403 Forbidden if any check fails
        """
        if all(permissions):
            return

        error = (
            ErrorBuilder()
            .with_code("PERMISSION_DENIED")
            .with_message(f"Permission denied for {action} on {resource}")
            .with_correlation_id(correlation_id)
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error.build().model_dump(),
        )


def require_permission(
    check_fn: Callable[[], bool],
    action: str = "access",
    resource: str = "resource",
    correlation_id: str | None = None,
) -> None:
    """
    Require permission (callable pattern).

    Args:
        check_fn: Function that returns True if permitted
        action: Permission action
        resource: Resource name
        correlation_id: Request correlation ID

    Raises:
        HTTPException: 403 Forbidden if check fails
    """
    PermissionChecker.check(
        check_fn(),
        action=action,
        resource=resource,
        correlation_id=correlation_id,
    )
