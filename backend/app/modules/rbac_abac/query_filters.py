from __future__ import annotations

from sqlalchemy.sql import Select

from app.core.rbac_abac import ActorContext, scoped_query

from .types import Subject


def apply_abac_filters(query: Select, subject: Subject, model: type) -> Select:
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
