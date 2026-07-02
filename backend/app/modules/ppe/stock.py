"""PPE warehouse stock ledger (P10-06, Approach B).

``batch.quantity`` is the live cached balance; every change to it is recorded as
an immutable ``PPEStockMovement`` in the same transaction. FIFO allocation and
movement recording are the only sanctioned way to mutate stock quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.feature_flags import is_feature_enabled
from app.models.ppe_registry import PPEStockBatch, PPEStockMovement

KIND_RECEIPT = "receipt"
KIND_ISSUE = "issue"
KIND_WRITEOFF = "writeoff"
KIND_ADJUSTMENT = "adjustment"
MANUAL_KINDS = frozenset({KIND_RECEIPT, KIND_WRITEOFF, KIND_ADJUSTMENT})
WAREHOUSE_FEATURE_CODE = "warehouse"


class InsufficientStockError(Exception):
    """Raised when a depletion would drive on-hand below zero."""

    def __init__(self, requested: int, available: int) -> None:
        super().__init__(
            f"insufficient stock: requested {requested}, available {available}"
        )
        self.requested = requested
        self.available = available


class StockBatchNotFound(Exception):
    """Raised when a referenced batch does not exist for the tenant/item."""

    def __init__(self, batch_id: str) -> None:
        super().__init__(f"PPE stock batch not found: {batch_id}")
        self.batch_id = batch_id


@dataclass(slots=True, frozen=True)
class Allocation:
    batch_id: str
    taken: int


def allocate_fifo(available: list[tuple[str, int]], quantity: int) -> list[Allocation]:
    """Allocate ``quantity`` across ``available`` (id, on_hand) pairs, oldest-first.

    ``available`` MUST already be ordered oldest-first by the caller. Raises
    :class:`InsufficientStockError` when the total on-hand is short.
    """
    if quantity <= 0:
        return []
    remaining = quantity
    result: list[Allocation] = []
    for batch_id, on_hand in available:
        if remaining <= 0:
            break
        if on_hand <= 0:
            continue
        take = min(on_hand, remaining)
        result.append(Allocation(batch_id=batch_id, taken=take))
        remaining -= take
    if remaining > 0:
        raise InsufficientStockError(requested=quantity, available=quantity - remaining)
    return result
