"""Unit tests for PPE stock transfer schemas (P10-06)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.ppe import (
    PPEStockLevelByLocationRead,
    PPEStockTransferCreate,
    PPEStockTransferRead,
)


def test_transfer_create_valid():
    m = PPEStockTransferCreate(source_batch_id="b1", to_location="B", quantity=3)
    assert m.quantity == 3
    assert m.reason is None


def test_transfer_create_rejects_nonpositive_quantity():
    with pytest.raises(ValidationError):
        PPEStockTransferCreate(source_batch_id="b1", to_location="B", quantity=0)


def test_transfer_create_rejects_empty_location():
    with pytest.raises(ValidationError):
        PPEStockTransferCreate(source_batch_id="b1", to_location="", quantity=1)


def test_transfer_read_shape():
    from datetime import datetime, timezone

    r = PPEStockTransferRead(
        ref_id="r1",
        item_id="i1",
        item_name="Каска",
        batch_no="B-1",
        from_location="A",
        to_location="B",
        quantity=3,
        source_batch_id="s1",
        dest_batch_id="d1",
        out_movement_id="m1",
        in_movement_id="m2",
        reason=None,
        occurred_at=datetime.now(tz=timezone.utc),
    )
    assert r.from_location == "A"
    assert r.to_location == "B"


def test_level_by_location_read_shape():
    r = PPEStockLevelByLocationRead(
        item_id="i1", item_name="Каска", location="A", quantity=7, batch_count=2
    )
    assert r.location == "A"
    assert r.quantity == 7
