"""Chain + shape guard for med02 (medical_factor catalog + risk_hazards link)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260613_med02_medical_factor_catalog.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("med02_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_med02_chains_to_ed03():
    mod = _load()
    assert mod.revision == "20260613_med02_medical_factor_catalog"
    assert mod.down_revision == "20260612_ed03_briefing_signature_unique"
    assert mod.depends_on is None


def test_med02_creates_table_and_column_with_literal_names():
    src = _MIGRATION.read_text(encoding="utf-8")
    assert "create_table(" in src and '"medical_factor"' in src
    for col in (
        "code",
        "name",
        "category",
        "exam_kinds",
        "periodicity_months",
        "participants",
        "lab_tests",
    ):
        assert f'"{col}"' in src
    assert "add_column(" in src and '"risk_hazards"' in src and '"medical_factor_code"' in src
    # round-trip-safe downgrade: drop column then table
    assert 'drop_column("risk_hazards", "medical_factor_code")' in src
    assert 'drop_table("medical_factor")' in src
