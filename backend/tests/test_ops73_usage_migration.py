"""Pin: ops73 api_deprecation_usage migration shape (OPS-73 срез-3)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260803_ops73_api_deprecation_usage.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("ops73_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260803_ops73_api_deprecation_usage"
    assert mod.down_revision == "20260803_sec65_rls_committee_invitation"


def test_migration_shape() -> None:
    text = _MIGRATION.read_text(encoding="utf-8")
    assert '"api_deprecation_usage"' in text
    assert "tenant_slug" in text
    # намеренно платформенная таблица: колонки tenant_id/FK нет — вне RLS-контура
    assert 'sa.Column("tenant_id"' not in text
    assert "uq_api_deprecation_usage" in text
    assert text.count("op.drop_table") == 1
