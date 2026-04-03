"""Defense-in-depth: validate tenant-scoped ORM rows against the active session tenant.

On SQLite (single shared schema), ``AsyncSession.get(Model, pk)`` can load another tenant's row.
HTTP handlers on Postgres often rely on schema search_path; Celery and tests still need this guard.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def assert_tenant_row_matches_session(
    session: AsyncSession,
    row: object | None,
    *,
    mismatch_event: str,
    not_found_message: str,
    expected_tenant_id: str | None = None,
) -> None:
    """Compare row.tenant_id to session tenant, or to ``expected_tenant_id`` if session has none.

    API tests sometimes use a session without ``info["tenant_id"]``; pass ``expected_tenant_id`` so
    PK loads on SQLite still cannot cross tenants.
    """

    if row is None:
        return
    session_tid = str(session.info.get("tenant_id") or "").strip()
    expected = str(expected_tenant_id).strip() if expected_tenant_id is not None else ""
    effective_tid = session_tid or expected
    if not effective_tid:
        return
    row_tid = getattr(row, "tenant_id", None)
    if row_tid is None:
        return
    if str(row_tid) == effective_tid:
        return
    logger.warning(
        mismatch_event,
        extra={
            "model": type(row).__name__,
            "row_id": getattr(row, "id", None),
            "row_tenant_id": str(row_tid),
            "session_tenant_id": session_tid or None,
            "expected_tenant_id": expected or None,
            "effective_tenant_id": effective_tid,
        },
    )
    raise ValueError(not_found_message)
