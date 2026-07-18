"""Pin tests for ``PPEItem`` (``ppeitem`` table) schema parity.

iter-24 RB-002n (NEW release-blocker class — same anti-pattern as iter-23
RefreshSession/SecurityAuditLog). Discovered by
``scripts/audit/check_orm_migration_drift.py`` (Session 71 ``--summary``
classified it as ``critical``).

Migration ``20260527_iter24_journal_ppeitem`` creates the table with two
tenant-scoped unique constraints, the ``ppeitemcategory`` PG enum, and a
tenant index. This file pins the model-side contract so future regressions —
removing a unique constraint, renaming the enum, dropping a column — trip
backend-tests before reaching Postgres.

Note: ``PPEIssue.item_id`` declares ``ForeignKey("ppeitem.id", ondelete=
"SET NULL")`` in the model but the legacy ``6b6dee7c951f_initial_schema.py``
that creates ``ppeissue`` does NOT yet add the ``item_id`` column. That is a
separate business-drift fix; out of iter-24 scope.
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.models import PPEItem, PPEItemCategory


def test_ppeitem_has_required_columns() -> None:
    columns = inspect(PPEItem).columns
    required = {
        "id",
        "tenant_id",
        "name",
        "code",
        "category",
        "description",
        "default_wear_days",
        "metadata_json",
        "deleted_at",
        "created_at",
        "updated_at",
        "version",
    }
    assert required.issubset(columns.keys()), (
        f"ppeitem missing columns: {required - set(columns.keys())}"
    )


def test_ppeitem_category_uses_ppeitemcategory_enum() -> None:
    column = inspect(PPEItem).columns["category"]
    assert column.type.enum_class is PPEItemCategory, (
        "ppeitem.category must be Enum(PPEItemCategory) — string column would "
        "lose type-safety vs the 7-value taxonomy"
    )
    expected_values = {
        "head", "hands", "respiratory", "body",
        "footwear", "fall_protection", "other",
    }
    actual_values = {member.value for member in PPEItemCategory}
    assert expected_values == actual_values, (
        f"PPEItemCategory value drift: {expected_values ^ actual_values}. "
        "If you add a value, extend the PG enum via ALTER TYPE in a separate "
        "revision (see [[rb002-enum-migration-cohort]] iter-19 lesson)."
    )


def test_ppeitem_tenant_scoped_unique_constraints() -> None:
    constraint_names = {
        constraint.name for constraint in PPEItem.__table__.constraints
    }
    assert "uq_ppe_item_name" in constraint_names, (
        "uq_ppe_item_name unique constraint on (tenant_id, name) required — "
        "duplicate item names within a tenant would break PPEIssue.item_name "
        "join semantics"
    )
    assert "uq_ppe_item_code" in constraint_names, (
        "uq_ppe_item_code unique constraint on (tenant_id, code) required — "
        "code is the canonical lookup key from inventory/barcode integrations"
    )


def test_ppeitem_tenant_index_exists() -> None:
    index_names = {idx.name for idx in PPEItem.__table__.indexes}
    assert "ix_ppeitem_tenant_id" in index_names, (
        "ix_ppeitem_tenant_id required for tenant-scoped catalog listing"
    )


def test_iter24_migration_creates_ppeitemcategory_enum() -> None:
    # Belt-and-suspenders: the migration source must explicitly name the
    # enum 'ppeitemcategory' so future enum-value extensions know the type
    # name to ALTER TYPE on.
    from pathlib import Path  # noqa: PLC0415

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260527_iter24_journal_ppeitem.py"
    )
    src = migration_path.read_text(encoding="utf-8")
    assert 'name="ppeitemcategory"' in src, (
        "iter-24 must declare ppeitemcategory enum name explicitly (default "
        "lowercased classname is fragile under refactor — see iter-19 PR #587)"
    )
    assert 'name="journaltype"' in src, (
        "iter-24 must declare journaltype enum name explicitly"
    )
