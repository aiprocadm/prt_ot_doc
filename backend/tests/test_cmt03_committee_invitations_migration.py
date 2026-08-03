"""Pin: cmt03 committee invitations + quorum threshold migration shape (P10-01 срез-4)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260803_cmt03_committee_invitations_quorum.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("cmt03_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260803_cmt03_committee_invitations_quorum"
    assert mod.down_revision == "20260730_ops71_import_preview_mode"


def test_upgrade_downgrade_callable() -> None:
    mod = _load()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_shape() -> None:
    text = _MIGRATION.read_text(encoding="utf-8")
    assert '"committee_meeting_invitation"' in text
    assert "quorum_threshold_pct" in text
    assert "uq_committee_invitation" in text
    # честный downgrade: таблица + колонка
    assert text.count("op.drop_table") == 1
    assert 'op.drop_column("committee", "quorum_threshold_pct")' in text
