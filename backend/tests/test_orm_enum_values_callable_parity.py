"""Fast pin (no PG): the 52 known ORM↔pg_enum label-drift columns must bind .value.

Authoritative source is the @pytest.mark.db keystone guard
(test_orm_enum_pg_label_parity.py), which introspects live pg_enum labels. This
fast pin lists the exact 52 Group-A columns from the 2026-06-02 audit so the
normal (no-Docker) suite catches regressions and gives incremental feedback.

NOT a universal "every native enum binds .value" rule: 31 Group-B columns have pg
types created with UPPER member-NAME labels and correctly bind names — adding
values_callable there would break PG inserts (see spec Appendix)."""
from __future__ import annotations

from sqlalchemy import Enum as SAEnum

import app.db.base  # noqa: F401  triggers all model imports incl. app.modules.*
from app.db.session import SharedBase, TenantBase

# Complete table registry. NOTE: app.db.base.ALEMBIC_METADATA omits app.modules.*
# (it is snapshotted before those imports — see spec Appendix), so iterate the live
# SharedBase + TenantBase registries instead. Key by BARE table name:
# SharedBase.metadata.schema == "public" makes its keys schema-qualified
# ("public.billing_events"), so .update(_md.tables) would leave the bare-name
# DEFECTIVE_COLUMNS lookups KeyError-ing unless an unrelated fixture reset the
# schema — keep this hermetic and order-independent.
ALL_TABLES = {}
for _md in (SharedBase.metadata, TenantBase.metadata):
    for _t in _md.tables.values():
        ALL_TABLES.setdefault(_t.name, _t)

# (table, column) — the Group-A defective columns (2026-06-02 full PG audit).
# Исходно 52; минус 2 после ed02 (2026-06-12): ORM-классы EdoEnvelope и
# Signature удалены, их таблицы edo_envelopes / signatures дропнуты
# (20260612_ed02_drop_legacy_signing_tables) → колонок больше не существует.
DEFECTIVE_COLUMNS = {
    # models.py (27)
    ("subscriptions", "status"), ("invoices", "status"), ("billing_events", "type"),
    ("user", "role"), ("user_role", "role"), ("training_session", "status"),
    ("ppeitem", "category"), ("package_profiles_v2", "status"),
    ("package_presets_v2", "source_type"), ("package_presets_v2", "status"),
    ("package_preset_items", "replace_mode"), ("package_preset_items", "output_format"),
    ("pack_runs", "source_type"), ("pack_runs", "status"), ("pack_run_items", "status"),
    ("pack_run_logs", "level"), ("package_runs", "status"),
    ("package_requirements", "type"), ("package_requirements", "status"),
    ("client_request_tickets", "status"), ("journal", "journal_type"),
    ("journalentry", "entry_type"), ("regulatory_inspection", "inspection_type"),
    ("attestation", "status"), ("inspection_prescription", "status"),
    ("approval_processes", "status"), ("approval_tasks", "status"),
    # notifications.py (8)
    ("notification_templates", "channel"), ("notification_templates", "type"),
    ("notifications", "channel"), ("notifications", "type"),
    ("notifications", "priority"), ("notifications", "status"),
    ("reminder_rules", "entity_type"), ("plan_tasks", "status"),
    # approval_workflow.py (3)
    ("approval_requests", "status"),
    ("edo_messages", "direction"), ("edo_status_history", "status"),
    # document.py (3)
    ("document", "status"), ("document_batch_run", "status"),
    ("document_batch_item", "status"),
    # finance.py (3)
    ("contract", "status"), ("order", "status"), ("invoice", "status"),
    # obligations.py (3)
    ("task", "status"), ("task", "priority"), ("task", "reminder_channel"),
    # app/modules/workflow/models.py (3)
    ("workflow_definition_versions", "status"), ("workflow_instances", "status"),
    ("workflow_tasks", "status"),
}


def test_exactly_50_columns_pinned() -> None:
    # 52 по аудиту 2026-06-02, минус edo_envelopes.status и signatures.status
    # (таблицы дропнуты ed02, ORM-классы удалены).
    assert len(DEFECTIVE_COLUMNS) == 50


def test_defective_columns_bind_enum_values_not_names() -> None:
    offenders = []
    for table_name, col_name in sorted(DEFECTIVE_COLUMNS):
        col = ALL_TABLES[table_name].columns[col_name]
        t = col.type
        assert isinstance(t, SAEnum) and t.enum_class is not None, f"{table_name}.{col_name} not a native enum"
        if list(t.enums) != [m.value for m in t.enum_class]:
            offenders.append(
                f"{table_name}.{col_name}: binds {list(t.enums)} not {[m.value for m in t.enum_class]}"
            )
    assert not offenders, "columns still bind member NAMES (apply native_enum):\n" + "\n".join(offenders)
