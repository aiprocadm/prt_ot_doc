"""ed01 migration guard: PEP columns on signature_requests, additive + reversible."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")

MIGRATION = Path(__file__).resolve().parents[1] / "app" / "migrations" / "versions" / "20260611_ed01_pep_signing_columns.py"

PEP_COLUMNS = {
    "signer_person_id",
    "content_hash",
    "purpose",
    "confirm_code_hash",
    "confirm_code_expires_at",
    "confirm_attempts",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("ed01_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeBatch:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def alter_column(self, *a, **k):
        return None


class _FakeDialect:
    name = "sqlite"


class _FakeBind:
    dialect = _FakeDialect()


def test_migration_revision_chain():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260611_ed01_pep_signing_columns"' in src
    assert 'down_revision = "20260611_sz02_drop_ppe_family_b_tables"' in src
    assert "depends_on = None" in src


def test_upgrade_adds_exactly_pep_columns(monkeypatch):
    module = _load_module()
    added: list[tuple[str, str]] = []
    monkeypatch.setattr(module.op, "add_column", lambda table, col, *a, **k: added.append((table, col.name)))
    monkeypatch.setattr(module.op, "create_index", lambda *a, **k: None)
    monkeypatch.setattr(module.op, "create_foreign_key", lambda *a, **k: None)
    monkeypatch.setattr(module.op, "execute", lambda *a, **k: None)
    monkeypatch.setattr(module.op, "batch_alter_table", lambda *a, **k: _FakeBatch())
    monkeypatch.setattr(module.op, "get_bind", lambda: _FakeBind())
    module.upgrade()
    assert {(t, c) for t, c in added} == {("signature_requests", c) for c in PEP_COLUMNS}


def test_downgrade_drops_exactly_pep_columns(monkeypatch):
    module = _load_module()
    dropped: list[tuple[str, str]] = []
    monkeypatch.setattr(module.op, "drop_column", lambda table, col, *a, **k: dropped.append((table, col)))
    monkeypatch.setattr(module.op, "drop_index", lambda *a, **k: None)
    monkeypatch.setattr(module.op, "drop_constraint", lambda *a, **k: None)
    monkeypatch.setattr(module.op, "execute", lambda *a, **k: None)
    monkeypatch.setattr(module.op, "batch_alter_table", lambda *a, **k: _FakeBatch())
    monkeypatch.setattr(module.op, "get_bind", lambda: _FakeBind())
    module.downgrade()
    assert {(t, c) for t, c in dropped} == {("signature_requests", c) for c in PEP_COLUMNS}
