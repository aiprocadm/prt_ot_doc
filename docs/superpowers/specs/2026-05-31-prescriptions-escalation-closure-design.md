# Prescriptions escalation + closure-rate — design (TZ-3.4-V12-01 → `done`)

- **Date:** 2026-05-31
- **REQ-ID:** `TZ-3.4-V12-01` `[v1.2]` — currently `partial`; this increment closes it to **`done`**.
- **Driver:** brainstorming → writing-plans → executing-plans. Continues `docs/superpowers/specs/2026-05-30-prescriptions-lifecycle-design.md` (which shipped FSM + evidence + verification and explicitly deferred *escalations* and *closure-rate*).
- **Roadmap:** W-A item #2, last open piece of the MVP matrix tails (`docs/superpowers/specs/2026-05-29-tz-completeness-roadmap-design.md` §3 W-A).

## 1 · Problem

The prescriptions lifecycle already ships: a status **FSM** (`OPEN→IN_PROGRESS→COMPLETED→VERIFIED`, rework, cancel), completion **evidence**, inspector **verification** (segregated to `admin`/`owner`), and a `closed_at` stamp. The matrix note records the two remaining gaps that keep `TZ-3.4-V12-01` at `partial`:

> *"escalations + closure-rate (% закрытия) deferred → P10"*

This increment delivers exactly those two, mirroring patterns already in the repo, and flips the row to `done`.

- **Escalations** — surface overdue prescriptions and notify, both on demand and on a schedule.
- **Closure-rate (% закрытия)** — an aggregate metric over prescription statuses.

## 2 · Decisions (locked in brainstorming)

| Decision | Choice |
|---|---|
| Escalation depth | **Briefings on-demand pattern + periodic beat sweep** (auto-notify across tenants) |
| Escalation mechanism | Reuse `OutboxService.enqueue` + `EventType.TASK_OVERDUE` (no new event type) |
| Beat cadence | **Daily** (mirrors `tasks.reminders.dispatch` @ 02:00) |
| Overdue definition | `due_at < today` **and** status **not terminal** (i.e. `OPEN`/`IN_PROGRESS`/**`COMPLETED`** count as overdue; `VERIFIED`/`CANCELLED` do not) |
| Closure-rate formula | `(VERIFIED + COMPLETED) / total`; `0.0` when `total == 0` |
| Summary payload | Always returns the **full per-status breakdown** + `overdue_count` + `closure_rate` (consumer can derive any other rate) |
| Schema | Add computed `is_overdue: bool` to `PrescriptionRead` (mirrors briefings `is_overdue`) |
| Migration | **None** — columns and indexes already exist |
| Matrix status | `partial → done` |

**Why "overdue includes COMPLETED":** mirrors the briefings rule (`status != "completed"` → overdue). A `COMPLETED` prescription past its deadline is *work done, awaiting inspector verification* — i.e. **not yet closed**, so it still warrants visibility/escalation. Only the two terminal states (`VERIFIED` real closure, `CANCELLED`) are exempt.

## 3 · No migration

`Prescription` (table `inspection_prescription`) already has every column this needs — `due_at: Date`, `status`, `closed_at`, `assignee_id` — and the relevant composite indexes are already declared on the model:

- `ix_prescription_status (tenant_id, status)` — powers the summary `GROUP BY status`.
- `ix_prescription_due (tenant_id, due_at)` — powers the overdue scan.

The increment is **pure reads + one outbox enqueue per overdue row + a beat task**. DDL = 0. No new contract on existing endpoints (purely additive).

## 4 · Pure core (app-free, runs on the Py3.13/Win local env)

Added to `app/domains/prescriptions/lifecycle.py` (alongside the existing FSM; no DB / no app-boot imports beyond the `PrescriptionStatus` enum, matching the file's current import):

```python
from datetime import date

def is_overdue(due_at: date | None, status: PrescriptionStatus, today: date) -> bool:
    """Past the deadline and not yet closed (terminal)."""
    return due_at is not None and due_at < today and status not in TERMINAL_STATES

def closure_rate(counts: Mapping[PrescriptionStatus, int]) -> float:
    """(VERIFIED + COMPLETED) / total; 0.0 when there are no prescriptions."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    closed = counts.get(PrescriptionStatus.VERIFIED, 0) + counts.get(PrescriptionStatus.COMPLETED, 0)
    return closed / total
```

`today` is an injected parameter (not `date.today()` inside) so unit tests are deterministic. `TERMINAL_STATES` already exists in the module.

## 5 · Service layer (DB + outbox) — `app/domains/prescriptions/service.py` (new)

Modelled on `app/modules/briefings/services.py::BriefingEntryService`. A small class `PrescriptionEscalationService` (or module-level functions — implementer's call during writing-plans) providing:

- `list_overdue(session, *, tenant_id, today) -> list[Prescription]` — tenant-scoped, `deleted_at IS NULL`, `due_at IS NOT NULL`, `due_at < today`, `status NOT IN TERMINAL_STATES`, ordered by `due_at ASC`. Uses `ix_prescription_due`.
- `notify_overdue(session, *, tenant_id, actor_id, today) -> list[Prescription]` — for each overdue row, `OutboxService(session).enqueue(...)` a `TASK_OVERDUE` event (see §7). Returns the overdue rows. No-op (empty list) when none.
- `status_summary(session, *, tenant_id, today) -> SummaryDTO` — one `SELECT status, COUNT(*) ... GROUP BY status` (uses `ix_prescription_status`) → a per-status dict; plus `overdue_count` (count of the overdue predicate) and `closure_rate(counts)` from the pure helper.

The pure predicate/formula live in §4; the service only does the I/O.

## 6 · API — `backend/app/api/routes/prescriptions.py`

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/prescriptions/overdue` | `ManagerAccess` | list overdue prescriptions |
| GET | `/prescriptions/summary` | `ManagerAccess` | per-status counts + `closure_rate` + `overdue_count` |
| POST | `/prescriptions/remind-overdue` | `EditorAccess` | enqueue `TASK_OVERDUE` for all overdue + audit `notify_overdue` + commit |

**Route ordering (critical):** declare `GET /prescriptions/overdue` and `GET /prescriptions/summary` **before** the existing `GET /prescriptions/{prescription_id}`, or the path param will capture the literals `overdue`/`summary`. (The existing `/transition` is a `POST`, so no clash today; the two new `GET`s introduce the only collision risk.)

- `/remind-overdue` audit row: `action="notify_overdue"`, `object_type="prescription"`, `object_id="bulk"`, `details={"count": n}` — mirrors `briefings.py::remind_overdue_entries`.
- Response shapes: `/overdue` → `PrescriptionPage` (reuse). `/summary` → a new `PrescriptionSummary` schema (`by_status: dict[str,int]`, `total: int`, `overdue_count: int`, `closure_rate: float`). `/remind-overdue` → `{"count": n, "items": [...]}` like briefings.

## 7 · Event emission

Reuse `EventType.TASK_OVERDUE` (briefings already reuses it for the same semantics — no new event type / no new consumer surface):

```python
await OutboxService(session).enqueue(
    tenant_id=tenant_id,
    event_type=EventType.TASK_OVERDUE.value,
    idempotency_key=f"prescription-overdue:{p.id}:{p.due_at.isoformat()}",
    payload={
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "task_id": p.id,
        "title": f"Prescription overdue: {p.description[:80]}",
        "due_at": p.due_at,
        "assignee_id": p.assignee_id,
        "status": p.status.value,
        "priority": "high",
        "overdue": True,
    },
)
```

The **date in the idempotency key** is what makes the daily/hourly sweep safe: re-running on the same calendar day dedups in the outbox, so escalations are not re-emitted until the due date itself rolls (matches the briefings precedent exactly). `p.due_at` is a `date`, so `.isoformat()` yields `YYYY-MM-DD`.

## 8 · Schema — `PrescriptionRead`

Add `is_overdue: bool = False`. It is **not** a DB column; it is computed when serializing, via a route helper `_to_read(record, *, today) -> PrescriptionRead` that mirrors `briefings.py::_entry_read`. This helper replaces the direct `PrescriptionRead.model_validate(record)` calls (5 call sites) so every read carries a correct, `today`-relative flag. Keeping `today` injectable keeps tests deterministic.

## 9 · Beat task — `app/tasks/_core.py` + `app/services/celery_app.py`

```python
@celery_app.task(name="prescriptions.escalate.tick", autoretry_for=RETRYABLE_EXCEPTIONS,
                 retry_backoff=True, retry_jitter=True, max_retries=5)
def prescriptions_escalate_tick() -> int:
    ...  # iterate active tenants, per-tenant notify_overdue, commit, sum counts
```

Shape mirrors `reminders.scan` / `_scan_reminders_job` (the **no-arg, iterate-active-tenants** form used by every beat-scheduled task), **not** the per-tenant-arg `workflow.sla.tick`. Per tenant: `tenant_context(slug)` + `ensure_tenant_schema` + `session_scope` + `service.notify_overdue(...)` + `commit`. Registered in `celery_app.conf.beat_schedule` as `"prescriptions-escalate-daily"` @ `crontab(hour=2, minute=0)`.

## 10 · Tests (TDD, RED → GREEN)

- **Unit (app-free)** `tests/unit/test_prescription_escalation.py`: `is_overdue` boundaries (due yesterday/today/tomorrow; each status incl. terminal exemption; `due_at is None`); `closure_rate` ((V+C)/total, `total==0 → 0.0`, all-cancelled, mixed).
- **API (app-booting)** `tests/api/test_prescriptions_escalation_api.py`: `/overdue` returns only past-due non-terminal rows in `due_at` order; `/summary` exact per-status counts + `closure_rate` + `overdue_count`; `/remind-overdue` writes one `TASK_OVERDUE` outbox row per overdue and a second same-day call adds **zero** new rows (idempotency-key dedup); `is_overdue` present and correct in `PrescriptionRead`; cross-tenant isolation (tenant B's overdue never appears / never notified for tenant A); RBAC (`403` without a prescriptions role; `/remind-overdue` needs editor).
- **Task** `backend/tests/test_prescriptions_escalate_tick.py`: in eager mode, the tick notifies overdue rows for an active tenant and is idempotent on a same-day re-run.

Local execution: unit runs on Py3.13/Win; the app-booting + task files run single-file locally but CI on 3.12.12 is canonical (`[[local_env_drift_windows]]`).

## 11 · Docs & matrix

- **Acceptance doc:** extend `docs/acceptance/prescriptions-lifecycle.md` with the overdue + closure-rate scenarios (reproducible request/response: create past-due → `/overdue` lists it → `/remind-overdue` emits once → `/summary` reflects counts/rate).
- **Matrix `TZ-3.4-V12-01`:** `partial → done`. Add the new files to the `backend`/`jobs`/`events`/`tests` columns; rewrite the note to *"FSM + evidence + verification + overdue escalations (on-demand + daily beat sweep, TASK_OVERDUE) + closure-rate (% закрытия) shipped"*. Re-run `scripts/audit/check_tz_coverage_matrix.py`.
- **Matrix `TZ-6.3-V11-01` (coverage-gate, out of scope here):** clarify the note to *"scoped ratchet gate + climb plan shipped; flips to `done` on W0 (CI re-enable + floor bootstrap)"* — **stays `partial`**; it cannot become `done` by code alone (needs a live CI run; user's purview). This is the one MVP-tail row this session cannot flip.

## 12 · Acceptance criteria

1. `/prescriptions/overdue`, `/prescriptions/summary`, `/prescriptions/remind-overdue` work; the two new `GET`s are declared before `/{prescription_id}` and are not captured as a path id.
2. `is_overdue` on `PrescriptionRead` is correct relative to `today` (true for past-due non-terminal; false for terminal or future/empty due).
3. `/remind-overdue` and the beat task emit `TASK_OVERDUE` for every overdue row; a same-day repeat emits **no** duplicates (idempotency-key dedup).
4. `closure_rate == (VERIFIED + COMPLETED) / total` (0.0 at total 0); per-status breakdown is exact.
5. `prescriptions.escalate.tick` is registered in `beat_schedule`, iterates active tenants, and is tenant-isolated.
6. All new tests green; `scripts/audit/check_tz_coverage_matrix.py` green; `TZ-3.4-V12-01 → done`.
7. No migration; no change to existing endpoint contracts (additive only).

## 13 · Out of scope (deferred hardening — not required for `done`)

These were noted in the prior lifecycle design and remain deferred; they are **not** part of the matrix-note gap, so the row reaches `done` without them:

- **File-attachment evidence** — `evidence` stays free-text; binding to the files module is later.
- **Verifier ≠ assignee identity check** — role segregation (`admin`/`owner`) is enforced; per-user "can't verify your own work" is a future hardening.
- **Multi-level escalation ladder** (assignee → manager → owner with configurable thresholds via `ReminderRule`) — explicitly chosen against in brainstorming; a future P10 increment if needed.
