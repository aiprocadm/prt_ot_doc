"""Pin: mc02 managed_client_access migration shape (BIZ-49 срез-6)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260804_mc02_managed_client_access.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("mc02_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260804_mc02_managed_client_access"
    assert mod.down_revision == "20260804_mc01_managed_client"


def test_rls_armed_in_the_same_slice() -> None:
    text = _MIGRATION.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "FORCE ROW LEVEL SECURITY" in text


def test_revocation_is_a_column_not_a_delete() -> None:
    """Отзыв доступа обязан оставлять след — иначе прошлое не разобрать."""
    text = _MIGRATION.read_text(encoding="utf-8")
    assert "revoked_at" in text and "revoked_by_user_id" in text
    assert "all_modules" in text and "modules" in text
    assert text.count("op.drop_table") == 1
