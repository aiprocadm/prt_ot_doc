# Prescriptions lifecycle — design (TZ-3.4-V12-01, W-A item #2)

- **Date:** 2026-05-30
- **REQ-ID:** `TZ-3.4-V12-01` `[v1.2]` — currently `partial`; stays `partial` after this increment (escalations + closure-rate remain deferred).
- **Driver:** brainstorming → writing-plans → executing-plans (W-A item #2, roadmap `docs/superpowers/specs/2026-05-29-tz-completeness-roadmap-design.md` §4).
- **Increment scope (chosen):** status-transition **FSM** + resolution **evidence** + **verification** state (повторные проверки). Decided over the leaner FSM-only and FSM+metric slices.

## 1 · Problem

`backend/app/api/routes/prescriptions.py` ships a CRUD skeleton (list/create/get/patch, ETag, audit), but `update_prescription` mutates fields via `for k, v in updates.items(): setattr(record, k, v)`. Status is therefore a **free-form field**: invalid jumps such as `CANCELLED → COMPLETED` or `COMPLETED → OPEN` silently succeed (HTTP 200). The spec (`vNext §14.3`) asks to *finalize the status workflow* — give `status` an explicit transition graph the API enforces — plus evidence of completion and an inspector re-check (verification) step.

The skeleton already covers two of the §14.3 aspects: **assignees** (`assignee_id`) and **deadlines** (`due_at`). This increment adds the **status workflow**, **evidence**, and **re-inspections (verification)**. **Escalations** and **closure-rate (% закрытия)** are explicitly **out of scope** here (separate future increments).

## 2 · Decisions (locked in brainstorming)

| Decision | Choice |
|---|---|
| Increment scope | FSM + evidence + verification |
| FSM policy | Linear + rework loop |
| API shape | Single transition endpoint `POST /prescriptions/{id}/transition` |
| Verify authority | **Segregation of duties** — `→VERIFIED` restricted to `admin`/`owner` |
| Creation state | Forced to `OPEN` (entry state) |
| `closed_at` | Included now (supports deferred closure-rate) |
| Matrix status | Stays `partial` (escalations + closure-rate deferred) |

## 3 · State machine

States: `OPEN`, `IN_PROGRESS`, `COMPLETED`, `VERIFIED` (new), `CANCELLED`.

```
   ┌───────────────────────────────────────────────┐
   │                                               ▼
 OPEN ──▶ IN_PROGRESS ──▶ COMPLETED ──▶ VERIFIED ✓ (terminal)
   │            │              │
   │            │              └──▶ IN_PROGRESS   (re-inspection FAILED → rework)
   ▼            ▼
 CANCELLED ◀────┘  (terminal — reachable only from OPEN / IN_PROGRESS)
```

| From | Allowed → To |
|---|---|
| `OPEN` | `IN_PROGRESS`, `CANCELLED` |
| `IN_PROGRESS` | `COMPLETED`, `CANCELLED` |
| `COMPLETED` | `VERIFIED`, `IN_PROGRESS` |
| `VERIFIED` | — terminal — |
| `CANCELLED` | — terminal — |

- **Self-transition** (`X → X`) is an idempotent no-op (HTTP 200, no state change, no audit row).
- Any edge not in the table → **409**.

Semantics: `COMPLETED` = work done + evidence attached, awaiting inspector re-check; `VERIFIED` = повторная проверка passed (real closure); a failed re-check sends it back to `IN_PROGRESS` for rework.

## 4 · Data model & migration

Enum gains one value:

```python
class PrescriptionStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"      # NEW
    CANCELLED = "cancelled"
```

Two additive nullable columns on `inspection_prescription`:

```python
evidence:  Mapped[str | None]      = mapped_column(Text)                      # proof set on →COMPLETED
closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # set on VERIFIED/CANCELLED
```

Migration `20260530_wa03_prescription_lifecycle` (chains off the current W-A head `20260530_wa02_featureenablement_drop_feature_fk`):

- `op.add_column` ×2 — nullable, **no backfill**.
- Postgres enum extension, **guarded and transaction-safe**:
  ```python
  if bind.dialect.name == "postgresql":
      op.execute("ALTER TYPE prescriptionstatus ADD VALUE IF NOT EXISTS 'verified'")
  ```
  `ALTER TYPE … ADD VALUE` historically cannot run inside a transaction block in Postgres; the migration must not wrap it in one (autocommit / `IF NOT EXISTS`). SQLite stores the enum as `VARCHAR`, so its schema comes from ORM `create_all` and needs no DDL here. See `[[rb002_enum_migration_cohort]]`.
- Downgrade: drop the two columns. The enum value is **not** removed (Postgres cannot drop an enum value without recreating the type — documented one-way, matching repo precedent).
- Additive + one of 8 heads by design (`[[alembic_heads_lesson]]`).

## 5 · FSM domain module — `app/domains/prescriptions/lifecycle.py`

Pure functions, **no DB / no app imports** (so unit tests run on the Py3.13/Win local env):

```python
ALLOWED_TRANSITIONS: dict[PrescriptionStatus, frozenset[PrescriptionStatus]] = {
    PrescriptionStatus.OPEN:        frozenset({IN_PROGRESS, CANCELLED}),
    PrescriptionStatus.IN_PROGRESS: frozenset({COMPLETED, CANCELLED}),
    PrescriptionStatus.COMPLETED:   frozenset({VERIFIED, IN_PROGRESS}),
    PrescriptionStatus.VERIFIED:    frozenset(),
    PrescriptionStatus.CANCELLED:   frozenset(),
}
TERMINAL_STATES = frozenset({VERIFIED, CANCELLED})
VERIFY_ROLES = frozenset({"admin", "owner"})

class InvalidTransition(Exception): ...

def validate_transition(current, target) -> None        # same → ok; else target ∈ ALLOWED[current] or raise
def is_terminal(status) -> bool
def requires_evidence(target) -> bool                    # True iff target == COMPLETED
```

## 6 · API changes — `backend/app/api/routes/prescriptions.py`

### New: `POST /prescriptions/{id}/transition`
Body `PrescriptionTransition { to: PrescriptionStatus, evidence: str | None, note: str | None }`. Dependency = existing `EditorAccess`.

Handler flow:
1. `ensure_tenant_context`; load tenant-scoped prescription → **404** `prescription_not_found` if absent.
2. `validate_transition(record.status, payload.to)` → **409** `prescription_invalid_transition` on failure.
3. If `payload.to == VERIFIED`: check `{v.lower() for v in access.to_auth_context().roles} & VERIFY_ROLES`; empty → **403** `prescription_verify_forbidden` (segregation of duties, mirrors `ensure_risk_access`).
4. If `requires_evidence(payload.to)` and no non-empty `evidence` (payload or already-stored) → **422** `evidence_required`.
5. Apply: set `status`; set `evidence` when provided; set `closed_at = now(UTC)` when `is_terminal(to)`. Only `VERIFIED`/`CANCELLED` are terminal and have no outgoing edges, so `closed_at` is write-once and never needs clearing.
6. Audit `action="transition"`, `object_type="prescription"`, `details={"from", "to", "evidence_present", "note"}`.
7. Commit, refresh, return `PrescriptionRead`. Self-transition short-circuits after step 2 (200, no write/audit).

### Changed: `PATCH /prescriptions/{id}`
Drops `status` from `PrescriptionUpdate`. Edits fields only: `description`, `due_at`, `assignee_id`, `inspection_id`, `incident_id`. (Status now moves **only** through `/transition`.)

### Changed: `POST /prescriptions`
`PrescriptionCreate` drops `status`; records are always created `OPEN`.

### Read schema
`PrescriptionRead` gains `evidence: str | None` and `closed_at: datetime | None`.

## 7 · Error contract

| Condition | Code | HTTP |
|---|---|---|
| Unknown prescription id | `prescription_not_found` | 404 |
| Edge not allowed by FSM | `prescription_invalid_transition` | 409 |
| `→VERIFIED` by non-admin/owner | `prescription_verify_forbidden` | 403 |
| `→COMPLETED` without evidence | `evidence_required` | 422 |

## 8 · Tests (TDD, RED → GREEN)

- **Unit — FSM** (app-free, `tests/unit/test_prescription_lifecycle.py`): every allowed edge passes; a representative set of invalid edges raise `InvalidTransition`; both terminals reject all outgoing edges; self-transition is allowed (no-op); `requires_evidence` true only for `COMPLETED`; `VERIFY_ROLES` constant pinned.
- **Migration pin** (app-free, `backend/tests/test_wa03_prescription_lifecycle_migration.py`): revision/down_revision metadata; both columns added; enum `ADD VALUE … 'verified'` present + `dialect=='postgresql'`-guarded; downgrade drops the two columns.
- **API** (app-booting, `tests/api/test_prescriptions_lifecycle_api.py`): full happy path `OPEN→IN_PROGRESS→COMPLETED(+evidence)→VERIFIED`; `409` on an invalid jump; `422` on complete-without-evidence; `403` when a `line_manager`/`hr` attempts `→VERIFIED`; `200` when `admin` verifies; cancel from `OPEN` and `IN_PROGRESS`; failed-verification rework `COMPLETED→IN_PROGRESS`; `PATCH` no longer changes status; `closed_at` set on terminal; audit `transition` row written; tenant isolation preserved.
- **Migrate existing** `tests/integration/test_prescriptions_api.py::test_prescription_crud_and_audit`: replace the `OPEN→COMPLETED` PATCH with the valid `/transition` path (`OPEN→IN_PROGRESS→COMPLETED` with evidence).

Local execution: unit + migration-pin run on Py3.13/Win; the app-booting file runs (slow, ~single-file) but CI on 3.12.12 is canonical (`[[local_env_drift_windows]]`).

## 9 · Docs & matrix

- **Acceptance doc:** short lifecycle scenario doc (e.g. `docs/acceptance/prescriptions-lifecycle.md`) — the happy path + each guarded rejection, as reproducible request/response steps.
- **Matrix `TZ-3.4-V12-01`:** stays `partial`; backend/db/tests columns gain the new files; plan note updated to: *"status-FSM + evidence + verification (segregated) shipped; escalations + closure-rate (% закрытия) deferred → P10"*. Re-run `scripts/audit/check_tz_coverage_matrix.py`.

## 10 · Out of scope (deferred)

- **Escalations** (overdue → notify/flag) — needs a job/scheduler hook; separate increment.
- **Closure-rate (% закрытия)** aggregate endpoint — `closed_at` is provisioned for it.
- **File-attachment evidence** — `evidence` is free-text here; binding to the files module is a later step.
- **Verifier ≠ assignee identity check** — this increment enforces *role* segregation (`admin`/`owner`), not per-user "can't verify your own work". Noted for a future hardening.

## 11 · Acceptance criteria

1. Status changes only via `/transition`; PATCH/create cannot set an arbitrary status.
2. Every FSM edge in §3 behaves exactly as tabled (allowed → 200; disallowed → 409; self → 200 no-op).
3. `→COMPLETED` without evidence → 422; with evidence persists `evidence`.
4. `→VERIFIED` allowed for `admin`/`owner` only (else 403); reaching `VERIFIED`/`CANCELLED` stamps `closed_at`.
5. Migration applies additively (`alembic upgrade heads`), enum carries `verified`, head count unchanged.
6. All new tests green; the migrated existing test green; matrix validator green.
