"""Pin: PPEStockBatch model + ppe_stock_batch migration shape (W-A / TZ-3.2-V11-01)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260529_wa01_ppe_stock_batch.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("wa01_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_ppe_stock_batch_model_table_and_columns() -> None:
    from app.models.models import PPEStockBatch

    assert PPEStockBatch.__tablename__ == "ppe_stock_batch"
    cols = set(PPEStockBatch.__table__.columns.keys())
    # tenant base + soft delete + version + own columns
    assert {
        "id",
        "tenant_id",
        "version",
        "created_at",
        "updated_at",
        "deleted_at",
        "item_id",
        "batch_no",
        "quantity",
        "received_at",
        "certificate_no",
        "certificate_expires_at",
        "location",
    } <= cols
    # wa07 (20260704) replaced the plain UniqueConstraint on
    # (tenant, item, batch_no) with a partial unique *index* that also spans
    # location — so the live model carries an index, not a constraint.
    unique_indexes = {ix.name for ix in PPEStockBatch.__table__.indexes if ix.unique}
    assert "uq_ppe_stock_batch_item_no_loc" in unique_indexes


def test_ppe_stock_batch_reexported_from_registry() -> None:
    from app.models.ppe_registry import PPEStockBatch  # noqa: F401


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260529_wa01_ppe_stock_batch"
    assert isinstance(mod.down_revision, str) and mod.down_revision
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'op.create_table(\n        "ppe_stock_batch"' in src
    assert 'op.drop_table("ppe_stock_batch")' in src
