"""Validation for PPE safety budget + batch unit_cost schemas (P10-06)."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.ppe import PPESafetyBudgetCreate, PPEStockBatchCreate


def test_period_end_before_start_rejected():
    with pytest.raises(ValidationError):
        PPESafetyBudgetCreate(
            name="x", period_start=date(2026, 12, 31), period_end=date(2026, 1, 1), planned_amount=1
        )


def test_planned_amount_non_negative():
    with pytest.raises(ValidationError):
        PPESafetyBudgetCreate(
            name="x", period_start=date(2026, 1, 1), period_end=date(2026, 12, 31), planned_amount=-1
        )


def test_valid_budget_ok():
    b = PPESafetyBudgetCreate(
        name="2026", period_start=date(2026, 1, 1), period_end=date(2026, 12, 31), planned_amount=5000
    )
    assert b.planned_amount == 5000


def test_batch_unit_cost_optional_and_non_negative():
    assert PPEStockBatchCreate(item_id="i", batch_no="B").unit_cost is None
    assert PPEStockBatchCreate(item_id="i", batch_no="B", unit_cost=100).unit_cost == 100
    with pytest.raises(ValidationError):
        PPEStockBatchCreate(item_id="i", batch_no="B", unit_cost=-5)
