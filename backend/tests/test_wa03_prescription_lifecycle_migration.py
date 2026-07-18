"""Pin: wa03 prescription lifecycle migration (TZ-3.4-V12-01). App-free."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260530_wa03_prescription_lifecycle.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("wa03_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260530_wa03_prescription_lifecycle"
    assert mod.down_revision == "20260530_wa02_featureenablement_drop_feature_fk"
    assert mod.depends_on is None


def test_upgrade_downgrade_shape() -> None:
    mod = _load()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)

    src = _MIGRATION.read_text(encoding="utf-8")
    # additive columns on inspection_prescription (format-agnostic — tolerant of
    # line-wrapping from ruff/black reflows)
    assert "add_column(" in src
    assert '"inspection_prescription"' in src
    assert '"evidence"' in src
    assert '"closed_at"' in src
    # enum extension, postgres-guarded, idempotent
    assert "ALTER TYPE prescriptionstatus ADD VALUE IF NOT EXISTS 'verified'" in src
    assert 'dialect.name == "postgresql"' in src
    # downgrade drops both columns
    assert 'drop_column("inspection_prescription", "closed_at")' in src
    assert 'drop_column("inspection_prescription", "evidence")' in src
