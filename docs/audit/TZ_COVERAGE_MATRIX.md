# TZ Coverage Matrix

Дата обновления: 2026-02-18  
Базовый прогон: `make cs:reset`, `cp .env.example .env`, `make cs:dev`, `make cs:test`, `. .venv/bin/activate && pytest --collect-only`, `npm --prefix frontend test`.

## MVP + ключевые acceptance criteria

| Requirement | Backend (module/file/endpoint) | DB (tables/migrations) | Jobs (Celery/tasks) | Events (outbox/webhooks) | Frontend (screens/features) | Tests | Status | Priority | Fix plan |
|---|---|---|---|---|---|---|---|---|---|
| §0.2 / §3 Pipeline steps | `backend/app/services/pipeline*`, `/api/v1/templates/*/pipeline` | `document_jobs`, `document_job_steps` | pipeline execution (eager in dev) | DocumentGenerated | Documents + job history | `tests/services/test_document_workflow.py`, `tests/test_templates_pipeline_api.py` | OK | P0 | — |
| §1.1 Tenant required (`X-Tenant`) | `backend/app/middleware/tenant.py`, `/api/v1/*` routers | tenant-aware entities | `tenant_id` in payload (logical) | tenant in payload | tenant gate + tenant store | `tests/test_tenant_header_required.py`, `tests/test_middleware_tenant.py` | OK | P0 | — |
| §1.2 RBAC | auth dependencies/policy checks | roles/users tables | n/a | audit access traces | route guards / Can component | `tests/test_rbac_abac.py`, `frontend/src/__tests__/Can.test.tsx` | Partial | P0 | синхронизировать полный список ролей с TZ при расширении |
| §1.3 ABAC attributes | policy engine + scoped filtering | domain scoped tables | n/a | access decision traces | action-level restrictions | `tests/unit/test_abac_policies.py`, `tests/test_policy_engine.py` | Partial | P0 | закрыть атрибуты `project_id/contractor_id` в расширенных сценариях |
| §1.4 Immutable audit log + diff | audit services/API | `audit_log` (append-only guards) | n/a | correlation-id in audit/events | audit view (admin) | `tests/test_audit_log_immutability.py`, `tests/test_audit_log_api.py` | OK | P0 | — |
| §2 / §3.1 Template versioning | templates API/service | unique `(code,version)` | n/a | template domain events | templates list | `tests/test_template_delete.py`, `tests/test_schemas_template.py` | OK | P0 | — |
| §3.3 Replace engine | replace service/API | replace batches/logs | batch operations | replace logs/events | replace workflow UI | `tests/test_pipeline_logging.py`, `tests/test_services_pipeline_extra.py` | Partial | P0 | shapes/textboxes + richer diff preview в v1.1 |
| §3.1 / §32 PDF conversion + fonts | pdf service + fallback flags | n/a | conversion task | conversion outcomes | document status details | `tests/test_services_pdf_unit.py` | Partial | P1 | embedded fonts strict check в v1.1 |
| §12.3 Outbox + retries + poison + metrics | outbox dispatcher/services | `outbox_events` | retries/backoff/dead-letter | delivery metrics | n/a | `tests/test_outbox_dispatch.py`, `tests/test_outbox_service.py` | OK | P0 | — |
| §12.2 Webhooks routing | webhook routing/services | subscriptions/config tables | dispatch worker | DocumentGenerated/Signed/Exported/RiskAssessed/PPEIssued/TrainingCompleted | n/a | `tests/test_webhook_routing.py`, `tests/test_webhooks_dispatch.py` | Partial | P0 | HMAC signing в v1.1 (контракт сохранён) |
| §6 Risk deterministic KPI | risk service/API | risk tables | optional async jobs | RiskAssessed | risks list/card | `tests/test_risk_assessment_kpi5.py`, `tests/test_domains_risk_calc.py` | OK | P0 | — |
| §7 PPE journal + event | PPE API/services | PPE issue/return/journal tables | issue/return tasks | PPEIssued | PPE registry | `tests/api/test_ppe_api.py`, `tests/api/test_ppe_events.py` | OK | P0 | — |
| §8 Training completion + event | training API/services | training registry tables | completion tasks | TrainingCompleted | training registry | `tests/api/test_training_api.py`, `tests/domains/test_training_domain.py` | OK | P0 | — |
| §9 Incidents + obligations/audit | incidents API/services | incidents + obligations/tasks | deadline checks | incident events | incidents list/create | `tests/api/test_incidents_api.py`, `tests/integration/test_obligation_tasks.py` | OK | P0 | — |
| §20.4 `/healthz` `/readyz` | health endpoints | n/a | n/a | n/a | n/a | `tests/test_health_ready.py` | OK | P0 | — |
| B1 API/contracts | FastAPI routers + OpenAPI | n/a | n/a | n/a | API consumers | `tests/contract/test_openapi_contract.py` | OK | P0 | — |
| B2 Data/migrations | SQLAlchemy + Alembic models | core/domain migrations | n/a | n/a | n/a | `tests/test_schemas_*`, migration smoke via app start | OK | P0 | — |
| B3 Pipeline/rendering | pipeline orchestration + renderer | job-related tables | pipeline tasks | pipeline events | documents pipeline UI | `tests/services/test_pack_generation_pipeline.py` | OK | P0 | — |
| B4 Domain services | risk/ppe/training/incidents services | domain tables | domain jobs | domain outbox events | domain pages | domain API/integration tests | OK | P0 | — |
| B5 Outbox/observability | outbox + metrics endpoints | `outbox_events` | dispatcher/retry | webhooks + metrics | n/a | `tests/test_smoke_observability.py`, webhook/outbox tests | OK | P0 | — |
| F1 Feature architecture + tenant context | frontend routing + api client | n/a | n/a | n/a | `features/*`, tenant gate | `frontend/src/__tests__/TenantGate.test.tsx` | Partial | P1 | продолжить feature split без массового рефакторинга |
| F2 MVP screens | backend endpoints used by pages | n/a | n/a | domain events consumed through API | login/dashboard/documents/replace/risk/ppe/training/incidents/admin | page smoke + integration tests | Partial | P1 | UX-polish и навигационные сценарии v1.1 |
| F3 Guards RBAC/ABAC | permission hooks + guards | n/a | n/a | n/a | protected routes and actions | `frontend/src/__tests__/ProtectedRoute.test.tsx`, `Can.test.tsx` | Partial | P1 | расширить ABAC-гварды на уровне UI в v1.1 |
| F4 Front tests smoke | vitest setup and smoke suites | n/a | n/a | n/a | key routes rendering | `frontend/src/__tests__/AppRouterSmoke.test.tsx`, `LoginPageSmoke.test.tsx` | OK | P0 | — |
| E1..E4 Codespaces DevX/docs | Makefile/scripts/docs | n/a | n/a | n/a | onboarding docs | `make cs:dev`, `make cs:test`, `pytest --collect-only` | OK | P0 | — |

## Сводка покрытия MVP
- **P0 OK:** tenant isolation, idempotency path, immutable audit, pipeline core, template guard, outbox, risk/PPE/training/incidents, health/readiness, baseline run.
- **P0 Partial:** полнота ABAC атрибутов; webhook HMAC (отмечен как v1.1).
- **P1 Partial:** расширенный replace (shapes/textboxes), strict embedded-fonts checks, фронтенд architecture/UX polish.

## План закрытия Partial
1. **v1.1:** webhook HMAC, shapes/textboxes replace, embedded-fonts post-check + integration test в CI.
2. **v1.2:** расширенные inspections/prescriptions UX + acceptance tests.
3. **v2.0:** расширенный EDO/sign orchestration + enterprise integrations.
