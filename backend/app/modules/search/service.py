from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import String, and_, asc, case, cast, desc, func, or_, select
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
    _TYPE_ALIASES: dict[str, set[str]] = {
        "documents": {"document"},
        "document": {"document"},
        "people": {"person"},
        "person": {"person"},
        "employee": {"person"},
        "employees": {"person"},
        "sites": {"site"},
        "site": {"site"},
        "incidents": {"incident"},
        "incident": {"incident"},
        "inspections": {"inspection"},
        "inspection": {"inspection"},
        "prescriptions": {"prescription"},
        "prescription": {"prescription"},
        "npa": {"npa"},
        "risk": {"risk", "risk_map"},
        "risks": {"risk", "risk_map"},
        "ppe": {"ppe_issue"},
        "tasks": {"task", "workflow_task"},
        "task": {"task"},
        "workflow_tasks": {"workflow_task"},
        "workflow_task": {"workflow_task"},
        "jobs": {"task", "workflow_task", "prescription"},
        "contracts": {"contract"},
        "contract": {"contract"},
        "orders": {"order"},
        "order": {"order"},
        "packages": {"package"},
        "package": {"package"},
        "files": {"file"},
        "file": {"file"},
        "templates": {"template"},
        "template": {"template"},
        "training": {"training_enrollment"},
    }
    _ENTITY_ROUTE_PREFIXES: dict[str, str] = {
        "documents": "documents",
        "document": "documents",
        "risk": "risk",
        "jobs": "jobs",
        "templates": "templates",
        "person": "persons",
        "site": "sites",
        "company": "companies",
        "incident": "incidents",
        "inspection": "inspections",
        "prescription": "prescriptions",
        "task": "tasks",
        "workflow_task": "workflow",
        "npa": "npa",
        "contract": "contracts",
        "order": "orders",
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
        criteria: list = [SearchIndexEntry.tenant_id == self.tenant_id]
        query = q.strip()
        if query:
            like = f"%{query}%"
            criteria.append(
                or_(
                    SearchIndexEntry.title.ilike(like),
                    SearchIndexEntry.subtitle.ilike(like),
                    cast(SearchIndexEntry.search_text, String).ilike(like),
                )
            )
        resolved_types = self._resolve_entity_types(types)
        if resolved_types:
            criteria.append(SearchIndexEntry.entity_type.in_(resolved_types))
        if filters.status:
            criteria.append(SearchIndexEntry.status == filters.status)
        if filters.site_id:
            criteria.append(SearchIndexEntry.tags_json["site_id"].astext == filters.site_id)
        if filters.company_id:
            criteria.append(SearchIndexEntry.tags_json["company_id"].astext == filters.company_id)
        if filters.contractor_id:
            criteria.append(SearchIndexEntry.tags_json["contractor_id"].astext == filters.contractor_id)
        if filters.project_id:
            criteria.append(SearchIndexEntry.tags_json["project_id"].astext == filters.project_id)
        if filters.risk_level:
            criteria.append(SearchIndexEntry.tags_json["risk_level"].astext == filters.risk_level)
        if filters.date_from:
            criteria.append(func.date(SearchIndexEntry.updated_at) >= filters.date_from)
        if filters.date_to:
            criteria.append(func.date(SearchIndexEntry.updated_at) <= filters.date_to)

        filter_expr = and_(*criteria)
        stmt = select(SearchIndexEntry).where(filter_expr)

        if sort == "updated_at":
            order_by = desc(SearchIndexEntry.updated_at)
        elif sort == "date":
            order_by = asc(SearchIndexEntry.updated_at)
        else:
            if query:
                lower_title = func.lower(func.coalesce(SearchIndexEntry.title, ""))
                lower_subtitle = func.lower(func.coalesce(SearchIndexEntry.subtitle, ""))
                lower_text = func.lower(cast(SearchIndexEntry.search_text, String))
                q_lower = query.lower()
                order_by = [
                    case((lower_title == q_lower, 0), (lower_title.like(f"{q_lower}%"), 1), else_=2),
                    case((lower_subtitle.like(f"{q_lower}%"), 0), else_=1),
                    func.instr(lower_text, q_lower),
                    desc(SearchIndexEntry.updated_at),
                ]
            else:
                order_by = desc(SearchIndexEntry.updated_at)
        facet_stmt = (
            select(SearchIndexEntry.entity_type, func.count())
            .where(filter_expr)
            .group_by(SearchIndexEntry.entity_type)
        )
        facet_rows = (await self.session.execute(facet_stmt)).all()
        status_rows = (
            await self.session.execute(
                select(SearchIndexEntry.status, func.count()).where(filter_expr).group_by(SearchIndexEntry.status)
            )
        ).all()
        company_rows = (
            await self.session.execute(
                select(SearchIndexEntry.tags_json["company_id"].astext, func.count())
                .where(filter_expr, SearchIndexEntry.tags_json["company_id"].astext.is_not(None))
                .group_by(SearchIndexEntry.tags_json["company_id"].astext)
            )
        ).all()
        site_rows = (
            await self.session.execute(
                select(SearchIndexEntry.tags_json["site_id"].astext, func.count())
                .where(filter_expr, SearchIndexEntry.tags_json["site_id"].astext.is_not(None))
                .group_by(SearchIndexEntry.tags_json["site_id"].astext)
            )
        ).all()
        project_rows = (
            await self.session.execute(
                select(SearchIndexEntry.tags_json["project_id"].astext, func.count())
                .where(filter_expr, SearchIndexEntry.tags_json["project_id"].astext.is_not(None))
                .group_by(SearchIndexEntry.tags_json["project_id"].astext)
            )
        ).all()
        risk_rows = (
            await self.session.execute(
                select(SearchIndexEntry.tags_json["risk_level"].astext, func.count())
                .where(filter_expr, SearchIndexEntry.tags_json["risk_level"].astext.is_not(None))
                .group_by(SearchIndexEntry.tags_json["risk_level"].astext)
            )
        ).all()
        total = int(await self.session.scalar(select(func.count()).select_from(SearchIndexEntry).where(filter_expr)) or 0)
        rows = (await self.session.execute(stmt.order_by(*order_by).offset(offset).limit(limit + 1))) if isinstance(order_by, list) else (await self.session.execute(stmt.order_by(order_by).offset(offset).limit(limit + 1)))
        rows = rows.scalars().all()
        has_more = len(rows) > limit
        items = rows[:limit]
        type_counts: dict[str, int] = {str(entity_type): int(total) for entity_type, total in facet_rows}
        status_counts: dict[str, int] = {str(status or "unknown"): int(total) for status, total in status_rows}
        company_counts: dict[str, int] = {str(company_id): int(total) for company_id, total in company_rows if company_id}
        site_counts: dict[str, int] = {str(site_id): int(total) for site_id, total in site_rows if site_id}
        project_counts: dict[str, int] = {str(project_id): int(total) for project_id, total in project_rows if project_id}
        risk_counts: dict[str, int] = {str(risk_level): int(total) for risk_level, total in risk_rows if risk_level}
        return {
            "q": q,
            "total": total,
            "facets": {"type_counts": type_counts, "status_counts": status_counts, "company_counts": company_counts, "site_counts": site_counts, "project_counts": project_counts, "risk_level_counts": risk_counts},
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

    @classmethod
    def _resolve_entity_types(cls, types: set[str]) -> set[str]:
        resolved: set[str] = set()
        for item in types:
            resolved.update(cls._TYPE_ALIASES.get(item, {item}))
        return resolved
