# Acceptance — Prescriptions lifecycle (TZ-3.4-V12-01)

Status moves only through `POST /api/v1/prescriptions/{id}/transition`. FSM:
`OPEN → IN_PROGRESS → COMPLETED → VERIFIED` (terminal); `COMPLETED → IN_PROGRESS`
on a failed re-inspection; `CANCELLED` reachable from `OPEN`/`IN_PROGRESS`.
Self-transitions are idempotent no-ops.

## Scenarios

1. **Happy path.** Create (OPEN) → transition `IN_PROGRESS` (200) → `COMPLETED`
   with `evidence` (200) → `VERIFIED` as admin/owner (200; `closed_at` set).
2. **Invalid jump.** `OPEN → COMPLETED` → **409** `prescription_invalid_transition`.
3. **Evidence gate.** `IN_PROGRESS → COMPLETED` without `evidence` → **422**
   `evidence_required`.
4. **Segregation of duties.** `COMPLETED → VERIFIED` by a non-admin/owner (e.g.
   `line_manager`) → **403** `prescription_verify_forbidden`.
5. **Rework.** `COMPLETED → IN_PROGRESS` (failed re-inspection) → 200; `closed_at`
   stays null.
6. **Cancel.** `OPEN`/`IN_PROGRESS → CANCELLED` → 200; `closed_at` set.
7. **PATCH cannot move status.** `PATCH` with a `status` field is ignored (200,
   status unchanged); field edits (description/due_at/assignee) still apply.

Every transition writes an immutable audit row (`action="transition"`,
`details={from, to, evidence_present, note}`).

## Tests
- `backend/tests/test_prescription_lifecycle.py` — FSM unit (app-free)
- `backend/tests/test_wa03_prescription_lifecycle_migration.py` — migration pin
- `tests/api/test_prescriptions_lifecycle_api.py` — HTTP contract (8 scenarios)
- `tests/integration/test_prescriptions_api.py` — CRUD + audit (FSM-aligned)

## Deferred (separate increments)
Escalations (overdue → notify), closure-rate (% закрытия) aggregate, file-bound
evidence, and per-user verifier ≠ assignee identity checks.
