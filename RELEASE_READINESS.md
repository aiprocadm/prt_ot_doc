# RELEASE_READINESS

- **Updated on (UTC):** 2026-04-22
- **Owner:** Release Manager + Platform + QA + SRE
- **Canonical status vocabulary:** `done` / `partial` / `missing`

## Evidence-backed readiness summary

| Readiness claim | Status | Test evidence | Workflow evidence | Script evidence | Doc evidence |
|---|---|---|---|---|---|
| Bootstrap and access foundations are release-usable | `done` | bootstrap smoke/test slices in acceptance matrix | `.github/workflows/ci.yml` | `scripts/bootstrap_tenant.py`, `scripts/bootstrap_demo_tenant.py` | `backend/app/services/dev_bootstrap.py`, `ACCEPTANCE_TEST_MATRIX.md` |
| Template upload/lint/preview + generation baseline is stable | `done` | `tests/test_template_catalog_scope.py`, `tests/test_documents_generate.py` | `.github/workflows/ci.yml` | — | `/api/v1/templates/*`, `/api/v1/documents/generate`, `ACCEPTANCE_TEST_MATRIX.md` |
| Backend coverage non-regression gate is active | `done` | pytest coverage artifacts generated in CI | `.github/workflows/ci.yml` (`backend-tests`) | `scripts/ci/check_backend_coverage_baseline.py` | `docs/stabilization/backend_coverage_baseline.json`, `docs/stabilization/coverage.md` |
| Tenant isolation + contract/idempotency slices are stable | `done` | `tests/integration/test_tenant_isolation.py`, `tests/contract/test_openapi_contract.py`, `tests/test_idempotency.py` | `.github/workflows/ci.yml` | `scripts/pytest.sh` | `ACCEPTANCE_TEST_MATRIX.md` |
| End-to-end operational cutover confidence is complete | `partial` | restore/security/e2e hardening tests are incomplete | `.github/workflows/e2e-smoke.yml` (hardening pending) | `scripts/restore_drill.py` (criteria formalization pending) | `docs/stabilization/PLAN.md`, `GAP_REPORT.md`, `KNOWN_LIMITATIONS.md` |
| Full production runbook closure (RTO/RPO + escalation ownership + secrets e2e diagnostics) is complete | `missing` | missing closure tests tracked in gap report | `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml` | restore/e2e scripts pending updates | `docs/stabilization/restore-drill.md`, `docs/stabilization/security-gates.md`, `docs/stabilization/e2e-access.md`, `GAP_REPORT.md` |

## Launch readiness verdict

- **Verdict date (UTC):** 2026-04-22
- **Verdict:** **NOT READY**
- **Evidence basis:**
  1. `GAP_REPORT.md` retains release-critical `missing` entries (restore go/no-go formalization, escalation ownership SLA, secrets-dependent e2e diagnostics).
  2. `docs/stabilization/PLAN.md` retains matching `missing` statuses in Blocks A, B, and C.
  3. `KNOWN_LIMITATIONS.md` lists operationally relevant `partial`/`missing` constraints that block clean cutover confidence.

This verdict is intentionally consistent with the open gaps listed above and should not be interpreted as contradictory with any `done` subsystem-level claims.

## Conditions to flip verdict to READY

All must be true:
1. Missing items in `docs/stabilization/PLAN.md` are closed to `done` with linked executable evidence.
2. `GAP_REPORT.md` has no unresolved release-critical `missing` entries.
3. `KNOWN_LIMITATIONS.md` has no release-blocking `missing` items.
4. Cutover checklist execution is evidenced by scripts/tests/workflows and recorded in release artifacts.
