# E2E quick start

## 1) Prerequisites

- Install Playwright browsers once:
  - `npm run e2e:install`

## 2) Prepare env file

- Create local env file from template:
  - PowerShell: `Copy-Item e2e.env.example e2e.env`
- Fill required values in `e2e.env`:
  - `E2E_USER_EMAIL`
  - `E2E_USER_PASSWORD`
- Keep `E2E_TENANT=demo` unless you use a different tenant.

## 3) Run key IA scenarios (Windows, one command)

- `npm run e2e:key-scenarios:ps`

This command loads `E2E_*` variables from `e2e.env` and runs:
- `playwright test e2e/key-scenarios.spec.ts`

## 4) Run smoke suite

- With local dev server:
  - `$env:E2E_START_SERVER="1"; npm run e2e`
- Against existing environment:
  - `$env:E2E_BASE_URL="http://127.0.0.1:4173"; npm run e2e`

## 5) Production bundle check

- `$env:E2E_PREVIEW="1"; $env:E2E_START_SERVER="1"; npm run e2e`

## 6) Limited-role access checks (optional)

Set these in `e2e.env`:
- `E2E_LIMITED_USER_EMAIL`
- `E2E_LIMITED_USER_PASSWORD`

Then run smoke:
- `npm run e2e`

## 7) Troubleshooting

- If all key scenarios are skipped, check:
  - `E2E_START_SERVER=1` or `E2E_BASE_URL` is set
  - `E2E_USER_EMAIL` and `E2E_USER_PASSWORD` are non-empty
- If login fails, verify tenant and credentials in `e2e.env`.
