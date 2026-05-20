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
    "apply_etag_response_headers",
    "build_not_modified_headers",
    "compute_list_etag",
]

#: Canonical ``Cache-Control`` for tenant-scoped list endpoints behind ETag.
#: See module docstring for the full rationale. Override per callsite only
#: when a stronger (e.g. ``no-store``) or weaker (e.g. ``public, max-age=N``)
#: policy is required — this string is the safe default for Phase 9 surfaces.
DEFAULT_LIST_CACHE_CONTROL: str = "private, max-age=0, must-revalidate"


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
) -> None:
    """Set ``ETag`` and ``Cache-Control`` on the 200 OK response, atomically.

    Mutates ``response.headers`` in place. Use on the success branch of a
    conditional-GET endpoint — the 304 branch should build its own headers
    via :func:`build_not_modified_headers` (FastAPI's injected ``response``
    is not what gets returned in a manually-constructed 304 ``Response``).

    Args:
        response: The FastAPI-injected ``Response`` for the success path.
        etag: A quoted ETag string as returned by :func:`compute_list_etag`.
        cache_control: Override the module-default
            ``"private, max-age=0, must-revalidate"``. Use sparingly — the
            default is the safe pattern for tenant-scoped data behind ETag.
    """
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = cache_control


def build_not_modified_headers(
    etag: str,
    *,
    cache_control: str = DEFAULT_LIST_CACHE_CONTROL,
) -> dict[str, str]:
    """Return the headers dict for a manually-constructed 304 ``Response``.

    The 304 path returns ``Response(status_code=304, headers=...)`` — that
    response is a NEW object, distinct from the FastAPI-injected one used
    on the 200 path, so we cannot rely on
    :func:`apply_etag_response_headers` (which mutated the injected
    response). This helper builds the corresponding dict.

    Args:
        etag: A quoted ETag string. The same value the client sent in
            ``If-None-Match`` — RFC 7232 § 4.1 requires echoing it back so
            shared caches can revalidate against the same validator.
        cache_control: Override the module default. Must match the value
            sent on the 200 path — clients use Cache-Control to decide
            *whether* to revalidate; a mismatch between 200 and 304
            confuses heuristics.

    Returns:
        A ``{"ETag": ..., "Cache-Control": ...}`` dict suitable for
        ``Response(headers=...)``.
    """
    return {"ETag": etag, "Cache-Control": cache_control}
