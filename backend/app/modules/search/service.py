from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, String, and_, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.models import Incident, Inspection, PPEItem, Person, Site, Training
from app.models.risk import Risk
from app.modules.files.models import FileContentIndex, FileObject, FileTextIndex, FileVersion


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
        like_q = f"%{normalized_q}%" if normalized_q else None

        if "documents" in types:
            queries.append(self._documents_query(like_q, filters, normalized_q))
        if "people" in types:
            queries.append(self._people_query(like_q, filters, normalized_q))
        if "sites" in types:
            queries.append(self._sites_query(like_q, filters, normalized_q))
        if "incidents" in types:
            queries.append(self._incidents_query(like_q, filters, normalized_q))
        if "inspections" in types:
            queries.append(self._inspections_query(like_q, filters, normalized_q))
        if "files" in types:
            queries.append(self._files_query(like_q, normalized_q))
        if "risk" in types:
            queries.append(self._risk_query(like_q, filters))
        if "ppe" in types:
            queries.append(self._ppe_query(like_q, filters))
        if "training" in types:
            queries.append(self._training_query(like_q, filters))

        if not queries:
            return {"q": q, "facets": {}, "items": [], "next_cursor": None}

        union_subq = queries[0]
        for query in queries[1:]:
            union_subq = union_subq.union_all(query)

        search_subq = union_subq.subquery("search_union")
        ranked = (
            select(
                search_subq.c.type,
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
            "total": sum(facets.values()),
            "facets": facets,
            "items": [
                {
                    "type": row["type"],
                    "id": row["id"],
                    "url": self._build_entity_url(row["type"], row["id"]),
                    "kind": row["kind"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["id"],
                    "permissions_scope": "tenant",
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

    @staticmethod
    def _build_entity_url(entity_type: str, entity_id: str) -> str:
        mapping = {
            "documents": f"/documents/{entity_id}",
            "people": f"/persons/{entity_id}",
            "sites": f"/sites/{entity_id}",
            "incidents": f"/incidents/{entity_id}",
            "inspections": f"/inspections/{entity_id}",
            "files": f"/files/{entity_id}",
            "risk": f"/risk/{entity_id}",
            "ppe": f"/ppe/{entity_id}",
            "training": f"/training/{entity_id}",
        }
        return mapping.get(entity_type, f"/{entity_type}/{entity_id}")

    def _documents_query(self, like_q: str | None, filters: SearchFilters, normalized_q: str):
        title = func.coalesce(Document.title, literal(""))
        file_name = func.coalesce(FileVersion.filename, literal(""))
        status_text = cast(Document.status, String)
        raw_text = func.coalesce(FileContentIndex.raw_text, literal(""))
        combined = func.concat_ws(" ", title, file_name, status_text, raw_text)

        fts_query = func.websearch_to_tsquery("russian", normalized_q) if normalized_q else None
        is_postgres = (self.session.bind is not None) and self.session.bind.dialect.name == "postgresql"
        score = (
            func.ts_rank_cd(FileContentIndex.content_text, fts_query)
            if is_postgres and fts_query is not None
            else case((combined.ilike(like_q) if like_q else literal(True), literal(1.0)), else_=literal(0.0))
        )
        snippet = (
            func.ts_headline("russian", func.coalesce(FileContentIndex.raw_text, literal("")), fts_query)
            if is_postgres and fts_query is not None
            else func.substr(raw_text, 1, 220)
        )
        stmt = (
            select(
                literal("documents").label("type"),
                literal("entity").label("kind"),
                literal("Document").label("entity_type"),
                Document.id.label("id"),
                func.coalesce(Document.title, FileVersion.filename, literal("Документ")).label("title"),
                status_text.label("status"),
                Document.updated_at.label("updated_at"),
                snippet.label("snippet"),
                score.label("score"),
            )
            .select_from(Document)
            .outerjoin(FileObject, and_(FileObject.owner_entity_id == Document.id, FileObject.owner_entity_type == literal("document")))
            .outerjoin(FileVersion, and_(FileVersion.file_id == FileObject.id, FileVersion.status == "ready"))
            .outerjoin(FileContentIndex, FileContentIndex.file_id == FileVersion.file_id)
            .where(Document.tenant_id == self.tenant_id, Document.deleted_at.is_(None))
        )
        if like_q:
            if is_postgres and fts_query is not None:
                stmt = stmt.where(FileContentIndex.content_text.op("@@")(fts_query))
            else:
                stmt = stmt.where(combined.ilike(like_q))
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

    def _people_query(self, like_q: str | None, filters: SearchFilters, normalized_q: str):
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
            (case((text.ilike(like_q), literal(0.8)), else_=literal(0.0)) if like_q else literal(0.3)).label("score"),
        ).where(Person.tenant_id == self.tenant_id, Person.deleted_at.is_(None))
        if like_q:
            stmt = stmt.where(text.ilike(like_q))
        if filters.company_id:
            stmt = stmt.where(Person.company_id == filters.company_id)
        return stmt

    def _sites_query(self, like_q: str | None, filters: SearchFilters, normalized_q: str):
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
            (case((text.ilike(like_q), literal(0.7)), else_=literal(0.0)) if like_q else literal(0.3)).label("score"),
        ).where(Site.tenant_id == self.tenant_id, Site.deleted_at.is_(None))
        if like_q:
            stmt = stmt.where(text.ilike(like_q))
        if filters.company_id:
            stmt = stmt.where(Site.company_id == filters.company_id)
        return stmt

    def _incidents_query(self, like_q: str | None, filters: SearchFilters, normalized_q: str):
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
            (case((text.ilike(like_q), literal(0.75)), else_=literal(0.0)) if like_q else literal(0.3)).label("score"),
        ).where(Incident.tenant_id == self.tenant_id, Incident.deleted_at.is_(None))
        if like_q:
            stmt = stmt.where(text.ilike(like_q))
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

    def _inspections_query(self, like_q: str | None, filters: SearchFilters, normalized_q: str):
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
            (case((text.ilike(like_q), literal(0.72)), else_=literal(0.0)) if like_q else literal(0.3)).label("score"),
        ).where(Inspection.tenant_id == self.tenant_id)
        if like_q:
            stmt = stmt.where(text.ilike(like_q))
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

    def _files_query(self, like_q: str | None, normalized_q: str):
        text = func.concat_ws(" ", FileVersion.filename, FileTextIndex.raw_text)
        stmt = (
            select(
                literal("files").label("type"),
                literal("file").label("kind"),
                literal("File").label("entity_type"),
                FileVersion.file_id.label("id"),
                FileVersion.filename.label("title"),
                FileVersion.status.label("status"),
                FileVersion.updated_at.label("updated_at"),
                func.substr(func.coalesce(FileTextIndex.raw_text, literal("")), 1, 220).label("snippet"),
                (case((text.ilike(like_q), literal(0.65)), else_=literal(0.0)) if like_q else literal(0.3)).label("score"),
            )
            .select_from(FileVersion)
            .outerjoin(FileTextIndex, FileTextIndex.file_version_id == FileVersion.id)
            .where(FileVersion.tenant_id == self.tenant_id, FileVersion.status == "ready")
        )
        if like_q:
            stmt = stmt.where(text.ilike(like_q))
        return stmt

    def _risk_query(self, like_q: str | None, filters: SearchFilters):
        text = func.concat_ws(" ", Risk.hazard, Risk.controls)
        stmt = select(
            literal("risk").label("type"),
            literal("entity").label("kind"),
            literal("Risk").label("entity_type"),
            Risk.id.label("id"),
            Risk.hazard.label("title"),
            cast(Risk.level, String).label("status"),
            Risk.updated_at.label("updated_at"),
            Risk.controls.label("snippet"),
            (case((text.ilike(like_q), literal(0.7)), else_=literal(0.0)) if like_q else literal(0.3)).label("score"),
        ).where(Risk.tenant_id == self.tenant_id)
        if like_q:
            stmt = stmt.where(text.ilike(like_q))
        if filters.site_id:
            stmt = stmt.where(Risk.site_id == filters.site_id)
        if filters.company_id:
            stmt = stmt.where(Risk.company_id == filters.company_id)
        if filters.risk_level:
            stmt = stmt.where(cast(Risk.level, String) == filters.risk_level)
        return stmt

    def _ppe_query(self, like_q: str | None, filters: SearchFilters):
        text = func.concat_ws(" ", PPEItem.name, PPEItem.code, PPEItem.description)
        stmt = select(
            literal("ppe").label("type"),
            literal("entity").label("kind"),
            literal("PPEItem").label("entity_type"),
            PPEItem.id.label("id"),
            PPEItem.name.label("title"),
            cast(PPEItem.category, String).label("status"),
            PPEItem.updated_at.label("updated_at"),
            PPEItem.description.label("snippet"),
            (case((text.ilike(like_q), literal(0.7)), else_=literal(0.0)) if like_q else literal(0.3)).label("score"),
        ).where(PPEItem.tenant_id == self.tenant_id, PPEItem.deleted_at.is_(None))
        if like_q:
            stmt = stmt.where(text.ilike(like_q))
        return stmt

    def _training_query(self, like_q: str | None, filters: SearchFilters):
        text = Training.course_name
        stmt = select(
            literal("training").label("type"),
            literal("entity").label("kind"),
            literal("Training").label("entity_type"),
            Training.id.label("id"),
            Training.course_name.label("title"),
            cast(Training.status, String).label("status"),
            Training.updated_at.label("updated_at"),
            literal(None).label("snippet"),
            (case((text.ilike(like_q), literal(0.65)), else_=literal(0.0)) if like_q else literal(0.3)).label("score"),
        ).where(Training.tenant_id == self.tenant_id)
        if like_q:
            stmt = stmt.where(text.ilike(like_q))
        if filters.status:
            stmt = stmt.where(cast(Training.status, String) == filters.status)
        return stmt
