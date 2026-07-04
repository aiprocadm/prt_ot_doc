"""wa08 adds the ppe_supplier directory + batch/item provenance FKs (P10-06)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260704_wa08_ppe_supplier.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("wa08_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_migration_file_exists():
    assert _MIGRATION.exists()


def test_migration_revision_metadata():
    mod = _load()
    assert mod.revision == "20260704_wa08_ppe_supplier"
    assert mod.down_revision == "20260704_wa07_ppe_stock_batch_location_unique"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade():
    mod = _load()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_shape():
    nospace = "".join(_MIGRATION.read_text(encoding="utf-8").split())
    assert 'create_table("ppe_supplier"' in nospace
    assert '"uq_ppe_supplier_name"' in nospace
    assert 'add_column("ppe_stock_batch"' in nospace
    assert 'add_column("ppeitem"' in nospace
    assert '"supplier_id"' in nospace
    assert '"preferred_supplier_id"' in nospace
    assert 'ondelete="SETNULL"' in nospace  # "SET NULL" with spaces stripped
    assert 'drop_table("ppe_supplier")' in nospace
