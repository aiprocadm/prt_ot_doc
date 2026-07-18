"""Backend test coverage for `SearchService.search()`.

Phase 4 Task 4.2 acceptance #6 (tests for search index accuracy / command parsing).
Frontend command parsing is covered in `frontend/src/__tests__/CommandBar.test.tsx`;
this file fills the backend coverage gap called out as Next Step #1 in Session 32
handoff. Exercises four areas of the service:

- `_resolve_entity_types` — alias expansion for the public-facing `types` query param.
- `search()` relevance ordering when `sort="relevance"` (exact > prefix > substring,
  updated_at tie-breaker, subtitle prefix boost).
- `search()` filter combinations (status, tags-json filters, date range, AND-composition).
- `search()` cross-cutting behaviors: tenant isolation, facets, pagination cursor,
  alternative sort modes, snippet rendering, deeplink fallback.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.modules.projections.models import SearchIndexEntry
from app.modules.search.service import SearchFilters, SearchService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _aware(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


async def _seed(
    session,
    tenant_id: str,
    rows: list[dict],
) -> list[SearchIndexEntry]:
    """Insert `SearchIndexEntry` rows; each dict may override any column."""

    entries: list[SearchIndexEntry] = []
    for idx, row in enumerate(rows):
        entry = SearchIndexEntry(
            tenant_id=tenant_id,
            entity_type=row.get("entity_type", "person"),
            entity_id=row.get("entity_id", f"e-{idx}"),
            title=row.get("title", f"Title {idx}"),
            subtitle=row.get("subtitle"),
            status=row.get("status"),
            tags_json=row.get("tags_json"),
            route=row.get("route"),
            preview_payload=row.get("preview_payload"),
            search_text=row.get("search_text"),
        )
        if "updated_at" in row:
            entry.updated_at = row["updated_at"]
        if "created_at" in row:
            entry.created_at = row["created_at"]
        session.add(entry)
        entries.append(entry)
    await session.flush()
    return entries


def _titles(payload: dict) -> list[str]:
    return [item["title"] for item in payload["items"]]


def _entity_types(payload: dict) -> list[str]:
    return [item["entity_type"] for item in payload["items"]]


# ---------------------------------------------------------------------------
# A. _resolve_entity_types — alias map
# ---------------------------------------------------------------------------


class TestResolveEntityTypes:
    def test_single_canonical_type_passes_through(self) -> None:
        assert SearchService._resolve_entity_types({"person"}) == {"person"}

    def test_plural_alias_collapses_to_singular_canonical(self) -> None:
        assert SearchService._resolve_entity_types({"people"}) == {"person"}
        assert SearchService._resolve_entity_types({"employees"}) == {"person"}
        assert SearchService._resolve_entity_types({"documents"}) == {"document"}
        assert SearchService._resolve_entity_types({"sites"}) == {"site"}

    def test_risks_alias_expands_to_two_canonical_types(self) -> None:
        assert SearchService._resolve_entity_types({"risks"}) == {"risk", "risk_map"}
        assert SearchService._resolve_entity_types({"risk"}) == {"risk", "risk_map"}

    def test_jobs_alias_expands_to_three_canonical_types(self) -> None:
        assert SearchService._resolve_entity_types({"jobs"}) == {
            "task",
            "workflow_task",
            "prescription",
        }

    def test_ppe_alias_maps_to_ppe_issue(self) -> None:
        assert SearchService._resolve_entity_types({"ppe"}) == {"ppe_issue"}

    def test_unknown_type_passes_through_unchanged(self) -> None:
        # Forward-compat: a new entity type the alias map doesn't know about
        # should still be applied as an exact filter rather than dropped.
        assert SearchService._resolve_entity_types({"frobnication"}) == {"frobnication"}

    def test_empty_input_returns_empty_set(self) -> None:
        assert SearchService._resolve_entity_types(set()) == set()

    def test_multiple_aliases_to_same_canonical_deduplicate(self) -> None:
        assert SearchService._resolve_entity_types(
            {"person", "people", "employee", "employees"}
        ) == {"person"}


# ---------------------------------------------------------------------------
# B. _build_snippet — query-aware text extraction
# ---------------------------------------------------------------------------


class TestBuildSnippet:
    def test_returns_none_when_haystack_is_empty(self) -> None:
        assert (
            SearchService._build_snippet(q="foo", title=None, subtitle=None, preview_payload=None)
            is None
        )

    def test_returns_first_180_chars_when_query_blank(self) -> None:
        long_title = "a" * 300
        snippet = SearchService._build_snippet(
            q="   ", title=long_title, subtitle=None, preview_payload=None
        )
        assert snippet is not None
        assert len(snippet) == 180
        assert snippet == "a" * 180

    def test_returns_haystack_prefix_when_query_not_found(self) -> None:
        snippet = SearchService._build_snippet(
            q="missing", title="Иван Иванов", subtitle="Менеджер", preview_payload=None
        )
        # Falls back to haystack[:180] when needle not present.
        assert snippet is not None
        assert snippet.startswith("Иван Иванов")

    def test_extracts_window_around_match_position(self) -> None:
        haystack_title = "x" * 100 + "TARGET" + "y" * 100
        snippet = SearchService._build_snippet(
            q="TARGET", title=haystack_title, subtitle=None, preview_payload=None
        )
        assert snippet is not None
        assert "TARGET" in snippet
        # Window: [max(pos-40, 0) : min(pos+len(q)+80, len(haystack))]
        # pos = 100, q-len = 6, so window is [60 : 186] → 126 chars
        assert 100 < len(snippet) <= 130


# ---------------------------------------------------------------------------
# C. search() — relevance ordering (sort="relevance" + non-empty query)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestRelevanceOrdering:
    async def test_exact_title_match_outranks_prefix_and_substring(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "p-substr", "title": "Старший инженер Иванов"},
                    {"entity_id": "p-prefix", "title": "Иванов Старший инженер"},
                    {"entity_id": "p-exact", "title": "Иванов"},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="Иванов",
                types=set(),
                filters=SearchFilters(),
                sort="relevance",
                limit=10,
                cursor=None,
            )

        assert payload["total"] == 3
        # case-1: lower_title == q_lower → bucket 0
        # case-2: lower_title.like(q% ) → bucket 1
        # case-3: substring only → bucket 2
        assert _titles(payload) == [
            "Иванов",
            "Иванов Старший инженер",
            "Старший инженер Иванов",
        ]

    async def test_subtitle_prefix_match_breaks_ties_inside_substring_bucket(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="acme")
            await _seed(
                session,
                tenant.id,
                [
                    {
                        "entity_id": "p-sub-mid",
                        "title": "Площадка А",
                        "subtitle": "Завод и Москва участок",
                    },
                    {
                        "entity_id": "p-sub-prefix",
                        "title": "Площадка Б",
                        "subtitle": "Москва участок",
                    },
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="Москва",
                types=set(),
                filters=SearchFilters(),
                sort="relevance",
                limit=10,
                cursor=None,
            )

        # Both share title-bucket 2 (substring only); subtitle-prefix bucket 0 wins.
        assert _titles(payload) == ["Площадка Б", "Площадка А"]

    async def test_updated_at_breaks_tie_when_ranking_signals_equal(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="beta")
            await _seed(
                session,
                tenant.id,
                [
                    {
                        "entity_id": "p-old",
                        "title": "Иванов",
                        "updated_at": _aware(2026, 1, 1),
                    },
                    {
                        "entity_id": "p-new",
                        "title": "Иванов",
                        "updated_at": _aware(2026, 4, 1),
                    },
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="Иванов",
                types=set(),
                filters=SearchFilters(),
                sort="relevance",
                limit=10,
                cursor=None,
            )

        # Both exact-match (bucket 0); newer updated_at wins by ORDER BY desc.
        assert [item["entity_id"] for item in payload["items"]] == ["p-new", "p-old"]

    async def test_empty_query_falls_back_to_updated_at_desc(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="gamma")
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "p-old", "title": "Old", "updated_at": _aware(2026, 1, 1)},
                    {"entity_id": "p-mid", "title": "Mid", "updated_at": _aware(2026, 2, 1)},
                    {"entity_id": "p-new", "title": "New", "updated_at": _aware(2026, 3, 1)},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(),
                sort="relevance",
                limit=10,
                cursor=None,
            )

        assert _titles(payload) == ["New", "Mid", "Old"]


# ---------------------------------------------------------------------------
# D. search() — type filter (via aliases)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestTypeFiltering:
    async def test_employees_alias_returns_person_entries_only(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="delta")
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "p1", "entity_type": "person", "title": "Иванов"},
                    {"entity_id": "d1", "entity_type": "document", "title": "Иванов договор"},
                    {"entity_id": "s1", "entity_type": "site", "title": "Иванов площадка"},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="Иванов",
                types={"employees"},
                filters=SearchFilters(),
                sort="relevance",
                limit=10,
                cursor=None,
            )

        assert payload["total"] == 1
        assert _entity_types(payload) == ["person"]
        assert payload["items"][0]["entity_id"] == "p1"

    async def test_risks_alias_returns_both_risk_and_risk_map(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="zeta")
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "r1", "entity_type": "risk", "title": "Risk A"},
                    {"entity_id": "rm1", "entity_type": "risk_map", "title": "Risk Map A"},
                    {"entity_id": "p1", "entity_type": "person", "title": "Risk Person A"},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="Risk",
                types={"risks"},
                filters=SearchFilters(),
                sort="relevance",
                limit=10,
                cursor=None,
            )

        assert payload["total"] == 2
        assert sorted(_entity_types(payload)) == ["risk", "risk_map"]

    async def test_jobs_alias_returns_task_workflow_task_and_prescription(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="epsilon")
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "t1", "entity_type": "task", "title": "Task A"},
                    {"entity_id": "w1", "entity_type": "workflow_task", "title": "WF Task A"},
                    {"entity_id": "pr1", "entity_type": "prescription", "title": "Prescription A"},
                    {"entity_id": "p1", "entity_type": "person", "title": "Person A"},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="A",
                types={"jobs"},
                filters=SearchFilters(),
                sort="relevance",
                limit=10,
                cursor=None,
            )

        assert payload["total"] == 3
        assert sorted(_entity_types(payload)) == ["prescription", "task", "workflow_task"]

    async def test_empty_types_set_returns_all_entity_types(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "p1", "entity_type": "person", "title": "X1"},
                    {"entity_id": "d1", "entity_type": "document", "title": "X2"},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(),
                sort="relevance",
                limit=10,
                cursor=None,
            )

        # No type filter means both rows from this tenant come back.
        # (Other tenants are isolated via tenant_id.)
        assert payload["total"] >= 2
        assert {"person", "document"}.issubset(set(_entity_types(payload)))


# ---------------------------------------------------------------------------
# E. search() — scalar and tags_json filters
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestFilterCombinations:
    async def test_status_filter_narrows_results(self, sessionmaker, data_factory) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="acme")
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "d-draft", "title": "Doc 1", "status": "draft"},
                    {"entity_id": "d-active", "title": "Doc 2", "status": "active"},
                    {"entity_id": "d-active-2", "title": "Doc 3", "status": "active"},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(status="active"),
                sort="updated_at",
                limit=10,
                cursor=None,
            )

        assert payload["total"] == 2
        assert all(item["status"] == "active" for item in payload["items"])

    async def test_site_id_filter_uses_tags_json_path(self, sessionmaker, data_factory) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="beta")
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "p-a", "title": "Person A", "tags_json": {"site_id": "site-a"}},
                    {"entity_id": "p-b", "title": "Person B", "tags_json": {"site_id": "site-b"}},
                    {"entity_id": "p-none", "title": "Person N", "tags_json": {}},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(site_id="site-a"),
                sort="updated_at",
                limit=10,
                cursor=None,
            )

        assert payload["total"] == 1
        assert payload["items"][0]["entity_id"] == "p-a"

    async def test_company_id_filter_uses_tags_json_path(self, sessionmaker, data_factory) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="gamma")
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "p-1", "title": "P 1", "tags_json": {"company_id": "c-1"}},
                    {"entity_id": "p-2", "title": "P 2", "tags_json": {"company_id": "c-2"}},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(company_id="c-2"),
                sort="updated_at",
                limit=10,
                cursor=None,
            )

        assert payload["total"] == 1
        assert payload["items"][0]["entity_id"] == "p-2"

    async def test_risk_level_filter_via_tags_json(self, sessionmaker, data_factory) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="delta")
            await _seed(
                session,
                tenant.id,
                [
                    {
                        "entity_id": "r-low",
                        "entity_type": "risk",
                        "title": "Risk low",
                        "tags_json": {"risk_level": "low"},
                    },
                    {
                        "entity_id": "r-high",
                        "entity_type": "risk",
                        "title": "Risk high",
                        "tags_json": {"risk_level": "high"},
                    },
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types={"risks"},
                filters=SearchFilters(risk_level="high"),
                sort="updated_at",
                limit=10,
                cursor=None,
            )

        assert payload["total"] == 1
        assert payload["items"][0]["entity_id"] == "r-high"

    async def test_date_range_filter_uses_updated_at(self, sessionmaker, data_factory) -> None:
        from datetime import date

        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="zeta")
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "p-jan", "title": "P jan", "updated_at": _aware(2026, 1, 15)},
                    {"entity_id": "p-feb", "title": "P feb", "updated_at": _aware(2026, 2, 15)},
                    {"entity_id": "p-mar", "title": "P mar", "updated_at": _aware(2026, 3, 15)},
                    {"entity_id": "p-apr", "title": "P apr", "updated_at": _aware(2026, 4, 15)},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(
                    date_from=date(2026, 2, 1),
                    date_to=date(2026, 3, 31),
                ),
                sort="updated_at",
                limit=10,
                cursor=None,
            )

        assert payload["total"] == 2
        assert sorted(item["entity_id"] for item in payload["items"]) == ["p-feb", "p-mar"]

    async def test_multiple_filters_compose_with_and(self, sessionmaker, data_factory) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="epsilon")
            await _seed(
                session,
                tenant.id,
                [
                    {
                        "entity_id": "match",
                        "entity_type": "document",
                        "title": "Doc A",
                        "status": "active",
                        "tags_json": {"site_id": "site-1", "company_id": "co-1"},
                    },
                    {
                        "entity_id": "wrong-status",
                        "entity_type": "document",
                        "title": "Doc B",
                        "status": "draft",
                        "tags_json": {"site_id": "site-1", "company_id": "co-1"},
                    },
                    {
                        "entity_id": "wrong-site",
                        "entity_type": "document",
                        "title": "Doc C",
                        "status": "active",
                        "tags_json": {"site_id": "site-2", "company_id": "co-1"},
                    },
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="Doc",
                types={"documents"},
                filters=SearchFilters(status="active", site_id="site-1", company_id="co-1"),
                sort="relevance",
                limit=10,
                cursor=None,
            )

        assert payload["total"] == 1
        assert payload["items"][0]["entity_id"] == "match"


# ---------------------------------------------------------------------------
# F. search() — tenant isolation, facets, pagination, sort, snippet, deeplink
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestSearchInfrastructure:
    async def test_tenant_isolation_excludes_other_tenants(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant_a = await data_factory.ensure_tenant(session=session, slug="acme")
            tenant_b = await data_factory.ensure_tenant(session=session, slug="beta")
            await _seed(session, tenant_a.id, [{"entity_id": "a1", "title": "Иванов A"}])
            await _seed(session, tenant_b.id, [{"entity_id": "b1", "title": "Иванов B"}])
            await session.commit()

            service_a = SearchService(session=session, tenant_id=tenant_a.id)
            payload_a = await service_a.search(
                q="Иванов",
                types=set(),
                filters=SearchFilters(),
                sort="relevance",
                limit=10,
                cursor=None,
            )

        assert payload_a["total"] == 1
        assert payload_a["items"][0]["entity_id"] == "a1"

    async def test_facets_include_type_status_and_tag_counts(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="gamma")
            await _seed(
                session,
                tenant.id,
                [
                    {
                        "entity_id": "p1",
                        "entity_type": "person",
                        "title": "P1",
                        "status": "active",
                        "tags_json": {"company_id": "co-1", "site_id": "s-1"},
                    },
                    {
                        "entity_id": "p2",
                        "entity_type": "person",
                        "title": "P2",
                        "status": "active",
                        "tags_json": {"company_id": "co-2", "site_id": "s-1"},
                    },
                    {
                        "entity_id": "d1",
                        "entity_type": "document",
                        "title": "D1",
                        "status": "draft",
                        "tags_json": {},
                    },
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(),
                sort="updated_at",
                limit=10,
                cursor=None,
            )

        facets = payload["facets"]
        assert facets["type_counts"]["person"] == 2
        assert facets["type_counts"]["document"] == 1
        assert facets["status_counts"]["active"] == 2
        assert facets["status_counts"]["draft"] == 1
        # tags_json[..].astext IS NULL rows are excluded from tag facets.
        assert facets["company_counts"] == {"co-1": 1, "co-2": 1}
        assert facets["site_counts"] == {"s-1": 2}

    async def test_facets_respect_active_filters(self, sessionmaker, data_factory) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="delta")
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "p1", "entity_type": "person", "title": "P1", "status": "active"},
                    {"entity_id": "p2", "entity_type": "person", "title": "P2", "status": "draft"},
                    {
                        "entity_id": "d1",
                        "entity_type": "document",
                        "title": "D1",
                        "status": "active",
                    },
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(status="active"),
                sort="updated_at",
                limit=10,
                cursor=None,
            )

        # Status filter is applied → type_counts only includes status=active rows.
        assert payload["facets"]["type_counts"] == {"person": 1, "document": 1}
        assert payload["facets"]["status_counts"] == {"active": 2}

    async def test_pagination_emits_next_cursor_when_more_rows_exist(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="zeta")
            # 5 rows so limit=2 yields pages 0-1, 2-3, 4-(end).
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": f"p-{i}", "title": f"T{i}", "updated_at": _aware(2026, 1, i + 1)}
                    for i in range(5)
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            page1 = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(),
                sort="updated_at",
                limit=2,
                cursor=None,
            )
            page2 = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(),
                sort="updated_at",
                limit=2,
                cursor=page1["next_cursor"],
            )
            page3 = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(),
                sort="updated_at",
                limit=2,
                cursor=page2["next_cursor"],
            )

        assert page1["next_cursor"] == "2"
        assert page2["next_cursor"] == "4"
        # Last page returns 1 item, no next_cursor.
        assert page3["next_cursor"] is None
        assert len(page3["items"]) == 1
        # All three pages return 5 distinct items total.
        ids = [item["entity_id"] for item in page1["items"] + page2["items"] + page3["items"]]
        assert sorted(ids) == sorted([f"p-{i}" for i in range(5)])

    async def test_sort_updated_at_returns_newest_first(self, sessionmaker, data_factory) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="epsilon")
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "old", "title": "Old", "updated_at": _aware(2026, 1, 1)},
                    {"entity_id": "new", "title": "New", "updated_at": _aware(2026, 4, 1)},
                    {"entity_id": "mid", "title": "Mid", "updated_at": _aware(2026, 2, 1)},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(),
                sort="updated_at",
                limit=10,
                cursor=None,
            )

        assert [item["entity_id"] for item in payload["items"]] == ["new", "mid", "old"]

    async def test_sort_date_returns_oldest_first(self, sessionmaker, data_factory) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            await _seed(
                session,
                tenant.id,
                [
                    {"entity_id": "z-old", "title": "Old", "updated_at": _aware(2026, 1, 1)},
                    {"entity_id": "z-new", "title": "New", "updated_at": _aware(2026, 4, 1)},
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(),
                sort="date",
                limit=10,
                cursor=None,
            )

        # asc order — first index is the older entry created in this test.
        ids = [item["entity_id"] for item in payload["items"]]
        # Other test rows may exist for tenant=test; pick out only ours.
        ours = [i for i in ids if i in {"z-old", "z-new"}]
        assert ours == ["z-old", "z-new"]

    async def test_snippet_contains_query_when_match_in_title(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="acme")
            await _seed(
                session,
                tenant.id,
                [{"entity_id": "p1", "title": "Иванов Иван Иванович"}],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="Иван",
                types=set(),
                filters=SearchFilters(),
                sort="relevance",
                limit=10,
                cursor=None,
            )

        assert payload["items"][0]["snippet"] is not None
        assert "Иван" in payload["items"][0]["snippet"]

    async def test_deeplink_uses_explicit_route_when_present(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="beta")
            await _seed(
                session,
                tenant.id,
                [
                    {
                        "entity_id": "p-with-route",
                        "title": "P R",
                        "route": "/custom-route/123",
                    },
                    {
                        "entity_id": "p-no-route",
                        "title": "P N",
                        "route": None,
                    },
                ],
            )
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(),
                sort="updated_at",
                limit=10,
                cursor=None,
            )

        by_id = {item["entity_id"]: item for item in payload["items"]}
        assert by_id["p-with-route"]["deeplink"] == "/custom-route/123"
        # Fallback uses _ENTITY_ROUTE_PREFIXES["person"] = "persons".
        assert by_id["p-no-route"]["deeplink"] == "/persons/p-no-route"

    async def test_invalid_cursor_is_treated_as_offset_zero(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session, slug="gamma")
            await _seed(session, tenant.id, [{"entity_id": "p1", "title": "T"}])
            await session.commit()

            service = SearchService(session=session, tenant_id=tenant.id)
            payload = await service.search(
                q="",
                types=set(),
                filters=SearchFilters(),
                sort="updated_at",
                limit=10,
                cursor="not-a-number",
            )

        # Non-numeric cursor is silently coerced to offset 0 (defensive parsing).
        assert payload["total"] == 1
        assert payload["items"][0]["entity_id"] == "p1"
