"""Pin: mc04 managed_client_consent migration shape (BIZ-49 срез-12)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260807_mc04_managed_client_consent.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("mc04_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260807_mc04_managed_client_consent"
    assert mod.down_revision == "20260805_mc03_managed_client_context_session"


def test_rls_armed_in_the_same_slice() -> None:
    """Урок cmt03: tenant-таблица без RLS в той же миграции = красный сторож."""
    text = _MIGRATION.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "FORCE ROW LEVEL SECURITY" in text


def test_revocation_is_a_column_not_a_delete() -> None:
    """Отзыв согласия обязан оставлять след — вопрос аудита, а не истории."""
    text = _MIGRATION.read_text(encoding="utf-8")
    assert "revoked_at" in text and "revoked_by_user_id" in text
    assert "document_ref" in text and "expires_at" in text
    assert text.count("op.drop_table") == 1
