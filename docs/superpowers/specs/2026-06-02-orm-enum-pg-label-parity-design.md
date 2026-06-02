# Design — systemic ORM↔Postgres enum-label drift (52 native-enum columns fail on PG insert)

- **Date:** 2026-06-02
- **Branch:** `fix/iter38-enum-server-default-case` (continuation; off `main`)
- **Status:** design approved (brainstorming) → pending implementation plan
- **Driver:** brainstorming → writing-plans → TDD/executing-plans (against live PG16)
- **Release context:** this is the **next masked layer** after the iter38 `server_default` fix (commit `54cae5c`) and the iter43 downgrade fix (`1c8f71d`). `alembic upgrade heads` is now GREEN on fresh PG, so the app *boots* on Postgres — but ORM **writes** to ~52 native-enum columns still fail. This must close before "canonical PG" means "the app works on Postgres," not merely "migrations apply." See `AI_IMPLEMENTATION_REPORT.md` (handoff 2026-06-02, §3 MAJOR), `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`, `KNOWN_LIMITATIONS.md`.

## Problem (reproduced canonically, not inferred)

SQLAlchemy `Enum(MyEnum)` **without** `values_callable` persists the enum member **name** (UPPER, e.g. `'PENDING'`). Many migrations created the Postgres enum **types** with lowercase **value** labels (e.g. `pending`). So every ORM insert/update of these columns fails on PG:

```
SELECT 'PENDING'::approvalprocessstatus;
-- ERROR: invalid input value for enum approvalprocessstatus: "PENDING"
```

Hidden because: (a) the test suite is SQLite-only — `Enum` degrades to `VARCHAR` and accepts any string; (b) `alembic upgrade heads` never completed on fresh PG until iter38 (`54cae5c`), so no ORM write was ever exercised against the real types. The app boots on PG now; writes to these columns do not.

**Scale:** a live-PG audit of SQLAlchemy's bound strings vs. `pg_enum` labels found **52 of 83** native-enum ORM columns defective. (The task's "49 of 81" undercounts: its `ALEMBIC_METADATA` snapshot omits the 3 defective `app.modules.workflow` columns — see Appendix.) Only ~7 already use `values_callable` correctly (precedent: `backend/app/models/document.py:171`; `backend/app/models/models.py:737,748,…`). The convention was applied inconsistently.

Affected areas (non-exhaustive, the keystone guard regenerates the exact set): subscriptions, invoices, billing_events, contract, order, invoice, approval_processes/tasks/requests, signatures, edo_messages/edo_status_history/edo_envelopes, user/user_role (`roleenum`), training_session, ppeitem, package_profiles_v2/package_presets_v2/package_preset_items, pack_runs/pack_run_items/pack_run_logs, package_runs/package_requirements, client_request_tickets, journal/journalentry (`journaltype`), regulatory_inspection, attestation, inspection_prescription, document/document_batch_run/document_batch_item, notification_templates/notifications, reminder_rules, plan_tasks, task.

## Root cause

`Enum(SomeEnum)` defaults to binding the member **name**; `values_callable=lambda e: [m.value for m in e]` switches it to bind `.value`. These are `str`-enums, so `.value` already matches both the `pg_enum` labels (created lowercase/CamelCase by migrations) **and** the API/JSON layer. The fix is to apply `values_callable` consistently — the established precedent — plus, where the type is genuinely missing a label, add it.

### The four "caveat" enums collapse into one uniform rule

| Enum / column | `.value` casing | Live `pg_enum` label set | What's needed |
|---|---|---|---|
| `DocumentStatus` / `document.status` (`documentstatus`) | lowercase (`draft`…) | `{ARCHIVED,DRAFT,REVIEW,SIGNED,approved,generated,revoked}` | `values_callable` + ADD VALUE for missing lowercase `{draft,review,signed,archived}` |
| `NotificationType` / `notifications.type`, `notification_templates.type` | CamelCase (`JobStatusChanged`…) | CamelCase **subset** | `values_callable` + ADD VALUE for missing members |
| `NotificationChannel` / `notifications.channel` (+ template channel) | lowercase, incl. `webhook` | lacks `webhook` | `values_callable` + ADD VALUE `webhook` |
| `RoleEnum` / `user.role`, `user_role.role` (`roleenum`) | lowercase (`owner`…) | MIX of UPPER cruft + lowercase | `values_callable` + ADD VALUE for any missing lowercase |

So **every** case is the same: bind `.value`, then `ALTER TYPE … ADD VALUE IF NOT EXISTS` for any `.value` not yet a label. Stale UPPER labels remain as harmless, unused dead weight. The keystone guard surfaces precisely which columns need the ADD VALUE step.

## Decision — Additive, forward-only

Chosen over (b) recreating the mixed types and (c) data-backfilling existing rows, because it is the lowest-risk path that achieves fresh-PG correctness (the user's steer: "максимально эффективно и логично"):

- **No data mutation** — the task mandates the `cabinet` DB is never touched; PG tests use a throwaway DB.
- **Clean downgrade** — `ADD VALUE IF NOT EXISTS` is idempotent; downgrade is a no-op (PG has no `DROP VALUE`, and additive labels are harmless).
- **Stale UPPER labels are harmless** — they are never bound (the ORM now binds `.value`); removing them would require risky type recreation for zero correctness gain (YAGNI).

## Components

### 1. Keystone PG audit guard (authoritative)
`backend/tests/test_orm_enum_pg_label_parity.py`, `@pytest.mark.db`. Mirrors `backend/tests/test_alembic_postgres_upgrade.py`: provisions a throwaway DB, runs `alembic upgrade heads`, introspects `pg_enum`:

```sql
SELECT t.typname, e.enumlabel FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid;
```

For every native-enum ORM column — iterating the live `SharedBase.metadata` + `TenantBase.metadata` registries (**not** `ALEMBIC_METADATA`, which is snapshotted before the `app.modules.*` imports and would miss the workflow module) where `isinstance(col.type, sqlalchemy.Enum)`, `col.type.native_enum`, and `col.type.name` is present in the introspected types — assert:

```python
set(col.type.enums) <= pg_labels[col.type.name.lower()]
```

`col.type.enums` already reflects `values_callable` — it is the exact list of strings SQLAlchemy will send (same property the existing pin `test_documentversion_status_enum_values.py:38` relies on). **RED now** — the failure message enumerates every defective column and its out-of-range strings (the exact 52 + the exact missing labels). **GREEN after fix.** This is the ground-truth regeneration tool *and* the permanent regression guard.

### 2. Fast ORM-side pin (no PG) — the specific 52, not a universal rule
`backend/tests/test_orm_enum_values_callable_parity.py`, runs in the normal suite. Pins the **exact 52 defective columns** (authoritative list in the Appendix) — each must bind `.value`:

```python
for table_name, col_name in DEFECTIVE_COLUMNS:   # the 52
    col = ALL_TABLES[table_name].columns[col_name]   # SharedBase+TenantBase, not ALEMBIC_METADATA
    assert list(col.type.enums) == [m.value for m in col.type.enum_class]
```

**Why not a universal "every native enum binds `.value`" rule?** Because that over-reaches and would *introduce* bugs. The 83 native-enum columns split three ways (full-metadata audit, Appendix):

- **52 Group-A (defective, fix these):** pg type created with lowercase/`.value` labels → binding the UPPER member NAME fails (`bound ⊄ pg_labels`).
- **31 Group-B (leave alone):** pg type *also* created with UPPER member-NAME labels (e.g. `incidentseverity=[LOW,MEDIUM,HIGH]`) → binding names *works*. Adding `values_callable` would make them bind `'low'` into an UPPER-only type — **breaking a working column**.
- **20 VARCHAR-backed:** the ORM declares `Enum(...)` but the column is `VARCHAR` on PG (approval v2 tables, `contractors`, `safety_core`) → accepts any string, never fails.

**Defectiveness is therefore not an ORM-only property** — it is `bound ⊄ live_pg_labels`, which only the keystone guard (Component 1) can determine. This fast pin is a convenience for incremental TDD feedback and a normal-suite regression guard on the known 52; the keystone guard is authoritative and additionally catches brand-new columns and any Group-B breakage.

### 3. `native_enum()` helper
In `backend/app/models/base.py`:

```python
def native_enum(enum_cls, *, name=None, **kw):
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e], **kw)
```

One declaration site for the invariant — impossible to forget `values_callable`. Used for all defective columns; columns with unusual `Enum` kwargs pass through `**kw`. `base.py` is already imported by the model modules, so the import graph is unchanged. (Existing 7 inline precedents may optionally be unified for uniformity; not required for correctness.)

### 4. ADD VALUE migration
`backend/app/migrations/versions/<ts>_iterNN_enum_label_backfill.py`. For each `.value` the keystone guard reports missing, emit:

```python
ADD_VALUES = {  # authoritative — see Appendix
    "documentstatus": ["archived", "draft", "review", "signed"],
    "notificationchannel": ["webhook"],
    "notificationtype": ["ApprovalDeadline", "BillingLimitWarning", "EdoStatusChanged",
        "IncidentCreated", "InspectionCreated", "IntegrationError", "MedicalOverdue",
        "PPEOverdue", "PackageRunCompleted", "PackageRunFailed", "PrescriptionOverdue"],
    "roleenum": ["auditor_ro", "clerk", "client", "executor", "inspector_contractor",
        "manager", "ot_head", "student", "teacher"],
}
def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for type_name, values in ADD_VALUES.items():
        for v in values:
            op.execute(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{v}'")
```

Idempotent; safe under the existing AUTOCOMMIT + `transaction_per_migration` env.py (each migration commits separately, so new labels are durable — and crucially these labels are **not** used as a `server_default` in the same migration, so the iter38 `UnsafeNewEnumValueUsageError` cannot recur). SQLite branch is a no-op (enums are VARCHAR). **Downgrade = documented no-op** (PG has no `DROP VALUE`). The repo has **8 live Alembic heads** awaiting a merge (the iter43 docstring notes this); this migration's `down_revision` is the tuple of all 8, so it **doubles as the heads-merge** — one file collapsing to a single clean head. Revision id `20260602_iter49_enum_label_parity`.

### 5. Column edits (exactly 52)
Swap `Enum(...)` → `native_enum(...)` in **seven files** (authoritative per-file lists in the Appendix): `backend/app/models/models.py` (28), `notifications.py` (8), `approval_workflow.py` (4), `document.py` (3), `finance.py` (3), `obligations.py` (3), and `backend/app/modules/workflow/models.py` (3). Each file adds `native_enum` to its existing `from app.models.base import …` line. All targets are single-line `Enum(...)` calls; in `models.py`, `Enum(RoleEnum)` and `Enum(JournalType)` each appear twice (both are targets → `replace_all`).

## Data flow

ORM insert → `bind_processor` → `.value` string → matches a `pg_enum` label (pre-existing or newly added) → INSERT succeeds and round-trips back to the enum member on read.

## Edge cases & risks

- **SQLite suite** — mechanically unaffected (`Enum`→`VARCHAR`; schema is recreated per run, so no stale rows mis-map). **But** any test asserting a stored UPPER string (e.g. `row.status == "PENDING"`, or a raw-string DB read) will need updating to compare the member or `.value`. Surfaced by running the full suite; fixed in execution.
- **Pre-existing PG rows** written under the old name-binding behavior (UPPER `role`, `document.status`) would need a one-time `UPDATE` backfill to remain queryable after the switch. **Out of scope** (pre-release; `cabinet` untouched). Documented as a caveat in `KNOWN_LIMITATIONS.md`.
- **Group-B columns (31) are left untouched** — their pg type was created with UPPER member-NAME labels (e.g. `incidentseverity=[LOW,MEDIUM,HIGH]`, `equipmentstatus=[ACTIVE,…]`), so the ORM's existing name-binding already matches. Applying `values_callable` to them would bind `'low'` into an UPPER-only type and break inserts — the fix is deliberately targeted, not a blanket rewrite.
- **NotificationType ADD VALUE** must use exact CamelCase `.value` casing (`ApprovalDeadline`, not `approval_deadline`).
- **Module enum columns** with extra `Enum` kwargs → pass through `native_enum(**kw)` or keep inline.

## Verification

1. Keystone guard #1: **RED → GREEN** on a Docker PG16 throwaway DB (lists then clears all 52).
2. Fast guard #2: **RED → GREEN** in the normal suite.
3. Full existing SQLite suite **green** — fix any UPPER stored-string assertions surfaced.
4. **Real ORM insert smoke** on throwaway PG: insert a previously-defective entity (e.g. `Notification(channel=WEBHOOK, type=…)`, an `ApprovalProcess`, a `Document`) and assert the write succeeds and round-trips.
5. Throwaway DB dropped; `cabinet` never touched.

Environment: Win + `.venv\Scripts\python.exe` (Py3.13.7) + Docker PG16 `promtech-cabinet-db-1`; run pytest via the PowerShell tool redirecting to a file (`[[py313_win_pytest_invocation]]`). Canonical run is Py3.12.12 in CI (currently disabled).

## Delivery

**Single plan + single PR.** The keystone guard is all-or-nothing (green only when every column is fixed) and every change shares one root cause, so slicing would leave the guard red across PRs.

## Out of scope

- Removing stale UPPER `pg_enum` labels (type recreation) — harmless, risky, YAGNI.
- Data-migration backfill of existing UPPER rows — pre-release; `cabinet` untouched.
- Pre-existing downgrade debts unrelated to this drift (next63 `version_num`, iter41 `journaltype`) — separate "downgrade repair" plan per the handoff.
- The ~9 ORM-`Enum` columns that are `VARCHAR` on PG (approval v2 tables, `safety_core`) — a different ORM↔migration drift; they accept any string and do not fail inserts.

## Appendix — authoritative audit (2026-06-02, fresh PG16 throwaway DB)

Generated by upgrading a throwaway DB to `heads` and intersecting each native-enum column's SQLAlchemy-bound strings with live `pg_enum` labels, iterating the **complete** `SharedBase` + `TenantBase` registries. **52 defective**, 31 Group-B (untouched), 20 VARCHAR-backed (skipped) = **83** native-enum columns total. (The task's "49 of 81" used `ALEMBIC_METADATA`, which omits the 3 defective `app.modules.workflow` columns.)

### Defective columns by file (apply `native_enum`)

- **`models.py` (28):** subscriptions.status, invoices.status, billing_events.type, user.role, user_role.role, training_session.status, ppeitem.category, package_profiles_v2.status, package_presets_v2.source_type, package_presets_v2.status, package_preset_items.replace_mode, package_preset_items.output_format, pack_runs.source_type, pack_runs.status, pack_run_items.status, pack_run_logs.level, package_runs.status, package_requirements.type, package_requirements.status, client_request_tickets.status, journal.journal_type, journalentry.entry_type, regulatory_inspection.inspection_type, attestation.status, inspection_prescription.status, approval_processes.status, approval_tasks.status, edo_envelopes.status
- **`notifications.py` (8):** notification_templates.channel, notification_templates.type, notifications.channel, notifications.type, notifications.priority, notifications.status, reminder_rules.entity_type, plan_tasks.status
- **`approval_workflow.py` (4):** approval_requests.status, signatures.status, edo_messages.direction, edo_status_history.status
- **`document.py` (3):** document.status, document_batch_run.status, document_batch_item.status
- **`finance.py` (3):** contract.status, order.status, invoice.status
- **`obligations.py` (3):** task.status, task.priority, task.reminder_channel
- **`modules/workflow/models.py` (3):** workflow_definition_versions.status, workflow_instances.status, workflow_tasks.status — pg type already has the labels (no ADD VALUE)

### Types needing `ALTER TYPE … ADD VALUE` (only 4 of 52)

| pg type | column(s) | add labels |
|---|---|---|
| `documentstatus` | document.status | archived, draft, review, signed |
| `notificationchannel` | notifications.channel | webhook |
| `notificationtype` | notifications.type | ApprovalDeadline, BillingLimitWarning, EdoStatusChanged, IncidentCreated, InspectionCreated, IntegrationError, MedicalOverdue, PPEOverdue, PackageRunCompleted, PackageRunFailed, PrescriptionOverdue |
| `roleenum` | user.role, user_role.role | auditor_ro, clerk, client, executor, inspector_contractor, manager, ot_head, student, teacher |

The other 45 columns' `.value`s are already present in their pg type → `values_callable` alone suffices. Subtlety the live audit caught: the *template* variants are already complete (`notificationtemplatechannel` already has `webhook`; `notificationtemplatetype` already has all 26 members) — only the non-template `notifications.*` pair is short.

### 8 Alembic heads (this migration's `down_revision` tuple)

`20260529_iter35_riskmap_company`, `20260529_iter40_tc_legacy_cols`, `20260529_iter41_journalentry_concept`, `20260529_iter42_incident_family`, `20260529_iter43_incident_status_enum`, `20260529_iter46_approval_decisions_cols`, `20260529_iter47_file_business_cols`, `20260530_wa03_prescription_lifecycle`
