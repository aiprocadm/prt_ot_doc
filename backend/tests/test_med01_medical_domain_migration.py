from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260607_med01_medical_domain.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("med01_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata():
    mod = _load()
    assert mod.revision == "20260607_med01_medical_domain"
    assert mod.down_revision  # non-empty; points at prior head
    assert mod.depends_on is None


def test_migration_is_additive_and_symmetric():
    src = _MIGRATION.read_text(encoding="utf-8")
    for col in ("exam_kind", "fitness", "restrictions", "contraindications",
                "referral_id", "medical_org_name"):
        assert f'"{col}"' in src
    assert 'add_column("medical_exam"' in src
    for tbl in ("medical_norm", "medical_referral", "medical_suspension"):
        assert f'"{tbl}"' in src
        assert f'drop_table("{tbl}")' in src
    for col in ("exam_kind", "fitness", "restrictions", "contraindications",
                "referral_id", "medical_org_name"):
        assert f'drop_column("medical_exam", "{col}")' in src
    assert 'dialect.name == "postgresql"' in src
    assert "DROP TYPE IF EXISTS" in src
