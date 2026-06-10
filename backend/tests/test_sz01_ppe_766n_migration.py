"""sz01 migration + model shape: 766н fields, item_id on norms, VARCHAR status."""
from __future__ import annotations

import re
from pathlib import Path

from app.models.models import Person, PPEIssue, PPEIssueStatus, PPENorm

MIGRATION = Path(__file__).resolve().parents[1] / "app" / "migrations" / "versions" / "20260610_sz01_ppe_norms_card_766n.py"


def test_ppenorm_has_item_id():
    cols = PPENorm.__table__.c
    assert "item_id" in cols
    assert cols["item_id"].nullable is True


def test_person_has_ppe_sizes_json():
    assert "ppe_sizes" in Person.__table__.c
    assert Person.__table__.c["ppe_sizes"].nullable is True


def test_ppeissue_766n_columns():
    cols = PPEIssue.__table__.c
    for name in (
        "certificate_no", "wear_percent", "return_wear_percent",
        "signature_doc_ref", "writeoff_reason", "replaces_issue_id",
    ):
        assert name in cols, name
        assert cols[name].nullable is True, name


def test_ppeissue_status_is_varchar_not_native_enum():
    col = PPEIssue.__table__.c["status"]
    # String(32), NOT sqlalchemy Enum
    assert type(col.type).__name__ == "String"
    assert col.type.length == 32


def test_status_enum_has_all_five_values():
    assert {m.value for m in PPEIssueStatus} == {
        "issued", "returned", "written_off", "replaced", "lost",
    }


def test_migration_revision_chain():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260610_sz01_ppe_norms_card_766n"' in src
    assert 'down_revision = "20260610_con02_contractor_document_requirements"' in src


def test_migration_converts_status_and_drops_enum_type():
    src = MIGRATION.read_text(encoding="utf-8")
    # PG branch: USING lower(...), then drop the orphan enum type
    assert re.search(r"USING\s+lower\(status::text\)", src)
    assert "DROP TYPE IF EXISTS ppeissuestatus" in src
    # additive columns present
    for name in (
        "item_id", "ppe_sizes", "certificate_no", "wear_percent",
        "return_wear_percent", "signature_doc_ref", "writeoff_reason",
        "replaces_issue_id",
    ):
        assert name in src, name


def test_migration_downgrade_guards_new_values():
    src = MIGRATION.read_text(encoding="utf-8")
    # honest asymmetry: downgrade must refuse if written_off/replaced rows exist
    assert "written_off" in src and "replaced" in src
    assert "RuntimeError" in src
