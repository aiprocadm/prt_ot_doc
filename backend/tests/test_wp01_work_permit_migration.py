"""wp01 migration + model shape (mirrors test_sz01/test_prm01 — read file as text)."""
from __future__ import annotations

from pathlib import Path

from app.models.work_permit import WorkPermit, WorkPermitEvent, WorkPermitMember

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260616_wp01_work_permit_tables.py"
)


def test_models_tables_and_status_varchar():
    assert WorkPermit.__tablename__ == "work_permit"
    assert WorkPermitMember.__tablename__ == "work_permit_member"
    assert WorkPermitEvent.__tablename__ == "work_permit_event"
    status = WorkPermit.__table__.c["status"]
    assert type(status.type).__name__ == "String"
    assert status.type.length == 32


def test_migration_revision_chain():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260616_wp01_work_permit_tables"' in src
    assert 'down_revision = "20260615_prm01_permit_status_varchar"' in src


def test_migration_creates_three_tables_with_literal_names():
    src = MIGRATION.read_text(encoding="utf-8")
    for table in ("work_permit", "work_permit_member", "work_permit_event"):
        assert f'"{table}"' in src, table
    # downgrade drops in reverse dependency order (children before parent)
    assert src.index('drop_table("work_permit_event")') < src.index('drop_table("work_permit")')
    assert src.index('drop_table("work_permit_member")') < src.index('drop_table("work_permit")')
