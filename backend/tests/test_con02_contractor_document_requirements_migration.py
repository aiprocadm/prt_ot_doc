from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260610_con02_contractor_document_requirements.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("con02_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_model_table_and_columns() -> None:
    from app.modules.contractors.models import ContractorDocumentRequirement

    assert ContractorDocumentRequirement.__tablename__ == "contractor_document_requirement"
    cols = set(ContractorDocumentRequirement.__table__.columns.keys())
    assert {
        "id", "tenant_id", "version", "created_at", "updated_at", "deleted_at",
        "doc_type", "scope", "mandatory",
    } <= cols


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260610_con02_contractor_document_requirements"
    assert mod.down_revision == "20260609_con01_contractor_documents"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
