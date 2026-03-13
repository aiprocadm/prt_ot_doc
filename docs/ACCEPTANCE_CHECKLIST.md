# Acceptance Checklist (RC)

| Criterion | Status | Implemented / verified in RC pass | Remaining |
|---|---|---|---|
| Repeated POST with same `Idempotency-Key` returns same result | ✅ Done | Verified by integration test run (`test_idempotency_generate`). | - |
| Any business route without `X-Tenant` returns 400 | 🟡 Partial | Guardrail path verified by API guardrails tests; broad route-by-route sweep pending. | Add explicit coverage for every business router group. |
| Template selection strictly by `(code, version)` and conflict delete returns proper error | 🟡 Partial | Existing platform behavior present; no full matrix sweep performed in this pass. | Add dedicated regression matrix and negative cases. |
| Replace flow: dry-run report / apply / rollback state safety | 🟡 Partial | Existing pipeline/job flows validated partially via status & idempotency tests. | Add dedicated E2E replacement scenarios for dry-run/apply/rollback. |
| Jobs: queued/running/success/error/canceled are consistent | ✅ Done | Verified core state transitions by `test_job_status_flow`. | Expand to queue backend (celery + broker) e2e environment. |
| Client portal sees own statuses/packs/files/history | 🟡 Partial | Frontend build/tests green; no live multi-tenant e2e in this pass. | Add explicit tenant-isolation e2e smoke. |
| Dashboard/report/export paths minimally operational | 🟡 Partial | Frontend production build confirms route compile; no live backend smoke for all endpoints. | Add runtime smoke hitting each critical route. |
| Risk map / PPE / training / incidents / inspections CRUD/read flows stable | 🟡 Partial | Existing tests/build indicate baseline health; full CRUD smoke matrix not fully re-run in this pass. | Execute focused API + UI smoke matrix before release sign-off. |
| Frontend-backend key sections contract-aligned | 🟡 Partial | Critical CLI contract fixed; FE build/tests pass. | Complete explicit DTO diff audit by domain entities list. |
| CI has no critical regression errors | 🟡 Partial | Critical CLI regression fixed; FE tests/build green; targeted BE tests green. | Global lint/migration pipeline still not fully green in this environment. |
