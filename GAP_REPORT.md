# GAP_REPORT

- **Updated on (UTC):** 2026-04-22
- **Owner:** Stabilization Program (Platform + QA + Product Engineering)
- **Canonical status vocabulary:** `done` / `partial` / `missing`
- **Blocker status source of truth:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`

## `done` gaps (closed in recent waves)

| Gap area | Status | Test evidence | Workflow evidence | Script evidence | Doc evidence |
|---|---|---|---|---|---|
| Tenant/owner/demo bootstrap reproducibility | `done` | — | `.github/workflows/ci.yml` | `scripts/bootstrap_tenant.py`, `scripts/bootstrap_demo_tenant.py` | `backend/app/services/dev_bootstrap.py`, `ACCEPTANCE_TEST_MATRIX.md` |
| Template catalog contract normalization | `done` | `tests/test_template_catalog_scope.py` | `.github/workflows/ci.yml` | — | `backend/app/api/v1/router.py`, `docs/TEMPLATE_UPLOAD_AND_RENDERING.md` |
| Structured notifications validation hardening | `done` | `tests/api/test_notifications_calendar_api.py`, `tests/test_workflow_api.py` | `.github/workflows/ci.yml` | — | `ACCEPTANCE_TEST_MATRIX.md` |
| Branding header/footer detail split and branch label carry-through | `done` | `tests/api/test_branding_api.py` | `.github/workflows/ci.yml` | — | branding modules, `KNOWN_LIMITATIONS.md` |
| Branded wizard preview continuity | `done` | `frontend/src/__tests__/DocumentsWizardPage.test.tsx` | `.github/workflows/ci.yml` | frontend vitest commands | `frontend/src/stores/documentsWizard.ts` |
| Repo audit reproducibility checks | `done` | `tests/test_repo_audit.py` | `.github/workflows/ci.yml` | `scripts/repo_audit.py` | `ACCEPTANCE_TEST_MATRIX.md` |

## `partial` gaps (implemented but not fully closed)

| Gap area | Status | Test evidence | Workflow evidence | Script evidence | Doc evidence |
|---|---|---|---|---|---|
| Automatic `generate -> apply_headers -> pdf` chain across all entrypoints | `partial` | branded flow coverage (partial) | `.github/workflows/ci.yml` | `scripts/branded_document_smoke.py` | `KNOWN_LIMITATIONS.md` |
| Template override resolution centralization at generation time | `partial` | partial backend route coverage | `.github/workflows/ci.yml` | — | `ACCEPTANCE_TEST_MATRIX.md`, `backend/app/api/routes/documents.py` |
| Calendar/notification coverage breadth across all modules | `partial` | `tests/api/test_notifications_calendar_api.py`, `tests/test_workflow_api.py` | `.github/workflows/ci.yml` | — | `ACCEPTANCE_TEST_MATRIX.md` |
| Workspace hub routes maturity | `partial` | frontend route coverage (partial) | `.github/workflows/e2e-smoke.yml` | `npm --prefix frontend run build` | `frontend/src/pages/workspace/WorkspaceAttentionPage.tsx`, `WorkspaceDataQualityPage.tsx`, `SyncConflictHelpPage.tsx` |
| Coverage traceability beyond backend gate baseline | `partial` | e2e + integration slices (partial mapping) | `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml` | `scripts/pytest.sh` | `docs/stabilization/coverage.md`, `docs/TESTING.md`, `ACCEPTANCE_TEST_MATRIX.md` |

## `missing` gaps (explicit next-wave work)

| Gap area | Status | Test evidence target | Workflow evidence target | Script evidence target | Doc evidence target |
|---|---|---|---|---|---|
| Fully relational/indexed template scope model (away from metadata-only scope) | `missing` | new API + migration tests | `.github/workflows/ci.yml` | migration/validation scripts | schema/migration design docs |
| Dedicated branch entity separate from current `Site` model | `missing` | new backend contract tests | `.github/workflows/ci.yml` | migration scripts | backend model/migration docs |
| Restore drill RTO/RPO formal go/no-go criteria | `missing` | `tests/test_health_ready.py` (closure criteria updates) | `.github/workflows/ci.yml` | `scripts/restore_drill.py` | `docs/stabilization/restore-drill.md`, `docs/runbooks/RESTORE_TENANT.md` |
| Security gate ownership fallback + escalation SLA codification | `missing` | ownership/guardrail regression tests (target) | `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml` | `scripts/ci/static_gates.sh` (target updates) | `docs/stabilization/security-gates.md`, `.github/CODEOWNERS` |
| Secrets-dependent e2e diagnostics hardening | `missing` | `tests/e2e/access/test_access_enforcement_matrix.py` | `.github/workflows/e2e-smoke.yml` | e2e diagnostics scripts (target) | `docs/stabilization/e2e-access.md` |
