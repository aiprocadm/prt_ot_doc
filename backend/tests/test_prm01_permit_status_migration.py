"""prm01 migration + model shape: Permit.status is VARCHAR(32), not native enum."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.models import Permit, PermitStatus

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260615_prm01_permit_status_varchar.py"
)


def test_permit_status_is_varchar_not_native_enum():
    col = Permit.__table__.c["status"]
    assert type(col.type).__name__ == "String"
    assert col.type.length == 32


def test_permit_status_enum_values_lowercase():
    assert {m.value for m in PermitStatus} == {"active", "expired", "revoked"}


def test_migration_revision_chain():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260615_prm01_permit_status_varchar"' in src
    assert 'down_revision = "20260614_drift01_orm_pg_column_closure"' in src


def test_migration_converts_status_and_drops_enum_type():
    src = MIGRATION.read_text(encoding="utf-8")
    assert "VARCHAR(32)" in src
    assert re.search(r"USING\s+lower\(status::text\)", src)
    assert "DROP TYPE IF EXISTS permitstatus" in src
    assert re.search(r"USING\s+upper\(status\)", src)
