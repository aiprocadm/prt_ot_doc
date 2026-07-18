"""Unit tests for the shared ETag list helper
(Phase 9.2 refactor / Session 50).

Verifies that ``compute_list_etag`` from ``app.api.helpers.etag``:

1. Produces output byte-identical to the seven pre-existing inline
   ``_<entity>_etag`` functions across companies / sites / documents /
   tasks / persons / incidents / inspections — so existing clients holding
   ETags from before the refactor continue to resolve to 304.
2. Handles edge cases correctly: empty items, no scalars, ``None`` scalar
   values, items with ``updated_at = None``.
3. Is deterministic and order-sensitive on scalars (cache-key collisions
   would break pagination/filter isolation).

The byte-equivalence tests recompute the hash by hand using ``hashlib.sha256``
and the exact string format each route module used before the refactor —
so any drift in ``compute_list_etag`` surfaces here, not in production at
the moment a client gets an unexpected cache miss.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from app.api.helpers.etag import compute_list_etag

# -----------------------------------------------------------------------------
# Test doubles
# -----------------------------------------------------------------------------


@dataclass
class _Row:
    id: str
    updated_at: datetime | None


def _hash(parts: list[str]) -> str:
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()
    return f'"{digest}"'


# -----------------------------------------------------------------------------
# Format guarantees
# -----------------------------------------------------------------------------


def test_etag_returns_quoted_string_per_rfc7232() -> None:
    etag = compute_list_etag(tenant_id="tx", items=[], scalars=())
    assert etag.startswith('"') and etag.endswith('"')


def test_etag_is_deterministic_for_same_input() -> None:
    rows = [_Row(id="r1", updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc))]
    a = compute_list_etag(tenant_id="t1", items=rows, scalars=[("total", 1)])
    b = compute_list_etag(tenant_id="t1", items=rows, scalars=[("total", 1)])
    assert a == b


def test_etag_is_sensitive_to_tenant_id() -> None:
    rows = [_Row(id="r1", updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc))]
    a = compute_list_etag(tenant_id="tenant-A", items=rows, scalars=[])
    b = compute_list_etag(tenant_id="tenant-B", items=rows, scalars=[])
    assert a != b


def test_etag_is_sensitive_to_scalar_order() -> None:
    """Different scalar order → different ETag.

    Cache key is order-dependent. The companies route emits
    ``[("total", T), ("limit", L), ("offset", O)]``; if a refactor swaps
    that order, clients that cached the old hash should miss — and this
    test makes that surface visible.
    """
    rows = [_Row(id="r1", updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc))]
    a = compute_list_etag(
        tenant_id="t", items=rows, scalars=[("total", 1), ("limit", 50), ("offset", 0)]
    )
    b = compute_list_etag(
        tenant_id="t", items=rows, scalars=[("limit", 50), ("offset", 0), ("total", 1)]
    )
    assert a != b


def test_etag_is_sensitive_to_item_order() -> None:
    """Different result-row order → different ETag (correctly caches per-ordering)."""
    dt = datetime(2026, 5, 1, tzinfo=timezone.utc)
    rows_ab = [_Row(id="a", updated_at=dt), _Row(id="b", updated_at=dt)]
    rows_ba = [_Row(id="b", updated_at=dt), _Row(id="a", updated_at=dt)]
    a = compute_list_etag(tenant_id="t", items=rows_ab, scalars=[])
    b = compute_list_etag(tenant_id="t", items=rows_ba, scalars=[])
    assert a != b


def test_etag_changes_when_a_row_updated_at_changes() -> None:
    """Bumping ``updated_at`` for any row → new ETag (the invalidation invariant)."""
    rows_old = [_Row(id="r1", updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc))]
    rows_new = [_Row(id="r1", updated_at=datetime(2026, 5, 2, tzinfo=timezone.utc))]
    a = compute_list_etag(tenant_id="t", items=rows_old, scalars=[])
    b = compute_list_etag(tenant_id="t", items=rows_new, scalars=[])
    assert a != b


# -----------------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------------


def test_empty_items_still_produces_valid_etag() -> None:
    """Empty list must produce a stable, well-formed ETag (304 works on empty pages)."""
    a = compute_list_etag(tenant_id="t", items=[], scalars=[("total", 0)])
    assert a.startswith('"') and len(a) > 2
    # Same call twice → identical
    b = compute_list_etag(tenant_id="t", items=[], scalars=[("total", 0)])
    assert a == b


def test_no_scalars_still_works() -> None:
    """Routes that don't pass any pagination/filter scalars still get a usable ETag."""
    rows = [_Row(id="r1", updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc))]
    etag = compute_list_etag(tenant_id="t", items=rows)
    assert etag.startswith('"')


def test_none_scalar_value_normalised_to_empty_string() -> None:
    """``None`` scalar value renders as empty string (e.g. unset filter)."""
    rows = [_Row(id="r1", updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc))]
    with_none = compute_list_etag(tenant_id="t", items=rows, scalars=[("company", None)])
    with_empty = compute_list_etag(tenant_id="t", items=rows, scalars=[("company", "")])
    assert with_none == with_empty


def test_row_with_missing_updated_at_renders_empty_timestamp() -> None:
    """Row with ``updated_at = None`` participates in hash as ``id:`` (empty timestamp)."""
    rows = [_Row(id="r1", updated_at=None)]
    etag = compute_list_etag(tenant_id="t", items=rows, scalars=[])
    expected = _hash(["tenant:t", "r1:"])
    assert etag == expected


def test_items_can_be_any_iterable_with_id_and_updated_at() -> None:
    """Generator (not a list) also accepted — single-pass iteration is fine."""
    dt = datetime(2026, 5, 1, tzinfo=timezone.utc)

    def gen():
        yield _Row(id="r1", updated_at=dt)
        yield _Row(id="r2", updated_at=dt)

    etag_gen = compute_list_etag(tenant_id="t", items=gen(), scalars=[])
    etag_list = compute_list_etag(
        tenant_id="t",
        items=[_Row(id="r1", updated_at=dt), _Row(id="r2", updated_at=dt)],
        scalars=[],
    )
    assert etag_gen == etag_list


def test_integer_and_string_scalars_render_via_str() -> None:
    rows = [_Row(id="r1", updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc))]
    int_form = compute_list_etag(tenant_id="t", items=rows, scalars=[("total", 5)])
    str_form = compute_list_etag(tenant_id="t", items=rows, scalars=[("total", "5")])
    # Both render as "total:5" — identical ETag.
    assert int_form == str_form


# -----------------------------------------------------------------------------
# Byte-equivalence with pre-refactor inline helpers
# -----------------------------------------------------------------------------


def test_byte_equivalence_companies_helper_format() -> None:
    """Identical to the pre-S50 ``_companies_etag`` output."""
    dt = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    rows = [_Row(id="c1", updated_at=dt), _Row(id="c2", updated_at=None)]
    expected = _hash(
        [
            "tenant:t-uuid",
            "total:2",
            "limit:50",
            "offset:0",
            f"c1:{dt.isoformat()}|c2:",
        ]
    )
    got = compute_list_etag(
        tenant_id="t-uuid",
        items=rows,
        scalars=[("total", 2), ("limit", 50), ("offset", 0)],
    )
    assert got == expected


def test_byte_equivalence_documents_helper_format() -> None:
    """Identical to the pre-S50 ``_documents_list_etag`` output (page/page_size).

    Documents pre-refactor used ``item.updated_at.isoformat()`` without
    None-guard. Helper now defensively handles None — but since real rows
    always have ``updated_at`` (TimestampMixin), the production hash is
    byte-identical to pre-refactor for all real inputs.
    """
    dt = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    rows = [_Row(id="d1", updated_at=dt)]
    expected = _hash(
        [
            "tenant:doctenant",
            "page:1",
            "page_size:10",
            "total:1",
            f"d1:{dt.isoformat()}",
        ]
    )
    got = compute_list_etag(
        tenant_id="doctenant",
        items=rows,
        scalars=[("page", 1), ("page_size", 10), ("total", 1)],
    )
    assert got == expected


def test_byte_equivalence_incidents_helper_format() -> None:
    """Identical to the pre-S50 ``_incidents_etag`` output (4 filter axes)."""
    dt = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    rows = [_Row(id="i1", updated_at=dt)]
    expected = _hash(
        [
            "tenant:ten",
            "total:1",
            "limit:50",
            "offset:0",
            "company:co-123",
            "site:",
            "status:reported",
            "type:",
            f"i1:{dt.isoformat()}",
        ]
    )
    got = compute_list_etag(
        tenant_id="ten",
        items=rows,
        scalars=[
            ("total", 1),
            ("limit", 50),
            ("offset", 0),
            ("company", "co-123"),
            ("site", ""),
            ("status", "reported"),
            ("type", ""),
        ],
    )
    assert got == expected


def test_byte_equivalence_inspections_helper_format() -> None:
    """Identical to the pre-S50 ``_inspections_etag`` output (5 filter axes)."""
    dt = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    rows = [_Row(id="ins1", updated_at=dt), _Row(id="ins2", updated_at=dt)]
    expected = _hash(
        [
            "tenant:ten",
            "total:2",
            "limit:50",
            "offset:0",
            "company:",
            "site:",
            "status:planned",
            "type:internal",
            "responsible:resp-1",
            f"ins1:{dt.isoformat()}|ins2:{dt.isoformat()}",
        ]
    )
    got = compute_list_etag(
        tenant_id="ten",
        items=rows,
        scalars=[
            ("total", 2),
            ("limit", 50),
            ("offset", 0),
            ("company", ""),
            ("site", ""),
            ("status", "planned"),
            ("type", "internal"),
            ("responsible", "resp-1"),
        ],
    )
    assert got == expected


# -----------------------------------------------------------------------------
# Anti-leak: tenant-prefix participation
# -----------------------------------------------------------------------------


def test_tenant_id_always_first_part_of_hash() -> None:
    """``tenant:{id}`` must be the first hash part so different tenants never collide.

    A refactor that dropped tenant from the hash would let one tenant see
    another's 304. Guard regression here.
    """
    rows = [_Row(id="r1", updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc))]
    scalars = [("total", 1), ("limit", 50)]
    tenant_a = compute_list_etag(tenant_id="A", items=rows, scalars=scalars)
    tenant_b = compute_list_etag(tenant_id="B", items=rows, scalars=scalars)
    assert tenant_a != tenant_b
    # And reflect this by reconstructing — tenant goes first.
    expected_a = _hash(
        [
            "tenant:A",
            "total:1",
            "limit:50",
            f"r1:{datetime(2026, 5, 1, tzinfo=timezone.utc).isoformat()}",
        ]
    )
    assert tenant_a == expected_a
