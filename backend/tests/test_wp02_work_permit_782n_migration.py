"""Guard: wp02 chains from wp01 and adds exactly the 782н columns (additive)."""
import importlib.util
from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[1]
    / "app/migrations/versions/20260617_wp02_work_permit_782n_fields.py"
)

NEW_COLUMNS = {
    "subdivision_text", "content_text", "conditions_text", "safety_systems",
    "measures_before_text", "measures_during_text", "special_conditions_text", "ppe_text",
}


def _load():
    spec = importlib.util.spec_from_file_location("wp02_mig", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wp02_chain_and_revision():
    mod = _load()
    assert mod.revision == "20260617_wp02_work_permit_782n_fields"
    assert mod.down_revision == "20260616_wp01_work_permit_tables"


def test_wp02_source_adds_and_drops_all_columns():
    src = MIG.read_text(encoding="utf-8")
    for col in NEW_COLUMNS:
        assert f'add_column("work_permit"' in src or "add_column(\n" in src  # additive present
        assert f'"{col}"' in src, f"missing column literal: {col}"
        assert f'drop_column("work_permit", "{col}")' in src, f"downgrade missing: {col}"


def test_model_has_782n_columns():
    from app.models.work_permit import WorkPermit

    cols = set(WorkPermit.__table__.columns.keys())
    assert NEW_COLUMNS.issubset(cols)
