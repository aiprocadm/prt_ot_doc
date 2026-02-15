# TZ_COMPLIANCE

Статусы: **OK / Partial / Missing**. Приоритет: **P0 / P1 / P2**.

## SPEC ↔ CODE matrix

| Требование | Реализация | Статус | Priority | План |
|---|---|---|---|---|
| KPI-2: X-Tenant обязателен на `/api/v1` | `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`, `tests/test_tenant_header_required.py` | OK | P0 | Поддерживать guardrails при добавлении новых роутов |
| Tenant isolation in DB | tenant-aware sessions/schemas (`backend/app/db/session.py`, `backend/app/models/models.py`) | OK | P0 | Непрерывные integration проверки |
| RBAC + ABAC | `backend/app/core/security.py`, `backend/app/api/dependencies.py`, `tests/test_rbac_abac.py`, `tests/unit/test_abac_policies.py` | Partial | P1 | Расширять ABAC coverage на новые mutation endpoints |
| Audit append-only | `AuditLog` + listeners `before_update/delete` в `backend/app/models/models.py`, tests `tests/test_audit_log_immutability.py` | OK | P0 | Закрыто |
| Documents generate/batch idempotency (KPI-1) | `backend/app/services/idempotency.py`, idempotency middleware в `backend/app/api/app.py`, tests `tests/test_idempotency.py` | OK | P0 | Закрыто |
| Templates strict `(template_code, version)` + delete guard 409 (KPI-3) | docs routes/services + tests `tests/test_template_delete.py` | OK | P0 | Закрыто |
| Outbox + retries/backoff + dead-letter + metrics | `backend/app/services/outbox.py`, `backend/app/services/webhooks.py`, tests `tests/test_outbox_dispatch.py`, `tests/test_webhook_routing.py` | OK | P0 | Закрыто |
| KPI-4 outbox→webhook ≤60s | async dispatch tests (`tests/test_outbox_dispatch.py`) | Partial | P1 | Добавить явную time-bound assertion на уровне integration/perf profile |
| KPI-5 deterministic risk + action plan | `backend/app/services/risk.py`, tests `tests/test_risk_assessment_kpi5.py` | OK | P0 | Закрыто |
| Webhooks global + per-tenant override | settings + subscription routing (`backend/app/services/webhooks.py`, `WebhookSubscription`) | OK | P0 | Закрыто |
| Obligations/deadlines central value | `backend/app/services/obligations.py`, `tasks.py`, integration tests | Partial | P1 | Расширить dashboard overdue/reporting на UX-уровне |
| DevX “open → run” | `Makefile` + `scripts/dev_lite.sh` + docs | OK | P0 | Закрыто |
| Test discovery in Codespaces/VS Code | `pyproject.toml`, `.vscode/settings.json`, `sitecustomize.py`, `vscode_pytest.py`, `test_env_defaults.py` | OK | P0 | Закрыто |

## Gap list (P0/P1/P2)

### P0 (fixed)
1. Dependency onboarding unified to pip/requirements.
2. Discovery defaults switched to memory/local to avoid external services.
3. Codespaces dev flow now prints backend readiness and supports repeatable startup.
4. Dev admin bootstrap validated in `APP_ENV=development|test` flow.

### P1 (open)
1. KPI-4 explicit 60s SLA assertion can be made stricter in dedicated integration/perf checks.
2. ABAC coverage should expand as new write endpoints appear.
3. Frontend has several test warnings (`act(...)`, react-router future flags); non-blocking but noisy.

### P2 (open)
1. Reduce SAWarning noise (relationship overlaps hints) for cleaner local DX.
2. Dependency/transitive vulnerability cleanup for frontend npm tree.
