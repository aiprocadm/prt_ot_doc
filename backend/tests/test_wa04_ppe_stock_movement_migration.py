"""Pin: PPEStockMovement model + ppe_stock_movement migration shape (P10-06)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260702_wa04_ppe_stock_movement.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("wa04_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_ppe_stock_movement_model_table_and_columns() -> None:
    from app.models.models import PPEStockMovement

    assert PPEStockMovement.__tablename__ == "ppe_stock_movement"
    cols = set(PPEStockMovement.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "version",
        "created_at",
        "updated_at",
        "item_id",
        "batch_id",
        "kind",
        "quantity_delta",
        "occurred_at",
        "reason",
        "ref_type",
        "ref_id",
    } <= cols
    # append-only journal: no soft-delete column
    assert "deleted_at" not in cols


def test_ppe_stock_movement_reexported_from_registry() -> None:
    from app.models.ppe_registry import PPEStockMovement  # noqa: F401


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260702_wa04_ppe_stock_movement"
    assert mod.down_revision == "20260702_br01_branch_entity"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'op.create_table(\n        "ppe_stock_movement"' in src
    assert 'op.drop_table("ppe_stock_movement")' in src
