"""PPE inventory count (stocktake) workflow (P10-06).

Two-phase count session (``draft`` → ``applied`` / ``cancelled``) layered over the
honest-balance ledger. ``apply`` reconciles physical counts into ``adjustment``
movements through ``record_movement`` — the single sanctioned mutation point for
``batch.quantity``. This module never mutates stock quantity directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ppe import (
    PPEInventoryCount,
    PPEInventoryCountLine,
    PPEItem,
    PPEStockBatch,
)
from app.modules.ppe.stock import KIND_ADJUSTMENT, record_movement

# movement ref_type stamped on adjustment movements by ``apply_count``
INVENTORY_REF_TYPE = "ppe_inventory_count"


class InventoryCountNotFound(Exception):
    """Raised when a count/line does not exist for the tenant."""

    def __init__(self, count_id: str) -> None:
        super().__init__(f"PPE inventory count not found: {count_id}")
        self.count_id = count_id


class InventoryCountNotDraft(Exception):
    """Raised when a mutating action targets a non-``draft`` count."""

    def __init__(self, count_id: str, status: str) -> None:
        super().__init__(f"inventory count {count_id} is not draft (status={status})")
        self.count_id = count_id
        self.status = status


@dataclass(slots=True, frozen=True)
class CountLineView:
    id: str
    batch_id: str
    item_id: str
    batch_no: str
    location: str | None
    item_name: str
    system_qty: int
    counted_qty: int | None
    on_hand: int
    delta: int | None
    adjustment_movement_id: str | None


@dataclass(slots=True, frozen=True)
class CountDetailView:
    count: PPEInventoryCount
    lines: list[CountLineView]
    line_count: int
    counted_count: int
    diff_count: int


@dataclass(slots=True, frozen=True)
class CountSummaryView:
    count: PPEInventoryCount
    line_count: int
    counted_count: int


async def _load_count(session: AsyncSession, tenant_id: str, count_id: str) -> PPEInventoryCount:
    stmt = select(PPEInventoryCount).where(
        PPEInventoryCount.id == count_id,
        PPEInventoryCount.tenant_id == tenant_id,
        PPEInventoryCount.deleted_at.is_(None),
    )
    count = (await session.execute(stmt)).scalar_one_or_none()
    if count is None:
        raise InventoryCountNotFound(count_id)
    return count


async def create_count(
    session: AsyncSession,
    tenant_id: str,
    *,
    scope_item_id: str | None = None,
    scope_location: str | None = None,
    note: str | None = None,
) -> PPEInventoryCount:
    """Open a draft count and seed one line per active batch under the filter."""
    count = PPEInventoryCount(
        tenant_id=tenant_id,
        status="draft",
        scope_item_id=scope_item_id,
        scope_location=scope_location,
        note=note,
    )
    session.add(count)
    await session.flush()

    stmt = select(PPEStockBatch).where(
        PPEStockBatch.tenant_id == tenant_id,
        PPEStockBatch.deleted_at.is_(None),
    )
    if scope_item_id is not None:
        stmt = stmt.where(PPEStockBatch.item_id == scope_item_id)
    if scope_location is not None:
        stmt = stmt.where(PPEStockBatch.location == scope_location)
    batches = list((await session.execute(stmt)).scalars().all())
    for batch in batches:
        session.add(
            PPEInventoryCountLine(
                tenant_id=tenant_id,
                count_id=count.id,
                item_id=batch.item_id,
                batch_id=batch.id,
                system_qty=batch.quantity,
                counted_qty=None,
            )
        )
    await session.flush()
    return count


async def get_count_detail(session: AsyncSession, tenant_id: str, count_id: str) -> CountDetailView:
    """Load a count with per-line live ``on_hand``/``delta`` (this is the preview).

    Batched queries only (no lazy ``line.batch``): no N+1, no soft-deleted leak.
    A line whose batch is soft-deleted/absent reports ``on_hand=0`` and ``delta=None``
    (apply skips such lines).
    """
    count = await _load_count(session, tenant_id, count_id)
    lines = list(
        (
            await session.execute(
                select(PPEInventoryCountLine)
                .where(
                    PPEInventoryCountLine.tenant_id == tenant_id,
                    PPEInventoryCountLine.count_id == count_id,
                )
                .order_by(PPEInventoryCountLine.id.asc())
            )
        )
        .scalars()
        .all()
    )
    batch_ids = [line.batch_id for line in lines]
    item_ids = {line.item_id for line in lines}

    on_hand: dict[str, int] = {}
    batch_no: dict[str, str] = {}
    location: dict[str, str | None] = {}
    if batch_ids:
        rows = (
            await session.execute(
                select(
                    PPEStockBatch.id,
                    PPEStockBatch.quantity,
                    PPEStockBatch.batch_no,
                    PPEStockBatch.location,
                ).where(
                    PPEStockBatch.id.in_(batch_ids),
                    PPEStockBatch.deleted_at.is_(None),
                )
            )
        ).all()
        for bid, qty, bno, loc in rows:
            on_hand[bid] = int(qty or 0)
            batch_no[bid] = bno
            location[bid] = loc

    names: dict[str, str] = {}
    if item_ids:
        name_rows = (
            await session.execute(select(PPEItem.id, PPEItem.name).where(PPEItem.id.in_(item_ids)))
        ).all()
        names = {iid: name for iid, name in name_rows}

    views: list[CountLineView] = []
    counted_count = 0
    diff_count = 0
    for line in lines:
        oh = on_hand.get(line.batch_id, 0)
        batch_present = line.batch_id in on_hand
        if line.counted_qty is not None:
            counted_count += 1
            if batch_present:
                delta: int | None = line.counted_qty - oh
                if delta != 0:
                    diff_count += 1
            else:
                # batch soft-deleted after seeding -> apply skips it; no reconcilable delta
                delta = None
        else:
            delta = None
        views.append(
            CountLineView(
                id=line.id,
                batch_id=line.batch_id,
                item_id=line.item_id,
                batch_no=batch_no.get(line.batch_id, ""),
                location=location.get(line.batch_id),
                item_name=names.get(line.item_id, ""),
                system_qty=line.system_qty,
                counted_qty=line.counted_qty,
                on_hand=oh,
                delta=delta,
                adjustment_movement_id=line.adjustment_movement_id,
            )
        )
    return CountDetailView(
        count=count,
        lines=views,
        line_count=len(lines),
        counted_count=counted_count,
        diff_count=diff_count,
    )


async def set_line_counts(
    session: AsyncSession,
    tenant_id: str,
    *,
    count_id: str,
    entries: list[tuple[str, int | None]],
) -> PPEInventoryCount:
    """Bulk-set ``counted_qty`` on a draft count's lines. ``None`` clears a count."""
    count = await _load_count(session, tenant_id, count_id)
    if count.status != "draft":
        raise InventoryCountNotDraft(count_id, count.status)

    line_ids = [line_id for line_id, _ in entries]
    by_id: dict[str, PPEInventoryCountLine] = {}
    if line_ids:
        rows = (
            (
                await session.execute(
                    select(PPEInventoryCountLine).where(
                        PPEInventoryCountLine.tenant_id == tenant_id,
                        PPEInventoryCountLine.count_id == count_id,
                        PPEInventoryCountLine.id.in_(line_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        by_id = {line.id: line for line in rows}

    for line_id, counted_qty in entries:
        line = by_id.get(line_id)
        if line is None:
            raise InventoryCountNotFound(line_id)
        line.counted_qty = counted_qty
    await session.flush()
    return count


async def list_counts(
    session: AsyncSession,
    tenant_id: str,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[CountSummaryView], int]:
    """Paginated counts (newest first) with cheap per-count line/counted tallies."""
    base = select(PPEInventoryCount).where(
        PPEInventoryCount.tenant_id == tenant_id,
        PPEInventoryCount.deleted_at.is_(None),
    )
    if status is not None:
        base = base.where(PPEInventoryCount.status == status)
    stmt = (
        base.order_by(PPEInventoryCount.created_at.desc(), PPEInventoryCount.id.desc())
        .limit(limit)
        .offset(offset)
    )
    counts = list((await session.execute(stmt)).scalars().all())
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    tallies: dict[str, tuple[int, int]] = {}
    count_ids = [c.id for c in counts]
    if count_ids:
        rows = (
            await session.execute(
                select(
                    PPEInventoryCountLine.count_id,
                    func.count(),
                    func.count(PPEInventoryCountLine.counted_qty),
                )
                .where(
                    PPEInventoryCountLine.tenant_id == tenant_id,
                    PPEInventoryCountLine.count_id.in_(count_ids),
                )
                .group_by(PPEInventoryCountLine.count_id)
            )
        ).all()
        tallies = {cid: (int(lc or 0), int(cc or 0)) for cid, lc, cc in rows}

    views = [
        CountSummaryView(
            count=c,
            line_count=tallies.get(c.id, (0, 0))[0],
            counted_count=tallies.get(c.id, (0, 0))[1],
        )
        for c in counts
    ]
    return views, int(total or 0)


async def apply_count(
    session: AsyncSession, tenant_id: str, *, count_id: str, now: datetime
) -> PPEInventoryCount:
    """Reconcile physical counts into ``adjustment`` movements and freeze the count.

    Emits an adjustment only for counted lines whose ``counted_qty`` differs from the
    **live** batch on-hand (set-to-absolute via ``record_movement``). Uncounted lines,
    zero-delta lines, and lines whose batch is soft-deleted are skipped. Concurrent
    applies are guarded by the ``VersionedMixin`` optimistic lock on the header (the
    losing flush raises ``StaleDataError``, surfaced as 409 at the route).
    """
    count = await _load_count(session, tenant_id, count_id)
    if count.status != "draft":
        raise InventoryCountNotDraft(count_id, count.status)

    lines = list(
        (
            await session.execute(
                select(PPEInventoryCountLine).where(
                    PPEInventoryCountLine.tenant_id == tenant_id,
                    PPEInventoryCountLine.count_id == count_id,
                )
            )
        )
        .scalars()
        .all()
    )
    batch_ids = [line.batch_id for line in lines]
    live: dict[str, int] = {}
    if batch_ids:
        rows = (
            await session.execute(
                select(PPEStockBatch.id, PPEStockBatch.quantity).where(
                    PPEStockBatch.id.in_(batch_ids),
                    PPEStockBatch.deleted_at.is_(None),
                )
            )
        ).all()
        live = {bid: int(qty or 0) for bid, qty in rows}

    for line in lines:
        if line.counted_qty is None:
            continue
        if line.batch_id not in live:
            continue  # batch soft-deleted after seeding
        if line.counted_qty == live[line.batch_id]:
            continue  # zero delta — advisory skip; record_movement is source of truth
        movement = await record_movement(
            session,
            tenant_id=tenant_id,
            batch_id=line.batch_id,
            kind=KIND_ADJUSTMENT,
            quantity=line.counted_qty,
            reason=f"inventory {count_id}",
            ref_type=INVENTORY_REF_TYPE,
            ref_id=count_id,
        )
        line.adjustment_movement_id = movement.id

    count.status = "applied"
    count.applied_at = now
    await session.flush()
    return count


async def cancel_count(
    session: AsyncSession, tenant_id: str, *, count_id: str
) -> PPEInventoryCount:
    """Cancel a draft count. Emits no movements."""
    count = await _load_count(session, tenant_id, count_id)
    if count.status != "draft":
        raise InventoryCountNotDraft(count_id, count.status)
    count.status = "cancelled"
    await session.flush()
    return count
