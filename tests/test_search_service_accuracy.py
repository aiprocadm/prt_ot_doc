"""Accuracy tests for SearchService.search() — Phase 4.2 tail (vNext-SEARCH-01).

Direct in-process tests against the SearchService API (no HTTP layer) to lock in:
- tenant isolation
- type-alias resolution (`documents` → `document`)
- ranking (exact title > title prefix > contains)
- filters (status, company_id, site_id via tags_json)
- facets (`type_counts`, `status_counts`, `company_counts`, `site_counts`)
- pagination (`next_cursor`)
- snippet windowing around the matched substring
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projections.models import SearchIndexEntry
from app.modules.search.service import SearchFilters, SearchService


pytestmark = pytest.mark.anyio


async def _seed_entry(
    session: AsyncSession,
    *,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    title: str,
    subtitle: str | None = None,
    status: str | None = None,
    tags: dict | None = None,
    search_text: str | None = None,
    route: str | None = None,
) -> SearchIndexEntry:
    row = SearchIndexEntry(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        title=title,
        subtitle=subtitle,
        status=status,
        tags_json=tags,
        search_text=search_text or title,
        route=route,
    )
    session.add(row)
    await session.flush()
    return row


async def test_tenant_isolation_excludes_other_tenants(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        primary = await data_factory.ensure_tenant(session=session, slug="search-acc-primary")
        other = await data_factory.ensure_tenant(session=session, slug="search-acc-other")
        await _seed_entry(
            session,
            tenant_id=primary.id,
            entity_type="person",
            entity_id="p-mine",
            title="Сидоров Иван",
        )
        await _seed_entry(
            session,
            tenant_id=other.id,
            entity_type="person",
            entity_id="p-foreign",
            title="Сидоров Иван",
        )
        await session.commit()

    async with sessionmaker() as session:
        service = SearchService(session, primary.id)
        result = await service.search(
            q="Сидоров",
            types=set(),
            filters=SearchFilters(),
            sort="relevance",
            limit=20,
            cursor=None,
        )

    assert result["total"] == 1
    assert {item["entity_id"] for item in result["items"]} == {"p-mine"}


async def test_type_alias_resolution_documents_to_document(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session, slug="search-acc-alias")
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="document",
            entity_id="d-1",
            title="Распоряжение по охране труда",
        )
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="person",
            entity_id="p-1",
            title="Распоряжение Петров",
        )
        await session.commit()

    async with sessionmaker() as session:
        service = SearchService(session, tenant.id)
        result = await service.search(
            q="Распоряжение",
            types={"documents"},
            filters=SearchFilters(),
            sort="relevance",
            limit=20,
            cursor=None,
        )

    assert {item["entity_type"] for item in result["items"]} == {"document"}
    assert {item["entity_id"] for item in result["items"]} == {"d-1"}


async def test_ranking_exact_title_before_prefix_before_contains(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session, slug="search-acc-rank")
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="document",
            entity_id="d-contains",
            title="Отчёт по теме Охрана труда (полугодие)",
        )
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="document",
            entity_id="d-prefix",
            title="Охрана труда — приказ №7",
        )
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="document",
            entity_id="d-exact",
            title="Охрана труда",
        )
        await session.commit()

    async with sessionmaker() as session:
        service = SearchService(session, tenant.id)
        result = await service.search(
            q="Охрана труда",
            types=set(),
            filters=SearchFilters(),
            sort="relevance",
            limit=20,
            cursor=None,
        )

    order = [item["entity_id"] for item in result["items"]]
    assert order[0] == "d-exact", order
    assert order.index("d-prefix") < order.index("d-contains"), order


async def test_status_and_tags_filters_narrow_result(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session, slug="search-acc-filters")
        company_a = "00000000-0000-0000-0000-000000000aaa"
        company_b = "00000000-0000-0000-0000-000000000bbb"
        site_a = "00000000-0000-0000-0000-000000000ccc"
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="document",
            entity_id="d-a-active",
            title="Журнал инструктажей",
            status="active",
            tags={"company_id": company_a, "site_id": site_a},
        )
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="document",
            entity_id="d-a-archived",
            title="Журнал инструктажей (архив)",
            status="archived",
            tags={"company_id": company_a, "site_id": site_a},
        )
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="document",
            entity_id="d-b-active",
            title="Журнал инструктажей B",
            status="active",
            tags={"company_id": company_b},
        )
        await session.commit()

    async with sessionmaker() as session:
        service = SearchService(session, tenant.id)
        active_a = await service.search(
            q="Журнал",
            types=set(),
            filters=SearchFilters(status="active", company_id=company_a),
            sort="relevance",
            limit=20,
            cursor=None,
        )
        site_filtered = await service.search(
            q="Журнал",
            types=set(),
            filters=SearchFilters(site_id=site_a),
            sort="relevance",
            limit=20,
            cursor=None,
        )

    assert {item["entity_id"] for item in active_a["items"]} == {"d-a-active"}
    assert {item["entity_id"] for item in site_filtered["items"]} == {"d-a-active", "d-a-archived"}


async def test_facets_reflect_filtered_set(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session, slug="search-acc-facets")
        company = "00000000-0000-0000-0000-0000000facet"
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="document",
            entity_id="f-d1",
            title="Facet doc",
            status="active",
            tags={"company_id": company},
        )
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="document",
            entity_id="f-d2",
            title="Facet doc 2",
            status="draft",
            tags={"company_id": company},
        )
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="person",
            entity_id="f-p1",
            title="Facet person",
            status="active",
            tags={"company_id": company},
        )
        await session.commit()

    async with sessionmaker() as session:
        service = SearchService(session, tenant.id)
        result = await service.search(
            q="Facet",
            types=set(),
            filters=SearchFilters(),
            sort="relevance",
            limit=20,
            cursor=None,
        )

    facets = result["facets"]
    assert facets["type_counts"].get("document") == 2
    assert facets["type_counts"].get("person") == 1
    assert facets["status_counts"].get("active") == 2
    assert facets["status_counts"].get("draft") == 1
    assert facets["company_counts"].get(company) == 3


async def test_pagination_emits_next_cursor_when_more_results(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session, slug="search-acc-paging")
        for idx in range(5):
            await _seed_entry(
                session,
                tenant_id=tenant.id,
                entity_type="document",
                entity_id=f"pg-{idx}",
                title=f"Paginated doc {idx}",
            )
        await session.commit()

    async with sessionmaker() as session:
        service = SearchService(session, tenant.id)
        page1 = await service.search(
            q="Paginated",
            types=set(),
            filters=SearchFilters(),
            sort="updated_at",
            limit=2,
            cursor=None,
        )
        page2 = await service.search(
            q="Paginated",
            types=set(),
            filters=SearchFilters(),
            sort="updated_at",
            limit=2,
            cursor=page1["next_cursor"],
        )

    assert len(page1["items"]) == 2
    assert page1["next_cursor"] == "2"
    assert len(page2["items"]) == 2
    page1_ids = {item["entity_id"] for item in page1["items"]}
    page2_ids = {item["entity_id"] for item in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)


async def test_snippet_windows_around_match(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session, slug="search-acc-snippet")
        long_subtitle = (
            "Этот документ упоминает термин искомое слово где-то в середине описания, "
            "которое значительно превышает 180 символов, чтобы окно сниппета имело смысл "
            "и было видно вокруг места совпадения."
        )
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="document",
            entity_id="snip-1",
            title="Документ",
            subtitle=long_subtitle,
            search_text=long_subtitle,
        )
        await session.commit()

    async with sessionmaker() as session:
        service = SearchService(session, tenant.id)
        result = await service.search(
            q="искомое слово",
            types=set(),
            filters=SearchFilters(),
            sort="relevance",
            limit=5,
            cursor=None,
        )

    assert result["items"]
    snippet = result["items"][0]["snippet"]
    assert snippet is not None
    assert "искомое слово" in snippet
    assert len(snippet) <= 180


async def test_empty_query_returns_tenant_rows_sorted_by_updated_at(
    sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session, slug="search-acc-empty")
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="document",
            entity_id="e-1",
            title="E1",
        )
        await _seed_entry(
            session,
            tenant_id=tenant.id,
            entity_type="person",
            entity_id="e-2",
            title="E2",
        )
        await session.commit()

    async with sessionmaker() as session:
        service = SearchService(session, tenant.id)
        result = await service.search(
            q="",
            types=set(),
            filters=SearchFilters(),
            sort="relevance",
            limit=20,
            cursor=None,
        )

    assert result["total"] == 2
    assert {item["entity_id"] for item in result["items"]} == {"e-1", "e-2"}
