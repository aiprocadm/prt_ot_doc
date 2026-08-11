"""Pin tests for iter-45: heavyweight audit ``alter_column`` rename tracking.

Closes the LAST false positive in the heavyweight ORM↔migration drift audit
(``scripts/audit/check_orm_migration_drift.py``). That audit parses migration
``upgrade()`` bodies with ``ast`` and tracks ``create_table`` / ``add_column`` /
``drop_column`` / ``drop_table`` / ``rename_table`` — but **not**
``alter_column(..., new_column_name=...)``. A column renamed that way leaves the
OLD name stranded in the audit's migration-side column set while the model
declares the NEW name, producing a two-sided ``[business]`` drift entry that is
a pure FALSE POSITIVE (the migration history is correct; the detector is blind).

Two upgrade-path column renames exist in the repo, each causing one FP:

  * ``20260304_next32_reliability_core``  webhook_deliveries: subscription_id → endpoint_id
  * ``20250325_outbox_outbound_traffic``  outbox:             processed_at   → sent_at

Confirmed against the models: ``WebhookDelivery.endpoint_id``
(``backend/app/models/models.py``) and ``Outbox.sent_at`` — the migration side
held ``subscription_id`` / ``processed_at`` instead, so ``_diff`` reported both
``model_only`` (endpoint_id / sent_at) and ``migration_only`` (subscription_id /
processed_at) → ``business`` severity.

The fix teaches ``_parse_migration`` to extract
``batch.alter_column("old", new_column_name="new")`` (the rename form every
migration in the repo uses) as a ``rename_column`` ``(table, old, new)`` op, and
``_collect_migration_columns`` to replay those renames on the aggregate column
set (after table-renames, before drop subtraction) — exactly mirroring the
existing ``rename_table`` handling. The bare top-level ``op.alter_column`` form
is a documented audit limitation (the repo has none); see the audit module's
``Limitations`` section.

After iter-45 lands, the migration side carries ``endpoint_id`` / ``sent_at``
(matching the models), so neither table is a drift entry — the heavyweight
audit's business-FP class is closed.

Tests are pure AST + audit-parser-integration (no full app boot — the audit's
only app import lives inside ``_load_model_columns``, which these tests never
call). So they run on Win+Py3.13 without the conftest crash. Mirrors the iter-48
pin-test.
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_VERSIONS = REPO_ROOT / "backend" / "app" / "migrations" / "versions"

# The two real upgrade-path column renames (migration file, table, old, new).
WEBHOOK_MIGRATION = _VERSIONS / "20260304_next32_reliability_core.py"
OUTBOX_MIGRATION = _VERSIONS / "20250325_outbox_outbound_traffic.py"

WEBHOOK_RENAME = ("webhook_deliveries", "subscription_id", "endpoint_id")
OUTBOX_RENAME = ("outbox", "processed_at", "sent_at")


@lru_cache(maxsize=1)
def _audit():
    """Load ``check_orm_migration_drift`` by path (module-level code is app-free;
    the ``app.*`` import is confined to ``_load_model_columns``, never called)."""
    audit_path = REPO_ROOT / "scripts" / "audit" / "check_orm_migration_drift.py"
    spec = importlib.util.spec_from_file_location("check_orm_migration_drift", audit_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _collected() -> dict[str, set[str]]:
    """Aggregate ``{table: {col, ...}}`` the audit derives from all migrations."""
    table_columns, _per_file = _audit()._collect_migration_columns()
    return table_columns


def _rename_columns(path: Path) -> list[tuple[str, str, str]]:
    """``rename_column`` ops the audit extracts from one migration's upgrade()."""
    ops = _audit()._parse_migration(path)
    return list(ops.get("rename_column", []))


# ---------------------------------------------------------------------------
# _parse_migration: a renaming alter_column becomes a rename_column op.
# ---------------------------------------------------------------------------


def test_parse_returns_rename_column_key() -> None:
    """``_parse_migration`` must surface a ``rename_column`` list (the new op
    bucket) alongside create_table / add_column / drop_column / rename_table."""
    ops = _audit()._parse_migration(WEBHOOK_MIGRATION)
    assert "rename_column" in ops, "parse result is missing the rename_column key"
    assert isinstance(ops["rename_column"], list)


def test_parse_extracts_webhook_batch_rename() -> None:
    """``batch.alter_column("subscription_id", new_column_name="endpoint_id")`` in
    the webhook_deliveries batch block is recorded as a (table, old, new)."""
    assert WEBHOOK_RENAME in _rename_columns(WEBHOOK_MIGRATION), (
        "audit did not extract the webhook_deliveries subscription_id→endpoint_id "
        f"rename; got {_rename_columns(WEBHOOK_MIGRATION)}"
    )


def test_parse_extracts_outbox_batch_rename() -> None:
    """``batch.alter_column("processed_at", new_column_name="sent_at")`` in the
    outbox batch block is recorded."""
    assert OUTBOX_RENAME in _rename_columns(OUTBOX_MIGRATION), (
        "audit did not extract the outbox processed_at→sent_at rename; "
        f"got {_rename_columns(OUTBOX_MIGRATION)}"
    )


def test_parse_ignores_non_rename_alter_column() -> None:
    """``alter_column`` calls WITHOUT ``new_column_name`` (type / nullable /
    server_default changes) are not renames. The outbox upgrade has several such
    calls (last_error type, destination/status/next_attempt_at server_default) —
    none must produce a rename_column entry. The renaming one is the ONLY entry."""
    assert _rename_columns(OUTBOX_MIGRATION) == [OUTBOX_RENAME], (
        "non-renaming alter_column calls leaked into rename_column: "
        f"{_rename_columns(OUTBOX_MIGRATION)}"
    )


def test_parse_ignores_downgrade_rename() -> None:
    """Only ``upgrade()`` is parsed (forward-only history). The outbox downgrade
    renames sent_at→processed_at — that reverse op must NOT appear."""
    renames = _rename_columns(OUTBOX_MIGRATION)
    assert (
        "outbox",
        "sent_at",
        "processed_at",
    ) not in renames, "downgrade rename leaked into the forward-only parse"


# ---------------------------------------------------------------------------
# _collect_migration_columns: renames are replayed on the aggregate set.
# ---------------------------------------------------------------------------


def test_collect_applies_webhook_rename() -> None:
    """After replay, webhook_deliveries carries the NEW name ``endpoint_id`` and
    no longer the OLD ``subscription_id``."""
    cols = _collected().get("webhook_deliveries", set())
    assert "endpoint_id" in cols, f"endpoint_id missing after replay; cols={sorted(cols)}"
    assert "subscription_id" not in cols, "old subscription_id still stranded after replay"


def test_collect_applies_outbox_rename() -> None:
    """After replay, outbox carries ``sent_at`` and no longer ``processed_at``."""
    cols = _collected().get("outbox", set())
    assert "sent_at" in cols, f"sent_at missing after replay; cols={sorted(cols)}"
    assert "processed_at" not in cols, "old processed_at still stranded after replay"


def test_collect_preserves_table_rename() -> None:
    """Guard: the existing ``rename_table`` handling still collapses the singular
    ``webhook_delivery`` into ``webhook_deliveries`` — the column-rename change
    must not regress it. (Stays green across the change.)"""
    assert not _collected().get(
        "webhook_delivery"
    ), "webhook_delivery (singular) should be empty/absent after table-rename merge"


# ---------------------------------------------------------------------------
# Closed-loop: the FP is gone. The false positive existed iff the migration
# side held the OLD name while the model held the NEW name. The model side is
# verified-constant (WebhookDelivery.endpoint_id / Outbox.sent_at in
# models.py), so asserting the migration side now matches the model's names is
# a complete proof that _diff yields neither model_only nor migration_only for
# the rename pair → no [business] entry.
# ---------------------------------------------------------------------------


def test_no_business_fp_for_webhook_deliveries() -> None:
    table, old_col, new_col = WEBHOOK_RENAME
    cols = _collected().get(table, set())
    assert new_col in cols and old_col not in cols, (
        f"{table}: migration side must match model ({new_col} present, {old_col} "
        f"absent) to clear the business FP; cols={sorted(cols)}"
    )


def test_no_business_fp_for_outbox() -> None:
    table, old_col, new_col = OUTBOX_RENAME
    cols = _collected().get(table, set())
    assert new_col in cols and old_col not in cols, (
        f"{table}: migration side must match model ({new_col} present, {old_col} "
        f"absent) to clear the business FP; cols={sorted(cols)}"
    )
