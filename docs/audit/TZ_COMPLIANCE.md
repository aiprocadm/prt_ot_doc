# TZ Compliance Matrix (Full Spec 1–13)

Legend: **OK** / **Partial** / **Missing**. Severity: **P0** (must-fix now), **P1**, **P2**.

## Failure Map (diagnostic pass)
- `pytest --collect-only -q` initially failed with `ModuleNotFoundError: pytest_asyncio` when only runtime deps were installed; fixed by explicit `requirements.txt + requirements-dev.txt` install flow in runbooks.
- Dockerless bootstrap with `alembic upgrade head` failed because repo has multiple Alembic heads; fixed by upgrading via `heads`.
- Dockerless bootstrap with SQLite migrations failed (`JSONB` types in initial migration). For Codespaces lite mode, startup now relies on metadata bootstrap path (DB file reset) rather than Alembic against SQLite.
- Existing local `dev.db` schema drift can break startup (missing columns, e.g. `company.kpp`); fixed by deterministic DB reset in `scripts/dev_lite.sh`.
- Direct backend smoke call must target `/health` (not `/api/v1/health`), because service probes are mounted outside `/api/v1` in `backend/app/api/routes/health.py`.
- Direct KPI test execution without `APP_ENV=test` and in-memory Redis variables can fail with Redis DNS errors; documented deterministic test env (`REDIS_URL=memory://`, `REDIS_RESULT_URL=cache+memory://`, `RATE_LIMIT_STORAGE_URI=memory://`).

## Matrix

| # | Requirement | Where in code | Status | Severity | Fix plan |
|---|---|---|---|---|---|
| 1 | Multitenancy and strict isolation (`X-Tenant` on business routes, tenant-scoped DB) | `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`, `backend/app/api/dependencies.py`, `frontend/src/api/client.ts`, tests `tests/test_tenant_header_required.py`, `frontend/src/__tests__/apiClient.test.ts` | OK | - | Keep coverage for new routes. |
| 2 | Roles and access (RBAC + ABAC by company/site/document/status/risk_level) | `backend/app/core/security.py`, `backend/app/services/auth.py`, `frontend/src/permissions/*`, tests `tests/test_rbac_abac.py`, `tests/unit/test_abac_policies.py` | Partial | P1 | Extend ABAC checks for more mutation paths and domain resources. |
| 3 | Append-only audit log (no update/delete) | `backend/app/services/audit.py`, `backend/app/api/routes/audit.py`, tests `tests/test_audit_log_immutability.py`, `tests/test_audit_log_api.py` | OK | - | Keep immutable API shape and migration guards. |
| 4 | Core entities (counterparties/contracts/orders/invoices/org/person/workplace) | `backend/app/models/*`, routers `contracts.py`, `orders.py`, `invoices.py`, `companies.py`, `persons.py`, `departments.py`, `sites.py` | Partial | P1 | Fill lifecycle/business validations where CRUD-only. |
| 5 | Documents/templates/versioning (`template_code+version`, delete referenced -> 409, pipeline) | `backend/app/api/routes/documents.py`, `backend/app/services/documents.py`, `backend/app/services/pipeline.py`, tests `tests/test_documents_generate.py`, `tests/test_template_delete.py` | OK | - | Continue hardening conversion extras (QR/watermark) under flags. |
| 6 | EDI/signature status model (MVP internal contour acceptable) | `backend/app/domains/sign/signer.py`, `backend/app/services/events.py`, document/outbox events in document services/tests | Partial | P2 | Expand protocol detail and external provider adapters gradually. |
| 7 | Risks: methodologies, deterministic cards + action plans | `backend/app/services/risk.py`, `backend/app/domains/risk/calc.py`, routes `risk.py`, tests `tests/test_risk_assessment_kpi5.py` | OK | - | Keep deterministic fixtures and idempotency coverage. |
| 8 | PPE norms/issues/returns/journal | routes `backend/app/api/routes/ppe.py`, domain `backend/app/domains/ppe/service.py`, tests `tests/api/test_ppe_api.py` | Partial | P1 | Add deeper stock/accounting validations and reminders. |
| 9 | Training/instruction journals | routes `backend/app/api/routes/training.py`, `journals.py`, domain `backend/app/domains/training/service.py`, tests `tests/api/test_training_api.py` | Partial | P1 | Add richer protocol/certificate lifecycle checks. |
| 10 | Incidents/inspections/prescriptions non-empty modules | routes `incidents.py`, `inspections.py`, `prescriptions.py`, tests `tests/api/test_incidents_api.py`, `tests/integration/test_prescriptions_api.py` | Partial | P2 | Expand workflows from registry skeletons. |
| 11 | Obligations/tasks/reminders/overdue control | `backend/app/services/obligations.py`, `backend/app/services/tasks.py`, routes `obligations.py`, `tasks.py`, tests `tests/integration/test_obligation_tasks.py`, `tests/unit/test_task_reminders.py` | OK | - | Continue auto-creation expansion per domain events. |
| 12 | Integrations: Idempotency-Key, outbox retries/backoff/dead-letter/metrics, webhooks routing global + tenant | `backend/app/core/idempotency.py`, `backend/app/services/idempotency.py`, `backend/app/services/outbox.py`, `backend/app/services/webhooks.py`, tests `tests/test_idempotency.py`, `tests/test_outbox_dispatch.py`, `tests/test_webhook_routing.py`, `tests/test_webhooks_dispatch.py` | OK | - | Keep SLA checks and retry metrics visible in runbook. |
| 13 | DevX/quality: Codespaces open→run, dockerless fallback, test discovery, docs truth source, CI checks only | `.devcontainer/*`, `scripts/dev_lite.sh`, `scripts/test_lite.sh`, `.vscode/settings.json`, `Makefile`, `.github/workflows/ci.yml`, `docs/runbook-codespaces.md`, `README.md` | OK | - | Keep CI in `.github/workflows`, avoid auto-fix actions. |

## Security & Tenant Isolation Risks
- **P1:** ABAC policies are present but still uneven across some low-frequency mutation endpoints.
- **P1:** Tenant mismatch protections are strong on API/middleware, but every new endpoint must keep tenant-scoped repository filters by default.

## DevX Risks (Codespaces)
- **Resolved P0:** multiple Alembic heads made default `upgrade head` non-deterministic.
- **Resolved P0:** SQLite + Alembic mismatch (`JSONB`) broke dockerless setup; runbook/scripts rely on dockerless metadata bootstrap path for local lite mode.

## Test Discovery Risks
- **Resolved P0:** missing dev dependencies causes immediate collection failure (`pytest_asyncio`).
- VS Code Python testing discovery is configured (`.vscode/settings.json` + `vscode_pytest.py`) and CLI collection works.

## Docs Consistency Risks
- **Resolved P1:** CI file moved to `.github/workflows/ci.yml` so GitHub Actions discovers it.
- **Resolved P1:** migration command references normalized from `upgrade head` to `upgrade heads` where Alembic is used.

## Summary
- **OK:** 6
- **Partial:** 6
- **Missing:** 0
- **Open P0:** 0
- **Open P1:** 5
- **Open P2:** 2

## Prioritized change list (post-audit)

### P0 (must keep green)
- No open P0 gaps after current verification pass (`make test:lite`, `pytest --collect-only -q`, frontend vitest run).

### P1 (next iteration)
- **Backend:** broaden ABAC enforcement to all mutation endpoints (especially registry update/delete paths still operating as role-only checks).
- **Backend:** deepen PPE/training workflow states (protocol lifecycle, stock reconciliation, stricter due-date automations).
- **Frontend:** expose richer obligation overdue analytics and tenant-aware filters for registry-heavy pages.
- **DevX:** reduce duplicate dependency bootstrap in `scripts/dev_lite.sh`/`scripts/test_lite.sh` (cache/pinning optimization for Codespaces cold starts).
- **Tests/CI:** convert recurring React `act(...)` warnings into explicit async UI waits to lower noisy CI logs.

### P2 (deferred enhancements)
- Expand EDI/signature protocol detail beyond MVP internal contour.
- Extend inspections/prescriptions registry skeletons to full investigation workflows and richer reporting forms.
