"""Pin: corrective migration dropping the cross-base featureenablement->feature
FK (W-A / TZ-3.2-V11-01)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260530_wa02_featureenablement_drop_feature_fk.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("wa02_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260530_wa02_featureenablement_drop_feature_fk"
    # Chains off the W-A head (ppe_stock_batch), keeping this on the W-A branch.
    assert mod.down_revision == "20260529_wa01_ppe_stock_batch"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)

    src = _MIGRATION.read_text(encoding="utf-8")
    # Upgrade drops the (Postgres default-named) cross-base FK, idempotently.
    assert "DROP CONSTRAINT IF EXISTS" in src
    assert "featureenablement_feature_id_fkey" in src
    # Postgres-guarded so the SQLite create_all path is unaffected.
    assert 'dialect.name == "postgresql"' in src
    # Downgrade restores the FK for reversibility.
    assert "create_foreign_key" in src
