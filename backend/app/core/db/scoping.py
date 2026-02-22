"""Shared query scoping utilities for tenant + ABAC constraints."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_
from sqlalchemy.sql import Select


def scope_query(
    query: Select[Any],
    *,
    model: type[Any],
    tenant_id: str,
    allowed_company_ids: tuple[str, ...] = (),
    allowed_site_ids: tuple[str, ...] = (),
    allowed_project_ids: tuple[str, ...] = (),
    allowed_contractor_ids: tuple[str, ...] = (),
) -> Select[Any]:
    """Apply mandatory tenant filter and optional ABAC scope filters."""

    if not hasattr(model, "tenant_id"):
        raise ValueError(f"Model {model.__name__} does not expose tenant_id for scoping")

    filters = [model.tenant_id == str(tenant_id)]
    if hasattr(model, "company_id") and allowed_company_ids:
        filters.append(model.company_id.in_(allowed_company_ids))
    if hasattr(model, "site_id") and allowed_site_ids:
        filters.append(model.site_id.in_(allowed_site_ids))
    if hasattr(model, "project_id") and allowed_project_ids:
        filters.append(model.project_id.in_(allowed_project_ids))
    if hasattr(model, "contractor_id") and allowed_contractor_ids:
        filters.append(model.contractor_id.in_(allowed_contractor_ids))

    return query.where(and_(*filters))
