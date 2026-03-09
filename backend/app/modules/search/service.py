from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import String, cast, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projections.models import SearchIndexEntry


@dataclass(slots=True)
class SearchFilters:
    status: str | None = None
    company_id: str | None = None
    site_id: str | None = None
    project_id: str | None = None
    contractor_id: str | None = None
    risk_level: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class SearchService:
    _ENTITY_ROUTE_PREFIXES: dict[str, str] = {
        "documents": "documents",
        "document": "documents",
        "risk": "risk",
        "jobs": "jobs",
        "templates": "templates",
    }

    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    @classmethod
    def _build_entity_url(cls, entity_type: str, entity_id: str) -> str:
        prefix = cls._ENTITY_ROUTE_PREFIXES.get(entity_type, entity_type)
        return f"/{prefix}/{entity_id}"

    async def search(
        self,
        *,
        q: str,
        types: set[str],
        filters: SearchFilters,
        sort: str,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        offset = int(cursor or "0") if (cursor or "0").isdigit() else 0
        stmt = select(SearchIndexEntry).where(SearchIndexEntry.tenant_id == self.tenant_id)
        if q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    SearchIndexEntry.title.ilike(like),
                    SearchIndexEntry.subtitle.ilike(like),
                    cast(SearchIndexEntry.search_text, String).ilike(like),
                )
            )
        if types:
            stmt = stmt.where(SearchIndexEntry.entity_type.in_(types))
        if filters.status:
            stmt = stmt.where(SearchIndexEntry.status == filters.status)
        if filters.site_id:
            stmt = stmt.where(SearchIndexEntry.tags_json["site_id"].astext == filters.site_id)
        if filters.company_id:
            stmt = stmt.where(SearchIndexEntry.tags_json["company_id"].astext == filters.company_id)
        if filters.contractor_id:
            stmt = stmt.where(SearchIndexEntry.tags_json["contractor_id"].astext == filters.contractor_id)

        order_by = desc(SearchIndexEntry.updated_at) if sort in {"updated_at", "date", "relevance"} else desc(SearchIndexEntry.updated_at)
        rows = (await self.session.execute(stmt.order_by(order_by).offset(offset).limit(limit + 1))).scalars().all()
        has_more = len(rows) > limit
        items = rows[:limit]
        return {
            "q": q,
            "total": len(items),
            "items": [
                {
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "title": row.title,
                    "subtitle": row.subtitle,
                    "status": row.status,
                    "route": row.route,
                    "preview_payload": row.preview_payload,
                    "tags": row.tags_json or {},
                }
                for row in items
            ],
            "next_cursor": str(offset + limit) if has_more else None,
        }
