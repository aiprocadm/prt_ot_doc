"""Chain + shape guard for ed04 (BriefingTemplate.require_signature_code)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260613_ed04_briefing_require_signature_code.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("ed04_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_ed04_chains_to_med02():
    mod = _load()
    assert mod.revision == "20260613_ed04_briefing_require_signature_code"
    assert mod.down_revision == "20260613_med02_medical_factor_catalog"
    assert mod.depends_on is None


def test_ed04_adds_column_with_literal_names():
    src = _MIGRATION.read_text(encoding="utf-8")
    assert "add_column(" in src and '"briefing_templates"' in src
    assert '"require_signature_code"' in src
    assert "server_default=sa.false()" in src
    # honest downgrade drops the column
    assert 'drop_column("briefing_templates", "require_signature_code")' in src
