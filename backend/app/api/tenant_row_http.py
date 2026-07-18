"""Map ``assert_tenant_row_matches_session`` to HTTP errors for route handlers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant_row_guard import assert_tenant_row_matches_session


def enforce_row_belongs_to_tenant(
    session: AsyncSession,
    row: object,
    *,
    tenant_id: str,
    mismatch_event: str,
    detail: str | dict[str, Any] = "Not found",
    status_code: int = status.HTTP_404_NOT_FOUND,
) -> None:
    """Use after ``session.get`` when the id came from path/body/queue. Raises on tenant mismatch."""

    try:
        assert_tenant_row_matches_session(
            session,
            row,
            mismatch_event=mismatch_event,
            not_found_message="tenant_scope_mismatch",
            expected_tenant_id=tenant_id,
        )
    except ValueError:
        raise HTTPException(status_code, detail) from None
