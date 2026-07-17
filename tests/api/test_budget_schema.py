"""Validation for cross-domain safety-budget schemas (§12.4 срез-1, task 2)."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.budget import (
    BudgetExpenseCreate,
    SafetyBudgetCreate,
    SafetyBudgetUpdate,
)


def test_budget_period_inversion_rejected():
    with pytest.raises(ValidationError):
        SafetyBudgetCreate(
            name="x",
            domain="training",
            period_start=date(2026, 5, 1),
            period_end=date(2026, 4, 1),
            planned_amount=1,
        )


def test_budget_domain_whitelist():
    with pytest.raises(ValidationError):
        SafetyBudgetCreate(
            name="x",
            domain="ppe",  # СИЗ ведётся на складе, не здесь
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            planned_amount=1,
        )


def test_expense_amount_must_be_positive():
    with pytest.raises(ValidationError):
        BudgetExpenseCreate(domain="events", title="x", occurred_on=date(2026, 1, 1), amount=0)


def test_update_partial_keeps_unset():
    upd = SafetyBudgetUpdate(planned_amount=10)
    assert "name" not in upd.model_dump(exclude_unset=True)


def test_expense_entity_id_without_entity_type_rejected():
    with pytest.raises(ValidationError):
        BudgetExpenseCreate(
            domain="events",
            title="x",
            occurred_on=date(2026, 1, 1),
            amount=10,
            entity_id="x",
        )


def test_expense_valid_with_entity_ref_ok():
    exp = BudgetExpenseCreate(
        domain="events",
        title="x",
        occurred_on=date(2026, 1, 1),
        amount=10,
        entity_type="corrective_action",
        entity_id="abc",
    )
    assert exp.entity_type == "corrective_action"
    assert exp.entity_id == "abc"
