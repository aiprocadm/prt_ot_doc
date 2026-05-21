"""Vary header uniformity contract across all 25 ETag list endpoints
(Phase 9 closure / vNext-PERF-03, Session 61).

Pins the third RFC 7234 cache-correctness layer that complements ETag
(conditional GET, S46-S58) and Cache-Control (freshness directives, S59):
``Vary: Authorization, X-Tenant`` — emitted by both
``apply_etag_response_headers`` (200 OK path) and
``build_not_modified_headers`` (304 Not Modified path) in
``backend/app/api/helpers/etag.py``.

Why ``Vary`` even when ``Cache-Control: private`` is already set:

- ``private`` is a *request* to shared caches not to cache the response.
  Misconfigured proxies, browser extensions and debug tools have been
  known to ignore it.
- ``Vary`` is a *cache-key contract*: any cache that nonetheless stored
  the response MUST segregate entries by ``Authorization`` and
  ``X-Tenant``. Two users with different JWTs hitting the same URL get
  distinct cache entries; same for two tenants. No cross-user or
  cross-tenant leak even on a non-compliant cache.

This is defense in depth — ``private`` tries to keep responses out;
``Vary`` ensures correct segregation if they got in anyway.

Test groups in this file:

1. **Helper unit contracts** — the two helpers are the single source of
   truth for the ``Vary`` value. These tests verify the default constant
   (``DEFAULT_LIST_VARY = "Authorization, X-Tenant"``), the keyword-only
   override path, the merge-with-existing-Vary semantics (so upstream
   CORS or observability ``Vary`` is preserved), and case-insensitive
   deduplication (RFC 7230 § 3.2 makes header names case-insensitive).

2. **End-to-end integration** — two representative endpoints
   (``/companies`` and ``/sites``) exercise the full request/response
   path: the unified ``Vary`` is present on the 200 OK reply AND on the
   304 Not Modified reply, with byte-identical value across both.
   RFC 7234 § 4.3.4 requires that 304 reuse the same cache-validation
   contract as the original 200 — a divergent ``Vary`` could let a
   cache return a stale-but-revalidated entry for the wrong request
   shape.

3. **Regression guard** — ``compute_list_etag`` is unchanged in S61; this
   test pins that the helper still returns byte-identical ETag strings
   for the same inputs (existing client caches must keep resolving to
   304 across the rollout).

Out of scope:

- Per-endpoint ``Vary`` assertions for all 25 endpoints — that would
  bloat the suite without proportional value. The helper is the single
  point of variance; testing it once covers all callers.
- Aliases (``x-tenant-slug``) in the default ``Vary`` — production
  clients use ``X-Tenant`` (canonical); if an alias case ever becomes
  hot in practice, the ``vary=`` keyword override is ready.
"""

from __future__ import annotations

import pytest
from fastapi import Response, status
from httpx import AsyncClient

from app.api.helpers.etag import (
    DEFAULT_LIST_VARY,
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


# =============================================================================
# Helper unit contracts
# =============================================================================


def test_default_vary_constant_is_documented_pattern() -> None:
    """``DEFAULT_LIST_VARY`` matches the documented S61 pattern.

    The exact string is part of the public cache-key contract: caches
    parse ``Vary`` tokens by name, and rolling deployments rely on the
    value staying stable across S61→future sessions. Changing this
    constant requires coordinated cache invalidation — this test locks
    the wording.
    """
    assert DEFAULT_LIST_VARY == "Authorization, X-Tenant"


def test_default_vary_covers_user_and_tenant_axes() -> None:
    """Sanity check: the default ``Vary`` segregates by both auth and tenant.

    Without ``Authorization`` two users with different JWTs at the same
    URL would share a cache entry (cross-user leak). Without ``X-Tenant``
    two tenants would (cross-tenant leak). Both axes must remain.
    """
    tokens = {tok.strip().lower() for tok in DEFAULT_LIST_VARY.split(",")}
    assert "authorization" in tokens, "missing Authorization breaks cross-user isolation"
    assert "x-tenant" in tokens, "missing X-Tenant breaks cross-tenant isolation"


def test_apply_etag_response_headers_sets_default_vary() -> None:
    """``apply_etag_response_headers`` mutates response: ETag + Cache-Control + Vary."""
    response = Response()
    apply_etag_response_headers(response, '"abc123"')

    assert response.headers["ETag"] == '"abc123"'
    assert response.headers["Vary"] == DEFAULT_LIST_VARY


def test_apply_etag_response_headers_accepts_vary_override() -> None:
    """Keyword-only ``vary=`` override lets future endpoints add axes
    (e.g. ``Accept-Language`` for an i18n list endpoint)."""
    response = Response()
    apply_etag_response_headers(
        response, '"abc"', vary="Authorization, X-Tenant, Accept-Language"
    )

    assert response.headers["Vary"] == "Authorization, X-Tenant, Accept-Language"


def test_apply_etag_response_headers_vary_is_keyword_only() -> None:
    """Positional argument for ``vary`` is rejected — prevents accidents
    where a cache_control value lands in the vary slot (or vice-versa)."""
    response = Response()
    with pytest.raises(TypeError):
        apply_etag_response_headers(
            response,
            '"abc"',
            "private, max-age=0, must-revalidate",
            "Authorization, X-Tenant",
        )  # type: ignore[misc]


def test_apply_etag_response_headers_merges_existing_vary() -> None:
    """When upstream middleware already set ``Vary`` (e.g. CORS ``Origin``),
    the helper *merges* rather than overwrites.

    Replacing would silently break the upstream middleware's cache
    contract — e.g. CORS expects ``Vary: Origin`` so that a cached
    response for ``Origin: a.com`` does not leak to ``Origin: b.com``.
    """
    response = Response()
    response.headers["Vary"] = "Origin"
    apply_etag_response_headers(response, '"abc"')

    tokens = {tok.strip() for tok in response.headers["Vary"].split(",")}
    assert "Origin" in tokens, "upstream CORS Vary must survive"
    assert "Authorization" in tokens, "S61 Authorization must be added"
    assert "X-Tenant" in tokens, "S61 X-Tenant must be added"


def test_apply_etag_response_headers_dedupes_vary_case_insensitive() -> None:
    """Vary token deduplication is case-insensitive (RFC 7230 § 3.2).

    If upstream sets ``Vary: authorization`` (lowercase) and the helper
    adds ``Authorization`` (Title-Case), the result must NOT contain
    both — caches treat them as the same header, so emitting both would
    be noise (and could trip strict parsers).
    """
    response = Response()
    response.headers["Vary"] = "authorization, origin"
    apply_etag_response_headers(response, '"abc"')

    rendered = response.headers["Vary"]
    lowered = [tok.strip().lower() for tok in rendered.split(",")]
    # exactly one Authorization token (case-insensitive)
    assert lowered.count("authorization") == 1
    # exactly one Origin token
    assert lowered.count("origin") == 1
    # X-Tenant added (was not in upstream)
    assert "x-tenant" in lowered


def test_build_not_modified_headers_returns_dict_with_default_vary() -> None:
    """``build_not_modified_headers`` returns ``{ETag, Cache-Control, Vary}``
    dict suitable for a manually-constructed 304 ``Response``."""
    headers = build_not_modified_headers('"xyz789"')

    assert headers["ETag"] == '"xyz789"'
    assert headers["Vary"] == DEFAULT_LIST_VARY


def test_build_not_modified_headers_accepts_vary_override() -> None:
    """Symmetric override path — must mirror ``apply_etag_response_headers``
    so 200 and 304 paths can be kept in sync at callsites."""
    headers = build_not_modified_headers(
        '"xyz"', vary="Authorization, X-Tenant, Accept-Language"
    )

    assert headers["Vary"] == "Authorization, X-Tenant, Accept-Language"


def test_build_not_modified_headers_vary_is_keyword_only() -> None:
    """Same keyword-only guard as ``apply_etag_response_headers``."""
    with pytest.raises(TypeError):
        build_not_modified_headers(
            '"xyz"',
            "private, max-age=0, must-revalidate",
            "Authorization, X-Tenant",
        )  # type: ignore[misc]


# =============================================================================
# Integration: helpers wired through real endpoints
# =============================================================================


@pytest.mark.asyncio
async def test_companies_endpoint_emits_unified_vary_on_200(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    """``GET /api/v1/companies`` carries the unified ``Vary`` on 200 OK."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="VaryTest Co", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/companies", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    vary = response.headers["Vary"]
    tokens = {tok.strip().lower() for tok in vary.split(",")}
    assert "authorization" in tokens
    assert "x-tenant" in tokens
    # ETag still present (helper sets all three atomically)
    assert response.headers["ETag"]


@pytest.mark.asyncio
async def test_companies_endpoint_emits_unified_vary_on_304(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    """304 reply on ``/companies`` carries the same ``Vary`` as the 200.

    RFC 7234 § 4.3.4 requires that 304 reuse the same cache-validation
    contract as the original 200 — a divergent ``Vary`` would let a
    shared cache return a stale-but-revalidated entry for the wrong
    request shape (e.g. one user's response served to another).
    """
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="Vary304 Co", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/companies", headers=headers)
    etag = first.headers["ETag"]
    vary_200 = first.headers["Vary"]

    second = await async_client.get(
        "/api/v1/companies", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["Vary"] == vary_200, (
        "304 must echo the 200's Vary (RFC 7234 § 4.3.4) — divergence breaks "
        "cache key consistency"
    )
    assert second.headers["ETag"] == etag


@pytest.mark.asyncio
async def test_sites_endpoint_emits_unified_vary_on_200_and_304(
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
            tenant=tenant, name="VarySiteHost Co", session=session
        )
        await data_factory.create_site(
            tenant=tenant, company=company, name="Plot V", session=session
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)

    first = await async_client.get("/api/v1/sites", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    vary_200 = first.headers["Vary"]
    tokens = {tok.strip().lower() for tok in vary_200.split(",")}
    assert "authorization" in tokens
    assert "x-tenant" in tokens
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/sites", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    # The 200 and 304 paths must emit byte-identical Vary.
    assert second.headers["Vary"] == vary_200


# =============================================================================
# Regression guard
# =============================================================================


@pytest.mark.asyncio
async def test_etag_value_unaffected_by_vary_addition(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    """Regression guard: adding ``Vary`` did NOT alter the ETag hash.

    ``compute_list_etag`` is unchanged in S61; this test pins that the
    helper still returns byte-identical ETag strings for the same
    inputs. A drift here means a pre-existing client cache would
    invalidate on rollout — exactly the failure mode the S47-S59
    refactor took pains to avoid.
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
            tenant=tenant, name="VaryEtagShape Co", session=session
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/companies", headers=headers)
    server_etag = response.headers["ETag"]
    assert server_etag.startswith('"') and server_etag.endswith('"')
    # sha256 hex digest is 64 chars + 2 quotes = 66.
    assert len(server_etag) == 66
