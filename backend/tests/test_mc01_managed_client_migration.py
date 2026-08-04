"""Pin: mc01 managed_client migration shape (BIZ-49 срез-1)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260804_mc01_managed_client.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("mc01_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260804_mc01_managed_client"
    assert mod.down_revision == "20260803_ops73_api_deprecation_usage"


def test_migration_arms_rls_in_the_same_slice() -> None:
    """Урок cmt03: tenant-таблица без RLS = красный сторож на main."""
    text = _MIGRATION.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "FORCE ROW LEVEL SECURITY" in text
    assert "tenant_isolation" in text


def test_migration_shape_and_honest_downgrade() -> None:
    text = _MIGRATION.read_text(encoding="utf-8")
    assert '"managed_client"' in text or '_TABLE = "managed_client"' in text
    assert "dedicated_tenant_slug" in text
    assert "uq_managed_client_name" in text
    assert text.count("op.drop_table") == 1
    # enum'ы, созданные этой миграцией, ею же и снимаются
    assert "_CONTRACT_STATUS.drop" in text and "_MODE.drop" in text
