# Acceptance Traceability (Release-Critical Stories)

- **Updated on (UTC):** 2026-04-23
- **Owner:** QA + Backend + Frontend + Platform + SRE
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Status sync source:** `ACCEPTANCE_TEST_MATRIX.md` + `RELEASE_READINESS.md`

## Release-critical story map (minimum required coverage)

| Story ID | User story (role + target outcome) | Test(s) (exact path / identifier) | Workflow job | Artifact path | Current status | Gap comment |
|---|---|---|---|---|---|---|
| US-ATTN-001 | **As an unauthenticated or limited user**, I want workspace/attention routes to enforce redirect/deny rules so that protected tenant data is not exposed. | `frontend/e2e/smoke.spec.ts` → `attention hub route redirects to login when logged out`; `frontend/e2e/smoke.spec.ts` → `limited user denied on attention hub...` | `.github/workflows/e2e-smoke.yml` → `playwright-smoke-minimal`, `playwright-smoke-credential` | Playwright run logs; `e2e-backend-log-*` (failure-only) | `done` (sync: `ACCEPTANCE_TEST_MATRIX.md`, RC-010) | Matrix marks scenario as done; remaining gap is keeping this evidence rolled into final acceptance summary (`RC-004` still `partial`). |
| US-DOC-ORCH-002 | **As an operations specialist**, I want generate→headers→pdf→handoff orchestration to progress deterministically (with retry states) so that document delivery is auditable and recoverable. | `backend/tests/test_document_orchestration_state.py`; `frontend/e2e/key-scenarios.spec.ts` → `quick generation timeline shows orchestration states for chain flow`; `tests/test_documents_generate.py`; `tests/pdf/test_api_idempotency.py`; `backend/tests/test_next57_approval_sign_edo_services.py` | `.github/workflows/ci.yml` → `backend-tests`; `.github/workflows/e2e-smoke.yml` → `playwright-smoke-credential` | `artifacts/backend-junit.xml`; `artifacts/coverage.json`; Playwright logs; `artifacts/final_acceptance/summary.json` | `done` for orchestration path (sync: `ACCEPTANCE_TEST_MATRIX.md`, RC-017), but bundle `partial` (sync: RC-004) | Orchestration scenario is covered, but release bundle remains `partial` until all mandatory acceptance scenarios converge to `overall_status=pass`. |
| US-TENANT-FILES-003 | **As a tenant user**, I want cross-tenant file access denied by default so that files and signed URL flows remain isolated to my tenant and permission scope. | `tests/test_tenant_security.py`; `tests/integration/test_tenant_isolation.py`; `tests/integration/test_abac_query_isolation.py`; `tests/test_files_access_parity.py`; `tests/services/test_file_storage_service.py` | `.github/workflows/ci.yml` → `lint-and-static`, `backend-tests` | `artifacts/backend-junit.xml`; `artifacts/coverage.json` | `partial` (sync anchor: release bundle `RC-004` in matrix/readiness is `partial`) | Dedicated acceptance criterion for files-deny isolation is not yet normalized as a standalone RC row; evidence exists but closure is indirect via final acceptance aggregate. |
| US-RES-PERF-004 | **As a release manager/SRE**, I want restore and performance readiness gates to be green with reproducible manifests so that launch risk is bounded by explicit RTO/RPO and perf baselines. | Restore: `scripts/restore_drill.py` (`--mode postgres-minio`), `docs/stabilization/restore-drill.md`; Perf: `scripts/perf/api_load.py`, `scripts/perf/scenarios.json`, `scripts/perf/README.md` | `.github/workflows/restore-drill.yml` → `restore-drill`; `.github/workflows/perf-baseline.yml` → `baseline` | `artifacts/restore-drill/latest-postgres-minio.json`; `artifacts/perf/nightly/trend-manifest.json`; `artifacts/perf/nightly/summary.md` | `partial` (sync: `RELEASE_READINESS.md`, RC-001 + RC-002) | Both gates are instrumented, but latest readiness verdict remains NOT READY until restore/perf acceptance checklists are formally closed. |
| US-E2E-NO-CREDS-005 | **As a CI owner**, I want mandatory smoke to run without external credentials so that baseline acceptance is deterministic across environments. | `frontend/e2e/smoke.spec.ts` → tests tagged `mandatory (no external creds)`; workflow matrix identifier `credential_source=bootstrap_local` in `.github/workflows/e2e-smoke.yml` | `.github/workflows/e2e-smoke.yml` → `playwright-smoke-minimal`, `playwright-smoke-credential` (`bootstrap_local`) | Playwright run logs; `e2e-backend-log-bootstrap_local` (failure-only) | `partial` (sync anchor: `RELEASE_READINESS.md`, RC-006 is `missing`; credential-independent lane exists but diagnostics closure is pending) | Baseline lane exists and is executable, but release criterion for secrets/diagnostics hardening is still open (`RC-006`). |

## Status synchronization notes

1. Story statuses above are intentionally **mirrored** from currently published release-facing docs (`ACCEPTANCE_TEST_MATRIX.md`, `RELEASE_READINESS.md`) and do not override canonical blocker tracking.
2. If any release-critical status changes, update order remains:
   1) `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
   2) `RELEASE_READINESS.md`
   3) `ACCEPTANCE_TEST_MATRIX.md`
   4) this traceability map.

## Related sources

- `ACCEPTANCE_TEST_MATRIX.md`
- `RELEASE_READINESS.md`
- `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- `.github/workflows/ci.yml`
- `.github/workflows/e2e-smoke.yml`
- `.github/workflows/restore-drill.yml`
- `.github/workflows/perf-baseline.yml`
