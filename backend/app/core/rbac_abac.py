from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.sql import Select


class Action(str, enum.Enum):
    READ = "read"
    LIST = "list"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    APPROVE = "approve"
    SIGN = "sign"
    EXPORT = "export"


@dataclass(frozen=True, slots=True)
class ActorContext:
    roles: tuple[str, ...]
    company_ids: tuple[str, ...] = ()
    site_ids: tuple[str, ...] = ()
    project_ids: tuple[str, ...] = ()
    contractor_ids: tuple[str, ...] = ()


def policy_forbidden(reason: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "forbidden", "type": "policy", "message": reason},
    )


def _normalize_list(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if item)
    return ()


def actor_from_claims(claims: dict[str, Any] | Any, roles: list[str]) -> ActorContext:
    return ActorContext(
        roles=tuple(role.lower() for role in roles),
        company_ids=_normalize_list(claims.get("company_ids") or claims.get("company_id")),
        site_ids=_normalize_list(claims.get("site_ids") or claims.get("site_id")),
        project_ids=_normalize_list(claims.get("project_ids") or claims.get("project_id")),
        contractor_ids=_normalize_list(claims.get("contractor_ids") or claims.get("contractor_id")),
    )


def apply_abac_filters(query: Select[Any], actor: ActorContext, model: type[Any]) -> Select[Any]:
    if hasattr(model, "company_id") and actor.company_ids:
        query = query.where(model.company_id.in_(actor.company_ids))
    if hasattr(model, "site_id") and actor.site_ids:
        query = query.where(model.site_id.in_(actor.site_ids))
    if hasattr(model, "project_id") and actor.project_ids:
        query = query.where(model.project_id.in_(actor.project_ids))
    if hasattr(model, "contractor_id") and actor.contractor_ids:
        query = query.where(model.contractor_id.in_(actor.contractor_ids))
    return query
