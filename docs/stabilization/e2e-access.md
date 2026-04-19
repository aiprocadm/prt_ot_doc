# E2E Access and Credential Matrix (Stabilization)

_Last updated: 2026-04-19._

This file tracks what end-to-end access paths are implemented today and where signal is reduced by credential-dependent skips.

## Existing E2E execution paths

- Browser smoke scenarios: `frontend/e2e/smoke.spec.ts`.
- Scheduled/manual E2E workflow: `.github/workflows/e2e-smoke.yml`.
- Backend pilot e2e-like checks: `tests/e2e/pilot_smoke/test_pilot_smoke_matrix.py`.

## Scenario-to-evidence map

| Scenario | Where implemented | Required env/secrets | Current behavior |
|---|---|---|---|
| Login page renders | `frontend/e2e/smoke.spec.ts` (`login page renders`) | none (server required) | Runs when `E2E_BASE_URL` or `E2E_START_SERVER=1` is set |
| Protected route redirects to login | `frontend/e2e/smoke.spec.ts` (`protected route redirects to login when logged out`) | none (server required) | Runs without user credentials |
| Wrong password inline error | `frontend/e2e/smoke.spec.ts` (`login wrong password shows inline error`) | `E2E_USER_EMAIL` | Skipped if email is missing |
| Happy-path login (R11) | `frontend/e2e/smoke.spec.ts` (`R11 login happy path`) | `E2E_USER_EMAIL`, `E2E_USER_PASSWORD` | Skipped if creds are missing |
| Limited-role denied on documents (R12) | `frontend/e2e/smoke.spec.ts` (`R12 limited user denied on documents route`) | `E2E_LIMITED_USER_EMAIL`, `E2E_LIMITED_USER_PASSWORD` | Skipped if limited creds are missing |
| Logout returns to login | `frontend/e2e/smoke.spec.ts` (`logout returns to login`) | default user creds | Skipped if creds are missing |

## Workflow-level evidence

`.github/workflows/e2e-smoke.yml`:

- Runs weekly (`cron`) and manually (`workflow_dispatch`).
- Installs Playwright browsers and runs `npm run e2e`.
- Passes `E2E_*` values from repository secrets.
- Notes in workflow comments indicate tests can be skipped without failing when secrets are absent.

## Explicit current gaps

1. Credentialed authorization scenarios are non-mandatory in CI due to skip behavior.
2. No gate verifies that required e2e credentials are present for release-candidate branches.
3. No dedicated artifact policy (trace/video/log retention) defined in stabilization docs.

## Acceptance criteria for this workstream

- Required credential matrix (default + limited role user) is documented and validated for release environments.
- Stabilization sign-off requires successful execution of credentialed scenarios (R11/R12 + logout).
- Workflow artifacts for failed and passed runs are retained and linked in release evidence.
