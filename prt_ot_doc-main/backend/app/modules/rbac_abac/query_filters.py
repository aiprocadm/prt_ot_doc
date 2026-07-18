from __future__ import annotations

from sqlalchemy import false
from sqlalchemy.sql import Select

from app.core.rbac_abac import ActorContext, scoped_query

from .types import Subject


def apply_abac_filters(query: Select, subject: Subject, model: type) -> Select:
    scoped_model = any(hasattr(model, field) for field in ("company_id", "site_id", "project_id", "contractor_id")) or model.__tablename__ in {"company", "site", "project", "contractor"}
    if scoped_model and not any((subject.company_ids, subject.site_ids, subject.project_ids, subject.contractor_ids)):
        return query.where(false())

    actor = ActorContext(
        user_id=subject.user_id,
        tenant_id=subject.tenant_id,
        roles=subject.roles,
        company_ids=subject.company_ids,
        site_ids=subject.site_ids,
        project_ids=subject.project_ids,
        contractor_ids=subject.contractor_ids,
    )
    return scoped_query(query, model=model, actor=actor, resource=model.__tablename__)
