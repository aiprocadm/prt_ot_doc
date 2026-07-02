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
        super().__init__(f"insufficient stock: requested {requested}, available {available}")
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


@dataclass(slots=True, frozen=True)
class ShortageProjection:
    below_threshold: bool
    deficit: int
    days_to_depletion: float | None
    days_to_threshold: float | None


def project_shortage(on_hand: int, min_stock: int, avg_daily: float) -> ShortageProjection:
    """Pure shortage math. ``avg_daily`` is average daily consumption (issues).

    - below_threshold: a positive threshold is set and on-hand is under it.
    - deficit: units to reorder back up to the threshold.
    - days_to_depletion: on_hand / avg_daily (None when there is no consumption).
    - days_to_threshold: days until on-hand reaches the threshold (0 if already
      at/below it; None when there is no consumption).
    """
    below_threshold = min_stock > 0 and on_hand < min_stock
    deficit = max(0, min_stock - on_hand)
    if avg_daily > 0:
        days_to_depletion: float | None = on_hand / avg_daily
        days_to_threshold: float | None = max(0, on_hand - min_stock) / avg_daily
    else:
        days_to_depletion = None
        days_to_threshold = None
    return ShortageProjection(
        below_threshold=below_threshold,
        deficit=deficit,
        days_to_depletion=days_to_depletion,
        days_to_threshold=days_to_threshold,
    )


async def _load_batch(
    session: AsyncSession,
    tenant_id: str,
    batch_id: str,
    *,
    item_id: str | None = None,
) -> PPEStockBatch:
    stmt = select(PPEStockBatch).where(
        PPEStockBatch.id == batch_id,
        PPEStockBatch.tenant_id == tenant_id,
        PPEStockBatch.deleted_at.is_(None),
    )
    if item_id is not None:
        stmt = stmt.where(PPEStockBatch.item_id == item_id)
    batch = (await session.execute(stmt)).scalar_one_or_none()
    if batch is None:
        raise StockBatchNotFound(batch_id)
    return batch


async def _write_movement(
    session: AsyncSession,
    *,
    tenant_id: str,
    batch: PPEStockBatch,
    kind: str,
    delta: int,
    reason: str | None = None,
    occurred_at: datetime | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
) -> PPEStockMovement:
    """Apply ``delta`` to the batch balance and append the journal row.

    The ONLY place ``batch.quantity`` is mutated. Guards on-hand >= 0.
    """
    new_qty = batch.quantity + delta
    if new_qty < 0:
        raise InsufficientStockError(requested=-delta, available=batch.quantity)
    batch.quantity = new_qty
    movement = PPEStockMovement(
        tenant_id=tenant_id,
        item_id=batch.item_id,
        batch_id=batch.id,
        kind=kind,
        quantity_delta=delta,
        occurred_at=occurred_at or datetime.now(tz=timezone.utc),
        reason=reason,
        ref_type=ref_type,
        ref_id=ref_id,
    )
    session.add(movement)
    await session.flush()
    await session.refresh(movement)
    return movement


async def record_movement(
    session: AsyncSession,
    *,
    tenant_id: str,
    batch_id: str,
    kind: str,
    quantity: int,
    reason: str | None = None,
    occurred_at: datetime | None = None,
) -> PPEStockMovement:
    """Manual receipt / writeoff / adjustment against one batch.

    - receipt: +quantity   (quantity must be > 0)
    - writeoff: -quantity   (quantity must be > 0)
    - adjustment: set the batch to an absolute ``quantity`` (>= 0)
    """
    if kind not in MANUAL_KINDS:
        raise ValueError(f"unsupported manual movement kind: {kind}")
    batch = await _load_batch(session, tenant_id, batch_id)
    if kind == KIND_RECEIPT:
        if quantity <= 0:
            raise ValueError("receipt quantity must be positive")
        delta = quantity
    elif kind == KIND_WRITEOFF:
        if quantity <= 0:
            raise ValueError("writeoff quantity must be positive")
        delta = -quantity
    else:  # KIND_ADJUSTMENT — set-to absolute
        delta = quantity - batch.quantity
    return await _write_movement(
        session,
        tenant_id=tenant_id,
        batch=batch,
        kind=kind,
        delta=delta,
        reason=reason,
        occurred_at=occurred_at,
    )


async def deplete_for_issue(
    session: AsyncSession,
    *,
    tenant_id: str,
    item_id: str,
    quantity: int,
    batch_id: str | None = None,
    ref_id: str,
) -> list[PPEStockMovement]:
    """Deplete stock for a worker issuance. Returns the ``issue`` movements.

    No-op (returns ``[]``) when the warehouse flag is off for the tenant or the
    item has no stock batches — this preserves the pre-ledger issuance behaviour.
    Explicit ``batch_id`` depletes that batch; otherwise FIFO by ``received_at``
    (nulls last), then ``created_at`` (insertion order) and ``id`` as tiebreakers.
    Raises :class:`InsufficientStockError` when the requested quantity exceeds
    available on-hand.
    """
    if quantity <= 0:
        return []
    if not await is_feature_enabled(session, tenant_id, WAREHOUSE_FEATURE_CODE):
        return []

    if batch_id is not None:
        candidates = [await _load_batch(session, tenant_id, batch_id, item_id=item_id)]
    else:
        stmt = (
            select(PPEStockBatch).where(
                PPEStockBatch.tenant_id == tenant_id,
                PPEStockBatch.item_id == item_id,
                PPEStockBatch.deleted_at.is_(None),
                PPEStockBatch.quantity > 0,
            )
            # portable NULLS LAST: is_(None) sorts False(0) before True(1).
            # created_at breaks same-received_at ties by insertion order (true
            # FIFO); id is a final deterministic tiebreaker (uuid, not ordered).
            .order_by(
                PPEStockBatch.received_at.is_(None),
                PPEStockBatch.received_at.asc(),
                PPEStockBatch.created_at.asc(),
                PPEStockBatch.id.asc(),
            )
        )
        candidates = list((await session.execute(stmt)).scalars().all())
        if not candidates:
            return []

    by_id = {b.id: b for b in candidates}
    allocations = allocate_fifo([(b.id, b.quantity) for b in candidates], quantity)

    movements: list[PPEStockMovement] = []
    for alloc in allocations:
        movements.append(
            await _write_movement(
                session,
                tenant_id=tenant_id,
                batch=by_id[alloc.batch_id],
                kind=KIND_ISSUE,
                delta=-alloc.taken,
                ref_type="ppe_issue",
                ref_id=ref_id,
            )
        )
    return movements
