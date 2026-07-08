# Broad code-review sweep — 2026-07-08

Multi-agent adversarial review of the codebase (18 domain slices, each finding
verified by 3 independent skeptics; majority-real survived). 55 candidates → **37
confirmed**. This document records the disposition of every confirmed finding.

Legend: **FIXED** = applied + regression-checked · **DEFERRED** = real, but needs a
design/domain decision (recorded here with a recommendation) · **NOT A BUG** = a
verified false positive.

## Fixed (28)

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
- **#27** `modules/files/service/_uploads.py:129` — sha256 dedup was tenant-wide and merged the caller's metadata into the found record, reassigning another company's file. Now only dedups/merges within the same company (`metadata_json.company_id`); cross-company identical content gets its own record.
- **#33** `services/billing.py:330` — `add_usage` applied the `s3_bytes` delta unconditionally, so a retried call double-counted storage. Now guarded by an idempotent `FILE_UPLOADED`/`ref_type="s3_bytes"` billing event (same pattern as docs/edo).
- **#32 (isolation half)** `routes/packs/run.py` — `pack_safety_summary` now validates the run (404 on an unknown/cross-tenant `pack_run_id`) instead of returning a 200 with arbitrary persons. Regression test added. The person-scoping half remains deferred (no `PackRunItem.person_id`).

State-machine guards
- `routes/invoices.py:210` — invoice status could revert from terminal PAID/VOID. Reject changes from terminal states.
- `routes/sout.py` — `update_workplace`/`add_factor`/`update_factor`/`add_guarantee` could mutate a COMPLETED/DECLARED campaign. Added `ensure_campaign_open` guard (mirrors `add_workplace`).
- `routes/edo_workflow.py:473` — `decide_approval_request` could mutate a terminal request. Guard `status is RUNNING`.
- `routes/approval_signing_v1.py:429` — re-deciding a DONE task re-advanced the process (duplicate tasks). Guard `status is OPEN`.
- `routes/safety_ops.py` — `complete_action`/`verify_action` had no state guard (regressed verified actions / verified un-completed ones). Guarded against terminal regression and verify-before-complete.

Security / authorization
- `routes/edo_workflow.py` (per-tenant EDO webhook) — a configured `edo_webhook_secret` did not reject a *missing* `X-Signature` (bypass by omitting the header). Now mandatory. **Behavior change**: providers that don't sign will be rejected; the prior lenient contract was explicitly tightened with owner approval. Test updated + rejection test added.
- **#4** `routes/edo_workflow.py:487` — `decide_approval_request` never checked the step's required role, so any actor could approve every step of a multi-step route. Now the actor must hold `rules.steps[i].role` (admin/owner may approve any step).
- **#17** `domains/work_permits/service.py:388` — `signed_closing_kinds` derived both сдал/принял kinds from one person holding two roles (single-signature two-party bypass). Now each closing kind must be backed by a distinct signer (greedy bipartite assignment).

## Deferred — need a design/domain decision (8)

1. **#14 Incident status transitions unvalidated** (`modules/incidents/operations.py:191`). `IncidentCaseService.validate_transition` exists but uses a *stale vocabulary* (`draft/registered/awaiting_actions/archived`) that does not match the real `IncidentStatus` enum (`reported/investigating/corrective_actions/closed/cancelled`). Wiring it in would reject legitimate transitions. Needs the real lifecycle spec.
2. **#15 `mark-passed` leaves completion fields stale** (`routes/training_next.py:516`). Sets `status/completed_at` but not `completion_status`, `progress_percent`, `expires_at`, so passed enrolments read as incomplete/overdue. Needs the completion-status vocabulary and the certificate-validity source for `expires_at`.
3. **#16 Person-compliance projection hardcodes `unknown`** (`modules/projections/services.py:364`). `overdue_trainings`/`overdue_briefings` never populated → dependent KPIs are permanently 0. Needs the per-person overdue computation.
4. **#20 Webhook-delivery retry is a no-op** (`routes/webhooks.py:721`). `WebhookDelivery` is a status-mirror keyed by `(endpoint_id, event_id)`, upserted by the Outbox processor (`services/outbox.py:662`); nothing *scans* it. `:retry` flips its status, but delivery is driven by the **Outbox**, so the retry does nothing. A correct fix must re-drive the source Outbox entry, but the delivery→outbox link is only a fuzzy JSON match (`event_id = payload.event_id or outbox.id`, plus the `X-Webhook-Endpoint-Id` header) and the per-endpoint fan-out model must be confirmed — a fragile partial fix would be worse than the honest no-op. Needs the delivery↔outbox linkage nailed down (or an explicit `outbox_id` FK on `WebhookDelivery`).
5. **#25 Audit hash-chain forks under concurrency** (`services/audit.py:210`). The chain is *global by design* — `verify_audit_chain` (line 325) has no tenant filter either, so `_prev_hash` and verify are mutually consistent. The real defect: a global hash chain needs *serialized appends*; two concurrent writes read the same latest hash and fork, and verify then reports false tampering. **No small backward-compatible patch exists** — adding a tenant filter would break verification of all historically-chained rows without fixing the fork. Recommended fix: serialize appends around read-prev+insert (e.g. `pg_advisory_xact_lock` on a fixed chain key, a no-op path on the SQLite test backend) — this is PG-specific and serializes all audit writes (a throughput tradeoff), so it needs an explicit architectural decision. Alternative: per-tenant chains + a deterministic `(when, id)` tiebreak + a re-chain migration.
6. **#26 Calendar badge counts ignore the date range** (`services/calendar_aggregator.py:407`). The generic `_scoped_count(Model, ...)` filters tenant/person/site but not `from_at/to_at`, so per-source totals/overdue don't match the windowed item list. This is a ~18-edit per-builder change: each of the ~9 `_build_*` methods counts on its *own* window column (`MedicalExam.valid_until`, `MedicalReferral.due_at`, PPE `expires_at`, …), so every `_scoped_count(...)` call must add that builder's specific window predicate — the same one already applied to its item-list query. Best done as a focused refactor with a `count == len(items)` assertion per source; deferred to avoid a wrong-column silent-miscount at session tail.
7. **#29 Analytics `trend_series` is flat** (`modules/analytics/services.py:97`). Every time bucket runs the same current-snapshot query; the read-models store no history, so a real trend cannot be reconstructed without a time-series snapshot table.
8. **#32 `pack_safety_summary` — person-scoping half only** (`routes/packs/run.py:447`). The isolation/correctness half is **FIXED** (batch 4/5: a bogus/cross-tenant `pack_run_id` now 404s instead of returning a 200 with arbitrary persons). The remaining half — scoping the summary to *the run's* persons — is not achievable today: `PackRunItem` has no `person_id`/subject link, so it still returns up to 100 tenant persons. Needs a schema linkage (person↔run) or source-row re-derivation.

## Not a bug (1)

- **#28 MIME order** (`modules/files/utils.py:72`). The provided-Content-Type-first order is intentional: the legacy upload path catches content/extension spoofing via a separate mismatch check (`test_upload_file_rejects_mismatched_extension`). Reordering broke the "unsupported" classification. Reverted.
