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
    response.headers["ETag"] = etag
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED,
                        headers={"ETag": etag})
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from typing import Any

__all__ = ["compute_list_etag"]


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
