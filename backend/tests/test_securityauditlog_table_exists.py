"""Pin tests for ``SecurityAuditLog`` (``securityauditlog`` table) schema parity.

iter-23 RB-002k (NEW release-blocker class, cohort member with RB-002j).
Same anti-pattern: ``SecurityAuditLog`` (``backend/app/models/models.py:2154``)
was added without a paired Alembic migration. The model declares the table
for RBAC+ABAC enforcement decision logging — every authenticated request
triggers an INSERT via ``modules/audit/security_log.py:26``. Without the
migration, Postgres production crashes on the first authenticated request
that touches a guarded endpoint.

The naming convention (``securityauditlog`` — no underscores) follows the
default ``TenantBaseModel.__tablename__`` rule (``cls.__name__.lower()``)
rather than the snake_case style used elsewhere. The migration matches the
model's convention rather than fighting it (renaming the table would break
every existing ``SecurityAuditLog`` query without commensurate benefit).
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.models import SecurityAuditLog


def test_securityauditlog_has_required_columns() -> None:
    columns = inspect(SecurityAuditLog).columns
    required = {
        "id",
        "tenant_id",
        "when",
        "user_id",
        "action",
        "resource_type",
        "resource_id",
        "decision",
        "reason_code",
        "ip",
        "user_agent",
        "correlation_id",
        "details",
        "created_at",
        "updated_at",
        "version",
    }
    assert required.issubset(
        columns.keys()
    ), f"securityauditlog missing columns: {required - set(columns.keys())}"


def test_securityauditlog_user_fk_sets_null_on_delete() -> None:
    column = inspect(SecurityAuditLog).columns["user_id"]
    foreign_keys = list(column.foreign_keys)

    assert len(foreign_keys) == 1, "user_id must have exactly one FK"
    fk = foreign_keys[0]
    assert fk.column.table.name == "user"
    assert fk.column.name == "id"
    # SET NULL (not CASCADE) preserves audit history when a user is deleted —
    # regulatory requirement: we must remember a decision was made even after
    # the actor is removed.
    assert (
        fk.ondelete == "SET NULL"
    ), "ondelete must be SET NULL — preserve audit row after user deletion"


def test_securityauditlog_user_id_is_nullable() -> None:
    column = inspect(SecurityAuditLog).columns["user_id"]
    assert column.nullable is True, (
        "user_id must be nullable — SET NULL ondelete requires it; also "
        "anonymous/system actions log with user_id=NULL"
    )


def test_securityauditlog_has_decision_lookup_indexes() -> None:
    index_names = {idx.name for idx in SecurityAuditLog.__table__.indexes}
    required = {
        "ix_security_auditlog_action",
        "ix_security_auditlog_decision",
        "ix_security_auditlog_resource",
        "ix_security_auditlog_when",
    }
    missing = required - index_names
    assert not missing, f"securityauditlog missing required indexes for audit queries: {missing}"


def test_iter23_migration_creates_securityauditlog_table() -> None:
    # Static check via importlib (same trick as the iter-21 pin tests) —
    # confirms the upgrade() body contains create_table("securityauditlog").
    from pathlib import Path  # noqa: PLC0415

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260527_iter23_refresh_session_securityauditlog.py"
    )
    assert migration_path.exists()
    source = migration_path.read_text(encoding="utf-8")
    # Quoted literal — keeps the assert resilient to whitespace/keyword reordering.
    assert (
        '"securityauditlog"' in source
    ), "iter-23 migration must contain create_table for 'securityauditlog'"
    assert '"refresh_session"' in source, (
        "iter-23 migration must also contain create_table for 'refresh_session' " "(cohort fix)"
    )
