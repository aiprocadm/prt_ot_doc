"""wa05 adds an additive ppeitem.min_stock column (P10-06)."""

from __future__ import annotations

import pathlib

MIGRATION = pathlib.Path("backend/app/migrations/versions/20260703_wa05_ppeitem_min_stock.py")


def test_migration_file_exists():
    assert MIGRATION.exists(), "wa05 migration missing"


def test_migration_is_additive_add_column():
    text = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260703_wa05_ppeitem_min_stock"' in text
    assert 'down_revision = "20260702_wa04_ppe_stock_movement"' in text
    assert 'op.add_column("ppeitem"' in text
    assert '"min_stock"' in text
    assert 'server_default="0"' in text
    assert 'op.drop_column("ppeitem", "min_stock")' in text
    assert "drop_table" not in text


def test_model_has_min_stock():
    from app.models.ppe import PPEItem

    assert "min_stock" in PPEItem.__table__.columns
    assert PPEItem.__table__.columns["min_stock"].nullable is False
