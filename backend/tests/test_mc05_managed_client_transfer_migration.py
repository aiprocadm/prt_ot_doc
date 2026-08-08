"""Pin: mc05 managed_client_transfer migration shape (BIZ-49 срез-14)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260808_mc05_managed_client_transfer.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("mc05_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260808_mc05_managed_client_transfer"
    assert mod.down_revision == "20260807_mc04_managed_client_consent"


def test_rls_armed_in_the_same_slice() -> None:
    """Урок cmt03: tenant-таблица без RLS в той же миграции = красный сторож."""
    text = _MIGRATION.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "FORCE ROW LEVEL SECURITY" in text


def test_journal_keeps_id_map() -> None:
    """Без соответствия id «сохранение timeline» — угадывание, кто есть кто."""
    text = _MIGRATION.read_text(encoding="utf-8")
    assert "id_map" in text and "counts" in text
    assert "target_tenant_slug" in text
    assert text.count("op.drop_table") == 1
