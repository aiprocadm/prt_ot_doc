# GAP_REPORT

- **Updated on:** 2026-04-22
- **Owner:** Stabilization Program (Platform + QA + Product Engineering)
- **Canonical status vocabulary:** `done` / `partial` / `missing`

## Done (closed in recent waves)

| Gap area | Status | Evidence |
|---|---|---|
| Tenant/owner/demo bootstrap reproducibility | done | `scripts/bootstrap_tenant.py`, `scripts/bootstrap_demo_tenant.py`, `backend/app/services/dev_bootstrap.py`, `ACCEPTANCE_TEST_MATRIX.md` |
| Template catalog contract normalization | done | `tests/test_template_catalog_scope.py`, `backend/app/api/v1/router.py`, `docs/TEMPLATE_UPLOAD_AND_RENDERING.md` |
| Structured notifications validation hardening | done | `tests/api/test_notifications_calendar_api.py`, `tests/test_workflow_api.py` |
| Branding header/footer detail split and branch label carry-through | done | `tests/api/test_branding_api.py`, branding modules, `KNOWN_LIMITATIONS.md` |
| Branded wizard preview continuity | done | `frontend/src/stores/documentsWizard.ts`, `frontend/src/__tests__/DocumentsWizardPage.test.tsx` |
| Repo audit reproducibility checks | done | `scripts/repo_audit.py`, `tests/test_repo_audit.py` |

## Partial (implemented but not fully closed)

| Gap area | Status | Evidence |
|---|---|---|
| Automatic `generate -> apply_headers -> pdf` chain across all entrypoints | partial | `KNOWN_LIMITATIONS.md`, `scripts/branded_document_smoke.py` |
| Template override resolution centralization at generation time | partial | `ACCEPTANCE_TEST_MATRIX.md`, `backend/app/api/routes/documents.py` |
| Calendar/notification coverage breadth across all modules | partial | `tests/api/test_notifications_calendar_api.py`, `tests/test_workflow_api.py` |
| Workspace hub routes maturity | partial | `frontend/src/pages/workspace/WorkspaceAttentionPage.tsx`, `WorkspaceDataQualityPage.tsx`, `SyncConflictHelpPage.tsx`, `npm --prefix frontend run build` |
| Coverage traceability beyond backend gate baseline | partial | `docs/stabilization/coverage.md`, `docs/TESTING.md`, `ACCEPTANCE_TEST_MATRIX.md` |

## Missing (explicit next-wave work)

| Gap area | Status | Evidence target |
|---|---|---|
| Fully relational/indexed template scope model (away from metadata-only scope) | missing | schema/migration + API tests (future PR) |
| Dedicated branch entity separate from current `Site` model | missing | backend model + migration + API contract tests |
| Restore drill RTO/RPO formal go/no-go criteria | missing | `docs/stabilization/restore-drill.md`, `docs/runbooks/RESTORE_TENANT.md`, `scripts/restore_drill.py` |
| Security gate ownership fallback + escalation SLA codification | missing | `docs/stabilization/security-gates.md`, `.github/CODEOWNERS` |
| Secrets-dependent e2e diagnostics hardening | missing | `.github/workflows/e2e-smoke.yml`, `docs/stabilization/e2e-access.md` |
