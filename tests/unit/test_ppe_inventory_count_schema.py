"""Schema shape for the PPE inventory-count slice (P10-06)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.ppe import (
    PPEInventoryCountCreate,
    PPEInventoryCountDetail,
    PPEInventoryCountLinesUpdate,
)


def test_create_defaults_are_optional():
    payload = PPEInventoryCountCreate()
    assert payload.scope_item_id is None
    assert payload.scope_location is None
    assert payload.note is None


def test_lines_update_accepts_null_and_nonnegative():
    upd = PPEInventoryCountLinesUpdate(
        entries=[{"line_id": "l1", "counted_qty": 0}, {"line_id": "l2", "counted_qty": None}]
    )
    assert upd.entries[0].counted_qty == 0
    assert upd.entries[1].counted_qty is None


def test_lines_update_rejects_negative_counted():
    with pytest.raises(ValidationError):
        PPEInventoryCountLinesUpdate(entries=[{"line_id": "l1", "counted_qty": -1}])


def test_detail_carries_diff_count_and_lines():
    fields = set(PPEInventoryCountDetail.model_fields.keys())
    assert {"diff_count", "lines", "line_count", "counted_count", "status"} <= fields
