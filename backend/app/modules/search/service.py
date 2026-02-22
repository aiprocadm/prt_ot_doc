from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, String, and_, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.models import Incident, Inspection, Person, Site
from app.modules.files.models import FileObject, FileTextIndex, FileVersion


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
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def search(
        self,
        *,
        q: str,
        types: set[str],
        filters: SearchFilters,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        offset = int(cursor or "0") if (cursor or "0").isdigit() else 0
        queries: list[Any] = []
        normalized_q = q.strip()
        if not normalized_q:
            return {"q": q, "facets": {}, "items": [], "next_cursor": None}

        like_q = f"%{normalized_q}%"

        if "documents" in types:
            queries.append(self._documents_query(like_q, filters))
        if "people" in types:
            queries.append(self._people_query(like_q, filters))
        if "sites" in types:
            queries.append(self._sites_query(like_q, filters))
        if "incidents" in types:
            queries.append(self._incidents_query(like_q, filters))
        if "inspections" in types:
            queries.append(self._inspections_query(like_q, filters))
        if "files" in types:
            queries.append(self._files_query(like_q))

        if not queries:
            return {"q": q, "facets": {}, "items": [], "next_cursor": None}

        union_subq = queries[0]
        for query in queries[1:]:
            union_subq = union_subq.union_all(query)

        search_subq = union_subq.subquery("search_union")
        ranked = (
            select(
                search_subq.c.kind,
                search_subq.c.entity_type,
                search_subq.c.id,
                search_subq.c.title,
                search_subq.c.status,
                search_subq.c.updated_at,
                search_subq.c.snippet,
                search_subq.c.score,
            )
            .order_by(search_subq.c.score.desc(), search_subq.c.updated_at.desc().nullslast())
            .offset(offset)
            .limit(limit + 1)
        )
        rows = (await self.session.execute(ranked)).mappings().all()

        facets_stmt = select(search_subq.c.entity_type, func.count()).group_by(search_subq.c.entity_type)
        facet_rows = (await self.session.execute(facets_stmt)).all()
        facets = {row[0]: row[1] for row in facet_rows}

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = str(offset + limit) if has_more else None

        return {
            "q": q,
            "facets": facets,
            "items": [
                {
                    "kind": row["kind"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["id"],
                    "file_id": row["id"] if row["entity_type"] == "File" else None,
                    "title": row["title"],
                    "subtitle": row["entity_type"],
                    "tags": {"status": row["status"]} if row["status"] else {},
                    "status": row["status"],
                    "updated_at": row["updated_at"],
                    "snippet": row["snippet"],
                    "score": float(row["score"] or 0),
                }
                for row in items
            ],
            "next_cursor": next_cursor,
        }

    def _documents_query(self, like_q: str, filters: SearchFilters):
        title = func.coalesce(Document.title, literal(""))
        file_name = func.coalesce(FileVersion.filename, literal(""))
        status_text = cast(Document.status, String)
        raw_text = func.coalesce(FileTextIndex.raw_text, literal(""))
        combined = func.concat_ws(" ", title, file_name, status_text, raw_text)

        score = case((combined.ilike(like_q), literal(1.0)), else_=literal(0.0))
        stmt = (
            select(
                literal("documents").label("type"),
                literal("entity").label("kind"),
                literal("Document").label("entity_type"),
                Document.id.label("id"),
                func.coalesce(Document.title, FileVersion.filename, literal("Документ")).label("title"),
                status_text.label("status"),
                Document.updated_at.label("updated_at"),
                func.substr(raw_text, 1, 220).label("snippet"),
                score.label("score"),
            )
            .select_from(Document)
            .outerjoin(FileObject, and_(FileObject.owner_entity_id == Document.id, FileObject.owner_entity_type == literal("document")))
            .outerjoin(FileVersion, and_(FileVersion.file_id == FileObject.id, FileVersion.status == "ready"))
            .outerjoin(FileTextIndex, FileTextIndex.file_version_id == FileVersion.id)
            .where(Document.tenant_id == self.tenant_id, combined.ilike(like_q), Document.deleted_at.is_(None))
        )
        if filters.status:
            stmt = stmt.where(cast(Document.status, String) == filters.status)
        if filters.company_id:
            stmt = stmt.where(Document.company_id == filters.company_id)
        if filters.site_id:
            stmt = stmt.where(Document.site_id == filters.site_id)
        if filters.date_from:
            stmt = stmt.where(cast(Document.updated_at, Date) >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(cast(Document.updated_at, Date) <= filters.date_to)
        return stmt

    def _people_query(self, like_q: str, filters: SearchFilters):
        full_name = func.concat_ws(" ", Person.last_name, Person.first_name, Person.middle_name)
        text = func.concat_ws(" ", full_name, Person.personnel_number, Person.employment_status)
        stmt = select(
            literal("people").label("type"),
            literal("entity").label("kind"),
            literal("Person").label("entity_type"),
            Person.id.label("id"),
            full_name.label("title"),
            cast(Person.employment_status, String).label("status"),
            Person.updated_at.label("updated_at"),
            literal(None).label("snippet"),
            case((text.ilike(like_q), literal(0.8)), else_=literal(0.0)).label("score"),
        ).where(Person.tenant_id == self.tenant_id, text.ilike(like_q), Person.deleted_at.is_(None))
        if filters.company_id:
            stmt = stmt.where(Person.company_id == filters.company_id)
        return stmt

    def _sites_query(self, like_q: str, filters: SearchFilters):
        text = func.concat_ws(" ", Site.name, Site.address, Site.opo_register_number)
        stmt = select(
            literal("sites").label("type"),
            literal("entity").label("kind"),
            literal("Site").label("entity_type"),
            Site.id.label("id"),
            Site.name.label("title"),
            literal(None).label("status"),
            Site.updated_at.label("updated_at"),
            Site.address.label("snippet"),
            case((text.ilike(like_q), literal(0.7)), else_=literal(0.0)).label("score"),
        ).where(Site.tenant_id == self.tenant_id, text.ilike(like_q), Site.deleted_at.is_(None))
        if filters.company_id:
            stmt = stmt.where(Site.company_id == filters.company_id)
        return stmt

    def _incidents_query(self, like_q: str, filters: SearchFilters):
        text = func.concat_ws(" ", Incident.title, Incident.description, Incident.location_description)
        stmt = select(
            literal("incidents").label("type"),
            literal("entity").label("kind"),
            literal("Incident").label("entity_type"),
            Incident.id.label("id"),
            Incident.title.label("title"),
            cast(Incident.status, String).label("status"),
            Incident.updated_at.label("updated_at"),
            func.coalesce(Incident.description, Incident.location_description).label("snippet"),
            case((text.ilike(like_q), literal(0.75)), else_=literal(0.0)).label("score"),
        ).where(Incident.tenant_id == self.tenant_id, text.ilike(like_q), Incident.deleted_at.is_(None))
        if filters.company_id:
            stmt = stmt.where(Incident.company_id == filters.company_id)
        if filters.site_id:
            stmt = stmt.where(Incident.site_id == filters.site_id)
        if filters.status:
            stmt = stmt.where(cast(Incident.status, String) == filters.status)
        if filters.date_from:
            stmt = stmt.where(cast(Incident.occurred_at, Date) >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(cast(Incident.occurred_at, Date) <= filters.date_to)
        return stmt

    def _inspections_query(self, like_q: str, filters: SearchFilters):
        text = func.concat_ws(" ", Inspection.authority, Inspection.purpose, Inspection.result_summary)
        stmt = select(
            literal("inspections").label("type"),
            literal("entity").label("kind"),
            literal("Inspection").label("entity_type"),
            Inspection.id.label("id"),
            Inspection.authority.label("title"),
            cast(Inspection.status, String).label("status"),
            Inspection.updated_at.label("updated_at"),
            func.coalesce(Inspection.purpose, Inspection.result_summary).label("snippet"),
            case((text.ilike(like_q), literal(0.72)), else_=literal(0.0)).label("score"),
        ).where(Inspection.tenant_id == self.tenant_id, text.ilike(like_q))
        if filters.company_id:
            stmt = stmt.where(Inspection.company_id == filters.company_id)
        if filters.site_id:
            stmt = stmt.where(Inspection.site_id == filters.site_id)
        if filters.status:
            stmt = stmt.where(cast(Inspection.status, String) == filters.status)
        if filters.date_from:
            stmt = stmt.where(cast(Inspection.scheduled_at, Date) >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(cast(Inspection.scheduled_at, Date) <= filters.date_to)
        return stmt

    def _files_query(self, like_q: str):
        text = func.concat_ws(" ", FileVersion.filename, FileTextIndex.raw_text)
        return (
            select(
                literal("files").label("type"),
                literal("file").label("kind"),
                literal("File").label("entity_type"),
                FileVersion.file_id.label("id"),
                FileVersion.filename.label("title"),
                FileVersion.status.label("status"),
                FileVersion.updated_at.label("updated_at"),
                func.substr(func.coalesce(FileTextIndex.raw_text, literal("")), 1, 220).label("snippet"),
                case((text.ilike(like_q), literal(0.65)), else_=literal(0.0)).label("score"),
            )
            .select_from(FileVersion)
            .outerjoin(FileTextIndex, FileTextIndex.file_version_id == FileVersion.id)
            .where(FileVersion.tenant_id == self.tenant_id, text.ilike(like_q), FileVersion.status == "ready")
        )
