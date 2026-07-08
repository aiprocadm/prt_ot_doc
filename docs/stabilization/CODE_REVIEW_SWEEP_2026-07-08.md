# Broad code-review sweep — 2026-07-08

Multi-agent adversarial review of the codebase (18 domain slices, each finding
verified by 3 independent skeptics; majority-real survived). 55 candidates → **37
confirmed**. This document records the disposition of every confirmed finding.

Legend: **FIXED** = applied + regression-checked · **DEFERRED** = real, but needs a
design/domain decision (recorded here with a recommendation) · **NOT A BUG** = a
verified false positive.

## Fixed (24)

Crashes / missing methods
- `routes/briefings.py:399` — `bulk-create` passed `person_id` twice (inherited via `**base`) → guaranteed `TypeError` on every call. Excluded the inherited key.
- `routes/safety_ops.py` (`recalc_gaps`) — called nonexistent `GapAnalysisService.recalculate_package_gaps` → 500. Implemented the recompute via `detect_gaps` (delete + re-insert `InspectionPrepGap`).
- `modules/files/s3.py` — `abort_upload` called nonexistent `s3.delete_object` (error swallowed → object leaked). Implemented `delete_object` for memory/local/boto3 backends.
- `routes/public_api.py:223` — unvalidated `sort_by` → `getattr` on a non-column → 500. Whitelisted to real table columns.

Data integrity / logic
- `routes/public_api.py:226` — external list endpoint returned soft-deleted rows. Added `deleted_at IS NULL`.
- `routes/webhooks.py:748` — replay reset status but not `attempts` → DEAD event re-killed without redelivery. Reset `attempts = 0`.
- `services/notifications.py` (`apply_quiet_hours`) — a same-day quiet window delayed notifications ~24h. Only bump to next day for overnight windows.
- `modules/risk/services.py` (`_pick_level`) — out-of-range score defaulted to `critical` (residual 0 mislabelled). Clamp to nearest band.
- `modules/compliance_deadlines/services.py:37` — certificate marked overdue at 00:00 on its last valid day. Compare on date grain.
- PPE safety budget — inverted period accepted on partial PATCH; transfer dest batch dropped `unit_cost`. Both fixed with tests.
- `modules/analytics/services.py` + `modules/projections/services.py` — `incidents_open`/`inspections_open` counted CLOSED/CANCELLED/COMPLETED and (projection) soft-deleted. Added the `dashboard.py` status predicate + `deleted_at`.
- `routes/medical/catalog.py:374` — referral could be completed with another person's exam. Scoped the exam query to `record.person_id`.
- `modules/packs/service.py:353` — PackRun stats counted out-of-range rows as success. Base counts on valid rows only.
- `routes/approval_orchestration.py:877` — webhook dedupe fallback used per-process-randomized `hash()`. Switched to sha256 over canonical JSON.
- `modules/notifications/delivery.py` + `services/notifications.py` — escalation to the guaranteed-terminal in-app channel was dropped when in-app was disabled. Added `force=True` bypass for escalation.
- `frontend/src/api/client.ts:221` — queued 401s on refresh-failure rejected with a raw AxiosError. Normalized like the other paths.

State-machine guards
- `routes/invoices.py:210` — invoice status could revert from terminal PAID/VOID. Reject changes from terminal states.
- `routes/sout.py` — `update_workplace`/`add_factor`/`update_factor`/`add_guarantee` could mutate a COMPLETED/DECLARED campaign. Added `ensure_campaign_open` guard (mirrors `add_workplace`).
- `routes/edo_workflow.py:473` — `decide_approval_request` could mutate a terminal request. Guard `status is RUNNING`.
- `routes/approval_signing_v1.py:429` — re-deciding a DONE task re-advanced the process (duplicate tasks). Guard `status is OPEN`.
- `routes/safety_ops.py` — `complete_action`/`verify_action` had no state guard (regressed verified actions / verified un-completed ones). Guarded against terminal regression and verify-before-complete.

Security
- `routes/edo_workflow.py` (per-tenant EDO webhook) — a configured `edo_webhook_secret` did not reject a *missing* `X-Signature` (bypass by omitting the header). Now mandatory. **Behavior change**: providers that don't sign will be rejected; the prior lenient contract was explicitly tightened with owner approval. Test updated + rejection test added.

## Deferred — need a design/domain decision (12)

1. **#4 Approval step-role not enforced** (`routes/edo_workflow.py:487`). Any actor satisfying `AccessDep` can approve any step; a single actor can walk a multi-step route. Fix requires matching the actor's roles to `rules.steps[current_step_index].role`. Deferred because the role model + alias handling must be confirmed to avoid locking out legitimate approvers.
2. **#14 Incident status transitions unvalidated** (`modules/incidents/operations.py:191`). `IncidentCaseService.validate_transition` exists but uses a *stale vocabulary* (`draft/registered/awaiting_actions/archived`) that does not match the real `IncidentStatus` enum (`reported/investigating/corrective_actions/closed/cancelled`). Wiring it in would reject legitimate transitions. Needs the real lifecycle spec.
3. **#15 `mark-passed` leaves completion fields stale** (`routes/training_next.py:516`). Sets `status/completed_at` but not `completion_status`, `progress_percent`, `expires_at`, so passed enrolments read as incomplete/overdue. Needs the completion-status vocabulary and the certificate-validity source for `expires_at`.
4. **#16 Person-compliance projection hardcodes `unknown`** (`modules/projections/services.py:364`). `overdue_trainings`/`overdue_briefings` never populated → dependent KPIs are permanently 0. Needs the per-person overdue computation.
5. **#17 Work-permit two-party closing bypass** (`domains/work_permits/service.py:388`). One person holding two member roles can satisfy both сдал/принял closing kinds with a single signature. Needs a distinct-signer rule.
6. **#20 Webhook-delivery retry is a no-op** (`routes/webhooks.py:721`). `:retry` flips `WebhookDelivery.status` but nothing consumes `WebhookDelivery` (only Outbox is processed). Needs a delivery processor or to route retries through Outbox.
7. **#25 Audit hash-chain forks under concurrency** (`services/audit.py:210`). `_prev_hash` reads the global latest hash with no tenant scope / monotonic tiebreak; concurrent writes chain to the same prev → `verify_audit_chain` reports false tampering. Needs a per-tenant chain + stable ordering (careful, integrity-sensitive).
8. **#26 Calendar badge counts ignore the date range** (`services/calendar_aggregator.py:407`). `_scoped_count` omits `from_at/to_at`, so totals/overdue don't match the windowed item list. Needs per-entity window predicates threaded into the counts.
9. **#27 File dedup reassigns another company's file** (`modules/files/service/_uploads.py:129`). sha256 dedup is tenant-wide (no company scope) and then merges caller metadata into the found record. Needs a dedup-scope policy decision.
10. **#29 Analytics `trend_series` is flat** (`modules/analytics/services.py:97`). Every time bucket runs the same current-snapshot query; the read-models store no history, so a real trend cannot be reconstructed without a time-series snapshot table.
11. **#32 `pack_safety_summary` ignores `pack_run_id`** (`routes/packs/run.py:447`). Returns up to 100 unrelated tenant persons and never validates the run. Needs scoping to the run's persons + a 404 on unknown run.
12. **#33 Billing double-counts `s3_bytes` on retry** (`services/billing.py:330`). The storage delta is applied unconditionally while docs/edo are idempotency-guarded. Needs a storage billing-event type (or dedup key) to guard.

## Not a bug (1)

- **#28 MIME order** (`modules/files/utils.py:72`). The provided-Content-Type-first order is intentional: the legacy upload path catches content/extension spoofing via a separate mismatch check (`test_upload_file_rejects_mismatched_extension`). Reordering broke the "unsupported" classification. Reverted.
