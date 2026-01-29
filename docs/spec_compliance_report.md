# Specification Compliance Report — Backend_TZ v2.1

This report cross-checks the current `prt_ot_doc` codebase against the mandatory requirements captured in `docs/Backend_TZ.md`.
Status legend: ✅ — implemented, ⚠️ — partially implemented, ❌ — missing.

## Executive summary

| Area | Verdict | Notes |
| --- | --- | --- |
| Architecture & multi-tenancy | ⚠️ | Tenant middleware, scoped sessions, and ABAC wrappers are present, yet writes still bypass mandatory audit/outbox hooks and cache layers expected in the request pipeline.【F:docs/Backend_TZ.md†L15-L28】【F:backend/app/middleware/tenant.py†L1-L22】【F:backend/app/api/dependencies.py†L1-L43】【F:backend/app/repository.py†L1-L120】 |
| Data model coverage | ⚠️ | Models cover tenants, users, companies, personnel, PPE norms/issues, packs, templates/versions, risks, incidents, audit, outbox, and API keys, but feature flags, document jobs/versions, checklist/violation actions, and file_object metadata remain absent from the ORM layer.【F:docs/Backend_TZ.md†L47-L55】【F:backend/app/models/models.py†L1-L704】 |
| Business rules & invariants | ❌ | Repositories and route handlers persist entities without emitting audit/outbox records or validating cross-entity invariants (e.g., PPE stock, pack completeness, pipeline state transitions).【F:docs/Backend_TZ.md†L24-L44】【F:backend/app/repository.py†L1-L120】【F:backend/app/api/routes/persons.py†L1-L120】 |
| API surface | ⚠️ | v1 exposes tenants, companies, persons, files, packs, NPA, risks, documents, tasks, and pipeline helpers, but lacks endpoints for LMS flows, medical exams, PPE lifecycle management, inspections/violations, and document job orchestration promised in the contract.【F:docs/Backend_TZ.md†L57-L67】【F:backend/app/api/v1/router.py†L53-L120】【F:backend/app/api/routes/packs.py†L1-L260】 |
| Security & access control | ⚠️ | ABAC/RBAC dependencies and API-key auth exist, yet most routers do not enforce JWT verification and there is no policy store or feature toggle integration, leaving gaps in authentication coverage.【F:docs/Backend_TZ.md†L70-L74】【F:backend/app/core/security.py†L400-L476】【F:backend/app/api/routes/persons.py†L1-L31】 |
| Asynchronous processing | ⚠️ | Celery tasks with retries handle pipeline runs, but only a single queue is configured and API handlers still allow synchronous execution instead of strictly enqueuing into dedicated `documents`/`reports`/`integrations` queues with beat oversight.【F:docs/Backend_TZ.md†L15-L21】【F:backend/app/services/tasks.py†L1-L78】【F:backend/app/services/celery_app.py†L1-L20】【F:backend/app/api/v1/router.py†L280-L459】 |
| File handling & compliance | ❌ | Storage remains an in-memory singleton without MIME sniffing, antivirus scans, signed URLs, MinIO buckets, or `file_object` metadata required for compliant document retention.【F:docs/Backend_TZ.md†L40-L44】【F:docs/Backend_TZ.md†L70-L89】【F:backend/app/services/file_storage.py†L1-L86】 |
| Logging, metrics & errors | ⚠️ | Observability middleware, Prometheus metrics, and structured logging are wired, but error envelopes still return generic `detail` payloads and trace/tenant identifiers are not propagated to responses or Celery headers.【F:docs/Backend_TZ.md†L15-L21】【F:docs/Backend_TZ.md†L70-L89】【F:backend/app/api/app.py†L1-L74】【F:backend/app/api/error_handlers.py†L1-L52】 |
| Non-functional targets | ❌ | Rate limiting middleware exists but lacks SLA-aligned limits; there are no queue capacity guards, backpressure policies, or performance budgets reflecting the stated P95/P99 targets.【F:docs/Backend_TZ.md†L77-L84】【F:backend/app/core/rate_limit.py†L1-L120】【F:backend/app/api/app.py†L1-L74】 |
| Testing & QA | ⚠️ | Unit and integration tests cover pipelines, idempotency, health, and storage, yet there are no Testcontainers, Schemathesis contract checks, or E2E scenarios for inspections, incidents, PPE, or LMS flows to reach the required pyramid depth.【F:docs/Backend_TZ.md†L92-L95】【F:tests/integration/test_pipeline_api.py†L1-L168】【F:tests/unit/test_pipeline_service.py†L1-L215】 |
| DevOps & automation | ⚠️ | Makefile and CI provide lint/test/build/SBOM, but still miss migration/seed/up/down targets, automated Alembic runs, and publishing of OpenAPI/ERD artefacts mandated by the delivery section.【F:docs/Backend_TZ.md†L92-L101】【F:Makefile†L1-L29】【F:.github/workflows/ci.yml†L1-L64】 |

## Detailed observations

### 1. Architecture & multi-tenancy (⚠️)
Tenant resolution middleware, tenant-scoped sessions, and ABAC helpers enforce basic isolation for requests.【F:backend/app/middleware/tenant.py†L1-L22】【F:backend/app/api/dependencies.py†L1-L43】 However, repository helpers write entities directly without emitting audit/outbox events or updating cache layers that the lifecycle in `Backend_TZ.md` requires.【F:docs/Backend_TZ.md†L15-L28】【F:backend/app/repository.py†L1-L120】 There is no shared caching for tenant configs or feature flags.

### 2. Data model coverage (⚠️)
The ORM includes tenants, users, companies, sites, positions, persons, medical exams, training, permits, PPE norms/issues, templates and versions, packs and pack items, pipeline runs, risks, incidents, audit log, outbox, journal entries, API keys, and assets/equipment.【F:backend/app/models/models.py†L1-L704】 Missing pieces relative to the ERD include feature toggles, policy rules, checklist/inspection results, violation/corrective-action tracking, document jobs/versions, and persistent `file_object` metadata.【F:docs/Backend_TZ.md†L47-L55】

### 3. Business rules & invariants (❌)
Mutating endpoints and repository helpers lack transactional invariants: no audit/outbox writes, no PPE stock or pack completeness checks, no template/version gating, and no risk or inspection workflow enforcement.【F:docs/Backend_TZ.md†L24-L44】【F:backend/app/repository.py†L1-L120】【F:backend/app/api/routes/persons.py†L1-L120】 Soft deletes are present but without cascading business validations.

### 4. API surface (⚠️)
API v1 aggregates routers for tenants, companies, persons, files, packs, NPA bindings, risks, documents, tasks, and pipeline helpers.【F:backend/app/api/v1/router.py†L53-L120】 The platform still lacks endpoints for LMS scheduling/testing, medical exams management, PPE issuance lifecycle, inspections/violations/corrective actions, and document job orchestration referenced in the spec and OpenAPI contract.【F:docs/Backend_TZ.md†L57-L67】【F:backend/app/api/routes/packs.py†L1-L260】 File links are limited to in-memory storage without signed URL support.

### 5. Security & access control (⚠️)
ABAC/RBAC dependencies guard routes and API-key authentication is available, but most routers omit JWT verification, leaving access enforcement dependent on optional dependencies rather than mandatory authentication flows.【F:docs/Backend_TZ.md†L70-L74】【F:backend/app/core/security.py†L400-L476】【F:backend/app/api/routes/persons.py†L1-L31】 There is no policy store or feature toggle model to back ABAC claims, and audit logging of security decisions is absent.

### 6. Asynchronous processing & queues (⚠️)
Celery is configured and pipeline execution tasks include retries with exponential backoff.【F:backend/app/services/celery_app.py†L1-L20】【F:backend/app/services/tasks.py†L1-L78】 Yet the API still permits synchronous pipeline runs and uses a single queue instead of isolating `documents`, `reports`, and `integrations` with beat-driven scheduling.【F:docs/Backend_TZ.md†L15-L21】【F:backend/app/api/v1/router.py†L280-L459】 Outbox-to-queue publishing is not implemented.

### 7. File handling & compliance (❌)
File storage remains an in-memory singleton lacking MIME validation, antivirus scanning, SHA256 hashing, `file_object` metadata, retention policies, and signed URLs required for compliant document handling.【F:docs/Backend_TZ.md†L40-L44】【F:docs/Backend_TZ.md†L70-L89】【F:backend/app/services/file_storage.py†L1-L86】 There is no MinIO/S3 integration or bucket lifecycle management.

### 8. Logging, metrics & error handling (⚠️)
CORS, tenant, observability, and rate-limit middlewares are configured; metrics endpoint and structured logging are enabled.【F:backend/app/api/app.py†L1-L74】【F:backend/app/core/logging.py†L1-L56】 Error handlers still return plain `{ "detail": ... }` payloads without the envelope and trace identifiers mandated by the spec, and Celery tasks do not propagate `trace_id`/tenant metadata.【F:docs/Backend_TZ.md†L15-L21】【F:docs/Backend_TZ.md†L70-L89】【F:backend/app/api/error_handlers.py†L1-L52】

### 9. Non-functional requirements (❌)
The spec calls for rate limiting per tenant, queue backpressure, and performance SLOs (P95/P99) with retries and circuit breakers.【F:docs/Backend_TZ.md†L77-L84】 Rate-limit middleware exists but lacks configured limits and monitoring; no queue capacity controls, circuit breakers, or SLA enforcement are coded.【F:backend/app/core/rate_limit.py†L1-L120】【F:backend/app/api/app.py†L1-L74】 Localization and fallback logic are also absent.

### 10. Testing & QA (⚠️)
Unit and integration tests cover pipeline services, idempotency, storage, and health endpoints.【F:tests/integration/test_pipeline_api.py†L1-L168】【F:tests/unit/test_pipeline_service.py†L1-L215】 The testing pyramid lacks Testcontainers-backed integration, Schemathesis contract checks, and E2E scenarios for inspections, incidents, PPE, and LMS workflows, falling short of the required ≥80% coverage and contract testing guidance.【F:docs/Backend_TZ.md†L92-L95】

### 11. DevOps & automation (⚠️)
Makefile targets cover install/lint/format/test/run/build/clean, and CI performs lint/test/build/SBOM, but there are no migration/seed/up/down targets or automated Alembic runs. CI does not publish OpenAPI/ERD artefacts or apply migrations as part of deployments, contrary to the delivery requirements.【F:docs/Backend_TZ.md†L92-L101】【F:Makefile†L1-L29】【F:.github/workflows/ci.yml†L1-L64】 Docker Compose lacks health checks for Celery/MinIO and there is no seed data automation.

## Critical gaps to resolve

1. Implement full ERD coverage, adding feature toggles, policy rules, document job/versioning tables, checklists/violations/corrective actions, and persistent file metadata, with Alembic migrations that preserve multi-tenant constraints.【F:docs/Backend_TZ.md†L47-L55】【F:backend/app/models/models.py†L1-L704】
2. Enforce authentication, RBAC/ABAC, audit logging, and outbox publishing on all mutating endpoints; introduce policy storage and feature flags to back authorization decisions.【F:docs/Backend_TZ.md†L24-L44】【F:docs/Backend_TZ.md†L70-L89】【F:backend/app/api/routes/persons.py†L1-L120】
3. Move document and pack generation to background queues only, splitting Celery into `documents`/`reports`/`integrations` with beat-driven retries and outbox-driven publishing; API responses should return 202 with job identifiers.【F:docs/Backend_TZ.md†L15-L21】【F:backend/app/services/tasks.py†L1-L78】【F:backend/app/api/v1/router.py†L280-L459】
4. Replace in-memory storage with MinIO/S3 integration that performs MIME/ClamAV/hash checks, records `file_object` metadata, and issues signed URLs with retention controls.【F:docs/Backend_TZ.md†L40-L44】【F:docs/Backend_TZ.md†L70-L89】【F:backend/app/services/file_storage.py†L1-L86】
5. Expand REST API and automated tests to cover LMS scheduling/testing, PPE issuance/returns, inspections/violations/corrective actions, incident workflows, document jobs, and health checks for background workers, backed by Schemathesis and Testcontainers to meet QA expectations.【F:docs/Backend_TZ.md†L57-L67】【F:docs/Backend_TZ.md†L92-L95】【F:tests/integration/test_pipeline_api.py†L1-L168】
6. Add operational guardrails: enforce rate limits aligned with SLAs, propagate trace/tenant IDs in error envelopes and task headers, configure Celery backpressure/retries, and add health checks for Redis/MinIO/Celery to satisfy observability requirements.【F:docs/Backend_TZ.md†L15-L21】【F:docs/Backend_TZ.md†L70-L89】【F:backend/app/api/error_handlers.py†L1-L52】【F:backend/app/services/tasks.py†L1-L78】
7. Augment DevOps automation with migration/seed/up/down Makefile targets, CI steps that run migrations and publish OpenAPI/ERD artefacts, and health-check-enabled Compose definitions for all services.【F:docs/Backend_TZ.md†L92-L101】【F:Makefile†L1-L29】【F:.github/workflows/ci.yml†L1-L64】

## Соответствие платформе по охране труда

- LMS и удостоверения: ⚠️ Базовые сущности `Training` и `Permit` присутствуют, но нет расписаний, попыток тестов, удостоверений и API для обучения/выдачи документов.【F:docs/NEXT_FEATURES.md†L7-L15】【F:backend/app/models/models.py†L241-L311】
- Сценарии допуск/НС/проверки/ОПО: ⚠️ Пакеты документов и шаблоны реализованы, но отсутствуют специализированные сценарные эндпоинты, чек-листы, нарушения и корректирующие действия для допусков, НС и проверок ОПО.【F:docs/NEXT_FEATURES.md†L17-L30】【F:backend/app/api/routes/packs.py†L1-L260】
- СИЗ и учет факторов: ⚠️ Есть нормы и выдачи СИЗ (`PPENorm`, `PPEIssue`), однако нет складского учета, привязки к опасным факторам и жизненного цикла возвратов/списания в API.【F:docs/NEXT_FEATURES.md†L21-L30】【F:backend/app/models/models.py†L276-L311】
- Журналы и аудит: ⚠️ Модели `AuditLog`, `JournalEntry`, `Outbox` существуют, но записи не создаются автоматически при операциях и нет журналов проверок/нарушений.【F:docs/NEXT_FEATURES.md†L21-L30】【F:backend/app/models/models.py†L1-L704】
- Аналитика и дашборды: ❌ Нет агрегированных выборок, дашбордных API или выгрузок для метрик по пакетам, рискам, обучению и инцидентам.【F:docs/NEXT_FEATURES.md†L32-L40】
- Конструктор процессов/маршрутов: ⚠️ Пайплайны и пакеты документов есть, но отсутствует no-code редактор процессов, узлы/переходы и история исполнения workflow.【F:docs/NEXT_FEATURES.md†L42-L52】【F:backend/app/models/models.py†L331-L427】
- Интеграции 1С/ЭДО/ФРДО/ЕИСОТ: ❌ Коннекторы задекларированы через интерфейсы, но нет конфигурации, адаптеров, планировщика синхронизаций и обработчиков ошибок/ретраев для реальных обменов.【F:docs/NEXT_FEATURES.md†L54-L65】【F:backend/app/api/dependencies.py†L1-L43】
- Мультиарендность и биллинг: ⚠️ Тенанты и API-ключи реализованы, но отсутствуют фичи биллинга, квоты, тарифные планы и отчётность по потреблению ресурсов.【F:docs/NEXT_FEATURES.md†L67-L77】【F:backend/app/models/models.py†L49-L120】
- Веб-интерфейс и админка: ⚠️ Бэкенд API частично закрывает CRUD компании/персонала/пакетов, однако нет административных API для массовых операций, интеграций и управления фича-флагами; фронтенд не синхронизирован с полным ТЗ.【F:docs/NEXT_FEATURES.md†L79-L87】【F:backend/app/api/v1/router.py†L53-L120】
