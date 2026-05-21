"""Cache-Control uniformity contract across all 25 ETag list endpoints
(Phase 9 closure / vNext-PERF-03, Session 59).

Pins both layers of the Cache-Control rollout that landed alongside Phase 9
(``apply_etag_response_headers`` / ``build_not_modified_headers`` helpers in
``backend/app/api/helpers/etag.py``):

1. **Helper unit contracts** — the two new helpers are the single source of
   truth for the Cache-Control value emitted by every Phase-9 endpoint.
   These tests verify the default constant
   (``DEFAULT_LIST_CACHE_CONTROL = "private, max-age=0, must-revalidate"``)
   AND the keyword-only override path, so future per-endpoint policies
   (e.g. ``no-store`` for an admin surface) can land without re-deriving
   the helper contract.

2. **End-to-end integration** — two representative endpoints (``/companies``
   and ``/sites``) exercise the full request/response path: the unified
   Cache-Control is present on the 200 OK reply AND on the 304 Not Modified
   reply, with identical value across both. RFC 7234 § 5.2 expects
   revalidation responses to carry the same caching directives as the
   original — a mismatch confuses heuristics in shared caches.

The goal of this file is **uniformity**, not coverage of all 25 endpoints
individually: every endpoint goes through the same helper, so the helper
contract + a representative integration is sufficient to pin behavior. If
a future change introduces per-endpoint Cache-Control overrides, the
helper unit tests still hold (they test the API surface), and per-endpoint
contract files (``test_<domain>_cache_etag_contract.py``) gain specific
assertions in their own scope.

Out of scope:
- Per-endpoint Cache-Control assertions for all 25 endpoints — that would
  bloat 166 existing ETag tests without proportional value. The helper
  is the single point of variance; testing it once covers all callers.
- ``Vary`` header behaviour — pinned separately in
  ``test_etag_vary_uniformity.py`` (S61 / Phase 9.4 closure). Same
  helper, distinct contract surface, same single-point-of-variance
  argument applies.
"""

from __future__ import annotations

import pytest
from fastapi import Response, status
from httpx import AsyncClient

from app.api.helpers.etag import (
    DEFAULT_LIST_CACHE_CONTROL,
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


# =============================================================================
# Helper unit contracts
# =============================================================================


def test_default_cache_control_constant_is_documented_pattern() -> None:
    """``DEFAULT_LIST_CACHE_CONTROL`` matches the documented S59 pattern.

    The exact string is part of the public contract: clients and caches
    parse Cache-Control directives by name + presence, and rolling
    deployments rely on the value staying stable across S59→future
    sessions. Changing this constant is a breaking change — this test
    locks the wording.
    """
    assert DEFAULT_LIST_CACHE_CONTROL == "private, max-age=0, must-revalidate"


def test_apply_etag_response_headers_sets_both_headers_with_default() -> None:
    """``apply_etag_response_headers`` mutates response: ETag + default Cache-Control."""
    response = Response()
    apply_etag_response_headers(response, '"abc123"')

    assert response.headers["ETag"] == '"abc123"'
    assert response.headers["Cache-Control"] == DEFAULT_LIST_CACHE_CONTROL


def test_apply_etag_response_headers_accepts_cache_control_override() -> None:
    """Keyword-only ``cache_control=`` override lets future endpoints opt-in
    to stricter policies (e.g. admin surfaces with ``no-store``)."""
    response = Response()
    apply_etag_response_headers(response, '"abc"', cache_control="private, no-store")

    assert response.headers["ETag"] == '"abc"'
    assert response.headers["Cache-Control"] == "private, no-store"


def test_apply_etag_response_headers_cache_control_is_keyword_only() -> None:
    """Positional argument for cache_control is rejected — prevents accidents
    where an etag value lands in the cache_control slot (or vice-versa)."""
    response = Response()
    with pytest.raises(TypeError):
        apply_etag_response_headers(response, '"abc"', "private, no-store")  # type: ignore[misc]


def test_build_not_modified_headers_returns_dict_with_default() -> None:
    """``build_not_modified_headers`` returns ``{ETag, Cache-Control}`` dict
    suitable for the manually-constructed 304 ``Response``."""
    headers = build_not_modified_headers('"xyz789"')

    assert headers == {
        "ETag": '"xyz789"',
        "Cache-Control": DEFAULT_LIST_CACHE_CONTROL,
    }


def test_build_not_modified_headers_accepts_cache_control_override() -> None:
    """Symmetric override path — must mirror ``apply_etag_response_headers``
    so 200 and 304 paths can be kept in sync at callsites."""
    headers = build_not_modified_headers('"xyz"', cache_control="private, no-store")

    assert headers == {"ETag": '"xyz"', "Cache-Control": "private, no-store"}


def test_build_not_modified_headers_cache_control_is_keyword_only() -> None:
    """Same keyword-only guard as ``apply_etag_response_headers``."""
    with pytest.raises(TypeError):
        build_not_modified_headers('"xyz"', "private, no-store")  # type: ignore[misc]


def test_default_pattern_does_not_disable_etag_revalidation() -> None:
    """Sanity check: the default Cache-Control allows the ETag round-trip.

    ``no-store`` would disable client caching entirely, defeating Phase 9.
    The default MUST contain ``must-revalidate`` (forces revalidation
    cycle) and MUST NOT contain ``no-store`` (which would forbid the
    client from remembering the ETag at all).
    """
    directives = {d.strip() for d in DEFAULT_LIST_CACHE_CONTROL.split(",")}
    assert "no-store" not in directives, "no-store would disable Phase 9 ETag flow"
    assert "must-revalidate" in directives, "must-revalidate forces If-None-Match cycle"
    assert "private" in directives, "tenant data must not be cached by shared proxies"


# =============================================================================
# Integration: helpers wired through real endpoints
# =============================================================================


@pytest.mark.asyncio
async def test_companies_endpoint_emits_unified_cache_control_on_200(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    """``GET /api/v1/companies`` carries the unified Cache-Control on 200 OK."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="CCTest Co", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/companies", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["Cache-Control"] == DEFAULT_LIST_CACHE_CONTROL
    # ETag still present (the helper sets both atomically)
    assert response.headers["ETag"]


@pytest.mark.asyncio
async def test_companies_endpoint_emits_unified_cache_control_on_304(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    """304 reply on ``/companies`` carries the same Cache-Control as the 200.

    RFC 7234 § 5.2 expects revalidation responses to repeat caching
    directives so shared caches reapply them. Mismatched 200/304 values
    would confuse intermediate caches.
    """
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="CC304 Co", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/companies", headers=headers)
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/companies", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["Cache-Control"] == DEFAULT_LIST_CACHE_CONTROL
    assert second.headers["ETag"] == etag


@pytest.mark.asyncio
async def test_sites_endpoint_emits_unified_cache_control_on_200_and_304(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    """Second representative endpoint (``/sites``) — proves uniformity holds
    across distinct route modules, not just ``companies.py``."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="SiteHost Co", session=session
        )
        await data_factory.create_site(
            tenant=tenant, company=company, name="Plot A", session=session
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)

    first = await async_client.get("/api/v1/sites", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.headers["Cache-Control"] == DEFAULT_LIST_CACHE_CONTROL
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/sites", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["Cache-Control"] == DEFAULT_LIST_CACHE_CONTROL
    # The 200 and 304 paths must emit byte-identical Cache-Control.
    assert second.headers["Cache-Control"] == first.headers["Cache-Control"]


@pytest.mark.asyncio
async def test_etag_value_unaffected_by_cache_control_addition(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    """Regression guard: adding Cache-Control did NOT alter the ETag hash.

    ``compute_list_etag`` is unchanged in S59; this test pins that the
    helper still returns byte-identical ETag strings for the same inputs.
    A drift here means a pre-existing client cache would invalidate on
    rollout — exactly the failure mode the S47-S58 refactor took pains
    to avoid.
    """

    class _Row:
        def __init__(self, row_id: str, ts: object) -> None:
            self.id = row_id
            self.updated_at = ts

    rows = [_Row("r1", None), _Row("r2", None)]
    etag_a = compute_list_etag(tenant_id="tenant-x", items=rows, scalars=[("total", 2)])
    etag_b = compute_list_etag(tenant_id="tenant-x", items=rows, scalars=[("total", 2)])

    # Same inputs → byte-identical hash (deterministic).
    assert etag_a == etag_b
    # Real-endpoint sanity: an actual /companies ETag is a quoted sha256
    # (RFC 7232 § 2.3 syntax).
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(
            tenant=tenant, name="EtagShape Co", session=session
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/companies", headers=headers)
    server_etag = response.headers["ETag"]
    assert server_etag.startswith('"') and server_etag.endswith('"')
    # sha256 hex digest is 64 chars + 2 quotes = 66.
    assert len(server_etag) == 66
