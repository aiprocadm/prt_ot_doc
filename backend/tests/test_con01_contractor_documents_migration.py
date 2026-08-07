"""Pin: ContractorDocument model + con01 migration shape (Подрядчики Срез-2)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260609_con01_contractor_documents.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("con01_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_model_table_and_columns() -> None:
    from app.modules.contractors.models import ContractorDocument

    assert ContractorDocument.__tablename__ == "contractor_documents"
    cols = set(ContractorDocument.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "version",
        "created_at",
        "updated_at",
        "deleted_at",
        "contractor_id",
        "employee_id",
        "doc_type",
        "title",
        "number",
        "issuing_org",
        "issued_at",
        "valid_until",
        "file_id",
        "status",
    } <= cols


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260609_con01_contractor_documents"
    assert mod.down_revision == "20260607_med01_medical_domain"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
