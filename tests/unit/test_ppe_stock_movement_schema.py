"""Schema contract for stock movements + issue batch_id (P10-06)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.ppe import (
    PPEIssueCreate,
    PPEStockBatchUpdate,
    PPEStockMovementCreate,
)


def test_movement_create_accepts_valid_kind() -> None:
    m = PPEStockMovementCreate(batch_id="b1", kind="receipt", quantity=5)
    assert m.kind == "receipt"


def test_movement_create_rejects_issue_kind() -> None:
    with pytest.raises(ValidationError):
        PPEStockMovementCreate(batch_id="b1", kind="issue", quantity=5)


def test_movement_create_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        PPEStockMovementCreate(batch_id="b1", kind="teleport", quantity=5)


def test_issue_create_has_optional_batch_id() -> None:
    assert PPEIssueCreate(person_id="p", item_id="i").batch_id is None
    assert PPEIssueCreate(person_id="p", item_id="i", batch_id="b").batch_id == "b"


def test_batch_update_drops_quantity() -> None:
    assert "quantity" not in PPEStockBatchUpdate.model_fields
