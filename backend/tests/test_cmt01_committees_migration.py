"""Pin: cmt01 committees migration shape (P10-01)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260625_cmt01_committees.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("cmt01_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260625_cmt01_committees"
    assert mod.down_revision == "20260623_cm01_company_status_tags_person_position"


def test_upgrade_downgrade_callable() -> None:
    mod = _load()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_file_creates_six_tables() -> None:
    text = _MIGRATION.read_text(encoding="utf-8")
    for table in (
        "committee",
        "committee_member",
        "committee_meeting",
        "committee_agenda_item",
        "committee_decision",
        "committee_decision_task",
    ):
        assert f'"{table}"' in text, f"missing create_table for {table}"
    assert text.count("op.drop_table") == 6
