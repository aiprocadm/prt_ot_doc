"""Pure FIFO allocation for the PPE stock ledger (P10-06)."""
from __future__ import annotations

import pytest

from app.modules.ppe.stock import Allocation, InsufficientStockError, allocate_fifo


def test_allocate_single_batch_partial() -> None:
    assert allocate_fifo([("b1", 10)], 4) == [Allocation(batch_id="b1", taken=4)]


def test_allocate_exact_single_batch() -> None:
    assert allocate_fifo([("b1", 5)], 5) == [Allocation(batch_id="b1", taken=5)]


def test_allocate_spans_multiple_batches_oldest_first() -> None:
    # caller passes batches already ordered oldest-first
    result = allocate_fifo([("b1", 3), ("b2", 10)], 7)
    assert result == [Allocation("b1", 3), Allocation("b2", 4)]


def test_allocate_skips_empty_batches() -> None:
    result = allocate_fifo([("b1", 0), ("b2", 5)], 5)
    assert result == [Allocation("b2", 5)]


def test_allocate_insufficient_raises_with_available() -> None:
    with pytest.raises(InsufficientStockError) as exc:
        allocate_fifo([("b1", 2), ("b2", 1)], 5)
    assert exc.value.requested == 5
    assert exc.value.available == 3


def test_allocate_zero_quantity_is_noop() -> None:
    assert allocate_fifo([("b1", 5)], 0) == []
