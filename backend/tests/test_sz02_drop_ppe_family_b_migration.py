"""sz02 migration guard: dead family-B PPE tables are dropped, exactly and reversibly.

Family-B PPE (next58: ppe_catalog/ppe_norms/.../ppe_personal_card_items) plus
the orphan ``warehouseppe`` (initial schema) lost their ORM classes in СИЗ
Срез-1 (PR #647); sz02 drops the tables. These tests pin:

  * the revision chain (on top of sz01);
  * that the migration drops EXACTLY the seven dead tables — never the live
    family-A tables (ppenorm/ppeissue/... — no underscores);
  * FK-safe ordering both ways (children dropped first, parents recreated first);
  * that the downgrade restores everything ``downgrade base`` walks through
    later (next58's three explicit indexes, warehouseppe's index, and the
    iter37 ``server_default="0"`` state on ``warehouseppe.quantity``).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

# Hermetic env defaults (same shape as test_orm_mapper_configuration.py) so
# importing the app's model graph never depends on ambient config / .env.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260611_sz02_drop_ppe_family_b_tables.py"
)

FAMILY_B_TABLES = {
    "ppe_personal_card_items",
    "ppe_personal_cards",
    "ppe_issues",
    "ppe_norm_items",
    "ppe_norms",
    "ppe_catalog",
    "warehouseppe",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("sz02_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260611_sz02_drop_ppe_family_b_tables"' in src
    assert 'down_revision = "20260610_sz01_ppe_norms_card_766n"' in src
    assert "depends_on = None" in src


def test_dropped_tables_have_no_orm_mapping():
    """Every table sz02 drops must be absent from BOTH declarative registries,
    while the live family-A PPE tables stay mapped — proof we are dropping the
    dead contour, not the live one."""
    import app.db.base  # noqa: F401  # side-effect: registers every model
    from app.db.session import SharedBase, TenantBase

    mapped = set(SharedBase.metadata.tables) | set(TenantBase.metadata.tables)
    leaked = FAMILY_B_TABLES & mapped
    assert not leaked, f"sz02 would drop tables still mapped by the ORM: {sorted(leaked)}"

    # contrast guard: live family-A PPE tables (no underscores) ARE mapped
    for live in ("ppenorm", "ppeissue", "ppe_stock_batch"):
        assert live in mapped, f"live family-A table {live!r} missing from ORM metadata"


def test_upgrade_drops_exactly_family_b_in_fk_safe_order(monkeypatch):
    module = _load_module()

    dropped: list[str] = []
    monkeypatch.setattr(module.op, "drop_table", lambda name, *a, **k: dropped.append(name))

    module.upgrade()

    assert set(dropped) == FAMILY_B_TABLES
    assert len(dropped) == len(FAMILY_B_TABLES), "a table is dropped twice"

    # children strictly before their parents
    order = {name: i for i, name in enumerate(dropped)}
    for child, parent in [
        ("ppe_personal_card_items", "ppe_personal_cards"),
        ("ppe_personal_card_items", "ppe_issues"),
        ("ppe_personal_card_items", "ppe_catalog"),
        ("ppe_issues", "ppe_norm_items"),
        ("ppe_issues", "ppe_catalog"),
        ("ppe_norm_items", "ppe_norms"),
        ("ppe_norm_items", "ppe_catalog"),
    ]:
        assert order[child] < order[parent], f"{child} must drop before {parent}"


def test_downgrade_recreates_tables_indexes_and_iter37_state(monkeypatch):
    module = _load_module()

    created: dict[str, dict] = {}
    indexes: list[tuple[str, str]] = []
    create_order: list[str] = []

    def fake_create_table(name, *cols, **kw):
        created[name] = {c.name: c for c in cols if hasattr(c, "name") and c.name}
        create_order.append(name)

    monkeypatch.setattr(module.op, "create_table", fake_create_table)
    monkeypatch.setattr(
        module.op, "create_index", lambda idx, table, *a, **k: indexes.append((idx, table))
    )
    monkeypatch.setattr(module.op, "f", lambda name: name)

    module.downgrade()

    # every dropped table comes back, none extra
    assert set(created) == FAMILY_B_TABLES

    # parents strictly before children
    order = {name: i for i, name in enumerate(create_order)}
    for parent, child in [
        ("ppe_catalog", "ppe_norm_items"),
        ("ppe_norms", "ppe_norm_items"),
        ("ppe_norm_items", "ppe_issues"),
        ("ppe_catalog", "ppe_issues"),
        ("ppe_personal_cards", "ppe_personal_card_items"),
        ("ppe_issues", "ppe_personal_card_items"),
    ]:
        assert order[parent] < order[child], f"{parent} must be recreated before {child}"

    # next58's downgrade drops these three indexes explicitly; sz02's downgrade
    # must restore them or `alembic downgrade base` breaks at next58 on PG.
    assert ("ix_ppe_norm_items_filter", "ppe_norm_items") in indexes
    assert ("ix_ppe_issues_filter", "ppe_issues") in indexes
    assert ("ix_ppe_personal_card_items_filter", "ppe_personal_card_items") in indexes
    # initial schema's downgrade drops warehouseppe's tenant index explicitly.
    assert ("ix_warehouseppe_tenant_id", "warehouseppe") in indexes

    # iter37 state: warehouseppe.quantity carries server_default "0" at sz01,
    # so the recreated table must too (iter37's downgrade resets it later).
    quantity = created["warehouseppe"]["quantity"]
    assert quantity.server_default is not None
    assert str(quantity.server_default.arg) == "0"

    # warehouseppe shape sanity: initial-schema columns, no deleted_at
    assert set(created["warehouseppe"]) == {
        "item_name",
        "quantity",
        "location",
        "tenant_id",
        "created_at",
        "updated_at",
        "version",
        "id",
    }
