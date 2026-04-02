"""Decorator for declarative audit-trail logging on route handlers.

Usage::

    @router.post("/items", status_code=201)
    @audit_operation("create", "item")
    async def create_item(
        payload: ItemPayload,
        request: Request,
        tenant: Tenant = Depends(get_tenant_record),
        session: AsyncSession = Depends(get_session),
    ):
        ...

The decorator wraps the coroutine *after* it completes successfully and writes
an audit log entry.  It preserves the function signature so FastAPI dependency
injection continues to work unmodified.

Extracted automatically from kwargs/request.state:
- ``tenant_id``   – from a ``Tenant`` kwarg (attr ``.id``) or ``tenant_id`` str
- ``user_id``     – from ``request.state.current_user_id``
- ``ip``          – from ``request.client.host``
- ``object_id``   – from the return value (attribute ``id_attr``), or ``"-"``
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps
from inspect import Signature, signature
from typing import Any, get_type_hints

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _resolved_signature(func: Callable[..., Any]) -> Signature:
    """Build a signature with resolved annotations in the original function scope.

    FastAPI evaluates annotations against the callable globals. Wrapped handlers live
    in this module, so forward refs from route modules can fail unless we resolve
    them upfront and pin the resulting signature on the wrapper.
    """

    raw_sig = signature(func)
    try:
        resolved = get_type_hints(func, globalns=func.__globals__, localns=None, include_extras=True)
    except Exception:  # noqa: BLE001 - fallback to raw annotations when resolution fails
        resolved = {}

    params = []
    for param in raw_sig.parameters.values():
        annotation = resolved.get(param.name, param.annotation)
        params.append(param.replace(annotation=annotation))

    return_annotation = resolved.get("return", raw_sig.return_annotation)
    return raw_sig.replace(parameters=params, return_annotation=return_annotation)


def _extract_tenant_id(kwargs: dict[str, Any]) -> str:
    """Try to resolve a tenant identifier from handler kwargs."""
    for key in ("tenant", "tenant_record"):
        obj = kwargs.get(key)
        if obj is not None:
            tid = getattr(obj, "id", None)
            if tid is not None:
                return str(tid)
    for key in ("tenant_id",):
        val = kwargs.get(key)
        if val is not None:
            return str(val)
    return "-"


def _extract_object_id(result: Any, id_attr: str) -> str:
    def _to_id(value: Any) -> str | None:
        if value is None:
            return None
        nested = getattr(value, "id", None)
        if nested is not None:
            return str(nested)
        if isinstance(value, dict):
            nested = value.get("id")
            if nested is not None:
                return str(nested)
        return str(value)

    if result is None:
        return "-"
    # Pydantic/ORM models
    val = getattr(result, id_attr, None)
    if val is not None:
        resolved = _to_id(val)
        if resolved:
            return resolved
    # dict-like results
    if isinstance(result, dict):
        val = result.get(id_attr)
        if val is not None:
            resolved = _to_id(val)
            if resolved:
                return resolved
    return "-"


def audit_operation(
    action: str,
    entity_type: str,
    *,
    id_attr: str = "id",
    details_fn: Callable[[Any], dict[str, Any]] | None = None,
) -> Callable[[Callable], Callable]:
    """Decorate a FastAPI route handler to emit an audit log entry.

    Args:
        action:      Audit action verb, e.g. ``"create"``, ``"update"``, ``"delete"``.
        entity_type: Resource type name, e.g. ``"document"``, ``"briefing_entry"``.
        id_attr:     Attribute or dict key to read ``object_id`` from the result.
        details_fn:  Optional callable ``(result) -> dict`` for extra audit details.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await func(*args, **kwargs)

            # After successful completion, emit audit event.
            try:
                request: Request | None = kwargs.get("request")
                session: AsyncSession | None = kwargs.get("session")

                if request is None or session is None:
                    return result

                tenant_id = _extract_tenant_id(kwargs)
                user_id_raw = getattr(request.state, "current_user_id", None)
                user_id = str(user_id_raw) if user_id_raw is not None else None
                ip = request.client.host if request.client else "unknown"
                object_id = _extract_object_id(result, id_attr)
                trace_id = getattr(request.state, "trace_id", None)

                extra: dict[str, Any] = {"trace_id": trace_id} if trace_id else {}
                if details_fn is not None:
                    try:
                        extra.update(details_fn(result))
                    except Exception:  # noqa: BLE001
                        pass

                # Import here to avoid circular imports at module load time.
                from app.services.audit import AuditService  # noqa: PLC0415

                await AuditService(session).log_event(
                    tenant_id=tenant_id,
                    action=action,
                    object_type=entity_type,
                    object_id=object_id,
                    user_id=user_id,
                    ip=ip,
                    details=extra or None,
                )
            except Exception:  # noqa: BLE001
                # Audit failure must never break the request.
                logger.exception(
                    "audit_decorator.log_failure",
                    extra={
                        "action": action,
                        "entity_type": entity_type,
                    },
                )

            return result

        wrapper.__signature__ = _resolved_signature(func)
        return wrapper

    return decorator
