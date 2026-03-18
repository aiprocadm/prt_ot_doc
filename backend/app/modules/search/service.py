from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import String, and_, cast, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projections.models import SearchIndexEntry
from app.modules.search.models import SearchRecentQuery, SearchSavedQuery


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

    @staticmethod
    def _build_snippet(*, q: str, title: str | None, subtitle: str | None, preview_payload: dict[str, Any] | None) -> str | None:
        haystack = " | ".join(part for part in [title or "", subtitle or "", str(preview_payload or "")] if part).strip()
        if not haystack:
            return None
        if not q.strip():
            return haystack[:180]
        lower = haystack.lower()
        q_lower = q.strip().lower()
        pos = lower.find(q_lower)
        if pos < 0:
            return haystack[:180]
        start = max(pos - 40, 0)
        end = min(pos + len(q_lower) + 80, len(haystack))
        return haystack[start:end].strip()

    async def track_recent_query(self, *, user_id: str, q: str, entity_types: set[str], filters: SearchFilters) -> None:
        query = q.strip()
        if not query:
            return
        row = (await self.session.execute(select(SearchRecentQuery).where(and_(SearchRecentQuery.tenant_id == self.tenant_id, SearchRecentQuery.user_id == user_id, SearchRecentQuery.query_text == query, SearchRecentQuery.deleted_at.is_(None))))).scalar_one_or_none()
        if row is None:
            row = SearchRecentQuery(tenant_id=self.tenant_id, user_id=user_id, query_text=query, entity_types=sorted(entity_types), hit_count=1, last_used_at=datetime.now(tz=timezone.utc))
            self.session.add(row)
        else:
            row.entity_types = sorted(entity_types)
            row.hit_count += 1
            row.last_used_at = datetime.now(tz=timezone.utc)
        await self.session.flush()

    async def list_recent_queries(self, *, user_id: str, limit: int = 8) -> list[dict[str, Any]]:
        rows = (await self.session.execute(select(SearchRecentQuery).where(SearchRecentQuery.tenant_id == self.tenant_id, SearchRecentQuery.user_id == user_id, SearchRecentQuery.deleted_at.is_(None)).order_by(SearchRecentQuery.last_used_at.desc().nullslast(), SearchRecentQuery.updated_at.desc()).limit(limit))).scalars().all()
        return [{"id": row.id, "q": row.query_text, "types": row.entity_types or [], "hit_count": row.hit_count, "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None} for row in rows]

    async def list_saved_queries(self, *, user_id: str) -> list[dict[str, Any]]:
        rows = (await self.session.execute(select(SearchSavedQuery).where(SearchSavedQuery.tenant_id == self.tenant_id, or_(SearchSavedQuery.user_id == user_id, SearchSavedQuery.is_shared.is_(True)), SearchSavedQuery.deleted_at.is_(None)).order_by(SearchSavedQuery.created_at.desc()))).scalars().all()
        return [{"id": row.id, "name": row.name, "q": row.query_text, "types": row.entity_types or [], "filters": row.filters_json or {}, "is_shared": row.is_shared} for row in rows]

    async def save_query(self, *, user_id: str, name: str, q: str, entity_types: set[str], filters: dict[str, Any], is_shared: bool = False) -> SearchSavedQuery:
        item = SearchSavedQuery(tenant_id=self.tenant_id, user_id=user_id, name=name, query_text=q.strip(), entity_types=sorted(entity_types), filters_json=filters, is_shared=is_shared)
        self.session.add(item)
        await self.session.flush()
        return item

    async def delete_saved_query(self, *, user_id: str, saved_query_id: str) -> bool:
        item = await self.session.get(SearchSavedQuery, saved_query_id)
        if item is None or item.tenant_id != self.tenant_id or item.user_id != user_id:
            return False
        await self.session.delete(item)
        await self.session.flush()
        return True

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
        type_counts: dict[str, int] = {}
        for row in items:
            type_counts[row.entity_type] = type_counts.get(row.entity_type, 0) + 1
        return {
            "q": q,
            "total": len(items),
            "facets": {"type_counts": type_counts},
            "items": [
                {
                    "kind": "entity",
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "title": row.title,
                    "subtitle": row.subtitle,
                    "status": row.status,
                    "route": row.route,
                    "deeplink": row.route or self._build_entity_url(row.entity_type, row.entity_id),
                    "preview_payload": row.preview_payload,
                    "snippet": self._build_snippet(q=q, title=row.title, subtitle=row.subtitle, preview_payload=row.preview_payload),
                    "tags": row.tags_json or {},
                }
                for row in items
            ],
            "next_cursor": str(offset + limit) if has_more else None,
        }
