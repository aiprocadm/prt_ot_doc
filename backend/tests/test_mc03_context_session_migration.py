"""Pin: mc03 managed_client_context_session migration shape (BIZ-49 срез-10)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260805_mc03_managed_client_context_session.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("mc03_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260805_mc03_managed_client_context_session"
    assert mod.down_revision == "20260804_mc02_managed_client_access"


def test_rls_armed_in_the_same_slice() -> None:
    text = _MIGRATION.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "FORCE ROW LEVEL SECURITY" in text


def test_exit_is_a_column_not_a_delete() -> None:
    """Клиент вправе запросить журнал доступа к своим данным (разд. 66)."""

    text = _MIGRATION.read_text(encoding="utf-8")
    assert "started_at" in text and "ended_at" in text and "ended_reason" in text
    assert text.count("op.drop_table") == 1
