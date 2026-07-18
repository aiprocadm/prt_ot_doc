"""Pin: so01 СОУТ migration shape (P10-04)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260626_so01_sout.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("so01_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260626_so01_sout"
    assert mod.down_revision == "20260625_cmt01_committees"


def test_upgrade_downgrade_callable() -> None:
    mod = _load()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_file_creates_four_tables() -> None:
    text = _MIGRATION.read_text(encoding="utf-8")
    for table in (
        "sout_campaign",
        "sout_workplace",
        "sout_factor",
        "sout_guarantee",
    ):
        assert f'"{table}"' in text, f"missing create_table for {table}"
    assert text.count("op.drop_table") == 4


def test_shared_soutclass_enum_created_once() -> None:
    """soutclass backs two columns but must be created exactly once."""
    text = _MIGRATION.read_text(encoding="utf-8")
    # one named declaration that emits DDL + one create_type=False reference
    assert text.count('name="soutclass"') == 2
    assert "create_type=False" in text
