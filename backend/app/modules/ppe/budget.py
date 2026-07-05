"""PPE safety budget service (P10-06 §12.4, СИЗ scope).

Thin CRUD over PPESafetyBudget (mirrors suppliers.py). compute_budget_actual
(procurement actual from the movement ledger) is added in the next task.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ppe_registry import (
    PPEItem,
    PPESafetyBudget,
    PPEStockBatch,
    PPEStockMovement,
)


@dataclass(slots=True, frozen=True)
class BudgetCategoryActual:
    category: str
    amount: float


@dataclass(slots=True, frozen=True)
class BudgetActual:
    actual_total: float
    by_category: list[BudgetCategoryActual]
    priced_receipt_count: int
    unpriced_receipt_count: int


_UPDATABLE_FIELDS = frozenset({"name", "period_start", "period_end", "planned_amount", "notes"})


class BudgetNotFound(Exception):
    def __init__(self, budget_id: str) -> None:
        super().__init__(f"PPE safety budget not found: {budget_id}")
        self.budget_id = budget_id


async def _load_budget(session: AsyncSession, tenant_id: str, budget_id: str) -> PPESafetyBudget:
    stmt = select(PPESafetyBudget).where(
        PPESafetyBudget.id == budget_id,
        PPESafetyBudget.tenant_id == tenant_id,
        PPESafetyBudget.deleted_at.is_(None),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise BudgetNotFound(budget_id)
    return row


async def create_budget(
    session: AsyncSession,
    *,
    tenant_id: str,
    name: str,
    period_start: date,
    period_end: date,
    planned_amount: float = 0,
    notes: str | None = None,
) -> PPESafetyBudget:
    budget = PPESafetyBudget(
        tenant_id=tenant_id,
        name=name,
        period_start=period_start,
        period_end=period_end,
        planned_amount=planned_amount,
        notes=notes,
    )
    session.add(budget)
    await session.flush()
    await session.refresh(budget)
    return budget


async def get_budget(session: AsyncSession, tenant_id: str, budget_id: str) -> PPESafetyBudget:
    return await _load_budget(session, tenant_id, budget_id)


async def list_budgets(
    session: AsyncSession, tenant_id: str, *, limit: int, offset: int
) -> tuple[list[PPESafetyBudget], int]:
    base = (
        PPESafetyBudget.tenant_id == tenant_id,
        PPESafetyBudget.deleted_at.is_(None),
    )
    items = list(
        (
            await session.execute(
                select(PPESafetyBudget)
                .where(*base)
                .order_by(PPESafetyBudget.period_start.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    total = (await session.execute(select(func.count()).where(*base))).scalar_one()
    return items, int(total or 0)


async def update_budget(
    session: AsyncSession, tenant_id: str, budget_id: str, **fields
) -> PPESafetyBudget:
    """Update a budget; only keys in ``_UPDATABLE_FIELDS`` are applied."""
    budget = await _load_budget(session, tenant_id, budget_id)
    for key, value in fields.items():
        if key in _UPDATABLE_FIELDS:
            setattr(budget, key, value)
    await session.flush()
    await session.refresh(budget)
    return budget


async def soft_delete_budget(session: AsyncSession, tenant_id: str, budget_id: str) -> None:
    budget = await _load_budget(session, tenant_id, budget_id)
    budget.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()


async def compute_budget_actual(
    session: AsyncSession, tenant_id: str, period_start: date, period_end: date
) -> BudgetActual:
    """Procurement actual = Σ(receipt quantity × batch.unit_cost) within the period.

    Only ``kind='receipt'`` positive movements count (issue/writeoff/adjustment/
    transfer are not procurement). Receipts on batches without a ``unit_cost`` are
    excluded from the total but counted in ``unpriced_receipt_count`` so callers can
    warn that the figure is incomplete. Single join query — no N+1. The ledger is the
    source of truth for spend, so a later soft-delete of the batch does not un-spend it.
    """
    start_dt = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(period_end, time.max, tzinfo=timezone.utc)
    stmt = (
        select(PPEItem.category, PPEStockMovement.quantity_delta, PPEStockBatch.unit_cost)
        .join(PPEStockBatch, PPEStockMovement.batch_id == PPEStockBatch.id)
        .join(PPEItem, PPEStockMovement.item_id == PPEItem.id)
        .where(
            PPEStockMovement.tenant_id == tenant_id,
            PPEStockMovement.kind == "receipt",
            PPEStockMovement.quantity_delta > 0,
            PPEStockMovement.occurred_at >= start_dt,
            PPEStockMovement.occurred_at <= end_dt,
        )
    )
    rows = (await session.execute(stmt)).all()

    total = 0.0
    priced = 0
    unpriced = 0
    by_cat: dict[str, float] = {}
    for category, delta, unit_cost in rows:
        if unit_cost is None:
            unpriced += 1
            continue
        priced += 1
        amount = float(unit_cost) * int(delta)
        total += amount
        key = category.value if hasattr(category, "value") else (category or "—")
        by_cat[key] = by_cat.get(key, 0.0) + amount

    by_category = [
        BudgetCategoryActual(category=k, amount=v)
        for k, v in sorted(by_cat.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return BudgetActual(
        actual_total=total,
        by_category=by_category,
        priced_receipt_count=priced,
        unpriced_receipt_count=unpriced,
    )
