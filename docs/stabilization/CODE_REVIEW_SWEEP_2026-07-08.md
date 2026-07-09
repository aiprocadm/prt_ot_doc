# Broad code-review sweep — 2026-07-08

Multi-agent adversarial review of the codebase (18 domain slices, each finding
verified by 3 independent skeptics; majority-real survived). 55 candidates → **37
confirmed**. This document records the disposition of every confirmed finding.

Legend: **FIXED** = applied + regression-checked · **DEFERRED** = real, but needs a
design/domain decision (recorded here with a recommendation) · **NOT A BUG** = a
verified false positive.

## Fixed (36)

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
- **#27** `modules/files/service/_uploads.py:129` — sha256 dedup was tenant-wide and merged the caller's metadata into the found record, reassigning another company's file. Now only dedups/merges within the same company (`metadata_json.company_id`); cross-company identical content gets its own record. (Self-review corrected a regression in the first cut: the initial company-gate still used `LIMIT 1`, which dropped same-company dedup for any company whose row the DB didn't happen to surface — now it matches the caller's company among all clean candidates. Regression test added.)
- **#33** `services/billing.py:330` — `add_usage` applied the `s3_bytes` delta unconditionally, so a retried call double-counted storage. Now guarded by an idempotent `FILE_UPLOADED`/`ref_type="s3_bytes"` billing event (same pattern as docs/edo). (Self-review corrected the first cut: the guard was a no-op because both finalize callers passed no `ref_id` — they now pass `file_id`, so the dedup key is populated.)
- **#32 (isolation half)** `routes/packs/run.py` — `pack_safety_summary` now validates the run (404 on an unknown/cross-tenant `pack_run_id`) instead of returning a 200 with arbitrary persons. Regression test added. The person-scoping half remains deferred (no `PackRunItem.person_id`).
- **#20** `services/outbox.py` + `routes/webhooks.py` + migration `wh01` — the delivery `:retry` was a no-op (it flipped a status-mirror no processor reads). Added an explicit `WebhookDelivery.outbox_id` (populated at delivery time), and `:retry` now re-drives the source Outbox entry (PENDING, attempts=0) so redelivery actually happens; falls back to `event_id` for legacy rows. Migration is additive/nullable. Regression test asserts the Outbox is re-driven.
- **#25 (concurrency-fork half)** `services/audit.py` — audit appends now take a transaction-scoped PostgreSQL advisory lock (`pg_advisory_xact_lock`) before reading the previous hash, so two concurrent writers can't chain onto the same `prev_hash` and fork the global hash chain. No-op on SQLite (guarded — writes serialize anyway), so existing chain tests are unaffected; real PG-concurrency serialization is CI-validated. Intentional throughput tradeoff (audit appends globally serialized). Residual minor: the chain is still global (by design) and same-`when` ordering has no explicit `(when, id)` tiebreak — now nearly moot under serialization; changing it would reinterpret historically-chained rows, so left as a follow-up.
- **#26** `services/calendar_aggregator.py` — per-source badge counts (`by_source.count`/`overdue_count`, and thus `total`/`overdue_count`) now apply the same `from_at/to_at` window as each source's item list, via a new `_apply_window` helper wired into all 9 `_build_*` counters (each on its own window column/grain). A windowed count previously reported all-time figures. Regression test asserts `count == windowed items`.

State-machine guards
- `routes/invoices.py:210` — invoice status could revert from terminal PAID/VOID. Reject changes from terminal states.
- `routes/sout.py` — `update_workplace`/`add_factor`/`update_factor`/`add_guarantee` could mutate a COMPLETED/DECLARED campaign. Added `ensure_campaign_open` guard (mirrors `add_workplace`).
- `routes/edo_workflow.py:473` — `decide_approval_request` could mutate a terminal request. Guard `status is RUNNING`.
- `routes/approval_signing_v1.py:429` — re-deciding a DONE task re-advanced the process (duplicate tasks). Guard `status is OPEN`.
- `routes/safety_ops.py` — `complete_action`/`verify_action` had no state guard (regressed verified actions / verified un-completed ones). Guarded against terminal regression and verify-before-complete.
- **#14 (full)** `modules/incidents/operations.py` — `update_incident` wrote `status` with no guard. Now enforces the incident lifecycle: terminal CLOSED/CANCELLED can't be changed (400); open states advance forward `reported → investigating → corrective_actions → closed` (skip-ahead allowed, backward rejected); cancel is allowed from any open state. **Documented decision** (owner may override the transition rules). Regression tests for both terminal-reopen and backward-move.
- **#16** `modules/projections/services.py` — the person-compliance projection hardcoded `readiness_status="unknown"` and never populated `overdue_trainings`/`overdue_briefings`, so dependent KPIs were permanently 0. Now computed per person (grouped, no N+1): overdue = a lapsed validity — a training enrolment past `expires_at` or a briefing past `valid_until`; `readiness_status` = "blocked" if any overdue else "ready" (**documented decision**). Also fixed a pre-existing latent crash on the same path: `row.site_id = person.site_id` (`Person` has no `site_id` since the ARCH-2 split) now uses `getattr(..., None)`. Regression test added.
- **#29** `modules/analytics/services.py` + `modules/projections/services.py` — `trend_series` re-ran the same current aggregate for every bucket (flat line). Now the latest bucket uses the live value and each past bucket reads the most recent daily `DashboardKpiSnapshot` on/before that date; the snapshot builder was extended to record all trend metrics (from the same read models) and to use the read models' correct open-count semantics. Real trends fill in as daily snapshots accumulate. Regression test asserts a past bucket differs from the live value.
- **#15** `routes/training_next.py` — `mark-passed` set only `status/completed_at`, so passed enrolments read as incomplete/overdue everywhere. Now mirrors the canonical `submit_attempt` completion: sets `completion_status="completed"`, `progress_percent=100`, and `expires_at` from the program's `validity_months`. Regression test added.

Security / authorization
- `routes/edo_workflow.py` (per-tenant EDO webhook) — a configured `edo_webhook_secret` did not reject a *missing* `X-Signature` (bypass by omitting the header). Now mandatory. **Behavior change**: providers that don't sign will be rejected; the prior lenient contract was explicitly tightened with owner approval. Test updated + rejection test added.
- **#4** `routes/edo_workflow.py:487` — `decide_approval_request` never checked the step's required role, so any actor could approve every step of a multi-step route. Now the actor must hold `rules.steps[i].role` (admin/owner may approve any step).
- **#17** `domains/work_permits/service.py:388` — `signed_closing_kinds` derived both сдал/принял kinds from one person holding two roles (single-signature two-party bypass). Now each closing kind must be backed by a distinct signer (greedy bipartite assignment).

## Deferred — needs a packs-v2 redesign, not implementable as-is (1)

1. **#32 `pack_safety_summary` — person-scoping half (not implementable without redesign)** (`routes/packs/run.py:447`). The isolation/correctness half is **FIXED** (a bogus/cross-tenant `pack_run_id` now 404s instead of returning a 200 with arbitrary persons). The remaining "scope to the run's persons" half was investigated and determined **not implementable with the current data model**: the packs-v2 `PackRun`/`PackRunItem` flow is created purely from `selected_rows` + `source_file_id` with **no `person_ids` and no `company_id`** anywhere (the person-based list lives in the *separate* `run_pack`/`PackRunRequest` flow, which does not feed this endpoint). A `PackRunItem.person_id` column would have no reliable population source (only fuzzy source-row re-derivation) and would stay NULL — dead schema. Truly per-run person-scoping requires a packs-v2 redesign to track subjects per run (a product decision). Left as tenant-wide person readiness for a validated run.

Everything else from the sweep is fixed or a verified false positive.

## Not a bug (1)

- **#28 MIME order** (`modules/files/utils.py:72`). The provided-Content-Type-first order is intentional: the legacy upload path catches content/extension spoofing via a separate mismatch check (`test_upload_file_rejects_mismatched_extension`). Reordering broke the "unsupported" classification. Reverted.
