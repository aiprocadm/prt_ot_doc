# TZ Coverage Matrix

Дата обновления: 2026-02-18  
Базовый прогон: `make cs:reset`, `make cs:dev`, `make cs:test`, `./scripts/pytest.sh --collect-only -q`, `npm --prefix frontend test`.

## MVP + ключевые acceptance criteria

| Requirement | Backend (module/file/endpoint) | DB (tables/migrations) | Jobs (Celery/tasks) | Events (outbox/webhooks) | Frontend (screens/features) | Tests | Status | Priority | Fix plan |
|---|---|---|---|---|---|---|---|---|---|
| §1.1 Tenant required (`X-Tenant`) | `backend/app/middleware/tenant.py`, `/api/v1/*` routers | tenant-aware entities | tenant_id in payload (logical) | tenant in event payload | tenant gate + tenant store | `tests/test_tenant_header_required.py`, `tests/test_middleware_tenant.py` | OK | P0 | — |
| §1.2 RBAC | auth dependencies/policy checks | roles/users tables | n/a | audit of access decisions | route guards / Can component | `tests/test_rbac_abac.py`, `frontend/src/__tests__/Can.test.tsx` | Partial | P0 | расширить полный список ролей при изменении ТЗ |
| §1.3 ABAC attributes | policy engine and ABAC filters | scoped domain tables | n/a | access decision traces via audit | action-level restrictions | `tests/test_policy_engine.py`, `tests/unit/test_abac_policies.py` | Partial | P0 | довести покрытие всех атрибутов из unified TZ |
| §1.4 Immutable audit log + diff | audit services/API | audit_log table (append-only) | n/a | correlation id in logs/events | audit UI (admin/reporting minimal) | `tests/test_audit_log_immutability.py`, `tests/test_audit_log_api.py` | OK | P0 | — |
| §2/§3.1 Template versioning | templates API/service | unique(code,version) | n/a | template events | templates list | `tests/test_template_delete.py`, `tests/test_schemas_template.py` | OK | P0 | — |
| §3 Document pipeline steps | document generation services/API | document_job + step fields | task orchestration (eager in dev) | DocumentGenerated | documents page/job history | `tests/services/test_document_workflow.py`, `tests/test_templates_pipeline_api.py` | OK | P0 | — |
| §3.3 Replace engine (dry-run/apply/rollback) | replace service/API | replace batches/logs | batch tasks | replace-related events/logs | replace workflow UI | `tests/test_pipeline_logging.py`, `tests/test_services_pipeline_extra.py` | Partial | P0 | shapes/textboxes и расширенный preview в v1.1 |
| §3 PDF conversion + fonts | pdf service + fallback feature flags | n/a | conversion task | conversion outcomes | document status view | `tests/test_services_pdf_unit.py` | Partial | P1 | embedded fonts strict-check в v1.1 |
| §12.3 Outbox + retries + poison + metrics | outbox dispatcher/services | `outbox_events` | dispatcher retries/backoff | delivery metrics + dead-letter | n/a | `tests/test_outbox_dispatch.py`, `tests/test_outbox_service.py` | OK | P0 | — |
| §12.2 Webhooks routing | webhook routing/services | subscriptions/config tables | dispatch worker | DocumentGenerated/Signed/Exported/RiskAssessed/PPEIssued/TrainingCompleted | n/a | `tests/test_webhook_routing.py`, `tests/test_webhooks_dispatch.py` | Partial | P0 | HMAC signing в v1.1 |
| §6 Risk deterministic KPI | risk domain service/API | risk domain tables | optional async jobs | RiskAssessed | risks list/card | `tests/test_risk_assessment_kpi5.py`, `tests/test_domains_risk_calc.py` | OK | P0 | — |
| §7 PPE journal + event | PPE API/services | ppe journal tables | issue/return tasks (if async) | PPEIssued | PPE registry page | `tests/api/test_ppe_api.py`, `tests/api/test_ppe_events.py` | OK | P0 | — |
| §8 Training completion + event | training API/services | training registry tables | completion tasks | TrainingCompleted | training registry page | `tests/api/test_training_api.py`, `tests/domains/test_training_domain.py` | OK | P0 | — |
| §9 Incidents + obligations/audit | incidents API/services | incidents + obligations/tasks | deadline control jobs | incident-related events | incidents list/create | `tests/api/test_incidents_api.py`, `tests/integration/test_obligation_tasks.py` | OK | P0 | — |
| §20.4 `/healthz` `/readyz` | health endpoints | n/a | n/a | health probes | n/a | `tests/test_health_ready.py` | OK | P0 | — |
| F1..F4 frontend MVP structure/screens/smoke | frontend app/router/features | n/a | n/a | consume backend events via API polling | login/dashboard/documents/replace/risk/ppe/training/incidents/admin | `frontend/src/__tests__/AppRouterSmoke.test.tsx`, `LoginPageSmoke.test.tsx`, `TenantGate.test.tsx` | Partial | P1 | продолжить feature-splitting и UX polish |
| E1..E4 Codespaces DevX/docs | Makefile/scripts/docs | n/a | n/a | n/a | onboarding docs | `make cs:dev`, `make cs:test`, `./scripts/pytest.sh --collect-only -q` | OK | P0 | — |

## Сводка покрытия MVP
- **P0 OK**: tenant/idempotency/audit/outbox/risk/ppe/training/incidents/health.
- **P0 Partial**: ABAC полнота атрибутов, webhook HMAC (контракт есть, подпись как roadmap).
- **P1 Partial**: расширенный replace (shapes/textboxes), strict embedded fonts checks, frontend architecture polishing.

## План закрытия Partial
1. **v1.1**: webhook HMAC, shapes/textboxes replace, embedded fonts post-check + integration test в CI.
2. **v1.2**: расширенные inspections/prescriptions UX и тесты.
3. **v2.0**: расширенный EDO/sign orchestration и внешние enterprise connectors.
