# ACCEPTANCE_TEST_MATRIX

- **Updated on (UTC):** 2026-04-22
- **Owner:** QA + Platform + Backend + Frontend
- **Canonical status vocabulary:** `done` / `partial` / `missing`
- **Blocker status source of truth:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`

## Acceptance gate (exact workflow + artifacts)

| Gate | Status | Partial/missing reason | Exact command/workflow | Artifact path(s) |
|---|---|---|---|---|
| Final acceptance gate | `partial` | Not all matrix scenarios are closed to `done`; required release-wide `overall_status=pass` evidence bundle is not yet recorded as closure artifact. | `make final-acceptance` (executes `scripts/final_acceptance.sh`), plus CI/e2e companion workflows `.github/workflows/ci.yml` and `.github/workflows/e2e-smoke.yml`. | `artifacts/final_acceptance/summary.json`, `artifacts/final_acceptance/summary.md`, `artifacts/final_acceptance/*.log`. |

Release decision is governed by the binary artifact-bound go/no-go in `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` and reflected in `RELEASE_READINESS.md`.

## Matrix (deduplicated canonical table)

| Scenario | Status | Partial/missing reason | Test evidence | Workflow evidence | Script evidence | Artifact path(s) | Doc evidence |
|---|---|---|---|---|---|---|---|
| Owner bootstrap | `done` | — | — | `.github/workflows/ci.yml` | `scripts/bootstrap_tenant.py` | CI logs for bootstrap step | `backend/app/services/tenants/bootstrap/service.py` |
| Demo bootstrap | `done` | — | — | `.github/workflows/ci.yml` | `scripts/bootstrap_demo_tenant.py` | CI logs for bootstrap step | `backend/app/services/demo_bootstrap.py` |
| Dev admin bootstrap | `done` | — | — | `.github/workflows/ci.yml` | — | CI logs for bootstrap step | `backend/app/services/dev_bootstrap.py` |
| Template catalog card creation | `done` | — | `tests/test_template_catalog_scope.py` | `.github/workflows/ci.yml` | — | `artifacts/backend-junit.xml` | `/api/v1/templates/catalog` |
| Template version upload | `done` | — | `tests/test_template_catalog_scope.py` | `.github/workflows/ci.yml` | — | `artifacts/backend-junit.xml` | `/api/v1/templates/{id}/versions:upload` |
| Template lint + preview API | `done` | — | `tests/test_template_catalog_scope.py` | `.github/workflows/ci.yml` | — | `artifacts/backend-junit.xml` | `/api/v1/templates/{id}/versions/{version_id}:lint`, `/api/v1/templates/{id}/versions/{version_id}:preview` |
| Organization document generation | `done` | — | `tests/test_documents_generate.py` | `.github/workflows/ci.yml` | — | `artifacts/backend-junit.xml` | `/api/v1/documents/generate` |
| Branch/site template scope | `partial` | Additional scope variants are not fully covered by dedicated acceptance scenarios. | `tests/test_template_catalog_scope.py` | `.github/workflows/ci.yml` | — | `artifacts/backend-junit.xml` | `docs/TEMPLATE_UPLOAD_AND_RENDERING.md` |
| Header/footer apply | `done` | — | `tests/api/test_branding_api.py` | `.github/workflows/ci.yml` | — | `artifacts/backend-junit.xml` | branding modules |
| Replace dry-run/reporting | `partial` | Foundation-only coverage; end-to-end acceptance reporting path is incomplete. | replace API/tests (foundation only) | `.github/workflows/ci.yml` | — | Partial CI logs only (no dedicated artifact bundle) | replace API docs |
| PDF conversion | `partial` | Existing tests do not yet close full acceptance criteria for conversion reliability. | existing celery/pdf tests | `.github/workflows/ci.yml` | — | Partial CI logs only (no dedicated artifact bundle) | celery/pdf modules |
| Approval/sign/archive handoff | `partial` | Flow is partially tested; full handoff acceptance path remains incomplete. | approval/sign/document preview tests (partial) | `.github/workflows/ci.yml` | — | Partial CI logs only (no dedicated artifact bundle) | flow docs |
| Tenant isolation | `done` | — | `tests/integration/test_tenant_isolation.py`, `tests/integration/test_abac_query_isolation.py` | `.github/workflows/ci.yml` | `./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_abac_query_isolation.py` | `artifacts/backend-junit.xml` | `docs/TESTING.md` |
| Structured errors contract | `done` | — | `tests/test_errors.py`, `tests/e2e/final_regression/test_final_regression_api.py`, frontend vitest slices | `.github/workflows/ci.yml` | `./scripts/pytest.sh ...` | `artifacts/backend-junit.xml` + e2e logs | `docs/TESTING.md` |
| Notifications contract hardening | `done` | — | `tests/api/test_notifications_calendar_api.py` | `.github/workflows/ci.yml` | `./scripts/pytest.sh tests/api/test_notifications_calendar_api.py` | `artifacts/backend-junit.xml` | `GAP_REPORT.md` |
| OpenAPI contract stability | `done` | — | `tests/contract/test_openapi_contract.py` | `.github/workflows/ci.yml` | `PYTHONPATH=backend python scripts/contract/validate.py` | contract test logs | `docs/TESTING.md` |
| Idempotent generation/writes | `done` | — | `tests/test_idempotency.py`, integration idempotency tests | `.github/workflows/ci.yml` | `./scripts/pytest.sh ...` | `artifacts/backend-junit.xml` | `docs/TESTING.md` |
| Async status transparency | `done` | — | `tests/integration/test_job_status_flow.py`, outbox/webhooks tests | `.github/workflows/ci.yml` | `./scripts/pytest.sh ...` | `artifacts/backend-junit.xml` | `docs/TESTING.md` |
| Search/export performance smoke | `partial` | Perf tooling exists, but release baseline evidence is tracked via perf workflow and not yet closed in readiness decision. | baseline scenarios from `scripts/perf/scenarios.json` | `.github/workflows/perf-baseline.yml` | `python scripts/perf/api_load.py ... --output-json artifacts/perf/nightly/<scenario>.json` | `artifacts/perf/nightly/*.json`, `artifacts/perf/nightly/trend-manifest.json` | `scripts/perf/README.md` |
| Release docs completeness | `done` | — | `tests/e2e/test_release_candidate_docs.py` | `.github/workflows/ci.yml` | `./scripts/pytest.sh tests/e2e/test_release_candidate_docs.py` | `artifacts/backend-junit.xml` | release docs |
| Repository audit reproducibility | `done` | — | `tests/test_repo_audit.py` | `.github/workflows/ci.yml` | `python scripts/repo_audit.py` | repo audit command log | repo audit docs |
| Frontend production bundle stability | `done` | — | — | `.github/workflows/ci.yml` | `npm --prefix frontend run build` | frontend build logs | `frontend/vite.config.ts` |
| Frontend no-dead-end wizard actions | `done` | — | frontend vitest wizard suites | `.github/workflows/e2e-smoke.yml` | `cd frontend && npx vitest run GeneratePackWizardPage DocumentsWizardPage` | vitest output logs | frontend wizard docs |
| Frontend branded preview continuity | `done` | — | `frontend/src/__tests__/DocumentsWizardPage.test.tsx` | `.github/workflows/ci.yml` | `cd frontend && npx vitest run src/__tests__/DocumentsWizardPage.test.tsx` | vitest output logs | `frontend/src/stores/documentsWizard.ts` |
| TZ Wave 3 document signed hook | `done` | — | `tests/services/test_domain_hooks_document_signed.py` | `.github/workflows/ci.yml` | `./scripts/pytest.sh tests/services/test_domain_hooks_document_signed.py` | `artifacts/backend-junit.xml` | TZ wave docs |
| TZ Wave 5 EDO adapter factory | `done` | — | `tests/services/test_edo_integration_factory.py` | `.github/workflows/ci.yml` | `./scripts/pytest.sh tests/services/test_edo_integration_factory.py` | `artifacts/backend-junit.xml` | TZ wave docs |
| TZ Wave 4 workspace hub routes | `partial` | Route coverage exists but remains partial for complete workspace acceptance behavior. | frontend route tests (partial) | `.github/workflows/e2e-smoke.yml` | `npm --prefix frontend run build` | frontend build logs + partial e2e logs | `frontend/src/pages/workspace/WorkspaceAttentionPage.tsx`, `WorkspaceDataQualityPage.tsx`, `SyncConflictHelpPage.tsx` |

## CI / merge-gate mapping

- Canonical testing map: `docs/TESTING.md`.
- Coverage non-regression gate: `docs/stabilization/coverage.md` + `.github/workflows/ci.yml` (`backend-tests`).
- Typical acceptance bundle:

```bash
make final-acceptance
./scripts/pytest.sh tests/test_errors.py tests/e2e/final_regression/test_final_regression_api.py
./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_job_status_flow.py
python scripts/perf/api_load.py --help
python scripts/pilot_readiness.py
```

## Linked decision docs

- Gap analysis: `GAP_REPORT.md`
- Release verdict: `RELEASE_READINESS.md`
- Blocker status source: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- Accepted constraints: `KNOWN_LIMITATIONS.md`
- Stabilization plan: `docs/stabilization/PLAN.md`
