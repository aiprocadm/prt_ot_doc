"""wa06 creates the additive ppe_inventory_count(+_line) tables (P10-06)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260703_wa06_ppe_inventory_count.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("wa06_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_migration_file_exists():
    assert _MIGRATION.exists(), "wa06 migration missing"


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260703_wa06_ppe_inventory_count"
    assert mod.down_revision == "20260703_wa05_ppeitem_min_stock"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_creates_and_drops_both_tables():
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'op.create_table(\n        "ppe_inventory_count"' in src
    assert 'op.create_table(\n        "ppe_inventory_count_line"' in src
    assert 'op.drop_table("ppe_inventory_count_line")' in src
    assert 'op.drop_table("ppe_inventory_count")' in src
    assert "add_column" not in src  # purely new tables, no existing-table mutation
