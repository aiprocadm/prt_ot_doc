"""Shared ETag computation for list endpoints.

Centralizes the conditional-GET cache-key hash that was duplicated across
``companies`` / ``sites`` / ``documents`` / ``tasks`` / ``persons`` /
``incidents`` / ``inspections`` route modules (Sessions 47-49). The contract
each route implements is the same shape:

    sha256("tenant:{id}::<scalar0>::<scalar1>::...::id:updated_at|id:updated_at|...")

where ``<scalarN>`` is a ``label:value`` pair from the route's cache key
(pagination, filters) and the final ``|``-joined section enumerates the
result rows by their ``(id, updated_at)`` pair.

This helper preserves byte-for-byte hash equivalence with each pre-existing
inline ``_<entity>_etag`` function — existing client-side ETags continue
to resolve to 304 after the refactor. Callers stay responsible for ordering
scalars deterministically (the hash depends on order).

Cache-Control uniformity (Session 59 / vNext-PERF-03 Phase 9.3 closure):

The ``apply_etag_response_headers`` / ``build_not_modified_headers`` pair
sets both ``ETag`` and ``Cache-Control`` atomically. Default Cache-Control
is ``private, max-age=0, must-revalidate`` — the canonical pattern for
tenant-scoped data behind a conditional-GET (ETag) layer:

- ``private``: shared proxies / CDNs MUST NOT cache (tenant data is
  per-tenant — leaking across customers via a corporate proxy is a hard
  defect class to detect).
- ``max-age=0``: no fresh window; client MUST revalidate immediately.
- ``must-revalidate``: clients MUST NOT serve stale entries without
  revalidation through ``If-None-Match``. Combined with the ETag, every
  repeat read is a cheap 304 (empty body, same hash) unless data
  actually changed.

This is intentionally not ``no-store``: that directive disables ETag
revalidation entirely (clients refuse to remember any response), which
would defeat Phase 9.2/9.3 conditional-GET savings. Admin endpoints
(``/admin/users``, ``/api-tokens``) inherit the same pattern because
``private`` + always-revalidate-via-ETag already satisfies their
threat model (no shared-cache leak, no stale credential surfaces).

Vary header uniformity (Session 61 / vNext-PERF-03 Phase 9.4 closure):

The same helper pair also emits ``Vary: Authorization, X-Tenant`` —
the third RFC 7234 cache-correctness layer that complements ETag
(conditional GET) and Cache-Control (freshness directives). ``Vary``
tells any cache (browser / proxy / CDN) which request headers participate
in the cache key:

- ``Authorization``: distinct JWT tokens (different users) MUST get
  distinct cache entries even at the same URL. Without this, a corporate
  proxy could serve user A's response to user B because both hit the
  same URL.
- ``X-Tenant``: distinct tenants likewise. ``private`` is a *request*
  to shared caches not to cache; ``Vary: X-Tenant`` is a *correctness*
  contract for any cache that ignored ``private`` (misconfigured proxy,
  browser extension, debug tool) — different tenant headers ⇒ different
  cache entries ⇒ no cross-tenant leak even on a non-compliant cache.

This is defense in depth: ``private`` tries to keep responses out of
shared caches; ``Vary`` ensures correct segregation if a response
nonetheless got cached. The pair guards both directions of the
misconfiguration threat model.

``apply_etag_response_headers`` *merges* with any upstream ``Vary`` token
(CORS ``Origin``, observability custom headers) rather than overwriting —
clobbering the upstream value would break those middlewares' cache
contracts. The 304 path (``build_not_modified_headers``) sets a fresh
``Vary`` value because a manually constructed ``Response(headers=...)``
does not inherit upstream middleware state.

Usage::

    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=rows,
        scalars=[
            ("total", total),
            ("limit", limit),
            ("offset", offset),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from typing import Any

from fastapi import Response

__all__ = [
    "DEFAULT_LIST_CACHE_CONTROL",
    "DEFAULT_LIST_VARY",
    "apply_etag_response_headers",
    "build_not_modified_headers",
    "compute_list_etag",
]

#: Canonical ``Cache-Control`` for tenant-scoped list endpoints behind ETag.
#: See module docstring for the full rationale. Override per callsite only
#: when a stronger (e.g. ``no-store``) or weaker (e.g. ``public, max-age=N``)
#: policy is required — this string is the safe default for Phase 9 surfaces.
DEFAULT_LIST_CACHE_CONTROL: str = "private, max-age=0, must-revalidate"

#: Canonical ``Vary`` for tenant-scoped list endpoints behind ETag.
#: ``Authorization`` segregates cache entries by JWT (distinct users);
#: ``X-Tenant`` segregates by tenant header (distinct tenants). Together
#: they guarantee cross-user and cross-tenant cache isolation even on
#: a shared cache that ignored ``Cache-Control: private``. See module
#: docstring for the full RFC 7234 § 7.1.4 rationale.
DEFAULT_LIST_VARY: str = "Authorization, X-Tenant"


def compute_list_etag(
    *,
    tenant_id: str,
    items: Iterable[Any],
    scalars: Sequence[tuple[str, Any]] = (),
) -> str:
    """Compute a quoted ETag for a list response.

    Args:
        tenant_id: Stringified tenant identifier. Always becomes the first
            ``tenant:`` part — guards against cross-tenant cache leak.
        items: Result rows. Each must expose ``id`` and ``updated_at``
            attributes. ``updated_at`` may be ``None``; the helper emits
            an empty string in that case (matching prior behaviour of
            ``companies`` / ``sites`` / ``persons`` / ``incidents`` /
            ``inspections``).
        scalars: Ordered ``(label, value)`` pairs that participate in the
            cache key — pagination (``total`` / ``limit`` / ``offset`` or
            ``page`` / ``page_size``) and filters. ``value`` may be any type
            with a sensible ``str()``; ``None`` is normalised to empty
            string. Order matters — distinct orderings produce distinct
            hashes.

    Returns:
        Quoted ETag string (e.g. ``"\"abc123...\""``) per RFC 7232 § 2.3.
    """
    parts: list[str] = [f"tenant:{tenant_id}"]
    for label, value in scalars:
        rendered = "" if value is None else str(value)
        parts.append(f"{label}:{rendered}")
    parts.append(
        "|".join(
            f"{item.id}:{item.updated_at.isoformat() if item.updated_at else ''}"
            for item in items
        )
    )
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()
    return f'"{digest}"'


def apply_etag_response_headers(
    response: Response,
    etag: str,
    *,
    cache_control: str = DEFAULT_LIST_CACHE_CONTROL,
    vary: str = DEFAULT_LIST_VARY,
) -> None:
    """Set ``ETag`` + ``Cache-Control`` + ``Vary`` on the 200 OK response.

    Mutates ``response.headers`` in place. Use on the success branch of a
    conditional-GET endpoint — the 304 branch should build its own headers
    via :func:`build_not_modified_headers` (FastAPI's injected ``response``
    is not what gets returned in a manually-constructed 304 ``Response``).

    ``Vary`` is *merged* with any value upstream middleware may have set
    (CORS ``Origin``, observability custom tokens). Tokens are deduplicated
    case-insensitively while preserving insertion order of the first
    occurrence's casing — replacing would silently break upstream cache
    contracts.

    Args:
        response: The FastAPI-injected ``Response`` for the success path.
        etag: A quoted ETag string as returned by :func:`compute_list_etag`.
        cache_control: Override the module-default
            ``"private, max-age=0, must-revalidate"``. Use sparingly — the
            default is the safe pattern for tenant-scoped data behind ETag.
        vary: Override the module-default ``"Authorization, X-Tenant"``.
            Add tokens (do not remove) when the endpoint additionally
            varies on a header like ``Accept-Language``.
    """
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = cache_control
    existing_vary = response.headers.get("Vary")
    if existing_vary:
        merged: dict[str, str] = {}
        for token in (*existing_vary.split(","), *vary.split(",")):
            stripped = token.strip()
            if stripped:
                merged.setdefault(stripped.lower(), stripped)
        response.headers["Vary"] = ", ".join(merged.values())
    else:
        response.headers["Vary"] = vary


def build_not_modified_headers(
    etag: str,
    *,
    cache_control: str = DEFAULT_LIST_CACHE_CONTROL,
    vary: str = DEFAULT_LIST_VARY,
) -> dict[str, str]:
    """Return the headers dict for a manually-constructed 304 ``Response``.

    The 304 path returns ``Response(status_code=304, headers=...)`` — that
    response is a NEW object, distinct from the FastAPI-injected one used
    on the 200 path, so we cannot rely on
    :func:`apply_etag_response_headers` (which mutated the injected
    response). This helper builds the corresponding dict.

    Note: unlike the 200 path, no merge with upstream ``Vary`` is needed —
    the manually-constructed ``Response`` does not inherit middleware
    headers (those are layered on by Starlette *after* the route function
    returns, against the new object, which would let downstream middleware
    still append their own ``Vary`` if needed).

    Args:
        etag: A quoted ETag string. The same value the client sent in
            ``If-None-Match`` — RFC 7232 § 4.1 requires echoing it back so
            shared caches can revalidate against the same validator.
        cache_control: Override the module default. Must match the value
            sent on the 200 path — clients use Cache-Control to decide
            *whether* to revalidate; a mismatch between 200 and 304
            confuses heuristics.
        vary: Override the module default. Must match the 200-path value —
            RFC 7234 § 4.3.4 requires that 304 reuse the same
            cache-validation contract; a divergent ``Vary`` could let a
            cache return a stale-but-revalidated entry for the wrong
            request shape.

    Returns:
        A ``{"ETag": ..., "Cache-Control": ..., "Vary": ...}`` dict
        suitable for ``Response(headers=...)``.
    """
    return {"ETag": etag, "Cache-Control": cache_control, "Vary": vary}
