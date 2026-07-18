"""wa05 adds an additive ppeitem.min_stock column (P10-06)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260703_wa05_ppeitem_min_stock.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("wa05_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_migration_file_exists():
    assert _MIGRATION.exists(), "wa05 migration missing"


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260703_wa05_ppeitem_min_stock"
    assert mod.down_revision == "20260702_wa04_ppe_stock_movement"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_is_additive_add_column():
    text = _MIGRATION.read_text(encoding="utf-8")
    assert 'op.add_column("ppeitem"' in text
    assert '"min_stock"' in text
    assert 'server_default="0"' in text
    assert 'op.drop_column("ppeitem", "min_stock")' in text
    assert "drop_table" not in text


def test_model_has_min_stock():
    from app.models.ppe import PPEItem

    assert "min_stock" in PPEItem.__table__.columns
    assert PPEItem.__table__.columns["min_stock"].nullable is False
