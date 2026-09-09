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
    ("subscriptions", "status"),
    ("invoices", "status"),
    ("billing_events", "type"),
    ("user", "role"),
    ("user_role", "role"),
    ("training_session", "status"),
    ("ppeitem", "category"),
    ("package_profiles_v2", "status"),
    ("package_presets_v2", "source_type"),
    ("package_presets_v2", "status"),
    ("package_preset_items", "replace_mode"),
    ("package_preset_items", "output_format"),
    ("pack_runs", "source_type"),
    ("pack_runs", "status"),
    ("pack_run_items", "status"),
    ("pack_run_logs", "level"),
    ("package_runs", "status"),
    ("package_requirements", "type"),
    ("package_requirements", "status"),
    ("client_request_tickets", "status"),
    ("journal", "journal_type"),
    ("journalentry", "entry_type"),
    ("regulatory_inspection", "inspection_type"),
    ("attestation", "status"),
    ("inspection_prescription", "status"),
    ("approval_processes", "status"),
    ("approval_tasks", "status"),
    # notifications.py (7 — срез-135 убрал reminder_rules)
    ("notification_templates", "channel"),
    ("notification_templates", "type"),
    ("notifications", "channel"),
    ("notifications", "type"),
    ("notifications", "priority"),
    ("notifications", "status"),
    ("plan_tasks", "status"),
    # approval_workflow.py (3)
    ("approval_requests", "status"),
    ("edo_messages", "direction"),
    ("edo_status_history", "status"),
    # document.py (3)
    ("document", "status"),
    ("document_batch_run", "status"),
    ("document_batch_item", "status"),
    # finance.py (3)
    ("contract", "status"),
    ("order", "status"),
    ("invoice", "status"),
    # obligations.py (3)
    ("task", "status"),
    ("task", "priority"),
    ("task", "reminder_channel"),
    # app/modules/workflow/models.py (3)
    ("workflow_definition_versions", "status"),
    ("workflow_instances", "status"),
    ("workflow_tasks", "status"),
}


def test_exactly_49_columns_pinned() -> None:
    # 52 по аудиту 2026-06-02, минус edo_envelopes.status и signatures.status
    # (таблицы дропнуты ed02, ORM-классы удалены) и минус reminder_rules.entity_type
    # (срез-135: ORM-класс удалён, таблица в базе осталась).
    assert len(DEFECTIVE_COLUMNS) == 49


def test_defective_columns_bind_enum_values_not_names() -> None:
    offenders = []
    for table_name, col_name in sorted(DEFECTIVE_COLUMNS):
        col = ALL_TABLES[table_name].columns[col_name]
        t = col.type
        assert (
            isinstance(t, SAEnum) and t.enum_class is not None
        ), f"{table_name}.{col_name} not a native enum"
        if list(t.enums) != [m.value for m in t.enum_class]:
            offenders.append(
                f"{table_name}.{col_name}: binds {list(t.enums)} not {[m.value for m in t.enum_class]}"
            )
    assert not offenders, "columns still bind member NAMES (apply native_enum):\n" + "\n".join(
        offenders
    )


# --- Сырой инвентарь (values_callable=None), запинен против регресса -----------
#
# Колонки, которые ЛЕГИТИМНО биндят имена членов (values_callable отсутствует).
# Live-PG re-аудит 2026-06-25 (throwaway PG16, keystone-guard) классифицировал их:
#   - GROUP-B (pg-тип создан с UPPER-именами членов) → биндить ИМЯ корректно;
#     добавление values_callable СЛОМАЕТ insert (`'low' ∉ [LOW,MEDIUM,HIGH]`);
#   - VARCHAR-backed (нативного pg-типа нет; approval-v2 + safety_core) → принимает
#     любую строку, values_callable бесполезен;
#   - OK (имена == значения: outbox.status, tenant.kind) → миграция не нужна.
# Все три категории должны оставаться СЫРЫМИ. На момент аудита: 0 GROUP-A дефектов,
# 0 колонок, ломающихся на PG. Точная классификация — за keystone-guard
# (`test_orm_enum_pg_label_parity.py`, live PG); этот пин лишь ФИКСИРУЕТ инвентарь.
#
# Падение теста ниже = осознанно классифицируй изменение:
#   * новая СЫРАЯ колонка → прогони keystone-guard; Group-A → native_enum (+ в
#     DEFECTIVE_COLUMNS), иначе добавь сюда;
#   * values_callable снят с Group-A колонки → колонка «всплыла» здесь → верни его;
#   * values_callable добавлен к Group-B колонке → колонка «пропала» отсюда →
#     это и есть регресс, который ломает PG-insert: откати.
# Срез-135: из инвентаря ушли колонки удалённых моделей (`reminder_rules`,
# `equipment`) — таблицы в базе остались, но кода, который их описывал, больше
# нет, и проверять на них нечего.
RAW_NATIVE_ENUM_COLUMNS = {
    ("approval_instance_steps", "status"),  # ApprovalInstanceStepStatus (VARCHAR)
    ("approval_instances", "status"),  # ApprovalInstanceStatus (VARCHAR)
    ("approval_route_steps", "step_type"),  # ApprovalStepType (VARCHAR)
    ("approval_routes", "applies_to"),  # ApprovalRouteAppliesTo (VARCHAR)
    ("approval_routes", "status"),  # ApprovalRouteStatus (VARCHAR)
    ("contractor_employees", "access_status"),  # ComplianceStatus (Group-B)
    ("contractor_employees", "medical_status"),  # ComplianceStatus (Group-B)
    ("contractor_employees", "training_status"),  # ComplianceStatus (Group-B)
    ("contractor_incidents", "severity"),  # IncidentSeverity (Group-B)
    ("correctiveaction", "status"),  # CorrectiveActionStatus (Group-B)
    ("file", "kind"),  # FileKind (Group-B)
    ("file", "scan_status"),  # FileScanStatus (Group-B)
    ("hazards", "source_type"),  # HazardSourceType (VARCHAR)
    ("idempotency_keys", "status"),  # IdempotencyStatus (Group-B)
    ("incident", "incident_type"),  # IncidentType (Group-B)
    ("incident", "investigation_stage"),  # IncidentStage (Group-B)
    ("incident", "severity"),  # IncidentSeverity (Group-B)
    ("incident", "status"),  # IncidentStatus (Group-B)
    ("incident_log", "stage"),  # IncidentStage (Group-B)
    ("incident_log", "status"),  # IncidentStatus (Group-B)
    ("incident_person", "role"),  # IncidentPersonRole (Group-B)
    ("inspection", "status"),  # InspectionStatus (Group-B)
    ("npa", "status"),  # NPAStatus (Group-B)
    ("outbox", "status"),  # OutboxStatus (OK: имена==значения)
    ("pipeline_runs", "status"),  # PipelineRunStatus (Group-B)
    ("plantask", "status"),  # PlanTaskStatus (Group-B)
    ("regulatory_inspection", "status"),  # InspectionStatus (Group-B)
    ("risk_map_items", "residual_risk_level"),  # RiskLevel (VARCHAR)
    ("risk_map_items", "risk_level"),  # RiskLevel (VARCHAR)
    ("risk_maps", "entity_type"),  # RiskMapEntityType (VARCHAR)
    ("risk_maps", "source"),  # RiskMapSource (VARCHAR)
    ("risk_maps", "status"),  # RecordStatus (VARCHAR)
    ("risk_measures", "measure_type"),  # MeasureType (VARCHAR)
    ("risk_methodologies", "status"),  # RecordStatus (VARCHAR)
    ("risk_methodologies", "type"),  # RiskMethodologyType (VARCHAR)
    ("template", "status"),  # TemplateStatus (Group-B)
    ("templateversion", "status"),  # TemplateVersionStatus (Group-B)
    ("tenant", "kind"),  # литеральный enum (OK: значения lowercase)
    ("training", "status"),  # TrainingStatus (Group-B)
    ("violation", "severity"),  # ViolationSeverity (Group-B)
}


def _actual_raw_native_enum_columns() -> set[tuple[str, str]]:
    raw: set[tuple[str, str]] = set()
    for table_name, table in ALL_TABLES.items():
        for col in table.columns:
            t = col.type
            if not isinstance(t, SAEnum) or not getattr(t, "native_enum", False):
                continue
            if t.values_callable is None:
                raw.add((table_name, col.name))
    return raw


def test_raw_native_enum_inventory_is_frozen() -> None:
    """Сырые (values_callable=None) native-enum колонки не должны меняться незаметно.

    Защищает от: (а) новой сырой колонки без классификации, (б) снятия
    values_callable с Group-A (всплывёт здесь), (в) добавления values_callable к
    Group-B (пропадёт отсюда — это регресс, ломающий PG-insert). См. длинный
    комментарий у RAW_NATIVE_ENUM_COLUMNS.
    """
    actual = _actual_raw_native_enum_columns()
    unexpected = actual - RAW_NATIVE_ENUM_COLUMNS
    missing = RAW_NATIVE_ENUM_COLUMNS - actual
    assert not unexpected, (
        "Новые СЫРЫЕ native-enum колонки — классифицируй через keystone PG-guard, "
        f"затем native_enum (Group-A) или сюда (Group-B/VARCHAR/OK): {sorted(unexpected)}"
    )
    assert not missing, (
        "Сырые колонки получили values_callable / исчезли. Если это Group-B — "
        f"откати (ломает PG-insert); иначе обнови allowlist: {sorted(missing)}"
    )


def test_group_a_and_raw_sets_are_disjoint() -> None:
    """Group-A (биндят .value) и сырой инвентарь не пересекаются — каждая
    native-enum колонка ровно в одной категории."""
    assert not (DEFECTIVE_COLUMNS & RAW_NATIVE_ENUM_COLUMNS)
