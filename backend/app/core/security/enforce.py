from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.errors import api_problem_detail
from app.core.rbac_abac import ActorContext, policy_engine


def enforce(
    *, user: ActorContext, action: str, resource: str, ctx: dict[str, Any] | None = None
) -> None:
    decision = policy_engine.enforce(user, action=action, resource=resource, ctx=ctx or {})
    if decision.allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=api_problem_detail(
            code="FORBIDDEN",
            message="Forbidden",
            error_type="policy",
            details={"reason_code": decision.reason},
        ),
    )
