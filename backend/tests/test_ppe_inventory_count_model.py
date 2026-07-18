"""Pin: PPEInventoryCount(+Line) ORM shape (P10-06 inventory count)."""

from __future__ import annotations


def test_inventory_count_header_table_and_columns():
    from app.models.ppe import PPEInventoryCount

    assert PPEInventoryCount.__tablename__ == "ppe_inventory_count"
    cols = set(PPEInventoryCount.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "status",
        "scope_item_id",
        "scope_location",
        "note",
        "applied_at",
        "deleted_at",
        "version",
    } <= cols


def test_inventory_count_line_table_and_columns():
    from app.models.ppe import PPEInventoryCountLine

    assert PPEInventoryCountLine.__tablename__ == "ppe_inventory_count_line"
    cols = set(PPEInventoryCountLine.__table__.columns.keys())
    assert {
        "count_id",
        "item_id",
        "batch_id",
        "system_qty",
        "counted_qty",
        "adjustment_movement_id",
    } <= cols
    assert "deleted_at" not in cols  # line has no SoftDeleteMixin
    assert PPEInventoryCountLine.__table__.columns["counted_qty"].nullable is True
    assert PPEInventoryCountLine.__table__.columns["system_qty"].nullable is False


def test_inventory_count_reexported_from_models():
    from app.models.models import PPEInventoryCount, PPEInventoryCountLine  # noqa: F401
