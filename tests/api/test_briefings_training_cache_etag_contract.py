"""HTTP cache (ETag / If-None-Match) contract for /api/v1/briefings/* and /api/v1/training/courses
(Phase 9.2 extension / vNext-PERF-03, Session 52).

Continues the ETag rollout. Four endpoints — three no-pagination collections
under `/briefings` (templates / journals / entries) and one paginated under
`/training/courses`. After S52, 14 list endpoints carry ETag conditional-GET.

Pinned axes: hit/miss/POST-invalidation/cross-endpoint isolation (the three
briefings collections must have distinct ETags even with identical row
counts — the `("kind", ...)` scalar guards against that)/empty-list stable/
cross-tenant anti-leak/RFC 7232 quoted format.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _seed_briefing_template(
    async_client: AsyncClient,
    headers: dict,
    *,
    code: str = "BR-1",
    title: str = "Вводный инструктаж",
    briefing_type: str = "introductory",
) -> dict:
    payload = {"code": code, "title": title, "briefing_type": briefing_type}
    response = await async_client.post(
        "/api/v1/briefings/templates", json=payload, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def _seed_briefing_journal(
    async_client: AsyncClient,
    headers: dict,
    *,
    code: str = "J-1",
    title: str = "Журнал вводного инструктажа",
    journal_type: str = "introductory",
) -> dict:
    payload = {"code": code, "title": title, "journal_type": journal_type}
    response = await async_client.post(
        "/api/v1/briefings/journals", json=payload, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def _seed_briefing_entry(
    async_client: AsyncClient,
    headers: dict,
    *,
    journal_id: str,
    briefing_type: str = "introductory",
) -> dict:
    payload = {
        "briefing_journal_id": journal_id,
        "briefing_type": briefing_type,
        "briefing_date": datetime.now(timezone.utc).isoformat(),
    }
    response = await async_client.post(
        "/api/v1/briefings/entries", json=payload, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def _seed_training_course(
    async_client: AsyncClient,
    headers: dict,
    *,
    title: str = "Охрана труда — базовый курс",
    code: str = "TRC-1",
) -> dict:
    payload = {"title": title, "code": code, "duration_hours": 8, "valid_period_days": 365}
    response = await async_client.post(
        "/api/v1/training/courses", json=payload, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


# =============================================================================
# /api/v1/briefings/templates
# =============================================================================


@pytest.mark.asyncio
async def test_briefings_templates_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_briefing_template(async_client, headers)

    first = await async_client.get("/api/v1/briefings/templates", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/briefings/templates", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.content == b""


@pytest.mark.asyncio
async def test_briefings_templates_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_briefing_template(async_client, headers, code="BR-A")
    first = await async_client.get("/api/v1/briefings/templates", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_briefing_template(async_client, headers, code="BR-B")

    second = await async_client.get("/api/v1/briefings/templates", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_briefings_templates_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="delta", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="delta")
    first = await async_client.get("/api/v1/briefings/templates", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/briefings/templates", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


# =============================================================================
# /api/v1/briefings/journals
# =============================================================================


@pytest.mark.asyncio
async def test_briefings_journals_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_briefing_journal(async_client, headers)

    first = await async_client.get("/api/v1/briefings/journals", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/briefings/journals", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_briefings_journals_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_briefing_journal(async_client, headers)

    response = await async_client.get(
        "/api/v1/briefings/journals", headers={**headers, "If-None-Match": '"stale"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"]


# =============================================================================
# /api/v1/briefings/entries
# =============================================================================


@pytest.mark.asyncio
async def test_briefings_entries_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    journal = await _seed_briefing_journal(async_client, headers, code="J-Hit")
    await _seed_briefing_entry(async_client, headers, journal_id=journal["id"])

    first = await async_client.get("/api/v1/briefings/entries", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/briefings/entries", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_briefings_entries_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    journal = await _seed_briefing_journal(async_client, headers, code="J-Mut")
    await _seed_briefing_entry(async_client, headers, journal_id=journal["id"])
    first = await async_client.get("/api/v1/briefings/entries", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_briefing_entry(async_client, headers, journal_id=journal["id"])

    second = await async_client.get("/api/v1/briefings/entries", headers=headers)
    assert second.headers["ETag"] != initial_etag


# =============================================================================
# Cross-endpoint isolation (the kind-scalar guard)
# =============================================================================


@pytest.mark.asyncio
async def test_briefings_kind_scalar_distinguishes_collections(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Three briefings collections with identical row counts → distinct ETags.

    The `("kind", "templates"|"journals"|"entries")` scalar guards against
    cross-endpoint cache collision when totals coincide. Without it, a client
    that cached `/templates` ETag could spuriously 304 on `/journals` with
    the same `total` count.
    """
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="gamma", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="gamma")
    # Seed exactly one row in each collection (so totals match).
    await _seed_briefing_template(async_client, headers, code="K-T")
    journal = await _seed_briefing_journal(async_client, headers, code="K-J")
    await _seed_briefing_entry(async_client, headers, journal_id=journal["id"])

    templates = await async_client.get("/api/v1/briefings/templates", headers=headers)
    journals = await async_client.get("/api/v1/briefings/journals", headers=headers)
    entries = await async_client.get("/api/v1/briefings/entries", headers=headers)

    etag_t = templates.headers["ETag"]
    etag_j = journals.headers["ETag"]
    etag_e = entries.headers["ETag"]
    assert etag_t != etag_j
    assert etag_j != etag_e
    assert etag_t != etag_e


# =============================================================================
# /api/v1/training/courses
# =============================================================================


@pytest.mark.asyncio
async def test_training_courses_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_training_course(async_client, headers)

    first = await async_client.get("/api/v1/training/courses", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/training/courses", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.content == b""


@pytest.mark.asyncio
async def test_training_courses_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_training_course(async_client, headers)

    response = await async_client.get(
        "/api/v1/training/courses", headers={**headers, "If-None-Match": '"stale-course"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"]


@pytest.mark.asyncio
async def test_training_courses_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_training_course(async_client, headers, code="TRC-A", title="Course A")
    first = await async_client.get("/api/v1/training/courses", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_training_course(async_client, headers, code="TRC-B", title="Course B")

    second = await async_client.get("/api/v1/training/courses", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_training_courses_etag_distinct_per_page(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    for i in range(4):
        await _seed_training_course(
            async_client, headers, code=f"TRC-P{i}", title=f"Course P{i}"
        )

    a = await async_client.get(
        "/api/v1/training/courses?limit=2&offset=0", headers=headers
    )
    b = await async_client.get(
        "/api/v1/training/courses?limit=2&offset=2", headers=headers
    )
    assert a.headers["ETag"] != b.headers["ETag"]


@pytest.mark.asyncio
async def test_training_courses_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="epsilon", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="epsilon")
    first = await async_client.get("/api/v1/training/courses", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/training/courses", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_training_courses_cross_tenant_etag_does_not_leak(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="acme", session=session)
        await data_factory.ensure_tenant(slug="beta", session=session)
        await session.commit()

    headers_a = await make_auth_headers(RoleEnum.ADMIN, tenant="acme")
    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant="beta")
    await _seed_training_course(async_client, headers_a, code="A-1")
    await _seed_training_course(async_client, headers_b, code="B-1")

    a = await async_client.get("/api/v1/training/courses", headers=headers_a)
    etag_a = a.headers["ETag"]

    leaked = await async_client.get(
        "/api/v1/training/courses", headers={**headers_b, "If-None-Match": etag_a}
    )
    assert leaked.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_training_courses_etag_quoted_per_rfc7232(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_training_course(async_client, headers, code="RFC-1")

    response = await async_client.get("/api/v1/training/courses", headers=headers)
    etag = response.headers["ETag"]
    assert etag.startswith('"') and etag.endswith('"'), f"ETag not quoted: {etag!r}"
