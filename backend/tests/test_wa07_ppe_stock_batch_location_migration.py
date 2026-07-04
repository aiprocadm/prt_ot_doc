"""wa07 replaces the batch unique key with a location-aware unique index (P10-06)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260704_wa07_ppe_stock_batch_location_unique.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("wa07_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_migration_file_exists():
    assert _MIGRATION.exists(), "wa07 migration missing"


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260704_wa07_ppe_stock_batch_location_unique"
    assert mod.down_revision == "20260703_wa06_ppe_inventory_count"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_swaps_unique_key():
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'drop_constraint("uq_ppe_stock_batch_item_no"' in src
    assert "uq_ppe_stock_batch_item_no_loc" in src
    assert "nulls_not_distinct" in src.lower()
    assert 'create_unique_constraint("uq_ppe_stock_batch_item_no"' in src
    assert "add_column" not in src
    # partial index so soft-deleted rows don't occupy the (item, batch_no, location) slot
    assert "deleted_at IS NULL" in src
