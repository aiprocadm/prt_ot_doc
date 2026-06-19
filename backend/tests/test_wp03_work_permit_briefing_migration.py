"""Guard: wp03 chains from wp02 and creates work_permit_briefing (additive)."""
import importlib.util
from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[1]
    / "app/migrations/versions/20260618_wp03_work_permit_briefing.py"
)

NEW_COLUMNS = {"work_permit_id", "conducted_by_person_id", "conducted_at", "topics_text"}


def _load():
    spec = importlib.util.spec_from_file_location("wp03_mig", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wp03_chain_and_revision():
    mod = _load()
    assert mod.revision == "20260618_wp03_work_permit_briefing"
    assert mod.down_revision == "20260617_wp02_work_permit_782n_fields"


def test_wp03_source_creates_and_drops_table():
    src = MIG.read_text(encoding="utf-8")
    assert 'create_table(\n        "work_permit_briefing"' in src or 'create_table("work_permit_briefing"' in src
    for col in NEW_COLUMNS:
        assert f'"{col}"' in src, f"missing column literal: {col}"
    assert 'drop_table("work_permit_briefing")' in src, "downgrade must drop the table"


def test_model_has_briefing_columns():
    from app.models.work_permit import WorkPermitBriefing

    cols = set(WorkPermitBriefing.__table__.columns.keys())
    assert NEW_COLUMNS.issubset(cols)
    assert WorkPermitBriefing.__tablename__ == "work_permit_briefing"
