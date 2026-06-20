"""Guard: wp04 chains from wp03, creates daily_admission table + adds event.meta."""
import importlib.util
from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[1]
    / "app/migrations/versions/20260618_wp04_work_permit_ops_journal.py"
)

ADMISSION_COLUMNS = {
    "work_permit_id", "admission_date", "start_at", "end_at",
    "admitted_by_person_id", "note",
}


def _load():
    spec = importlib.util.spec_from_file_location("wp04_mig", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wp04_chain_and_revision():
    mod = _load()
    assert mod.revision == "20260618_wp04_work_permit_ops_journal"
    assert mod.down_revision == "20260618_wp03_work_permit_briefing"


def test_wp04_source_table_and_meta_column():
    src = MIG.read_text(encoding="utf-8")
    assert 'create_table(\n        "work_permit_daily_admission"' in src or 'create_table("work_permit_daily_admission"' in src
    for col in ADMISSION_COLUMNS:
        assert f'"{col}"' in src, f"missing admission column literal: {col}"
    assert 'add_column("work_permit_event"' in src and '"meta"' in src, "must add event.meta"
    # honest downgrade: both drop_column(meta) and drop_table(admission)
    assert 'drop_column("work_permit_event", "meta")' in src
    assert 'drop_table("work_permit_daily_admission")' in src
